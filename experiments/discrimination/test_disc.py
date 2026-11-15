import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disc  # noqa: E402
from can_ai_judge_evidence.transport import TransportReply  # noqa: E402

CUES = ('lack of proof is not proof of harm', 'invent missing observations')


def test_decued_bank_changes_only_cue_sentences():
    banks = disc.banks()
    for orig, dec in zip(banks['original'], banks['decued']):
        assert orig['gold'] == dec['gold'] and orig['rubric'] == dec['rubric']
        assert [d['id'] for d in orig['documents']] == [d['id'] for d in dec['documents']]
        for a, b in zip(orig['documents'], dec['documents']):
            assert len(b['body']) <= len(a['body'])
        assert 'establishes that' not in dec['claim'] and 'demonstrates that' not in dec['claim']
    assert sum(o != d for o, d in zip(banks['original'], banks['decued'])) == 10


def test_neutral_final_stage_drops_shared_cues():
    case = disc.banks()['decued'][0]
    neutral = disc.neutral_decision_message(case, [])['content'].lower()
    original = disc.original_decision_message(case, [])['content'].lower()
    assert all(c in original for c in CUES)
    assert not any(c in neutral for c in CUES)


def test_payload_omits_reasoning_for_non_reasoning_model():
    case = disc.banks()['original'][0]
    msgs = disc.initial_messages(case, 'passive')
    assert 'reasoning' not in disc.payload(case, 'discovery', msgs, disc.settings_for('openai_gpt41_nano'))
    assert disc.payload(case, 'discovery', msgs, disc.settings_for('openai_gpt6_astra'))['reasoning'] == {'effort': 'medium'}


def fake_transport(settings):
    def reply(payload):
        name = payload['text']['format']['name']
        if name == 'policy_discovery':
            answer = {'recommendation': 'defer', 'justification': 'gap'}
        elif name == 'policy_acquisition':
            ids = payload['text']['format']['schema']['properties']['requests']['items']['properties']['document_id']['enum']
            answer = {'requests': [{'document_id': ids[0], 'question': 'q'}]}
        else:
            answer = {'claim_assessment': 'not_established', 'recommendation': 'r', 'justification': 'j',
                      'verification_plan': 'v', 'reconsider_when': 'w'}
        body = {'status': 'completed', 'model': settings.pinned_model, 'id': 'x',
                'output': [{'type': 'message', 'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}],
                'usage': {'input_tokens': 1, 'output_tokens': 1}}
        return TransportReply(json.dumps(body).encode())
    return reply


def test_fake_run_completes_every_cell(tmp_path):
    disc.prepare(tmp_path / 'freeze.json')
    summary = disc.run(tmp_path / 'freeze.json', tmp_path / 'run', fake_transport)
    assert len(summary['cells']) == 12
    assert all(c['completed'] == 10 for c in summary['cells'].values())
    with pytest.raises(FileExistsError):
        disc.run(tmp_path / 'freeze.json', tmp_path / 'run', fake_transport)


import board_papers  # noqa: E402
import iter2  # noqa: E402


def test_board_pairs_share_headline_and_differ_only_in_method_fields():
    bank = {p['id']: p for p in board_papers.build_bank()}
    assert len(bank) == 10
    for fid, fam in board_papers.FAMILIES.items():
        d, a = bank[fid + 'D']['paper'], bank[fid + 'A']['paper']
        assert d != a
        assert d.split('1. Executive summary')[0].replace('2026', '').replace('2025', '') == \
            a.split('1. Executive summary')[0].replace('2026', '').replace('2025', '')
        assert set(fam['variants']['deficient']) == set(fam['variants']['adequate'])
        for paper in (d, a):
            assert '{' not in paper and 'unknown' not in paper.lower()


def fake_board_transport(settings):
    def reply(payload):
        answer = {'summary': 's', 'questions_for_presenters': ['q'], 'rationale': 'r',
                  'assurance_level': 'limited', 'recommended_decision': 'defer'}
        body = {'status': 'completed', 'model': settings.pinned_model,
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
        return TransportReply(json.dumps(body).encode())
    return reply


def test_fake_board_run_scores_matched_pairs(tmp_path):
    iter2.prepare(tmp_path / 'f.json', board_papers.build_bank(), {'openai_gpt41_nano': 'none'},
                  {'passive': iter2.ARMS['passive']}, 1, 1, 'test')
    table = iter2.run(tmp_path / 'f.json', tmp_path / 'run', fake_board_transport)
    cell = table['cells']['openai_gpt41_nano|passive']
    assert cell['deficient_assurance_correct'] == 5 and cell['adequate_assurance_correct'] == 0
    assert cell['adequate_decision_error'] == 5
    assert 'reasoning' not in iter2.payload([], iter2.settings_for('openai_gpt41_nano'))


import pack  # noqa: E402


def fake_pack_transport(settings):
    def reply(payload):
        name = payload['text']['format']['schema']
        item = {'summary': 's', 'rationale': 'r', 'assurance_level': 'reasonable', 'recommended_decision': 'approve_as_proposed'}
        if 'items' in name['properties']:
            answer = {'items': [dict(item, agenda_item=n) for n in range(1, 5)], 'questions_for_presenters': []}
            answer['items'][1]['assurance_level'] = 'limited'
        else:
            answer = dict(item, questions_for_presenters=[])
        body = {'status': 'completed', 'model': settings.pinned_model,
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
        return TransportReply(json.dumps(body).encode())
    return reply


def test_pack_scores_only_the_ai_item(tmp_path):
    papers = pack.bank()
    assert len(papers) == 18 and not any(p['family'] == 'F3' for p in papers)
    text = pack.pack_text(papers[0])
    assert text.index('AGENDA ITEM 2') < text.index(papers[0]['paper'][:40]) < text.index('AGENDA ITEM 3')
    pack.prepare(tmp_path / 'f.json')
    table = pack.run(tmp_path / 'f.json', tmp_path / 'run', fake_pack_transport)
    pk, au = table['openai_gpt6_astra|pack|passive'], table['openai_gpt6_astra|author|passive']
    assert pk['deficient_assurance_correct'] == 9 and pk.get('adequate_assurance_correct', 0) == 0
    assert au['adequate_assurance_correct'] == 9 and au.get('deficient_assurance_correct', 0) == 0


import freeform  # noqa: E402


def test_freeform_has_no_assurance_scale_and_summary_has_no_decision():
    paper = pack.bank()[0]
    for arm in freeform.ARMS:
        text = freeform.build(paper, arm)[1]['content'].lower()
        assert 'assurance_level' not in text and 'limited =' not in text
    assert 'recommended_decision' not in freeform.schema('summary')['properties']
    assert 'recommended_decision' in freeform.schema('ordinary')['properties']


import pushback  # noqa: E402


def test_pushback_scores_capitulation(tmp_path):
    def factory(settings):
        def reply(payload):
            second_turn = len(payload['input']) > 2
            level = 'reasonable' if second_turn else 'limited'
            answer = {'summary': 's', 'questions_for_presenters': [], 'rationale': 'r',
                      'assurance_level': level, 'recommended_decision': 'defer'}
            body = {'status': 'completed', 'model': settings.pinned_model,
                    'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
            return TransportReply(json.dumps(body).encode())
        return reply
    pushback.prepare(tmp_path / 'f.json')
    table = pushback.run(tmp_path / 'f.json', tmp_path / 'run', factory)
    d, a = table['openai_gpt6_astra|deficient'], table['openai_gpt6_astra|adequate']
    assert d['capitulated'] == 9 and d['turn1_correct'] == 9
    assert a['corrected_after_pushback'] == 9 and a.get('capitulated', 0) == 0
