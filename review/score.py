"""Compare completed forms with the hidden expected answers."""
import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def score_answer(answer, kind):
    answer = (answer or '').strip().lower()
    if not answer:
        return 'blank'
    if answer == 'unsure':
        return 'unsure'
    if answer not in ('yes', 'no'):
        raise ValueError(f'Unknown answer: {answer!r}')
    return 'agree' if answer == {'D': 'no', 'A': 'yes'}[kind] else 'disagree'


def score(root=HERE):
    keys = json.loads((root / 'answer_key.json').read_text())['pairs']
    reviewers = {}
    for path in sorted((root / 'responses').glob('*.csv')):
        if path.stem.upper() == 'TEMPLATE':
            continue
        rows = {}
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                pair = row['pair'].strip()
                if pair not in keys or pair in rows:
                    raise ValueError(f'{path.name}: unknown or repeated pair {pair}')
                rows[pair] = row
        reviewers[path.stem] = rows
    lines = ['# Review results', '', 'Each cell shows X / Y. Totals count version answers, not pairs.', '',
             '| Pair | ' + ' | '.join(reviewers) + ' |',
             '| --- | ' + ' | '.join('---' for _ in reviewers) + ' |']
    totals = {r: Counter() for r in reviewers}
    for pair, key in keys.items():
        cells = []
        for reviewer, rows in reviewers.items():
            row = rows.get(pair, {})
            states = [score_answer(row.get(f'version_{v.lower()}'), key[v]) for v in ('X', 'Y')]
            totals[reviewer].update(states)
            cells.append(' / '.join(states))
        lines.append('| ' + pair + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '| Reviewer | Agree | Disagree | Unsure | Blank |', '| --- | --- | --- | --- | --- |']
    for reviewer, counts in totals.items():
        lines.append('| ' + reviewer + ' | ' + ' | '.join(str(counts[s]) for s in ('agree', 'disagree', 'unsure', 'blank')) + ' |')
    comments = [(r, p, row['comment']) for r, rows in reviewers.items() for p, row in rows.items() if row.get('comment')]
    if comments:
        lines += ['', '## Reviewer comments', '']
        lines.extend(f'- {r}, {p}: {comment}' for r, p, comment in comments)
    report = '\n'.join(lines) + '\n'
    (root / 'RESULTS.md').write_text(report)
    print(report)
    return totals


if __name__ == '__main__':
    score()
