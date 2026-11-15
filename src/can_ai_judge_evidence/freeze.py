"""Explicit research-freeze gates, not an assertion of scientific validity."""
from dataclasses import asdict
from pathlib import Path
import re

from .authoring import audit_suite
from .cases import case_pairs, smoke_fixture
from .harness import (ModelSettings, code_identity, decode_and_score, digest, request_payload,
                      runtime_identity, strict_json, utc_now, write_json)
from .prompts import validate_prompt_arms
from .transport import TransportReply


def read_json(path: Path):
    return strict_json(path.read_text(encoding='utf-8'))


def review_template(root: Path) -> dict:
    return {'reviewer_name': None, 'reviewed_at': None, 'human_approved': False,
            'source_sha256': code_identity(root)['source_sha256'],
            'cases': {c.case_id: {'narrative_no_answer_cues': False,
                                  'synthetic_domain_assumptions_acceptable': False,
                                  'comments': ''} for c in case_pairs()}}


def _check_review(review, source_hash):
    if (review.get('human_approved') is not True
            or not isinstance(review.get('reviewer_name'), str) or not review['reviewer_name'].strip()
            or not isinstance(review.get('reviewed_at'), str) or not review['reviewed_at'].strip()
            or review.get('source_sha256') != source_hash):
        raise ValueError('completed human review tied to current source is required')
    if set(review.get('cases', {})) != {c.case_id for c in case_pairs()}:
        raise ValueError('human review must cover all five cases')
    for row in review['cases'].values():
        if (row.get('narrative_no_answer_cues') is not True
                or row.get('synthetic_domain_assumptions_acceptable') is not True):
            raise ValueError('each case needs narrative and synthetic-domain sign-off')


def _run_evidence(directory: Path, mode: str, identity: dict, settings: ModelSettings) -> dict:
    manifest, summary = (read_json(directory / n) for n in ('manifest.json', 'summary.json'))
    if (manifest.get('mode') != mode or summary.get('mode') != mode
            or manifest.get('dry_run') is not False or summary.get('dry_run') is not False
            or summary.get('pipeline_pass') is not True
            or manifest.get('identity', {}).get('source_sha256') != identity['source_sha256']
            or manifest.get('settings') != asdict(settings)
            or {k: manifest.get(k) for k in runtime_identity()} != runtime_identity()
            or summary.get('response_models') != [settings.pinned_model]):
        raise ValueError(f'{mode} evidence must be a clean live run of current source/settings/model')
    expected = {'fixture'} if mode == 'smoke' else {c.case_id for c in case_pairs() if c.split == 'development'}
    jobs = manifest.get('jobs', [])
    if {job['case_id'] for job in jobs} != expected:
        raise ValueError(f'incorrect {mode} cases')
    expected_cells = ({('fixture', 'blind', 'ordinary')} if mode == 'smoke' else
                      {(c, v, a) for c in expected for v in ('blind', 'adequate')
                       for a in ('ordinary', 'generic_critique', 'targeted')})
    if {(j['case_id'], j['variant'], j['arm']) for j in jobs} != expected_cells:
        raise ValueError(f'incomplete {mode} cells')
    evidence = {'manifest': digest(manifest), 'summary': digest(summary), 'jobs': []}
    cases = {c.case_id: c for c in (*case_pairs(), smoke_fixture())}
    for index, job in enumerate(jobs):
        folder = directory / f'{index:04d}'
        result, request = (read_json(folder / n) for n in ('result.json', 'request.json'))
        case = cases[job['case_id']]
        if (any(result.get(k) != v for k, v in job.items()) or result.get('status') != 'scored'
                or result.get('request_sha256') != digest(request)
                or result.get('score', {}).get('format_valid') is not True
                or result.get('response_model') != settings.pinned_model
                or not tuple(folder.glob('attempt-*.body'))):
            raise ValueError(f'incomplete or inconsistent {mode} job evidence')
        if request != request_payload(case, job['variant'], job['arm'], settings):
            raise ValueError(f'{mode} request differs from current case/prompt/schema')
        attempts = sorted(folder.glob('attempt-*.json'))
        if not attempts:
            raise ValueError(f'{mode} attempt metadata missing')
        last = attempts[-1]
        attempt_metadata = read_json(last)
        if attempt_metadata.get('transport_error') is not None or attempt_metadata.get('status') != 200:
            raise ValueError(f'{mode} terminal attempt was not successful')
        raw = last.with_suffix('.body').read_bytes()
        rescored, metadata = decode_and_score(case.config(job['variant']), TransportReply(raw))
        if digest(asdict(rescored)) != digest(result['score']) or any(result.get(k) != v for k, v in metadata.items()):
            raise ValueError(f'{mode} score/metadata do not match retained raw response')
        import hashlib
        evidence['jobs'].append({'result': digest(result), 'request': digest(request),
                                'attempt_files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                  for p in sorted(folder.glob('attempt-*'))}})
    # The model need not solve the task to pass a pilot. Selection on accuracy
    # would bias the evaluation. This gate is format/provenance, not accuracy.
    return evidence


def create_freeze(*, root: Path, out: Path, smoke: Path, pilot: Path,
                  review: Path, settings: ModelSettings) -> dict:
    audit_suite()
    validate_prompt_arms()
    identity = code_identity(root)
    if identity['git_commit'] is None or identity['git_dirty']:
        raise ValueError('freeze requires a clean committed project repository')
    if (not settings.allow_undated_model
            and not re.search(r'-\d{4}-\d{2}-\d{2}$', settings.pinned_model)):
        raise ValueError('freeze requires an explicitly dated model snapshot, not a moving alias '
                         '(or an explicit, recorded allow_undated_model opt-in)')
    human_review = read_json(review)
    _check_review(human_review, identity['source_sha256'])
    record = {'frozen_at': utc_now(), 'identity': identity, 'settings': asdict(settings),
              'runtime': runtime_identity(),
              'human_review': human_review,
              'smoke_evidence': _run_evidence(smoke, 'smoke', identity, settings),
              'pilot_evidence': _run_evidence(pilot, 'pilot', identity, settings)}
    write_json(out, record)
    return record


def check_freeze_record(root: Path, record: dict, settings: ModelSettings) -> None:
    identity = code_identity(root)
    if (identity['git_dirty'] or identity['git_commit'] is None
            or record.get('identity') != identity or record.get('settings') != asdict(settings)
            or record.get('runtime') != runtime_identity()):
        raise ValueError('frozen commit/source/settings differ from this run')
    _check_review(record.get('human_review', {}), identity['source_sha256'])
    if not record.get('smoke_evidence') or not record.get('pilot_evidence'):
        raise ValueError('freeze is missing smoke/pilot evidence')


def verify_freeze(root: Path, path: Path, settings: ModelSettings) -> dict:
    record = read_json(path)
    check_freeze_record(root, record, settings)
    return record
