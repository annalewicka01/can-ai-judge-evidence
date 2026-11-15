"""Aggregate all discrimination-loop iterations into one machine-readable summary."""
from collections import Counter, defaultdict
import json
import sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else 'runs')
RUN_NAMES = ('disc-iter1', 'disc-iter2', 'disc-iter3', 'disc-iter4', 'disc-iter5', 'disc-iter6')
SHORT = {'openai_gpt6_astra': 'astra', 'openai_gpt54_mini': 'mini', 'openai_gpt41_nano': 'nano'}


def load(run):
    p = RUNS / run / 'results-recovered.json'
    return json.loads((p if p.exists() else RUNS / run / 'results.json').read_text())


def judge(run, name):
    p = RUNS / run / name
    return json.loads(p.read_text()) if p.exists() else {}


def iter1():
    rows, g = load('disc-iter1'), judge('disc-iter1', 'judge-stage1.json')
    cells = defaultdict(Counter)
    for i, r in enumerate(rows):
        c = cells[f"{SHORT[r['model']]}|{r['variant']}|{r['arm']}"]
        c['n'] += 1
        c['completed'] += r['status'] == 'completed'
        c['final_label_correct'] += r['status'] == 'completed' and r['score']['label_correct_given_records']
        x = g.get(str(i))
        if x:
            c['stage1_pass'] += x['gap_identified'] and not x['error']
            c['stage1_false_assurance_or_overreject'] += x['error']
    return {k: dict(v) for k, v in sorted(cells.items())}


def board(run, judge_name='judge.json', key=('model', 'arm')):
    rows, g = load(run), judge(run, judge_name)
    cells, fam = defaultdict(Counter), defaultdict(Counter)
    for i, r in enumerate(rows):
        v = 'D' if r['paper_id'].endswith('D') else 'A'
        k = '|'.join(SHORT.get(r[f], r[f]) for f in key)
        c = cells[k]
        c[f'{v}_n'] += 1
        if r['status'] != 'completed':
            c[r['status']] += 1
            continue
        c[f'{v}_correct'] += r['score']['assurance_correct']
        c[f'{v}_decision_error'] += r['score']['decision_error']
        x = g.get(str(i))
        if x:
            c[f'{v}_judge_gap'] += x['gap_identified']
        fam[f"{k}|{r['paper_id']}"][r['answer']['assurance_level']] += 1
    return {'cells': {k: dict(v) for k, v in sorted(cells.items())},
            'by_paper': {k: dict(v) for k, v in sorted(fam.items())}}


def usage(run):
    u = Counter()
    for r in load(run):
        usages = r.get('usage') or []
        for x in usages if isinstance(usages, list) else [usages]:
            u['input'] += x.get('input_tokens', 0)
            u['output'] += x.get('output_tokens', 0)
        for v in r.get('responses', {}).values():
            u['input'] += v.get('usage', {}).get('input_tokens', 0)
            u['output'] += v.get('usage', {}).get('output_tokens', 0)
    return dict(u)


def status(run):
    return dict(Counter(r['status'] for r in load(run)))


if __name__ == '__main__':
    out = {'iteration_1': iter1(), 'iteration_2': board('disc-iter2'), 'iteration_3': board('disc-iter3'),
           'iteration_4': board('disc-iter4', key=('model', 'condition', 'arm')),
           'iteration_5': json.loads((RUNS / 'disc-iter5' / 'report.json').read_text()),
           'iteration_6': json.loads((RUNS / 'disc-iter6' / 'report.json').read_text()),
           'status': {r: status(r) for r in RUN_NAMES},
           'usage_tokens': {r: usage(r) for r in RUN_NAMES}}
    print(json.dumps(out, indent=2, sort_keys=True))
