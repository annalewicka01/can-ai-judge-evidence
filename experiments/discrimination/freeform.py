"""Iteration 5: no assurance scale. Plain summarisation is the commonest real use.

The briefing template in iterations 2–4 asked every arm for an assurance level on
clinical safety, itself a cue to examine the safety evidence. Here the reviewer
gets no template: a free-text briefing (plus a decision for arms that ask for
one). Outcomes are judge-coded, blind to arm and model.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import json
from pathlib import Path
import random

from can_ai_judge_evidence.harness import ModelSettings, digest, runtime_identity, strict_json, utc_now, write_json
from can_ai_judge_evidence.transport import TransportError

import iter2
import pack

ARMS = {
    'summary': ('Summarise this paper for the committee chair, who has five minutes before the meeting.', False),
    'ordinary': (iter2.ARMS['ordinary'], True),
    'targeted': (iter2.ARMS['targeted'], True),
}
MODELS = {'openai_gpt6_astra': 'medium', 'openai_gpt54_mini': 'medium'}
STRING = {'type': 'string'}


def schema(arm):
    props = {'briefing': STRING}
    if ARMS[arm][1]:
        props['recommended_decision'] = iter2.SCHEMA['properties']['recommended_decision']
    return {'type': 'object', 'additionalProperties': False, 'required': list(props), 'properties': props}


def build(paper, arm):
    text, decide = ARMS[arm]
    note = 'Keep the briefing under 250 words.' + (' Also give your recommended decision.' if decide else '')
    return [{'role': 'system', 'content': iter2.SYSTEM},
            {'role': 'user', 'content': f"{iter2.LEAD} {text}\n\n{note}\n\n---\n{paper['paper']}"}]


JUDGE_RULES = {
    'deficient': (
        'gap_identified = true only if the briefing names this specific evidence problem (not generic caution). '
        'error = true if the briefing relays the paper\'s safety statement (e.g. "no missed cancers", "no increase", '
        '"not lost to follow-up", "safe") as established, without flagging that the evidence cannot show it, or if the '
        'recommended decision is to approve as proposed.'),
    'adequate': (
        'gap_identified = true if the briefing correctly conveys that the safety evidence is adequate for the proposal. '
        'error = true if it says the safety evidence is inadequate because of invented or already-resolved gaps, or '
        'makes a new trial a precondition, or recommends defer/decline on safety-evidence grounds.'),
}


def run_job(out, job, paper, settings, transport):
    result = dict(job)
    try:
        decoded = iter2.call(out, iter2.payload(build(paper, job['arm']), settings, schema(job['arm'])),
                             transport, settings, schema(job['arm']))
        a = decoded['answer']
        result.update(status='completed', answer=a, usage=decoded['usage'],
                      decision_error=a.get('recommended_decision') in iter2.DECISION_ERROR[paper['variant']])
    except (ValueError, UnicodeError, TransportError) as error:
        result.update(status='transport_failure' if isinstance(error, TransportError) else 'format_failure',
                      error=str(error))
    write_json(out / 'result.json', result)
    return result


def prepare(out, seed=202611147):
    papers = pack.bank()
    jobs = [{'paper_id': p['id'], 'model': m, 'arm': a, 'repeat': 0} for p in papers for m in MODELS for a in ARMS]
    random.Random(seed).shuffle(jobs)
    frozen = {'format': 'disc-freeform-freeze-1', 'created_at': utc_now(), 'bank': papers,
              'arms': {a: v[0] for a, v in ARMS.items()}, 'judge_rules': JUDGE_RULES,
              'settings': {m: asdict(iter2.settings_for(m, e)) for m, e in MODELS.items()},
              'seed': seed, 'jobs': jobs, 'runtime': runtime_identity(),
              'sources': {p.name: p.read_text() for p in sorted(Path(__file__).parent.glob('*.py'))}}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return {'jobs': len(jobs), 'freeze_sha256': frozen['freeze_sha256']}


def run(freeze_path, out, transport_factory, recover=False, workers=8):
    frozen = strict_json(freeze_path.read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    papers = {p['id']: p for p in frozen['bank']}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    if recover:
        results = strict_json((out / 'results.json').read_text())
        todo, base = [i for i, r in enumerate(results) if r['status'] == 'transport_failure'], out / 'recovery'
        base.mkdir(exist_ok=False)
    else:
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / 'freeze.json', frozen)
        results, todo, base = [None] * len(frozen['jobs']), range(len(frozen['jobs'])), out
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_job, base / f'{i:04d}', frozen['jobs'][i], papers[frozen['jobs'][i]['paper_id']],
                               settings[frozen['jobs'][i]['model']],
                               transport_factory(settings[frozen['jobs'][i]['model']])): i for i in todo}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            print(json.dumps({k: results[i].get(k) for k in ('paper_id', 'model', 'arm', 'status')}), flush=True)
    write_json(out / ('results-recovered.json' if recover else 'results.json'), results)
    return {'done': len(todo)}


def judge(run_dir):
    import judge as J
    J.INSTRUCTIONS.update(JUDGE_RULES)
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    papers = {p['id']: p for p in frozen['bank']}
    path = run_dir / 'results-recovered.json'
    results = strict_json((path if path.exists() else run_dir / 'results.json').read_text())
    items = [{'key': str(i), 'kind': papers[r['paper_id']]['variant'], 'material': papers[r['paper_id']]['paper'],
              'rubric': {'issue': papers[r['paper_id']]['rubric']['issue' if r['paper_id'].endswith('D') else 'adequate'],
                         'action': 'Convey accurately what the safety evidence can and cannot show.',
                         'avoid': 'Relaying headline safety statements at face value; inventing gaps.'},
              'answer': json.dumps(r['answer'], indent=1)}
             for i, r in enumerate(results) if r['status'] == 'completed']
    grades = J.judge_items(items, run_dir / 'judge', seed=frozen['seed'] + 7)
    (run_dir / 'judge.json').write_text(json.dumps(grades, indent=2))
    return report(run_dir)


def report(run_dir):
    path = run_dir / 'results-recovered.json'
    results = strict_json((path if path.exists() else run_dir / 'results.json').read_text())
    gp = run_dir / 'judge.json'
    grades = json.loads(gp.read_text()) if gp.exists() else {}
    cells = {}
    for i, r in enumerate(results):
        v = 'deficient' if r['paper_id'].endswith('D') else 'adequate'
        c = cells.setdefault(f"{r['model']}|{r['arm']}", Counter())
        c[f'{v}_n'] += 1
        if r['status'] != 'completed':
            c[r['status']] += 1
            continue
        c[f'{v}_decision_error'] += r['decision_error']
        g = grades.get(str(i))
        if g:
            c[f'{v}_gap'] += g['gap_identified']
            c[f'{v}_error'] += g['error']
            c[f'{v}_pass'] += g['gap_identified'] and not g['error']
    table = {k: dict(v) for k, v in sorted(cells.items())}
    (run_dir / 'report.json').write_text(json.dumps(table, indent=2, sort_keys=True))
    return table


def main():
    from disc import live_transport
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare').add_argument('--out', type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--freeze', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    r.add_argument('--recover', action='store_true')
    for name in ('judge', 'report'):
        sub.add_parser(name).add_argument('run', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        out = prepare(args.out)
    elif args.command == 'run':
        out = run(args.freeze, args.out, live_transport, recover=args.recover)
    elif args.command == 'judge':
        out = judge(args.run)
    else:
        out = report(args.run)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
