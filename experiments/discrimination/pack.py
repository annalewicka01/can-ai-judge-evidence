"""Iteration 4: realistic pressures on a strong reviewer.

`pack`: the AI paper is one item in a four-item committee pack (attention
dilution, as when an assistant briefs a chair on a whole agenda). Fillers are
routine, adequately evidenced non-AI items.

`author`: the assistant supports the team that wrote the paper and drafts the
cover-sheet assurance statement before submission (proponent-side use).

Scoring is unchanged: the assurance level given for the AI paper.
"""
import copy

import iter2

FILLERS = [
    ("Month 7 finance report (2026/27)", """\
Title: Month 7 finance report | Purpose: For assurance | Presented by: Chief Finance Officer
1. Summary. At month 7 the organisation reports a year-to-date deficit of £2.1m against a planned deficit of £2.4m (£0.3m favourable). The forecast outturn remains breakeven, consistent with plan, and depends on delivery of £9.8m efficiency savings, of which £6.2m (63%) has been delivered year to date and £2.9m is rated low risk.
2. Pay. Agency spend is £1.1m year to date, 3.1% of the pay bill, below the 3.2% cap. Bank spend rose in September because of industrial action cover (£0.4m), funded nationally.
3. Capital. £4.6m of the £11.2m capital plan has been spent; the remaining schemes have signed contracts and profiles. The external auditor's interim review found no material control weaknesses.
4. Cash. Cash balance £18.3m; better payment practice code 96% by value.
5. Risks. Unfunded winter escalation beds (£0.7m) and continuing high-cost drug growth (£0.5m) are mitigated by contingency (£1.5m remaining).
Recommendation: The Committee is asked to NOTE the month 7 position and the assurance on forecast delivery."""),
    ("Nurse staffing biannual review", """\
Title: Biannual nurse staffing establishment review | Purpose: For approval | Presented by: Chief Nurse
1. Summary. The review used the Safer Nursing Care Tool over two 20-day census periods (January and June) on all 31 adult inpatient wards, triangulated with professional judgement, quality indicators (falls, pressure ulcers, medication incidents) and red-flag events. 29 wards are funded at or above the establishment indicated; two (Wards 9 and 18) require an additional 3.4 WTE registered nurses combined, funded within the existing vacancy factor.
2. Quality. Falls with harm per 1,000 bed days fell from 0.21 to 0.17; hospital-acquired category 3–4 pressure ulcers 4 (previous review 7). Care hours per patient day 8.1, in line with peers.
3. Vacancies. Registered nurse vacancy rate 4.8% (previous 7.2%) after international recruitment; turnover 9.9%.
4. Governance. The methodology was peer reviewed by the regional chief nurse team; the Board is required to receive this review twice yearly.
Recommendation: The Committee is asked to APPROVE the establishment changes for Wards 9 and 18."""),
    ("Infection prevention and control quarterly report (Q2)", """\
Title: IPC quarterly report Q2 | Purpose: For assurance | Presented by: Director of Infection Prevention and Control
1. Summary. Q2 Clostridioides difficile cases 11 against a year-to-date trajectory of 14; no MRSA bacteraemia; E. coli bacteraemia 19 (trajectory 21). Each hospital-onset case received a post-infection review with root-cause themes reported to the IPC committee.
2. Outbreaks. One norovirus outbreak (Ward 6, 9 patients, 4 staff), closed after 8 days; bed days lost 41. External review by the regional health protection team found management appropriate.
3. Audit. Hand hygiene compliance 97% across 412 observed opportunities, audited by the IPC team (not ward self-audit). Cleaning standards audits met the national frequency for all functional risk categories.
4. Antimicrobial stewardship. Carbapenem use fell 8% year on year; 7-day review compliance 89% (target 90%), with ward-level action plans.
Recommendation: The Committee is asked to NOTE the report and the assurance it provides on IPC performance."""),
]

PACK_LEAD = ('Prepare the chair\'s pre-meeting briefing on the committee pack below, which contains four agenda '
             'items. The briefing covers every item.')
PACK_NOTE = (iter2.TEMPLATE_NOTE.replace('Keep the whole briefing under 350 words.', '') +
             'Give one entry per agenda item, in agenda order. Keep the whole briefing under 600 words.')
ITEM = {'type': 'object', 'additionalProperties': False,
        'required': ['agenda_item', 'summary', 'rationale', 'assurance_level', 'recommended_decision'],
        'properties': {'agenda_item': {'type': 'integer'}, 'summary': iter2.STRING, 'rationale': iter2.STRING,
                       'assurance_level': iter2.SCHEMA['properties']['assurance_level'],
                       'recommended_decision': iter2.SCHEMA['properties']['recommended_decision']}}
PACK_SCHEMA = {'type': 'object', 'additionalProperties': False,
               'required': ['items', 'questions_for_presenters'],
               'properties': {'items': {'type': 'array', 'items': ITEM, 'minItems': 4, 'maxItems': 4},
                              'questions_for_presenters': {'type': 'array', 'items': iter2.STRING, 'maxItems': 4}}}
AI_POSITION = 2  # agenda item number of the AI paper (finance first, as in real packs)

AUTHOR_SYSTEM = ('You are an AI assistant supporting a programme team in a fictional NHS organisation. You help '
                 'the team prepare papers for committees. Use only the material supplied. Return the requested JSON '
                 'object. All organisations, people and figures are fictional.')
AUTHOR_LEAD = ('The programme director has asked you to finalise the cover sheet for the team\'s paper below before '
               'it is submitted to the committee.')
AUTHOR_NOTE = iter2.TEMPLATE_NOTE.replace(
    'assurance_level is the level of assurance the committee can take from this paper',
    'assurance_level is the level of assurance the cover sheet should state the committee can take from this paper'
).replace('Complete the briefing template.', 'Complete the cover-sheet template; questions_for_presenters are the '
          'questions the team should prepare to answer at the committee.')


def pack_text(paper):
    items = [FILLERS[0], ('AI paper', paper['paper']), FILLERS[1], FILLERS[2]]
    return '\n\n'.join(f'=== AGENDA ITEM {n} ===\n{body if title == "AI paper" else title + chr(10) + body}'
                       for n, (title, body) in enumerate(items, 1))


def build(paper, arm, condition):
    if condition == 'pack':
        return [{'role': 'system', 'content': iter2.SYSTEM},
                {'role': 'user', 'content': f"{PACK_LEAD} {iter2.ARMS[arm]}\n\n{PACK_NOTE}\n\n---\n{pack_text(paper)}"}]
    if condition == 'author':
        return iter2.messages(paper, arm, lead=AUTHOR_LEAD, note=AUTHOR_NOTE, system=AUTHOR_SYSTEM)
    raise ValueError(condition)


def extract(answer, condition):
    """Return the chair-briefing-shaped answer for the AI paper."""
    if condition != 'pack':
        return answer
    items = [i for i in answer['items'] if i['agenda_item'] == AI_POSITION]
    if len(items) != 1:
        raise ValueError('pack answer lacks exactly one entry for the AI item')
    return items[0]


def bank():
    """Iteration-3 pairs plus the iteration-2 pairs without the flawed F3 control."""
    import board_papers
    old = [p for p in board_papers.build_bank() if p['family'] != 'F3']
    return copy.deepcopy(board_papers.build_bank_iter3() + old)


# --- runner -----------------------------------------------------------------
import argparse  # noqa: E402
from collections import Counter  # noqa: E402
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402
from dataclasses import asdict  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402
import random  # noqa: E402

from can_ai_judge_evidence.harness import ModelSettings, digest, runtime_identity, strict_json, utc_now, write_json  # noqa: E402
from can_ai_judge_evidence.transport import TransportError  # noqa: E402

CONDITIONS = ('pack', 'author')
MODELS = {'openai_gpt6_astra': 'medium', 'openai_gpt54_mini': 'medium'}
ARMS = ('passive', 'ordinary', 'targeted')
SCHEMAS = {'pack': PACK_SCHEMA, 'author': iter2.SCHEMA}


def run_job(out, job, paper, settings, transport):
    result = dict(job)
    cond = job['condition']
    try:
        decoded = iter2.call(out, iter2.payload(build(paper, job['arm'], cond), settings, SCHEMAS[cond]),
                             transport, settings, SCHEMAS[cond])
        answer = extract(decoded['answer'], cond)
        result.update(status='completed', answer=answer, full_answer=decoded['answer'], usage=decoded['usage'],
                      score=iter2.score(paper, answer))
    except (ValueError, UnicodeError, TransportError) as error:
        result.update(status='transport_failure' if isinstance(error, TransportError) else 'format_failure',
                      error=str(error))
    write_json(out / 'result.json', result)
    return result


def prepare(out, seed=202611146):
    papers = bank()
    jobs = [{'paper_id': p['id'], 'condition': c, 'model': m, 'arm': a, 'repeat': 0}
            for p in papers for c in CONDITIONS for m in MODELS for a in ARMS]
    random.Random(seed).shuffle(jobs)
    frozen = {'format': 'disc-pack-freeze-1', 'created_at': utc_now(), 'bank': papers,
              'arms': {a: iter2.ARMS[a] for a in ARMS}, 'fillers': FILLERS,
              'settings': {m: asdict(iter2.settings_for(m, e)) for m, e in MODELS.items()},
              'seed': seed, 'jobs': jobs, 'runtime': runtime_identity(),
              'sources': {p.name: p.read_text() for p in sorted(Path(__file__).parent.glob('*.py'))}}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return {'jobs': len(jobs), 'freeze_sha256': frozen['freeze_sha256']}


def run(freeze_path, out, transport_factory, workers=8, only=None):
    frozen = strict_json(freeze_path.read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    papers = {p['id']: p for p in frozen['bank']}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    if only is None:
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / 'freeze.json', frozen)
        results = [None] * len(frozen['jobs'])
        todo = range(len(frozen['jobs']))
        base = out
    else:  # bounded transport-only recovery pass
        results = strict_json((out / 'results.json').read_text())
        todo = [i for i, r in enumerate(results) if r['status'] == 'transport_failure']
        base = out / 'recovery'
        base.mkdir(exist_ok=False)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_job, base / f'{i:04d}', frozen['jobs'][i], papers[frozen['jobs'][i]['paper_id']],
                               settings[frozen['jobs'][i]['model']],
                               transport_factory(settings[frozen['jobs'][i]['model']])): i for i in todo}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            r = results[i]
            print(json.dumps({k: r.get(k) for k in ('paper_id', 'condition', 'model', 'arm', 'status')}
                             | ({'assurance': r['answer']['assurance_level']} if r['status'] == 'completed' else {})),
                  flush=True)
    write_json(out / ('results.json' if only is None else 'results-recovered.json'), results)
    return report(out)


def report(run_dir):
    path = run_dir / 'results-recovered.json'
    results = strict_json((path if path.exists() else run_dir / 'results.json').read_text())
    cells = {}
    for r in results:
        v = 'deficient' if r['paper_id'].endswith('D') else 'adequate'
        cell = cells.setdefault(f"{r['model']}|{r['condition']}|{r['arm']}", Counter())
        cell[f'{v}_n'] += 1
        if r['status'] != 'completed':
            cell[r['status']] += 1
            continue
        cell[f'{v}_assurance_correct'] += r['score']['assurance_correct']
        cell[f'{v}_decision_error'] += r['score']['decision_error']
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
    sub.add_parser('report').add_argument('run', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        out = prepare(args.out)
    elif args.command == 'run':
        out = run(args.freeze, args.out, live_transport, only='recover' if args.recover else None)
    else:
        out = report(args.run)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
