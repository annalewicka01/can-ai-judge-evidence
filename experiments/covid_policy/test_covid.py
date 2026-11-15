from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest

from can_ai_judge_evidence.harness import strict_json, write_json
from can_ai_judge_evidence.transport import TransportError, TransportReply

spec = importlib.util.spec_from_file_location('covid_runner', Path(__file__).with_name('covid.py'))
covid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(covid)


@pytest.fixture
def bank(tmp_path):
    base = tmp_path / 'bank'
    (base / 'packets').mkdir(parents=True)
    (base / 'keys').mkdir()
    for p in covid.PACKET_IDS:
        (base / 'packets' / f'{p}.md').write_text('Synthetic packet ' + p)
        (base / 'keys' / f'{p}.md').write_text('Draft key ' + p)
    return base


def approve(base):
    (base / 'signoff.json').unlink(missing_ok=True)  # signoff never overwrites
    return covid.signoff('Reviewer A', base=base, today=date(2026, 11, 14))


def freeze(bank, tmp_path):
    approve(bank)
    path = tmp_path / 'freeze.json'
    covid.prepare(path, base=bank)
    return path


def reply(model, text='A free-text review.'):
    return TransportReply(json.dumps({'status': 'completed', 'model': model,
                                     'output': [{'type': 'message', 'role': 'assistant',
                                                 'content': [{'type': 'output_text', 'text': text}]}]}).encode())


def test_instruction_verbatim():
    protocol = Path(__file__).with_name('PROTOCOL.md').read_text()
    block = protocol.split('## Reviewer task')[1].split('## ')[0]
    assert covid.REVIEW_INSTRUCTION == ' '.join(line[2:] for line in block.splitlines() if line.startswith('> '))


def test_prepare_gates(bank, tmp_path):
    with pytest.raises(ValueError, match='signoff'):
        covid.prepare(tmp_path / 'no.json', base=bank)
    approve(bank)
    (bank / 'packets/C17.md').write_text('Changed')
    with pytest.raises(ValueError, match='stale'):
        covid.prepare(tmp_path / 'stale.json', base=bank)
    approve(bank)
    (bank / 'keys/C17.md').write_text('Changed key')
    with pytest.raises(ValueError, match='stale'):
        covid.prepare(tmp_path / 'stale-key.json', base=bank)
    approve(bank)
    (bank / 'packets/C17.md').unlink()
    with pytest.raises(ValueError, match='missing'):
        covid.prepare(tmp_path / 'missing.json', base=bank)


@pytest.mark.parametrize('field,value', [('reviewer', ' '), ('date', 'invalid')])
def test_signoff_metadata(bank, tmp_path, field, value):
    record = approve(bank)
    record[field] = value
    (bank / 'signoff.json').write_text(json.dumps(record))
    with pytest.raises(ValueError):
        covid.prepare(tmp_path / 'bad.json', base=bank)


def test_prepare_jobs(bank, tmp_path):
    approve(bank)
    first = covid.prepare(tmp_path / 'first.json', base=bank)
    second = covid.prepare(tmp_path / 'second.json', base=bank)
    assert len(first['jobs']) == 8
    assert first['jobs'] == second['jobs']
    assert len({(j['packet_id'], j['model']) for j in first['jobs']}) == 8
    for model, settings in first['settings'].items():
        assert settings['reasoning_effort'] == 'medium'
        assert (settings['max_output_tokens'], settings['timeout_seconds'], settings['max_attempts']) == (8000, 240, 3)
    assert first['messages']['C17'] == [{'role': 'user', 'content': covid.REVIEW_INSTRUCTION + '\n\nSynthetic packet C17'}]
    assert first['packet_key_hashes'] and first['runner_hashes'] and first['runtime']


def test_run_content_failure_no_retry(bank, tmp_path):
    path = freeze(bank, tmp_path)
    calls = []
    def factory(settings):
        def transport(request):
            calls.append(request)
            return reply(settings.model, '')
        return transport
    out = tmp_path / 'run'
    summary = covid.run(path, out, factory, base=bank)
    assert summary == {'planned': 8, 'completed': 0, 'missing': 0, 'invalid': 8}
    assert len(calls) == 8
    assert len(list(out.glob('*/attempt-01.body'))) == 8
    assert len(list(out.glob('*/request.json'))) == 8
    assert not list(out.glob('*/attempt-02.body'))
    with pytest.raises(FileExistsError):
        covid.run(path, out, factory, base=bank)


def test_transport_retries_and_raw_failure(tmp_path):
    calls, waits = [], []
    def factory(settings):
        def transport(request):
            calls.append(request)
            raise TransportError('busy', retryable=True, reply=TransportReply(b'raw error', 503))
        return transport
    result = covid.run_job(tmp_path / 'job', {'packet_id': 'C17', 'model': 'openai_gpt6_astra'},
                           [], covid.settings_for('openai_gpt6_astra'), factory, sleep=waits.append)
    assert result['status'] == 'transport_failure'
    assert len(calls) == 3 and waits == [1, 2]
    assert (tmp_path / 'job/attempt-03.body').read_bytes() == b'raw error'


def test_run_missing(bank, tmp_path):
    path = freeze(bank, tmp_path)
    def factory(settings):
        def transport(request):
            raise TransportError('denied', retryable=False)
        return transport
    summary = covid.run(path, tmp_path / 'run', factory, base=bank)
    assert summary['missing'] == 8 and summary['invalid'] == 0


def test_run_integrity(bank, tmp_path):
    path = freeze(bank, tmp_path)
    frozen = strict_json(path.read_text())
    frozen['seed'] += 1
    altered = tmp_path / 'altered.json'
    write_json(altered, frozen)
    def forbidden(settings):
        pytest.fail('transport must not be constructed')
    with pytest.raises(ValueError, match='integrity'):
        covid.run(altered, tmp_path / 'bad-run', forbidden, base=bank)
    (bank / 'packets/C17.md').write_text('Changed')
    with pytest.raises(ValueError):
        covid.run(path, tmp_path / 'bad-run', forbidden, base=bank)
    assert not (tmp_path / 'bad-run').exists()


def test_mask_roundtrip(bank, tmp_path):
    path = freeze(bank, tmp_path)
    out = tmp_path / 'run'
    covid.run(path, out, lambda settings: lambda request: reply(settings.model, 'Review ' + request['input'][0]['content'][-3:]), base=bank)
    masked = tmp_path / 'masked'
    covid.mask(out, masked)
    items = strict_json((masked / 'grading-items.json').read_text())
    mapping = strict_json((masked / 'mapping.json').read_text())
    results = strict_json((out / 'results.json').read_text())['results']
    assert len(items) == len(mapping) == 8
    encoded = json.dumps(items)
    for identity in (*covid.MODELS, 'reasoning_effort', 'run_index'):
        assert identity not in encoded
    for item in items:
        identity = mapping[item['id']]
        assert item['packet_id'] == identity['packet_id']
        assert item['text'] == results[identity['run_index']]['text']
