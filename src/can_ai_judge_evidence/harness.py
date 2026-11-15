"""Independent requests, strict decoding, scoring and append-only run evidence."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import time

from jsonschema import Draft202012Validator

from . import __version__
from .authoring import audit_suite
from .cases import case_pairs, smoke_fixture
from .prompts import ARMS, messages, validate_prompt_arms
from .reporting import summarize_by_arm
from .response_schema import response_schema
from .scoring import score_response
from .transport import ENDPOINT, TransportError, TransportReply
from .validation import ValidationIssue


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f'non-JSON numeric constant: {value}')

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('JSON number exceeds finite floating-point range')
        return parsed

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant,
                      parse_float=finite_float)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def write_json(path: Path, value) -> None:
    """Exclusive creation: never overwrite an earlier run, result or manifest."""
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_identity() -> dict:
    return {'python': platform.python_version(),
            'dependencies': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'jsonschema')}}


def code_identity(root: Path) -> dict:
    files = sorted((root / 'src' / 'can_ai_judge_evidence').rglob('*.py'))
    files += [p for p in (root / 'pyproject.toml', root / 'PROTOCOL.md') if p.exists()]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if not hashes:
        raise ValueError('project source root is required for provenance')
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    # Do not inherit a parent/home repository's HEAD for an uninitialised project.
    toplevel = git('rev-parse', '--show-toplevel')
    owns_repo = toplevel is not None and Path(toplevel).resolve() == root.resolve()
    return {'source_sha256': digest(hashes), 'files': hashes,
            'git_commit': git('rev-parse', 'HEAD') if owns_repo else None,
            'git_dirty': bool(git('status', '--porcelain')) if owns_repo else None}


@dataclass(frozen=True)
class ModelSettings:
    model: str
    reasoning_effort: str = 'medium'
    max_output_tokens: int = 16000
    timeout_seconds: int = 120
    max_attempts: int = 3
    endpoint: str = ENDPOINT
    # Model ID the provider returns, if it differs from the requested ID (e.g. a
    # gateway alias). Every response must match it exactly.
    response_model: str | None = None
    # Explicit, recorded opt-in for a gateway that exposes no dated snapshot.
    allow_undated_model: bool = False
    # Public brief variant: 'scaffolded' names the changing group; 'open' does not.
    brief: str = 'scaffolded'

    @property
    def pinned_model(self) -> str:
        return self.response_model or self.model

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError('select an explicit model ID; there is no implicit provider/model fallback')
        if self.response_model is not None and (not isinstance(self.response_model, str)
                                                or not self.response_model.strip()):
            raise ValueError('response_model must be a non-empty string or omitted')
        if not isinstance(self.endpoint, str) or not self.endpoint.startswith('https://'):
            raise ValueError('endpoint must be an https URL')
        if type(self.allow_undated_model) is not bool:
            raise ValueError('allow_undated_model must be a boolean')
        if self.brief not in ('scaffolded', 'open'):
            raise ValueError('brief must be scaffolded or open')
        if self.reasoning_effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh'):
            raise ValueError('unsupported reasoning effort setting')
        for name in ('max_output_tokens', 'timeout_seconds', 'max_attempts'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f'{name} must be a positive integer')
        if self.max_attempts > 5:
            raise ValueError('max_attempts must be at most five')


def request_payload(case, variant: str, arm: str, settings: ModelSettings) -> dict:
    return {
        'model': settings.model, 'input': messages(case, variant, arm, settings.brief),
        'text': {'format': {'type': 'json_schema', 'name': 'monitoring_response',
                            'strict': True, 'schema': response_schema(case.config(variant))}},
        'reasoning': {'effort': settings.reasoning_effort},
        'max_output_tokens': settings.max_output_tokens,
        'tools': [], 'tool_choice': 'none', 'store': False,
    }


def decode_and_score(config, reply: TransportReply):
    """No fence stripping, JSON repair, inferred nulls or content retries."""
    envelope = None
    raw_text = None
    decoded = None
    errors = []
    try:
        envelope = strict_json(reply.body.decode('utf-8'))
        if not isinstance(envelope, dict):
            raise ValueError('provider envelope must be an object')
        if envelope.get('status') != 'completed':
            raise ValueError('provider response not completed')
        if not isinstance(envelope.get('model'), str) or not envelope['model'].strip():
            raise ValueError('provider model version missing')
        output = envelope.get('output')
        if not isinstance(output, list):
            raise ValueError('provider output must be a list')
        if any(not isinstance(item, dict) or item.get('type') not in ('reasoning', 'message')
               for item in output):
            raise ValueError('unexpected provider output or tool call')
        replies = [item for item in output if item.get('type') == 'message']
        if len(replies) != 1 or replies[0].get('role') != 'assistant':
            raise ValueError('expected one assistant message')
        content = replies[0].get('content')
        if (not isinstance(content, list) or len(content) != 1
                or not isinstance(content[0], dict) or content[0].get('type') != 'output_text'
                or not isinstance(content[0].get('text'), str)):
            raise ValueError('expected one output_text block; refusal is a format failure')
        raw_text = content[0]['text']
        decoded = strict_json(raw_text)
    except (ValueError, UnicodeError, RecursionError) as error:
        errors.append(ValidationIssue('transport_content', 'format_failure', str(error)))
    score = score_response(config, decoded)
    if decoded is not None:
        validator = Draft202012Validator(response_schema(config))
        for error in validator.iter_errors(decoded):
            path = '.'.join(str(p) for p in error.absolute_path)
            errors.append(ValidationIssue(path or 'response', 'json_schema', error.message))
    if errors:
        score = replace(score, format_valid=False, format_errors=(*score.format_errors, *errors))
    metadata = {'response_model': envelope.get('model') if isinstance(envelope, dict) else None,
                'response_id': envelope.get('id') if isinstance(envelope, dict) else None,
                'usage': envelope.get('usage') if isinstance(envelope, dict) else None,
                'raw_text': raw_text, 'decoded': decoded}
    return score, metadata


def run_jobs(*, root: Path, out: Path, settings: ModelSettings, transport,
             mode: str, repeats: int = 1, seed: int = 1729,
             dry_run: bool = False, sleep=time.sleep, freeze_record: dict | None = None) -> dict:
    if mode not in ('smoke', 'pilot', 'evaluation'):
        raise ValueError('unknown run mode')
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be a positive integer')
    if mode == 'evaluation' and not dry_run and freeze_record is None:
        raise ValueError('live evaluation requires a verified freeze record')
    if mode == 'evaluation' and not dry_run:
        from .freeze import check_freeze_record
        check_freeze_record(root, freeze_record, settings)
    audit_suite()
    validate_prompt_arms()
    cases = ((smoke_fixture(),) if mode == 'smoke' else
             tuple(c for c in case_pairs() if c.split == ('development' if mode == 'pilot' else 'evaluation')))
    jobs = [(case, variant, arm, repeat) for case in cases
            for variant in (('blind',) if mode == 'smoke' else ('blind', 'adequate'))
            for arm in (('ordinary',) if mode == 'smoke' else ARMS)
            for repeat in range(repeats)]
    random.Random(seed).shuffle(jobs)
    identity = code_identity(root)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'run_format_version': 1, 'mode': mode, 'dry_run': dry_run,
                'started_at': utc_now(), 'settings': asdict(settings), 'endpoint': settings.endpoint,
                'client': 'stdlib urllib; harness retry policy only',
                **runtime_identity(), 'package_version': __version__,
                'identity': identity, 'repeats': repeats, 'seed': seed,
                'arm_words': validate_prompt_arms(), 'length_unit': 'whitespace-separated words',
                'freeze': freeze_record,
                'jobs': [{'case_id': c.case_id, 'variant': v, 'arm': a, 'repeat': r}
                         for c, v, a, r in jobs]}
    write_json(out / 'manifest.json', manifest)
    scores_by_arm, scores_by_case = defaultdict(list), defaultdict(lambda: defaultdict(list))
    results, model_versions = [], set()
    aborted = False
    for index, (case, variant, arm, repeat) in enumerate(jobs):
        job_dir = out / f'{index:04d}'
        job_dir.mkdir()
        payload = request_payload(case, variant, arm, settings)
        write_json(job_dir / 'request.json', payload)
        result = {'case_id': case.case_id, 'variant': variant, 'arm': arm, 'repeat': repeat,
                  'request_sha256': digest(payload)}
        if dry_run:
            result['status'] = 'dry_run'
            write_json(job_dir / 'result.json', result)
            results.append(result)
            continue
        reply = None
        for attempt in range(1, settings.max_attempts + 1):
            started = utc_now()
            try:
                reply = transport(payload)
                if not isinstance(reply, TransportReply):
                    raise TypeError('transport must return TransportReply')
                if not 200 <= reply.status < 300:
                    raise ValueError('transport must raise TransportError for HTTP failures')
                with (job_dir / f'attempt-{attempt:02d}.body').open('xb') as stream:
                    stream.write(reply.body)
                write_json(job_dir / f'attempt-{attempt:02d}.json', {
                    'started_at': started, 'finished_at': utc_now(), 'status': reply.status,
                    'request_id': reply.request_id, 'transport_error': None})
                break
            except TransportError as error:
                if error.reply is not None:
                    with (job_dir / f'attempt-{attempt:02d}.body').open('xb') as stream:
                        stream.write(error.reply.body)
                write_json(job_dir / f'attempt-{attempt:02d}.json', {
                    'started_at': started, 'finished_at': utc_now(),
                    'status': error.reply.status if error.reply else None,
                    'request_id': error.reply.request_id if error.reply else None,
                    'transport_error': str(error), 'retryable': error.retryable})
                if not error.retryable or attempt == settings.max_attempts:
                    result.update(status='transport_failure', transport_error=str(error))
                    aborted = True
                    break
                sleep(min(2 ** (attempt - 1), 8))
        if reply is not None:
            score, metadata = decode_and_score(case.config(variant), reply)
            result.update(status='scored', **metadata, score=asdict(score))
            scores_by_arm[arm].append(score)
            scores_by_case[f'{case.case_id}/{variant}'][arm].append(score)
            if isinstance(metadata['response_model'], str):
                model_versions.add(metadata['response_model'])
            if mode == 'evaluation' and metadata['response_model'] != settings.pinned_model:
                result['protocol_violation'] = 'response_model_differs_from_frozen_snapshot'
                aborted = True
        write_json(job_dir / 'result.json', result)
        results.append(result)
        if aborted:
            break
    counts = Counter(r['status'] for r in results)
    summary = {'finished_at': utc_now(), 'mode': mode, 'dry_run': dry_run,
               'planned': len(jobs), 'attempted_jobs': len(results), 'counts': dict(counts),
               'aborted': aborted, 'response_models': sorted(model_versions),
               'format_failures': sum(not r['score']['format_valid'] for r in results if 'score' in r),
               'by_arm': summarize_by_arm(scores_by_arm),
               'by_case_variant': {c: summarize_by_arm(arms) for c, arms in scores_by_case.items()},
               'pipeline_pass': (not dry_run and not aborted and counts['scored'] == len(jobs)
                                 and model_versions == {settings.pinned_model}
                                 and all(r['score']['format_valid'] for r in results))}
    write_json(out / 'summary.json', summary)
    return summary
