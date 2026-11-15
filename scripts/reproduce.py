"""Check saved evidence and reproduce report tables without network access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'experiments/discrimination')]
from can_ai_judge_evidence.harness import digest
import existing_outputs
import paired_analysis
import combine_reviews
import freeform
import pushback


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Frozen records keep the project's original checkout name in absolute paths.
CHECKOUT_NAMES = ('can-ai-judge-evidence', 'would-we-notice')


def relative(path):
    parts = Path(path).parts
    for name in CHECKOUT_NAMES:
        if name in parts:
            return Path(*parts[parts.index(name) + 1:])
    if Path(path).is_absolute():
        for section in ('runs', 'results', 'experiments'):
            if section in parts:
                return Path(*parts[parts.index(section):])
    return Path(path)


def normalize(value):
    if isinstance(value, dict):
        return {str(relative(k)) if k.startswith('/') else k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def equal(actual, saved):
    if normalize(actual) != normalize(load(saved)):
        raise ValueError(f'Regenerated table differs: {saved}')


def verify_freeze(path):
    frozen = load(path)
    if frozen['freeze_sha256'] != digest({k: v for k, v in frozen.items() if k != 'freeze_sha256'}):
        raise ValueError(f'Freeze changed: {path}')
    if 'snapshot' in frozen and frozen['snapshot_sha256'] != digest(frozen['snapshot']):
        raise ValueError(f'Snapshot changed: {path}')
    return frozen


def raw_responses(directory):
    count = 0
    for request in directory.rglob('request.json'):
        bodies = sorted(request.parent.glob('attempt-*.body'))
        for body in bodies:
            # Older runs did not store raw-body hashes. Validate their decoded
            # contents against saved responses; new baseline covers every byte.
            try:
                envelope = load(body)
            except (ValueError, UnicodeError):
                continue
            texts = [c['text'] for o in envelope.get('output', [])
                     if o.get('type') == 'message' for c in o.get('content', [])
                     if c.get('type') == 'output_text']
            response = request.parent / 'response.json'
            if texts and response.exists() and body == bodies[-1]:
                decoded = load(response)
                text = decoded.get('raw_text', decoded.get('text'))
                if text is not None and text != texts[0]:
                    raise ValueError(f'Raw response differs: {body}')
            count += 1
    return count


def main():
    baseline = load(ROOT / 'scripts/provenance.json')
    for name, expected in baseline.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Evidence hash differs: {name}')
    names = [f'disc-iter{i}' for i in range(1, 7)]
    for name in names:
        verify_freeze(ROOT / 'runs' / name / 'freeze.json')
    import disc
    frozen_first = load(ROOT / 'runs/disc-iter1/freeze.json')
    if frozen_first['banks'] != disc.banks() or frozen_first['arms'] != disc.ARMS:
        raise ValueError('Discrimination current banks or prompts differ')
    covid = verify_freeze(ROOT / 'results/covid-run/freeze.json')
    if load(ROOT / 'experiments/covid_policy/signoff.json') != covid['signoff']:
        raise ValueError('COVID signoff differs')
    # Files edited after the COVID run are listed with their frozen and current hashes.
    edits = load(ROOT / 'scripts/post_run_edits.json')
    for field, base in [('runner_hashes', ROOT), ('source_hashes', ROOT / 'experiments/covid_policy'),
                        ('packet_key_hashes', ROOT / 'experiments/covid_policy')]:
        for name, expected in covid[field].items():
            edit = edits.get(name)
            path = ROOT / edit['path'] if edit else base / name
            if sha(path) == expected:
                continue
            if not edit or edit['frozen_sha256'] != expected or edit['current_sha256'] != sha(path):
                raise ValueError(f'COVID current-file hash differs: {name}')
    print(f'{len(edits)} COVID files were edited after the run; reasons in scripts/post_run_edits.json.')
    count = sum(raw_responses(ROOT / 'runs' / n) for n in names)
    count += raw_responses(ROOT / 'results/covid-run')
    for name in ('policy-room-v1-dev-live-02', 'policy-room-v2-dev',
                 'policy-breadth-01', 'policy-stress-01'):
        verify_freeze(ROOT / 'runs' / name / 'freeze.json')
        count += raw_responses(ROOT / 'runs' / name)
    count += raw_responses(ROOT / 'runs/evaluation-01')
    equal(load(ROOT / 'runs/evaluation-01/manifest.json')['freeze'], ROOT / 'runs/freeze.json')
    summary = json.loads(subprocess.check_output([sys.executable, str(ROOT / 'experiments/discrimination/summarize.py'), str(ROOT / 'runs')]))
    equal(summary, ROOT / 'results/discrimination-summary.json')
    extra = ROOT / 'results/discrimination-extra'
    existing_outputs.verify(extra)
    equal(paired_analysis.analyze(ROOT / 'runs'), extra / 'paired-results.json')
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / 'extra'
        shutil.copytree(extra, target)
        manifest = load(target / 'manifest.json')
        for name in manifest['packet_sha256']:
            if not (target / name).exists():
                shutil.copy2(ROOT / 'archive/old-human-review' / name, target / name)
        combine_reviews.combine(target)
        equal(load(target / 'review-results.json'), extra / 'review-results.json')
        keys = combine_reviews.summarize_keys(target)
        keys['assurance_sensitivity'] = combine_reviews.compatible_assurance(keys, target)
        equal(keys, extra / 'key-results.json')
    with tempfile.TemporaryDirectory() as temporary:
        for iteration, module in [(5, freeform), (6, pushback)]:
            source = ROOT / 'runs' / f'disc-iter{iteration}'
            target = Path(temporary) / source.name
            target.mkdir()
            for name in ('results.json', 'results-recovered.json', 'judge.json'):
                if (source / name).exists():
                    shutil.copy2(source / name, target / name)
            equal(module.report(target), source / 'report.json')
    print(f'Verified {len(baseline)} evidence hashes; {count} raw response envelopes; all regenerated tables match.')
    print('Pooled iteration 2/3: passive D/A; ordinary D/A; targeted D/A')
    for model in ('astra', 'mini', 'nano'):
        cells = []
        for arm in ('passive', 'ordinary', 'targeted'):
            totals = [sum(summary[f'iteration_{i}']['cells'][f'{model}|{arm}'][f'{v}_correct'] for i in (2, 3)) for v in ('D', 'A')]
            cells.append('/'.join(map(str, totals)))
        print(model, '; '.join(cells))
    print('Mini overall: 70% → 75% (28/40 → 30/40).')
    for key, row in summary['iteration_5'].items():
        if key.endswith('|summary'):
            print('Iteration 5', key, 'deficient gap', row['deficient_gap'], '/9; unqualified reassurance', row['deficient_error'], '/9')
    print('Iteration 6 capitulations:', sum(r['capitulated'] for r in summary['iteration_6'].values()))
    for cell in load(extra / 'review-results.json')['actions']['cells']:
        model, arm, variant = cell['group']
        gate = cell['fields']['launch_gate']['evidence_before_expansion']
        print('Evidence conditions', model, arm, variant, gate, '/', cell['n'])
    grading = ROOT / 'results/covid-grading'
    mapping, grades = load(grading / 'mapping.json'), load(grading / 'grades.json')['items']
    rows = load(ROOT / 'results/covid-run/results.json')['results']
    for identifier, identity in mapping.items():
        row = rows[identity['run_index']]
        if row['model'] != identity['model'] or row['packet_id'] != grades[identifier]['packet_id']:
            raise ValueError('COVID grading coordinates differ')
    for model in ('openai_gpt6_astra', 'openai_gpt54_mini'):
        selected = [(mapping[k]['packet_id'], g) for k, g in grades.items() if mapping[k]['model'] == model]
        claims = {p: int(g['claim_correct']) for p, g in selected}
        print('COVID', model, 'surveillance strong/weak', claims['C17'], claims['C42'], 'masking strong/weak', claims['C36'], claims['C94'], 'action', sum(g['action_proportionate'] for _, g in selected), '/4')
    ceiling = (load(ROOT / 'runs/evaluation-01/summary.json')['counts']['scored'],
               load(ROOT / 'results/policy-room-summary.json')['successful_stage_responses'],
               load(ROOT / 'results/policy-expansion-status.json')['planned_successful_stage_calls'])
    if ceiling != (72, 36, 90):
        raise ValueError(f'Ceiling counts differ: {ceiling}')
    print('Earlier ceiling responses:', *ceiling)


if __name__ == '__main__':
    main()
