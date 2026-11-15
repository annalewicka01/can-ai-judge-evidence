import csv
import json
from pathlib import Path
import re

from review.llm_review import review_pair
from review.score import score, score_answer
from can_ai_judge_evidence.transport import TransportReply


def test_mapping(tmp_path):
    (tmp_path / 'responses').mkdir()
    (tmp_path / 'answer_key.json').write_text(json.dumps({'pairs': {'p': {'X': 'A', 'Y': 'D'}, 'q': {'X': 'D', 'Y': 'A'}}}))
    with (tmp_path / 'responses' / 'someone.csv').open('w') as f:
        w = csv.writer(f)
        w.writerow(['pair', 'version_x', 'version_y', 'comment'])
        w.writerow(['p', 'yes', 'no', ''])
        w.writerow(['q', 'yes', 'unsure', ''])
    totals = score(tmp_path)
    assert totals['someone'] == {'agree': 2, 'disagree': 1, 'unsure': 1}
    assert score_answer('', 'D') == 'blank'


def test_papers_blinded():
    paths = list((Path(__file__).parent / 'papers').glob('*.md'))
    assert len(paths) == 11
    for path in paths:
        text = path.read_text()
        assert not re.search(r'\b(deficient|adequate)\b|\b[DA]/[DA]\b|Version [DA]\b|(?:variant|label|key)\s*[:=]\s*[DA]\b', text, re.I)
        assert '## Version X' in text and '## Version Y' in text


def test_fake_transport(tmp_path):
    paper = tmp_path / 'p.md'
    paper.write_text('Shared paper\nVersion X\nVersion Y')
    calls = []

    def fake(request):
        calls.append(request)
        answer = {'version_x': 'no', 'version_y': 'yes', 'comment': ''}
        body = {'model': 'fake-opus', 'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
        return TransportReply(json.dumps(body).encode())

    row = review_pair(paper, 'Human questions', fake, tmp_path / 'raw')
    assert row['version_x'] == 'no'
    assert calls[0]['input'][0]['content'] == paper.read_text() + '\n\nHuman questions'
    assert len(calls) == 1
    assert json.loads((tmp_path / 'raw/p.response.json').read_text())['model'] == 'fake-opus'
