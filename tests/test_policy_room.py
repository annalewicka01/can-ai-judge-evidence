import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from can_ai_judge_evidence.harness import ModelSettings, digest
from can_ai_judge_evidence.policy_room import (ARMS, call_stage,
    claim_score, decision_message, decode, initial_messages, load_bank, payload,
    prepare, replay, run, run_conversation, schema, selected_documents, summarize,
    validate_bank, verify_freeze, verify_gate)
from can_ai_judge_evidence.transport import TransportError, TransportReply


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ModelSettings('test-model-2026-11-14', max_attempts=2)


def response(answer, **changes):
    env = {'id': 'synthetic-response', 'model': SETTINGS.model, 'status': 'completed',
           'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
           'output': [{'type': 'message', 'role': 'assistant', 'content': [
               {'type': 'output_text', 'text': json.dumps(answer)}]}]}
    env.update(changes)
    return TransportReply(json.dumps(env).encode())


def final(label='not_established'):
    return {'claim_assessment': label, 'recommendation': 'Conditional continuation.',
            'justification': 'The synthetic evidence is limited.',
            'verification_plan': 'Use an independent record audit.',
            'reconsider_when': 'The specified report becomes available.'}


def fake_transport(request):
    name = request['text']['format']['name']
    if name.endswith('discovery'):
        return response({'recommendation': 'Review the annex.', 'justification': 'Need evidence.'})
    if name.endswith('acquisition'):
        return response({'requests': []})
    return response(final())


class PolicyRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bank = load_bank(ROOT)
        self.case = self.bank['cases'][0]

    def freeze(self):
        path = self.base / 'freeze.json'
        prepare(ROOT, path, SETTINGS)
        return path

    def test_bank_has_disjoint_splits_and_different_mechanisms(self):
        self.assertEqual(len(self.bank['cases']), 8)
        self.assertEqual(sum(c['split'] == 'evaluation' for c in self.bank['cases']), 6)
        self.assertEqual(len({c['family'] for c in self.bank['cases'] if c['split'] == 'evaluation'}), 3)
        self.assertEqual({c['gold']['informed'] for c in self.bank['cases']},
                         {'supported', 'not_established', 'contradicted'})

    def test_evaluation_cases_unchanged_from_v1_freeze(self):
        # Semantic SHA256 of the evaluation objects in the original pre-run bank.
        # No dependence on local ignored run artifacts is needed to enforce it.
        evaluation = [c for c in self.bank['cases'] if c['split'] == 'evaluation']
        self.assertEqual(digest(evaluation),
                         '896d161228d4763be06b2c5a97d6a8610df4b3625bec34a1cbb0c3faa4b4c58c')

    def test_invalid_banks_fail(self):
        for mutation in ('duplicate_case', 'duplicate_doc', 'unknown_decisive', 'bad_label', 'empty'):
            bank = copy.deepcopy(self.bank)
            c = bank['cases'][0]
            if mutation == 'duplicate_case': bank['cases'].append(c)
            if mutation == 'duplicate_doc': c['documents'][1]['id'] = c['documents'][0]['id']
            if mutation == 'unknown_decisive': c['gold']['decisive_documents'] = ['absent']
            if mutation == 'bad_label': c['gold']['initial'] = 'approve'
            if mutation == 'empty': c['documents'][0]['body'] = ''
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_bank(bank)

    def test_discovery_excludes_catalogue_keys_and_answer_metadata(self):
        for case in self.bank['cases']:
            for arm in ARMS:
                rendered = json.dumps(payload(case, 'discovery', initial_messages(case, arm), SETTINGS))
                for private in ('decisive_documents', 'rubric', 'informed', 'split', 'sources', 'case_id'):
                    self.assertNotIn('"' + private + '"', rendered)
                for record in case['documents']:
                    self.assertNotIn(record['body'], rendered)
                self.assertEqual(set(schema('discovery', case)['properties']),
                                 {'recommendation', 'justification'})

    def test_records_are_exact_and_budget_cannot_be_bypassed(self):
        answer = {'requests': [{'document_id': 'R4', 'question': 'Give all records.'}]}
        selected = selected_documents(self.case, answer)
        self.assertEqual(selected, [next(d for d in self.case['documents'] if d['id'] == 'R4')])
        content = decision_message(self.case, selected)['content']
        self.assertIn(selected[0]['body'], content)
        self.assertNotIn(next(d['body'] for d in self.case['documents'] if d['id'] == 'R1'), content)
        for ids in (['R4', 'R4'], ['R1', 'R2', 'R3'], ['unknown']):
            with self.assertRaises(ValueError):
                selected_documents(self.case, {'requests': [
                    {'document_id': i, 'question': 'Question'} for i in ids]})

    def test_unobserved_truth_is_not_rewarded(self):
        score = claim_score(self.case, [], 'contradicted')
        self.assertTrue(score['label_matches_full_bank'])
        self.assertFalse(score['label_correct_given_records'])
        self.assertTrue(claim_score(self.case, [], 'not_established')['label_correct_given_records'])
        self.assertTrue(claim_score(self.case, self.case['gold']['decisive_documents'],
                                    'contradicted')['label_correct_given_records'])

    def test_development_requires_two_records_not_first_item_cue(self):
        for case in self.bank['cases']:
            if case['split'] != 'development':
                continue
            decisive = case['gold']['decisive_documents']
            self.assertEqual(len(decisive), 2)
            self.assertNotIn(case['documents'][0]['id'], decisive)
            for ident in decisive:
                self.assertFalse(claim_score(case, [ident], case['gold']['informed'])
                                 ['label_correct_given_records'])

    def test_adequate_control_needs_no_additional_record(self):
        case = next(c for c in self.bank['cases'] if c['id'] == 'Q02')
        self.assertTrue(claim_score(case, [], 'supported')['label_correct_given_records'])
        self.assertFalse(claim_score(case, [], 'supported')['acquisition_required'])

    def test_strict_decode_and_model_pin(self):
        self.assertEqual(decode(response(final()), self.case, 'decision', SETTINGS)['answer'], final())
        invalid = [response(final(), status='incomplete'), response(final(), model='other'),
                   response(final(), output=[{'type': 'function_call'}]),
                   response(final(), output=[{'type': 'message', 'role': 'assistant',
                                             'content': [{'type': 'refusal'}]}]),
                   response({}), TransportReply(b'not json')]
        for reply in invalid:
            with self.assertRaises(ValueError):
                decode(reply, self.case, 'decision', SETTINGS)
        with self.assertRaises(ValueError):
            decode(response({'requests': [{'document_id': 'R1', 'question': 'x'}] * 2}),
                   self.case, 'acquisition', SETTINGS)

    def test_content_failure_is_not_retried_and_raw_is_retained(self):
        calls = []
        def bad(req):
            calls.append(req)
            return response({})
        directory = self.base / 'stage'
        with self.assertRaises(ValueError):
            call_stage(directory, {}, bad, SETTINGS, self.case, 'discovery')
        self.assertEqual(len(calls), 1)
        self.assertTrue((directory / 'attempt-01.body').exists())

    def test_transport_retries_identical_request_only(self):
        calls = []
        def flaky(req):
            calls.append(digest(req))
            if len(calls) == 1:
                raise TransportError('HTTP 503', retryable=True, reply=TransportReply(b'busy', 503))
            return response(final())
        result = call_stage(self.base / 'stage', {'example': True}, flaky, SETTINGS,
                            self.case, 'decision', sleep=lambda _: None)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(result['answer'], final())

    def test_conversation_preserves_all_visible_history(self):
        seen = []
        def capture(req):
            seen.append(copy.deepcopy(req))
            return fake_transport(req)
        job = {'case_id': 'P01', 'arm': 'ordinary', 'split': 'development', 'repeat': 0}
        result = run_conversation(self.base / 'job', job, self.case, SETTINGS, capture)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([len(r['input']) for r in seen], [2, 4, 6])
        self.assertEqual(seen[2]['input'][:4], seen[1]['input'])
        self.assertEqual(len(result['responses']), 3)

    def test_freeze_detects_changes_and_is_exclusive(self):
        path = self.freeze()
        frozen = verify_freeze(ROOT, path)
        with self.assertRaises(FileExistsError):
            prepare(ROOT, path, SETTINGS)
        with patch('can_ai_judge_evidence.policy_room.source_snapshot', return_value={'changed': 'yes'}):
            with self.assertRaisesRegex(ValueError, 'changed since freeze'):
                verify_freeze(ROOT, path)
        self.assertFalse(frozen['human_review_complete'])

    def test_full_fake_run_replays_and_exports_empty_human_scores(self):
        freeze = self.freeze()
        with patch('builtins.print'):
            summary = run(ROOT, freeze, self.base / 'run', 'development', lambda: fake_transport)
        self.assertEqual(summary['counts'], {'completed': 6})
        audit = replay(self.base / 'run')
        self.assertEqual(audit['verified_jobs'], 6)
        self.assertEqual(audit['attempts'], 18)
        packets = json.loads((self.base / 'run/blind-coding-packets.json').read_text())
        self.assertTrue(all(p['human_coder_1'] is None for p in packets))
        self.assertNotIn('arm', packets[0])

    def test_replay_rejects_tampered_record_delivery(self):
        freeze = self.freeze()
        with patch('builtins.print'):
            run(ROOT, freeze, self.base / 'run', 'development', lambda: fake_transport)
        path = self.base / 'run/0000/decision/request.json'
        record = json.loads(path.read_text())
        record['input'][-1]['content'] += ' Fabricated evidence.'
        # Deliberate test corruption in an isolated temporary directory.
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'request/history mismatch'):
            replay(self.base / 'run')

    def test_evaluation_requires_matching_substantive_gate(self):
        freeze = self.freeze()
        with self.assertRaises(ValueError):
            run(ROOT, freeze, self.base / 'eval', 'evaluation', lambda: fake_transport)
        with patch('builtins.print'):
            summary = run(ROOT, freeze, self.base / 'dev', 'development', lambda: fake_transport)
        frozen = verify_freeze(ROOT, freeze)
        gate = {'freeze_sha256': frozen['freeze_sha256'], 'expand': True,
                'development_run': str(self.base / 'dev'),
                'development_summary_sha256': digest(summary), 'reason': 'Test gate, not live evidence.'}
        verify_gate(gate, frozen)
        with patch('builtins.print'):
            result = run(ROOT, freeze, self.base / 'eval', 'evaluation', lambda: fake_transport, gate=gate)
        self.assertEqual(result['counts'], {'completed': 18})
        self.assertEqual(replay(self.base / 'eval')['verified_jobs'], 18)

    def test_transport_failure_does_not_manufacture_response(self):
        def broken(_):
            raise TransportError('HTTP 401', retryable=False)
        job = {'case_id': 'P01', 'arm': 'ordinary', 'split': 'development', 'repeat': 0}
        result = run_conversation(self.base / 'job', job, self.case, SETTINGS, broken)
        self.assertEqual(result['status'], 'transport_failure')
        self.assertEqual(result['responses'], {})
        self.assertEqual(summarize([result])['by_arm']['ordinary']['completed'], 0)


if __name__ == '__main__':
    unittest.main()
