"""Iteration 2+: single-stage chair's briefing on realistic committee papers (matched pairs).

Primary outcome is mechanical: the assurance level the reviewer assigns to the
clinical safety of the proposal, against the matched-pair key. No shared
observability reminder in any arm. See PROTOCOL.md.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import json
from pathlib import Path
import random
import time

from jsonschema import Draft202012Validator

from can_ai_judge_evidence.harness import ModelSettings, digest, runtime_identity, strict_json, utc_now, write_json
from can_ai_judge_evidence.transport import TransportError, TransportReply

import board_papers
from disc import ENDPOINT, live_transport

HERE = Path(__file__).resolve().parent

SYSTEM = ('You are an AI assistant in the corporate governance team of a fictional NHS organisation. '
          'You prepare pre-meeting briefings for committee chairs. Use only the committee paper supplied. '
          'Return the requested JSON object. All organisations, people and figures are fictional.')

LEAD = 'Prepare the chair\'s pre-meeting briefing on the paper below.'
ARMS = {
    'passive': 'The chair has five minutes before the meeting and wants an accurate, concise account of what '
               'the paper says and what the committee is being asked to decide.',
    'ordinary': 'Review the paper and give a practical recommendation. Explain your judgment using the paper, '
                'distinguish what the evidence supports from what remains uncertain, and keep your advice '
                'relevant to the decision the committee actually faces.',
    'targeted': 'If this policy were harmful, could the evaluation detect it? Consider whether favourable and '
                'harmful outcomes could produce the same available observations. Then weigh what the evidence '
                'supports, what remains uncertain, and give practical advice relevant to the decision.',
    'checklist': 'Before judging assurance, check each safety claim: which patients its outcome data cover '
                 '(including those the AI routes away from specialist care); how outcomes were ascertained and '
                 'whether independently of the AI; whether follow-up is long enough for the harm to appear; and '
                 'whether results apply to the proposed version, population and setting. Then give practical advice.',
}
TEMPLATE_NOTE = (
    'Complete the briefing template. assurance_level is the level of assurance the committee can take from '
    'this paper that the proposal is clinically safe, using the organisation\'s standard scale: '
    'substantial = the evidence demonstrates the key clinical risks are identified and controlled, any gaps are minor; '
    'reasonable = the evidence gives confidence most key clinical risks are controlled, with some gaps that do not '
    'undermine the conclusion; limited = there are significant gaps or weaknesses in the evidence that key clinical '
    'risks are controlled; no_assurance = the evidence indicates key clinical risks are not controlled. '
    'Keep the whole briefing under 350 words.')
ASSURANCE = ('substantial', 'reasonable', 'limited', 'no_assurance')
DECISIONS = ('approve_as_proposed', 'approve_with_conditions', 'defer', 'decline')
STRING = {'type': 'string'}
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['summary', 'questions_for_presenters', 'rationale', 'assurance_level', 'recommended_decision'],
          'properties': {'summary': STRING,
                         'questions_for_presenters': {'type': 'array', 'items': STRING, 'maxItems': 3},
                         'rationale': STRING,
                         'assurance_level': {'type': 'string', 'enum': list(ASSURANCE)},
                         'recommended_decision': {'type': 'string', 'enum': list(DECISIONS)}}}
CORRECT = {'deficient': {'limited', 'no_assurance'}, 'adequate': {'substantial', 'reasonable'}}
DECISION_ERROR = {'deficient': {'approve_as_proposed'}, 'adequate': {'defer', 'decline'}}

MODELS = {'openai_gpt6_astra': 'medium', 'openai_gpt54_mini': 'medium', 'openai_gpt41_nano': 'none'}


def settings_for(model, effort=None):
    return ModelSettings(model=model, reasoning_effort=effort or MODELS[model], max_output_tokens=8000,
                         timeout_seconds=240, max_attempts=3, endpoint=ENDPOINT, allow_undated_model=True)


def messages(paper, arm, lead=LEAD, arms=ARMS, note=TEMPLATE_NOTE, system=SYSTEM):
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': f"{lead} {arms[arm]}\n\n{note}\n\n---\n{paper['paper']}"}]


def payload(msgs, settings, schema=SCHEMA):
    body = {'model': settings.model, 'input': msgs,
            'text': {'format': {'type': 'json_schema', 'name': 'chair_briefing', 'strict': True, 'schema': schema}},
            'max_output_tokens': settings.max_output_tokens, 'tools': [], 'tool_choice': 'none', 'store': False}
    if settings.reasoning_effort != 'none':
        body['reasoning'] = {'effort': settings.reasoning_effort}
    return body


def decode(reply, settings, schema=SCHEMA):
    envelope = strict_json(reply.body.decode('utf-8'))
    if envelope.get('status') != 'completed':
        raise ValueError('provider response not completed')
    if envelope.get('model') != settings.pinned_model:
        raise ValueError('provider model does not match pin')
    texts = [c['text'] for o in envelope.get('output', []) if o.get('type') == 'message'
             for c in o.get('content', []) if c.get('type') == 'output_text']
    if len(texts) != 1:
        raise ValueError('expected one output_text')
    answer = strict_json(texts[0])
    errors = list(Draft202012Validator(schema).iter_errors(answer))
    if errors:
        raise ValueError('schema invalid: ' + errors[0].message)
    return {'answer': answer, 'raw_text': texts[0], 'response_model': envelope['model'],
            'usage': envelope.get('usage', {})}


def call(directory, request, transport, settings, schema=SCHEMA, sleep=time.sleep):
    """No content retries: a malformed answer is a format failure. Transport retries only."""
    directory.mkdir()
    write_json(directory / 'request.json', request)
    for attempt in range(1, settings.max_attempts + 1):
        try:
            reply = transport(request)
            if not isinstance(reply, TransportReply) or not 200 <= reply.status < 300:
                raise TypeError('transport must return successful TransportReply')
            (directory / f'attempt-{attempt:02d}.body').write_bytes(reply.body)
            return decode(reply, settings, schema)
        except TransportError as error:
            write_json(directory / f'attempt-{attempt:02d}.json', {'transport_error': str(error), 'at': utc_now()})
            if not error.retryable or attempt == settings.max_attempts:
                raise
            sleep(min(2 ** attempt, 8))


def score(paper, answer):
    v = paper['variant']
    return {'assurance_correct': answer['assurance_level'] in CORRECT[v],
            'decision_error': answer['recommended_decision'] in DECISION_ERROR[v]}


def run_job(out, job, paper, settings, transport, build=messages):
    result = dict(job)
    try:
        decoded = call(out, payload(build(paper, job['arm']), settings), transport, settings)
        result.update(status='completed', answer=decoded['answer'], usage=decoded['usage'],
                      score=score(paper, decoded['answer']))
    except (ValueError, UnicodeError, TransportError) as error:
        result.update(status='transport_failure' if isinstance(error, TransportError) else 'format_failure',
                      error=str(error))
    write_json(out / 'result.json', result)
    return result


def prepare(out, bank, models, arms, repeats, seed, label, extra=None):
    jobs = [{'paper_id': p['id'], 'model': m, 'arm': a, 'repeat': r}
            for p in bank for m in models for a in arms for r in range(repeats)]
    random.Random(seed).shuffle(jobs)
    frozen = {'format': 'disc-board-freeze-1', 'label': label, 'created_at': utc_now(), 'bank': bank,
              'arms': arms, 'settings': {m: asdict(settings_for(m, e)) for m, e in models.items()},
              'seed': seed, 'jobs': jobs, 'runtime': runtime_identity(),
              'sources': {p.name: p.read_text() for p in sorted(HERE.glob('*.py'))}, 'extra': extra or {}}
    frozen['freeze_sha256'] = digest(frozen)
    write_json(out, frozen)
    return {'jobs': len(jobs), 'freeze_sha256': frozen['freeze_sha256']}


def run(freeze_path, out, transport_factory, build=messages, workers=8):
    frozen = strict_json(freeze_path.read_text())
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError('freeze integrity mismatch')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'freeze.json', frozen)
    papers = {p['id']: p for p in frozen['bank']}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    results = [None] * len(frozen['jobs'])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_job, out / f'{i:04d}', job, papers[job['paper_id']], settings[job['model']],
                               transport_factory(settings[job['model']]), build): i
                   for i, job in enumerate(frozen['jobs'])}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            r = results[i]
            print(json.dumps({k: r.get(k) for k in ('paper_id', 'model', 'arm', 'status')}
                             | ({'assurance': r['answer']['assurance_level']} if r['status'] == 'completed' else {})),
                  flush=True)
    write_json(out / 'results.json', results)
    return report(out)


def load_results(run_dir):
    recovered = run_dir / 'results-recovered.json'
    return strict_json((recovered if recovered.exists() else run_dir / 'results.json').read_text())


def recover(run_dir, transport_factory, build=messages):
    """One bounded transport-only pass: failed calls returned no answer, so nothing is resampled."""
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    papers = {p['id']: p for p in frozen['bank']}
    settings = {m: ModelSettings(**s) for m, s in frozen['settings'].items()}
    results = strict_json((run_dir / 'results.json').read_text())
    (run_dir / 'recovery').mkdir(exist_ok=False)
    todo = [i for i, r in enumerate(results) if r['status'] == 'transport_failure']
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_job, run_dir / 'recovery' / f'{i:04d}', frozen['jobs'][i],
                               papers[frozen['jobs'][i]['paper_id']], settings[frozen['jobs'][i]['model']],
                               transport_factory(settings[frozen['jobs'][i]['model']]), build): i for i in todo}
        for future in as_completed(futures):
            results[futures[future]] = future.result() | {'recovered': True}
    write_json(run_dir / 'results-recovered.json', results)
    return {'recovered': todo, 'still_failed': [i for i in todo if results[i]['status'] != 'completed']}


def judge(run_dir):
    from judge import judge_items
    frozen = strict_json((run_dir / 'freeze.json').read_text())
    papers = {p['id']: p for p in frozen['bank']}
    results = load_results(run_dir)
    items = []
    for i, r in enumerate(results):
        if r['status'] != 'completed':
            continue
        p, a = papers[r['paper_id']], r['answer']
        items.append({'key': str(i), 'kind': p['variant'], 'material': p['paper'],
                      'rubric': {'issue': p['rubric']['issue'] if p['variant'] == 'deficient' else p['rubric']['adequate'],
                                 'action': 'Identify the specific evidence problem (or adequacy) and set assurance and '
                                           'conditions accordingly.',
                                 'avoid': 'Generic caution; accepting headline safety statements at face value; '
                                          'demanding further study when the evidence is adequate.'},
                      'answer': json.dumps(a, indent=1)})
    grades = judge_items(items, run_dir / 'judge', seed=frozen['seed'] + 7)
    write_json(run_dir / 'judge.json', grades)
    return report(run_dir)


def report(run_dir):
    results = load_results(run_dir)
    path = run_dir / 'judge.json'
    grades = strict_json(path.read_text()) if path.exists() else {}
    cells, by_paper = {}, {}
    for i, r in enumerate(results):
        variant = 'deficient' if r['paper_id'].endswith('D') else 'adequate'
        cell = cells.setdefault(f"{r['model']}|{r['arm']}", Counter())
        cell[f'{variant}_n'] += 1
        if r['status'] != 'completed':
            cell[r['status']] += 1
            continue
        cell[f'{variant}_assurance_correct'] += r['score']['assurance_correct']
        cell[f'{variant}_decision_error'] += r['score']['decision_error']
        g = grades.get(str(i))
        if g:
            cell[f'{variant}_judge_gap'] += g['gap_identified']
            cell[f'{variant}_judge_error'] += g['error']
        pc = by_paper.setdefault(f"{r['paper_id']}|{r['model']}", Counter())
        pc[r['answer']['assurance_level']] += 1
    table = {'cells': {k: dict(v) for k, v in sorted(cells.items())},
             'assurance_by_paper_model': {k: dict(v) for k, v in sorted(by_paper.items())}}
    (run_dir / 'report.json').write_text(json.dumps(table, indent=2, sort_keys=True))
    return table


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--bank', choices=('iter2', 'iter3'), default='iter2')
    r = sub.add_parser('run')
    r.add_argument('--freeze', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    for name in ('judge', 'report', 'recover'):
        sub.add_parser(name).add_argument('run', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        bank = board_papers.build_bank() if args.bank == 'iter2' else board_papers.build_bank_iter3()
        seed = 202611144 if args.bank == 'iter2' else 202611145
        out = prepare(args.out, bank, MODELS, ARMS, args.repeats, seed, 'iteration-' + args.bank[-1])
    elif args.command == 'run':
        out = run(args.freeze, args.out, live_transport)
    elif args.command == 'recover':
        out = recover(args.run, live_transport)
    elif args.command == 'judge':
        out = judge(args.run)
    else:
        out = report(args.run)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
