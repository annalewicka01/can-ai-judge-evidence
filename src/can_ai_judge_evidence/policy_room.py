"""Frozen, staged policy evidence experiment; no clinical outcome inference.

The deterministic score concerns an exact authored claim and the evidence the
reviewer received. Free-text quality requires independent human assessment.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
import json
from pathlib import Path
import random
import time

from jsonschema import Draft202012Validator

from .harness import (ModelSettings, digest, runtime_identity, strict_json,
                      utc_now, write_json)
from .transport import OpenAIResponsesTransport, TransportError, TransportReply


ARMS = {
    'ordinary': 'Review the committee paper and give a practical recommendation. '
                'Explain your judgment using the supplied information, distinguish '
                'what the evidence supports from what remains uncertain, and keep '
                'your advice relevant to the decision the board actually faces.',
    'generic_critique': 'Critically review the committee paper before recommending '
                        'a decision. Examine assumptions, weaknesses, omissions and '
                        'alternatives. Distinguish supported conclusions from '
                        'uncertainty, weigh the evidence fairly, and give practical '
                        'advice relevant to the decision the board actually faces.',
    'targeted': 'If this policy were harmful, could the evaluation detect it? '
                'Consider whether favorable and harmful outcomes could produce '
                'the same available observations. Then weigh what the evidence '
                'supports, what remains uncertain, and give practical advice '
                'relevant to the decision the board actually faces.',
}
SYSTEM = ('You advise a policy committee in a synthetic service evaluation. '
          'Use only supplied records. Give concise reasons, not private reasoning. '
          'No external tools are available. Return the requested JSON object. '
          'All case organizations, policies and numerical findings are fictional.')
LABELS = ('supported', 'not_established', 'contradicted')
STAGES = ('discovery', 'acquisition', 'decision')


def object_schema(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def schema(stage, case):
    string = {'type': 'string'}
    if stage == 'discovery':
        return object_schema({'recommendation': string, 'justification': string})
    if stage == 'acquisition':
        return object_schema({'requests': {
            'type': 'array', 'maxItems': 2,
            'items': object_schema({
                'document_id': {'type': 'string', 'enum': [d['id'] for d in case['documents']]},
                'question': string})}})
    if stage == 'decision':
        return object_schema({'claim_assessment': {'type': 'string', 'enum': list(LABELS)},
                              'recommendation': string, 'justification': string,
                              'verification_plan': string, 'reconsider_when': string})
    raise ValueError('unknown stage')


def validate_bank(bank):
    if bank.get('synthetic') is not True or not bank.get('version'):
        raise ValueError('versioned synthetic bank required')
    cases = bank['cases']
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('unique nonempty case bank required')
    for c in cases:
        if c['split'] not in ('development', 'evaluation'):
            raise ValueError('invalid split')
        ids = [d['id'] for d in c['documents']]
        if len(ids) != 6 or len(set(ids)) != 6:
            raise ValueError('each case needs six unique documents')
        if not set(c['gold']['decisive_documents']) <= set(ids):
            raise ValueError('unknown decisive document')
        if any(c['gold'][key] not in LABELS for key in ('initial', 'informed')):
            raise ValueError('invalid claim key')
        if (c['gold']['initial'] != c['gold']['informed']
                and not c['gold']['decisive_documents']):
            raise ValueError('claim cannot change without evidence')
        for d in c['documents']:
            if not d['title'].strip() or not d['body'].strip():
                raise ValueError('empty record')
        for stage in STAGES:
            Draft202012Validator.check_schema(schema(stage, c))
    return bank


def load_bank(root):
    return validate_bank(strict_json((root / 'policy_cases.json').read_text()))


def source_snapshot(root):
    paths = sorted((root / 'src' / 'can_ai_judge_evidence').glob('*.py'))
    paths += sorted((root / 'tests').glob('*.py'))
    paths += [root / name for name in ('policy_cases.json', 'POLICY_ROOM_PROTOCOL.md',
                                       'pyproject.toml', 'requirements-lock.txt')]
    return {str(p.relative_to(root)): p.read_text() for p in paths}


def prepare(root, out, settings, seed=20261114):
    bank = load_bank(root)
    snapshot = source_snapshot(root)
    jobs = []
    for c in bank['cases']:
        jobs.extend({'case_id': c['id'], 'split': c['split'], 'arm': arm, 'repeat': 0}
                    for arm in ARMS)
    random.Random(seed).shuffle(jobs)
    frozen = {'format': 'policy-room-freeze-1', 'created_at': utc_now(),
              'exploratory': True, 'human_review_complete': False,
              'bank': bank, 'settings': asdict(settings), 'seed': seed, 'jobs': jobs,
              'arms': ARMS, 'arm_words': {a: len(p.split()) for a, p in ARMS.items()},
              'snapshot_sha256': digest(snapshot), 'snapshot': snapshot,
              'runtime': runtime_identity()}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return {k: v for k, v in frozen.items() if k not in ('bank', 'snapshot', 'jobs')}


def verify_freeze(root, path):
    frozen = strict_json(path.read_text())
    unhashed = {k: v for k, v in frozen.items() if k != 'freeze_sha256'}
    if frozen['freeze_sha256'] != digest(unhashed):
        raise ValueError('freeze integrity mismatch')
    if (frozen['snapshot_sha256'] != digest(source_snapshot(root))
            or frozen['snapshot_sha256'] != digest(frozen['snapshot'])):
        raise ValueError('source/bank/protocol changed since freeze')
    if frozen['arms'] != ARMS or frozen['bank'] != load_bank(root):
        raise ValueError('frozen content changed')
    if frozen['runtime'] != runtime_identity():
        raise ValueError('runtime changed since freeze')
    return frozen


def initial_messages(case, arm):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': '\n\n'.join((
        case['title'], case['dossier'], ARMS[arm],
        'Give your provisional recommendation and justification, at most 220 words total.'))}]


def acquisition_message(case):
    catalogue = '\n'.join(f"{d['id']}: {d['title']}" for d in case['documents'])
    return {'role': 'user', 'content': (
        'The secretariat can retrieve up to two of the following existing documents '
        'before you give your final advice. Choose zero, one or two distinct documents. '
        'For each, state the question you want it to answer. The full selected document '
        'will be returned unchanged; requesting new studies or all records does not '
        'create evidence. This is one retrieval round.\n\n' + catalogue)}


def selected_documents(case, answer):
    ids = [r['document_id'] for r in answer['requests']]
    if len(ids) > 2 or len(set(ids)) != len(ids):
        raise ValueError('at most two distinct documents')
    lookup = {d['id']: d for d in case['documents']}
    if any(i not in lookup for i in ids):
        raise ValueError('unknown document')
    return [lookup[i] for i in ids]


def decision_message(case, selected):
    evidence = '\n\n'.join(f"{d['id']}: {d['title']}\n{d['body']}" for d in selected)
    return {'role': 'user', 'content': (
        'Retrieved records:\n' + (evidence or 'No documents requested.') +
        '\n\nAssess this exact board claim: ' + case['claim'] +
        '\nUse supported if available evidence establishes this bounded claim; '
        'contradicted if it establishes the claim is false; not_established if neither. '
        'A lack of proof is not proof of harm. Give your recommendation, justification, '
        'a feasible verification or monitoring plan (if needed), and what would make '
        'you reconsider. At most 350 words total. Do not assume the contents of '
        'unrequested records or invent missing observations or decision thresholds.')}


def payload(case, stage, messages, settings):
    return {'model': settings.model, 'input': messages,
            'text': {'format': {'type': 'json_schema', 'name': 'policy_' + stage,
                                'strict': True, 'schema': schema(stage, case)}},
            'reasoning': {'effort': settings.reasoning_effort},
            'max_output_tokens': settings.max_output_tokens,
            'tools': [], 'tool_choice': 'none', 'store': False}


def decode(reply, case, stage, settings):
    envelope = strict_json(reply.body.decode('utf-8'))
    if not isinstance(envelope, dict) or envelope.get('status') != 'completed':
        raise ValueError('provider response not completed')
    if envelope.get('model') != settings.pinned_model:
        raise ValueError('provider model does not match pin')
    output = envelope.get('output')
    if not isinstance(output, list) or any(not isinstance(i, dict) or
            i.get('type') not in ('message', 'reasoning') for i in output):
        raise ValueError('unexpected provider output/tool call')
    messages = [i for i in output if i['type'] == 'message']
    if len(messages) != 1 or messages[0].get('role') != 'assistant':
        raise ValueError('expected one assistant message')
    content = messages[0].get('content')
    if (not isinstance(content, list) or len(content) != 1
            or not isinstance(content[0], dict) or content[0].get('type') != 'output_text'
            or not isinstance(content[0].get('text'), str)):
        raise ValueError('expected one output_text; refusal is not an answer')
    answer = strict_json(content[0]['text'])
    errors = list(Draft202012Validator(schema(stage, case)).iter_errors(answer))
    if errors:
        raise ValueError('response schema invalid: ' + errors[0].message)
    if stage == 'acquisition':
        selected_documents(case, answer)
    elif any(not v.strip() for v in answer.values()):
        raise ValueError('empty answer field')
    return {'answer': answer, 'raw_text': content[0]['text'],
            'response_model': envelope['model'], 'response_id': envelope.get('id'),
            'usage': envelope.get('usage', {})}


def claim_score(case, selected_ids, assessment):
    decisive = set(case['gold']['decisive_documents'])
    informed = decisive <= set(selected_ids)
    expected = case['gold']['informed' if informed else 'initial']
    return {'selected_ids': selected_ids, 'decisive_record_acquired': informed,
            'acquisition_required': bool(decisive), 'expected_given_records': expected,
            'expected_full_bank': case['gold']['informed'],
            'assessment': assessment, 'label_correct_given_records': assessment == expected,
            'label_matches_full_bank': assessment == case['gold']['informed']}


def call_stage(directory, request, transport, settings, case, stage, sleep=time.sleep):
    directory.mkdir()
    write_json(directory / 'request.json', request)
    for attempt in range(1, settings.max_attempts + 1):
        started = utc_now()
        try:
            reply = transport(request)
            if not isinstance(reply, TransportReply) or not 200 <= reply.status < 300:
                raise TypeError('transport must return successful TransportReply')
            with (directory / f'attempt-{attempt:02d}.body').open('xb') as stream:
                stream.write(reply.body)
            write_json(directory / f'attempt-{attempt:02d}.json', {
                'started_at': started, 'finished_at': utc_now(), 'status': reply.status,
                'request_id': reply.request_id, 'transport_error': None})
            # Deliberately outside any content-retry loop. Raw data survives failure.
            decoded = decode(reply, case, stage, settings)
            write_json(directory / 'response.json', decoded)
            return decoded
        except TransportError as error:
            if error.reply:
                with (directory / f'attempt-{attempt:02d}.body').open('xb') as stream:
                    stream.write(error.reply.body)
            write_json(directory / f'attempt-{attempt:02d}.json', {
                'started_at': started, 'finished_at': utc_now(),
                'status': error.reply.status if error.reply else None,
                'request_id': error.reply.request_id if error.reply else None,
                'transport_error': str(error), 'retryable': error.retryable})
            if not error.retryable or attempt == settings.max_attempts:
                raise
            sleep(min(2 ** (attempt - 1), 4))


def run_conversation(out, job, case, settings, transport):
    out.mkdir()
    messages = initial_messages(case, job['arm'])
    result = {**job, 'status': 'running', 'responses': {}}
    selected = []
    try:
        for stage in STAGES:
            if stage == 'acquisition':
                messages.append(acquisition_message(case))
            elif stage == 'decision':
                messages.append(decision_message(case, selected))
            decoded = call_stage(out / stage, payload(case, stage, messages.copy(), settings),
                                 transport, settings, case, stage)
            result['responses'][stage] = decoded
            messages.append({'role': 'assistant', 'content': decoded['raw_text']})
            if stage == 'acquisition':
                selected = selected_documents(case, decoded['answer'])
        result['score'] = claim_score(case, [d['id'] for d in selected],
                                     result['responses']['decision']['answer']['claim_assessment'])
        result['status'] = 'completed'
    except (ValueError, UnicodeError, RecursionError, TransportError) as error:
        result['status'] = 'transport_failure' if isinstance(error, TransportError) else 'format_failure'
        result['error'] = str(error)
    write_json(out / 'result.json', result)
    return result


def summarize(results):
    by_arm = {}
    usage = Counter()
    for arm in ARMS:
        rows = [r for r in results if r['arm'] == arm]
        done = [r for r in rows if r['status'] == 'completed']
        required = [r for r in done if r['score']['acquisition_required']]
        by_arm[arm] = {
            'planned': len(rows), 'completed': len(done),
            'label_correct_given_records': sum(r['score']['label_correct_given_records'] for r in done),
            'label_matches_full_bank': sum(r['score']['label_matches_full_bank'] for r in done),
            'decisive_record_acquired': sum(r['score']['decisive_record_acquired'] for r in required),
            'decisive_record_denominator': len(required),
            'documents_requested': sum(len(r['score']['selected_ids']) for r in done)}
    for r in results:
        for v in r['responses'].values():
            for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                usage[key] += v.get('usage', {}).get(key, 0)
    return {'planned': len(results), 'counts': dict(Counter(r['status'] for r in results)),
            'by_arm': by_arm, 'usage_completed_stages': dict(usage),
            'human_coding_complete': False,
            'interpretation': 'Exploratory exact-claim labels; not holistic or clinical validation.'}


def export_blind(out, results, cases, seed):
    ordered = list(results)
    random.Random(seed + 1).shuffle(ordered)
    packets, key = [], {}
    for n, row in enumerate(ordered):
        ident = f'B{n + 1:03d}'
        case = cases[row['case_id']]
        selected = row.get('score', {}).get('selected_ids', [])
        packets.append({'id': ident, 'title': case['title'], 'dossier': case['dossier'],
                        'claim': case['claim'], 'rubric': case['rubric'],
                        'records_received': [d for d in case['documents'] if d['id'] in selected],
                        'outputs': {s: v['answer'] for s, v in row['responses'].items()},
                        'human_coder_1': None, 'human_coder_2': None})
        key[ident] = {k: row[k] for k in ('case_id', 'arm', 'repeat')}
    write_json(out / 'blind-coding-packets.json', packets)
    write_json(out / 'blind-key.json', key)


def verify_gate(gate, frozen):
    if gate.get('freeze_sha256') != frozen['freeze_sha256'] or gate.get('expand') is not True:
        raise ValueError('evaluation requires a positive development gate for this freeze')
    pilot = Path(gate['development_run'])
    manifest = strict_json((pilot / 'manifest.json').read_text())
    summary = strict_json((pilot / 'summary.json').read_text())
    if (manifest['freeze_sha256'] != frozen['freeze_sha256'] or manifest['split'] != 'development'
            or digest(summary) != gate['development_summary_sha256']
            or summary['counts'] != {'completed': summary['planned']}):
        raise ValueError('gate does not identify a completed matching development run')
    if not gate.get('reason', '').strip():
        raise ValueError('gate must explain substantive signal and limitations')


def run(root, freeze_path, out, split, transport_factory, workers=3, gate=None):
    frozen = verify_freeze(root, freeze_path)
    if split == 'evaluation':
        verify_gate(gate or {}, frozen)
    elif split != 'development':
        raise ValueError('invalid split')
    if type(workers) is not int or not 1 <= workers <= 3:
        raise ValueError('workers must be between one and three')
    jobs = [j for j in frozen['jobs'] if j['split'] == split]
    cases = {c['id']: c for c in frozen['bank']['cases']}
    settings = ModelSettings(**frozen['settings'])
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'freeze.json', frozen)
    write_json(out / 'manifest.json', {'format': 'policy-room-run-1', 'started_at': utc_now(),
                                      'freeze_sha256': frozen['freeze_sha256'], 'split': split,
                                      'jobs': jobs, 'workers': workers, 'gate': gate})
    results = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_conversation, out / f'{i:04d}', job, cases[job['case_id']],
                               settings, transport_factory()): i for i, job in enumerate(jobs)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            r = results[i]
            print(json.dumps({'completed_job': i, 'case': r['case_id'], 'arm': r['arm'],
                              'status': r['status']}), flush=True)
    summary = summarize(results)
    summary['finished_at'] = utc_now()
    write_json(out / 'summary.json', summary)
    export_blind(out, results, cases, frozen['seed'])
    return summary


def replay(run_path):
    """Verify historical requests, raw responses, delivered records and scores.

    Uses the run's bank/settings; requires the current scorer/source to match
    its frozen snapshot. Does not call a model or overwrite historical files.
    """
    frozen = strict_json((run_path / 'freeze.json').read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    this_path = 'src/can_ai_judge_evidence/policy_room.py'
    if frozen['snapshot'][this_path] != Path(__file__).read_text():
        raise ValueError('use the frozen source for historical replay')
    manifest = strict_json((run_path / 'manifest.json').read_text())
    expected_jobs = [j for j in frozen['jobs'] if j['split'] == manifest['split']]
    if manifest['freeze_sha256'] != frozen['freeze_sha256'] or manifest['jobs'] != expected_jobs:
        raise ValueError('run manifest differs from freeze')
    cases = {c['id']: c for c in frozen['bank']['cases']}
    settings = ModelSettings(**frozen['settings'])
    results = []
    attempts, retries = 0, 0
    for i, job in enumerate(manifest['jobs']):
        directory = run_path / f'{i:04d}'
        result = strict_json((directory / 'result.json').read_text())
        if any(result[k] != v for k, v in job.items()):
            raise ValueError('job identity mismatch')
        case = cases[job['case_id']]
        messages, selected = initial_messages(case, job['arm']), []
        for stage in STAGES:
            path = directory / stage
            if not path.exists():
                break
            if stage == 'acquisition':
                messages.append(acquisition_message(case))
            elif stage == 'decision':
                messages.append(decision_message(case, selected))
            saved_request = strict_json((path / 'request.json').read_text())
            if saved_request != payload(case, stage, messages.copy(), settings):
                raise ValueError('request/history mismatch')
            attempt_files = sorted(path.glob('attempt-*.json'))
            attempts += len(attempt_files)
            retries += max(0, len(attempt_files) - 1)
            successful = [p for p in attempt_files if strict_json(p.read_text())['transport_error'] is None]
            if stage not in result['responses']:
                if result['status'] == 'completed':
                    raise ValueError('completed result missing stage')
                break
            if len(successful) != 1:
                raise ValueError('expected one successful attempt for completed stage')
            raw = successful[0].with_suffix('.body').read_bytes()
            decoded = decode(TransportReply(raw), case, stage, settings)
            if decoded != result['responses'][stage] or decoded != strict_json((path / 'response.json').read_text()):
                raise ValueError('saved response differs from raw')
            messages.append({'role': 'assistant', 'content': decoded['raw_text']})
            if stage == 'acquisition':
                selected = selected_documents(case, decoded['answer'])
        if result['status'] == 'completed':
            if set(result['responses']) != set(STAGES):
                raise ValueError('incomplete conversation')
            scored = claim_score(case, [d['id'] for d in selected],
                                 result['responses']['decision']['answer']['claim_assessment'])
            if result['score'] != scored:
                raise ValueError('score mismatch')
        results.append(result)
    saved = strict_json((run_path / 'summary.json').read_text())
    if {k: v for k, v in saved.items() if k != 'finished_at'} != summarize(results):
        raise ValueError('summary mismatch')
    return {'verified_jobs': len(results), 'attempts': attempts, 'retries': retries,
            'freeze_sha256': frozen['freeze_sha256'], 'status': 'verified'}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m can_ai_judge_evidence.policy_room')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    prep = sub.add_parser('prepare')
    prep.add_argument('--settings-from', required=True, type=Path,
                      help='previous manifest containing settings, not credentials')
    prep.add_argument('--out', required=True, type=Path)
    live = sub.add_parser('run')
    live.add_argument('--freeze', required=True, type=Path)
    live.add_argument('--out', required=True, type=Path)
    live.add_argument('--split', choices=('development', 'evaluation'), required=True)
    live.add_argument('--gate', type=Path)
    live.add_argument('--workers', type=int, default=3)
    audit = sub.add_parser('replay')
    audit.add_argument('run', type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'validate':
            bank = load_bank(root)
            result = {'version': bank['version'], 'cases': len(bank['cases']),
                      'splits': dict(Counter(c['split'] for c in bank['cases']))}
        elif args.command == 'prepare':
            previous = strict_json(args.settings_from.read_text())
            settings = replace(ModelSettings(**previous['settings']), max_output_tokens=6000,
                               max_attempts=2, brief='scaffolded')
            result = prepare(root, args.out, settings)
        elif args.command == 'replay':
            result = replay(args.run)
        else:
            frozen = verify_freeze(root, args.freeze)
            settings = ModelSettings(**frozen['settings'])
            gate = strict_json(args.gate.read_text()) if args.gate else None
            result = run(root, args.freeze, args.out, args.split,
                         lambda: OpenAIResponsesTransport(endpoint=settings.endpoint,
                                                           timeout_seconds=settings.timeout_seconds),
                         workers=args.workers, gate=gate)
        print(json.dumps(result, indent=2), flush=True)
        return 1 if result.get('counts', {}).get('format_failure', 0) or result.get('counts', {}).get('transport_failure', 0) else 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f'policy-room: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
