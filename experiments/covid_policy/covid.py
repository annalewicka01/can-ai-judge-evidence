"""COVID illustration batch: two pairs x two models x one run. One user turn; no system prompt.

Free text needs its own decoder; recording/retry policy mirrors policy_room.call_stage.
signoff.json records one named reviewer's hashes of the four packets and keys;
prepare/run refuse if any changed. The mapping file is not grading input.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import random
import time

from can_ai_judge_evidence.harness import ModelSettings, digest, runtime_identity, strict_json, utc_now, write_json
from can_ai_judge_evidence.transport import ENDPOINT, OpenAIResponsesTransport, TransportError, TransportReply

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261114
REVIEW_INSTRUCTION = (
    'Review this adapted synthetic committee paper using only the supplied '
    'information. Do not search or consult outside sources. In at most 250 words '
    'total, provide five labelled sections: (1) Claim assessment: supported, '
    'not established, or contradicted; assess the exact quoted claim. '
    "(2) Policy recommendation: state a practical action under the paper's stated "
    'objectives and constraints. (3) Decisive reasons: cite packet evidence. '
    '(4) Necessary conditions, if any, including their burden and timing. '
    '(5) What evidence would change your decision. Assess the claim separately '
    'from the policy choice; explain your reasoning rather than only giving labels.')
# Selected before any output: surveillance (designated worked example) and masking.
PACKET_IDS = {'C17': 'stronger', 'C42': 'weaker', 'C36': 'stronger', 'C94': 'weaker'}
MODELS = {'openai_gpt6_astra': 'medium', 'openai_gpt54_mini': 'medium'}


def settings_for(model):
    return ModelSettings(model=model, reasoning_effort=MODELS[model], max_output_tokens=8000,
                         timeout_seconds=240, max_attempts=3, endpoint=ENDPOINT, allow_undated_model=True)


def file_hashes(base, paths):
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def current_hashes(base):
    paths = [base / d / f'{p}.md' for d in ('packets', 'keys') for p in PACKET_IDS]
    missing = [str(p.relative_to(base)) for p in paths if not p.is_file()]
    if missing:
        raise ValueError('missing packet/key files: ' + ', '.join(missing))
    return file_hashes(base, paths)


def signoff(name, base=HERE, today=None):
    if not name.strip():
        raise ValueError('reviewer name required')
    record = {'reviewer': name.strip(), 'date': (today or date.today()).isoformat(), 'sha256': current_hashes(base)}
    write_json(base / 'signoff.json', record)
    return record


def approved_hashes(base):
    hashes = current_hashes(base)
    path = base / 'signoff.json'
    if not path.is_file():
        raise ValueError('signoff.json required: review packets/keys, then run signoff')
    record = strict_json(path.read_text())
    if not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip():
        raise ValueError('reviewer name required')
    date.fromisoformat(record.get('date', ''))
    if record.get('sha256') != hashes:
        raise ValueError('signoff hashes stale or incomplete')
    return hashes, record


def prepare(out, base=HERE):
    hashes, approvals = approved_hashes(base)
    packets = {p: (base / 'packets' / f'{p}.md').read_text() for p in PACKET_IDS}
    jobs = [{'packet_id': p, 'model': m} for p in PACKET_IDS for m in MODELS]
    random.Random(SEED).shuffle(jobs)
    sources = [p for p in base.rglob('*') if p.is_file() and
               (p.parent == base and p.suffix in ('.py', '.md') or 'sources' in p.relative_to(base).parts)]
    frozen = {'format': 'covid-freeze-2', 'created_at': utc_now(), 'seed': SEED,
              'jobs': jobs, 'packets': packets, 'packet_key_hashes': hashes, 'signoff': approvals,
              'messages': {p: [{'role': 'user', 'content': REVIEW_INSTRUCTION + '\n\n' + text}]
                           for p, text in packets.items()},
              'settings': {m: asdict(settings_for(m)) for m in MODELS},
              'source_hashes': file_hashes(base, sources),
              'runner_hashes': file_hashes(ROOT, [Path(__file__), ROOT / 'src/can_ai_judge_evidence/harness.py',
                                               ROOT / 'src/can_ai_judge_evidence/transport.py']),
              'runtime': runtime_identity(), 'system_prompt': None}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return frozen


def decode(reply, settings):
    envelope = strict_json(reply.body.decode('utf-8'))
    if not isinstance(envelope, dict) or envelope.get('status') != 'completed':
        raise ValueError('provider response not completed')
    if envelope.get('model') != settings.pinned_model:
        raise ValueError('provider model does not match requested alias')
    output = envelope.get('output')
    if not isinstance(output, list) or any(not isinstance(o, dict) or o.get('type') not in ('reasoning', 'message') for o in output):
        raise ValueError('unexpected provider output/tool call')
    messages = [o for o in output if o['type'] == 'message']
    if len(messages) != 1 or messages[0].get('role') != 'assistant':
        raise ValueError('expected one assistant message')
    content = messages[0].get('content')
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict) or content[0].get('type') != 'output_text':
        raise ValueError('expected one output_text; refusal is invalid')
    text = content[0].get('text')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('empty output')
    return {'text': text, 'response_model': envelope['model'], 'response_id': envelope.get('id'), 'usage': envelope.get('usage', {})}


def run_job(out, job, messages, settings, transport_factory, sleep=time.sleep):
    out.mkdir()
    request = {'model': settings.model, 'input': messages, 'reasoning': {'effort': settings.reasoning_effort},
               'max_output_tokens': settings.max_output_tokens, 'tools': [], 'tool_choice': 'none', 'store': False}
    write_json(out / 'request.json', request)
    result = {**job, 'request_sha256': digest(request)}
    try:
        transport = transport_factory(settings)
        for attempt in range(1, settings.max_attempts + 1):
            started = utc_now()
            try:
                reply = transport(request)
                if not isinstance(reply, TransportReply) or not 200 <= reply.status < 300:
                    raise ValueError('transport must return successful TransportReply')
                (out / f'attempt-{attempt:02d}.body').write_bytes(reply.body)
                write_json(out / f'attempt-{attempt:02d}.json', {'started_at': started, 'finished_at': utc_now(),
                           'status': reply.status, 'request_id': reply.request_id})
                decoded = decode(reply, settings)
                write_json(out / 'response.json', decoded)
                result.update(status='completed', **decoded)
                break
            except TransportError as error:
                if error.reply:
                    (out / f'attempt-{attempt:02d}.body').write_bytes(error.reply.body)
                write_json(out / f'attempt-{attempt:02d}.json', {'started_at': started, 'finished_at': utc_now(),
                           'transport_error': str(error), 'retryable': error.retryable,
                           'status': error.reply.status if error.reply else None,
                           'request_id': error.reply.request_id if error.reply else None})
                if not error.retryable or attempt == settings.max_attempts:
                    raise
                sleep(min(2 ** (attempt - 1), 4))
    except (ValueError, UnicodeError, RecursionError, TypeError, KeyError, TransportError) as error:
        result.update(status='transport_failure' if isinstance(error, TransportError) else 'invalid', error=str(error))
    write_json(out / 'result.json', result)
    return result


def run(freeze_path, out, transport_factory, workers=6, base=HERE):
    frozen = strict_json(freeze_path.read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    hashes, approvals = approved_hashes(base)
    if hashes != frozen['packet_key_hashes'] or approvals != frozen['signoff']:
        raise ValueError('packets/keys/signoff changed since freeze')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'freeze.json', frozen)
    results = [None] * len(frozen['jobs'])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_job, out / f'{i:04d}', job, frozen['messages'][job['packet_id']],
                               ModelSettings(**frozen['settings'][job['model']]), transport_factory): i
                   for i, job in enumerate(frozen['jobs'])}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    summary = {'planned': len(results), 'completed': sum(r['status'] == 'completed' for r in results),
               'missing': sum(r['status'] == 'transport_failure' for r in results),
               'invalid': sum(r['status'] == 'invalid' for r in results)}
    write_json(out / 'results.json', {'results': results, 'summary': summary})
    return summary


def mask(run_dir, out, seed=SEED):
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    results = strict_json((run_dir / 'results.json').read_text())['results']
    pairs = [({'packet_id': r['packet_id'], 'text': r.get('text', ''), 'status': r['status']},
              {'run_index': i, 'model': r['model'], 'packet_id': r['packet_id']})
             for i, r in enumerate(results)]
    random.Random(seed).shuffle(pairs)
    items, mapping = [], {}
    for i, (item, identity) in enumerate(pairs):
        key = f'G{i + 1:03d}'
        items.append({'id': key, **item, 'packet': frozen['packets'][item['packet_id']]})
        mapping[key] = identity
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'grading-items.json', items)
    write_json(out / 'mapping.json', mapping)
    return {'items': len(items), 'warning': 'Grade grading-items.json before opening mapping.json; style may reveal source.'}


def live_transport(settings):
    return OpenAIResponsesTransport(endpoint=settings.endpoint, timeout_seconds=settings.timeout_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('signoff').add_argument('--name', required=True)
    sub.add_parser('prepare').add_argument('--out', type=Path, required=True)
    p = sub.add_parser('run')
    p.add_argument('freeze', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('mask')
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'signoff':
        result = signoff(args.name)
    elif args.command == 'prepare':
        f = prepare(args.out)
        result = {'jobs': len(f['jobs']), 'freeze_sha256': f['freeze_sha256']}
    elif args.command == 'run':
        result = run(args.freeze, args.out, live_transport)
    else:
        result = mask(args.run, args.out)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
