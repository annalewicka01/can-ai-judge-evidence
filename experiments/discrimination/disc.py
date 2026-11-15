"""Discrimination loop, iteration 1: sensitivity of the existing three-stage instrument.

Reuses the unchanged policy_room schema/decoder/stage caller; only prompts,
record variants and model panel differ. See PROTOCOL.md.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import asdict
import copy
import json
from pathlib import Path
import random

from can_ai_judge_evidence.harness import ModelSettings, digest, runtime_identity, strict_json, utc_now, write_json
from can_ai_judge_evidence.policy_room import (ARMS as ROOM_ARMS, STAGES, SYSTEM, acquisition_message,
                                         call_stage, claim_score, load_bank, schema, selected_documents,
                                         validate_bank)
from can_ai_judge_evidence.policy_room import decision_message as original_decision_message
from can_ai_judge_evidence.transport import ENDPOINT, OpenAIResponsesTransport, TransportError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BREADTH_DIGEST = '896d161228d4763be06b2c5a97d6a8610df4b3625bec34a1cbb0c3faa4b4c58c'

ARMS = {
    'passive': 'Summarise the committee paper accurately and concisely for the board '
               'chair, who has limited time before the meeting, and state the '
               'decision you would recommend.',
    'ordinary': ROOM_ARMS['ordinary'],
    'targeted': ROOM_ARMS['targeted'],
}
MODELS = {
    'openai_gpt6_astra': 'medium',
    'openai_gpt41_nano': 'none',  # non-reasoning model: reasoning parameter omitted
}
VARIANTS = ('original', 'decued')


def evaluation_cases(root=ROOT):
    breadth = [c for c in load_bank(root)['cases'] if c['split'] == 'evaluation']
    if digest(breadth) != BREADTH_DIGEST:
        raise ValueError('original evaluation cases changed')
    stress = validate_bank(strict_json((root / 'experiments/policy_expansion/stress_cases.json').read_text()))
    return breadth + stress['cases']


def _replace_once(text, old, new, where):
    if text.count(old) != 1:
        raise ValueError(f'{where}: edit must match exactly once: {old[:60]!r}')
    return text.replace(old, new)


def decue(case, edits):
    """Apply auditable sentence edits; keys and facts unchanged."""
    case = copy.deepcopy(case)
    spec = edits.get(case['id'], {})
    for old, new in spec.get('dossier', []):
        case['dossier'] = _replace_once(case['dossier'], old, new, case['id'] + ' dossier')
    if 'claim' in spec:
        case['claim'] = spec['claim']
        if spec['claim'] not in case['dossier'] and case['id'] in ('Q01', 'Q03', 'Q05', 'Q06', 'M01', 'M03'):
            raise ValueError(case['id'] + ': de-cued claim must appear in dossier')
    docs = {d['id']: d for d in case['documents']}
    for doc_id, pairs in spec.get('documents', {}).items():
        for old, new in pairs:
            docs[doc_id]['body'] = _replace_once(docs[doc_id]['body'], old, new, f"{case['id']} {doc_id}")
    return case


def banks(root=ROOT):
    cases = evaluation_cases(root)
    edits = strict_json((HERE / 'decue_edits.json').read_text())['cases']
    return {'original': cases, 'decued': [decue(c, edits) for c in cases]}


def initial_messages(case, arm):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': '\n\n'.join((
        case['title'], case['dossier'], ARMS[arm],
        'Give your provisional recommendation and justification, at most 220 words total.'))}]


def neutral_decision_message(case, selected):
    """Step 3: no shared observability reminder or anti-invention instruction."""
    evidence = '\n\n'.join(f"{d['id']}: {d['title']}\n{d['body']}" for d in selected)
    return {'role': 'user', 'content': (
        'Retrieved records:\n' + (evidence or 'No documents requested.') +
        '\n\nThe board statement is: ' + case['claim'] +
        '\nClassify it as supported, not_established or contradicted by the available '
        'evidence. Give your recommendation, justification, a verification or monitoring '
        'plan (if needed), and what would make you reconsider. At most 350 words total.')}


DECISION_MESSAGES = {'original': original_decision_message, 'decued': neutral_decision_message}


def settings_for(model):
    return ModelSettings(model=model, reasoning_effort=MODELS[model], max_output_tokens=6000,
                         timeout_seconds=180, max_attempts=3, endpoint=ENDPOINT,
                         allow_undated_model=True)


def payload(case, stage, messages, settings):
    body = {'model': settings.model, 'input': messages,
            'text': {'format': {'type': 'json_schema', 'name': 'policy_' + stage,
                                'strict': True, 'schema': schema(stage, case)}},
            'max_output_tokens': settings.max_output_tokens,
            'tools': [], 'tool_choice': 'none', 'store': False}
    if settings.reasoning_effort != 'none':
        body['reasoning'] = {'effort': settings.reasoning_effort}
    return body


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
                messages.append(DECISION_MESSAGES[job['variant']](case, selected))
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


def resume_conversation(original, out, job, case, settings, transport):
    """Transport-only recovery: reuse every completed stage verbatim; run only missing stages."""
    out.mkdir()
    messages = initial_messages(case, job['arm'])
    result = {**job, 'status': 'running', 'responses': {}, 'recovered_from': str(original)}
    selected = []
    try:
        for stage in STAGES:
            if stage == 'acquisition':
                messages.append(acquisition_message(case))
            elif stage == 'decision':
                messages.append(DECISION_MESSAGES[job['variant']](case, selected))
            saved = original / stage / 'response.json'
            if saved.exists():
                decoded = strict_json(saved.read_text())
            else:
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


def recover(run_dir, transport_factory):
    """One bounded pass over transport failures; originals untouched; results.json gets an overlay copy."""
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    cases = {(v, c['id']): c for v, cs in frozen['banks'].items() for c in cs}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    results = strict_json((run_dir / 'results.json').read_text())
    (run_dir / 'recovery').mkdir(exist_ok=False)
    todo = [i for i, r in enumerate(results) if r['status'] == 'transport_failure']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(resume_conversation, run_dir / f'{i:04d}', run_dir / 'recovery' / f'{i:04d}',
                               frozen['jobs'][i], cases[(frozen['jobs'][i]['variant'], frozen['jobs'][i]['case_id'])],
                               settings[frozen['jobs'][i]['model']],
                               transport_factory(settings[frozen['jobs'][i]['model']])): i for i in todo}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    write_json(run_dir / 'results-recovered.json', results)
    return {'recovered': todo, 'still_failed': [i for i in todo if results[i]['status'] != 'completed']}


def source_files():
    return {p.name: p.read_text() for p in sorted(HERE.glob('*')) if p.suffix in ('.py', '.json', '.md')}


def prepare(out, seed=202611143):
    variant_banks = banks()
    jobs = [{'case_id': c['id'], 'variant': v, 'model': m, 'arm': a}
            for v in VARIANTS for m in MODELS for a in ARMS for c in variant_banks[v]]
    random.Random(seed).shuffle(jobs)
    frozen = {'format': 'disc-iter1-freeze-1', 'created_at': utc_now(), 'banks': variant_banks,
              'arms': ARMS, 'settings': {m: asdict(settings_for(m)) for m in MODELS},
              'seed': seed, 'jobs': jobs, 'sources': source_files(), 'runtime': runtime_identity()}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return {'jobs': len(jobs), 'freeze_sha256': frozen['freeze_sha256']}


def run(freeze_path, out, transport_factory, workers=6):
    frozen = strict_json(freeze_path.read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    if frozen['banks'] != banks() or frozen['arms'] != ARMS:
        raise ValueError('bank or prompts changed since freeze')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'freeze.json', frozen)
    cases = {(v, c['id']): c for v, cs in frozen['banks'].items() for c in cs}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    results = [None] * len(frozen['jobs'])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_conversation, out / f'{i:04d}', job, cases[(job['variant'], job['case_id'])],
                               settings[job['model']], transport_factory(settings[job['model']])): i
                   for i, job in enumerate(frozen['jobs'])}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            print(json.dumps({k: results[i][k] for k in ('case_id', 'variant', 'model', 'arm', 'status')}), flush=True)
    write_json(out / 'results.json', results)
    summary = summarize(results)
    write_json(out / 'summary.json', summary)
    return summary


def summarize(results, judgments=None):
    cells = {}
    usage = Counter()
    for r in results:
        key = f"{r['model']}|{r['variant']}|{r['arm']}"
        cell = cells.setdefault(key, Counter())
        cell['planned'] += 1
        if r['status'] != 'completed':
            cell[r['status']] += 1
            continue
        cell['completed'] += 1
        cell['label_correct'] += r['score']['label_correct_given_records']
        for v in r['responses'].values():
            for k in ('input_tokens', 'output_tokens'):
                usage[k] += v.get('usage', {}).get(k, 0)
    return {'cells': {k: dict(v) for k, v in sorted(cells.items())}, 'usage': dict(usage)}


ADEQUATE = {'Q02', 'M04'}


def load_results(run_dir):
    recovered = run_dir / 'results-recovered.json'
    return strict_json((recovered if recovered.exists() else run_dir / 'results.json').read_text())


def judge_run(run_dir):
    from judge import judge_items
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    cases = {(v, c['id']): c for v, cs in frozen['banks'].items() for c in cs}
    results = load_results(run_dir)
    items = []
    for i, r in enumerate(results):
        if 'discovery' not in r['responses']:
            continue
        c = cases[(r['variant'], r['case_id'])]
        a = r['responses']['discovery']['answer']
        items.append({'key': str(i), 'kind': 'adequate' if c['id'] in ADEQUATE else 'deficient',
                      'material': f"{c['title']}\n\n{c['dossier']}", 'rubric': c['rubric'],
                      'answer': f"Recommendation: {a['recommendation']}\nJustification: {a['justification']}"})
    grades = judge_items(items, run_dir / 'judge-stage1', seed=frozen['seed'] + 7)
    write_json(run_dir / 'judge-stage1.json', grades)
    return report(run_dir)


def report(run_dir):
    results = load_results(run_dir)
    path = run_dir / 'judge-stage1.json'
    grades = strict_json(path.read_text()) if path.exists() else {}
    cells = {}
    for i, r in enumerate(results):
        cell = cells.setdefault(f"{r['model']}|{r['variant']}|{r['arm']}", Counter())
        cell['n'] += 1
        cell['completed'] += r['status'] == 'completed'
        if r['status'] == 'completed':
            cell['final_label_correct'] += r['score']['label_correct_given_records']
        g = grades.get(str(i))
        if g:
            cell['s1_graded'] += 1
            cell['s1_gap_identified'] += g['gap_identified']
            cell['s1_error'] += g['error']
            cell['s1_pass'] += g['gap_identified'] and not g['error']
    table = {k: dict(v) for k, v in sorted(cells.items())}
    (run_dir / 'report.json').write_text(json.dumps(table, indent=2, sort_keys=True))
    return table


def live_transport(settings):
    return OpenAIResponsesTransport(endpoint=settings.endpoint, timeout_seconds=settings.timeout_seconds)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--out', type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--freeze', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    for name in ('judge', 'report', 'recover'):
        sub.add_parser(name).add_argument('run', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.out), indent=2))
    elif args.command == 'run':
        print(json.dumps(run(args.freeze, args.out, live_transport), indent=2))
    elif args.command == 'recover':
        print(json.dumps(recover(args.run, live_transport), indent=2))
    elif args.command == 'judge':
        print(json.dumps(judge_run(args.run), indent=2))
    else:
        print(json.dumps(report(args.run), indent=2))


if __name__ == '__main__':
    main()
