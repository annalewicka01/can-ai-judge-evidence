from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from can_ai_judge_evidence.cases import case_pairs
from can_ai_judge_evidence.cli import export_cases
from can_ai_judge_evidence.freeze import create_freeze, review_template, verify_freeze
from can_ai_judge_evidence.harness import (ModelSettings, code_identity, decode_and_score, digest,
                                     request_payload, run_jobs, strict_json, write_json)
from can_ai_judge_evidence.transport import OpenAIResponsesTransport, TransportError, TransportReply


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ModelSettings('test-model-2026-11-13')


def answer(change=None):
    return {'existing_plan_meets_standard': 'no' if change else 'yes',
            'required_change': change, 'required_change_meets_standard': 'yes' if change else None,
            'rationale': 'Synthetic test response.', 'optional_suggestions': ''}


def envelope(text=None, **updates):
    body = {'id': 'test-response', 'model': SETTINGS.model, 'status': 'completed',
            'usage': {'input_tokens': 10, 'output_tokens': 10},
            'output': [{'type': 'message', 'role': 'assistant', 'content': [
                {'type': 'output_text', 'text': text if text is not None else json.dumps(answer())}]}]}
    body.update(updates)
    return TransportReply(json.dumps(body).encode(), request_id='test-request')


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.case = case_pairs()[0]
        self.config = self.case.config('blind')

    def test_valid_content_is_scored_and_raw_text_retained(self):
        data = answer(asdict(self.case.reference_repair))
        score, metadata = decode_and_score(self.config, envelope(json.dumps(data)))
        self.assertTrue(score.format_valid)
        self.assertTrue(score.effective_plan.valid)
        self.assertEqual(metadata['decoded'], data)
        self.assertEqual(metadata['raw_text'], json.dumps(data))

    def test_strict_json_rejects_duplicate_nonfinite_and_trailing_content(self):
        for raw in ('{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', 'NaN',
                    'Infinity', '-Infinity', '1e999', '{} {}', '```json\n{}\n```'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)
            score, _ = decode_and_score(self.config, envelope(raw))
            self.assertFalse(score.format_valid)

    def test_refusals_incomplete_empty_and_tool_outputs_are_format_failures(self):
        bad_outputs = ([], [{'type': 'function_call'}],
                       [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'refusal'}]}],
                       [{'type': 'message', 'role': 'user', 'content': []}],
                       [{'type': 'message', 'role': 'assistant', 'content': 'bad'}])
        replies = [envelope(output=o) for o in bad_outputs]
        replies += [envelope(status='incomplete'), envelope(model=None),
                    TransportReply(b'not json'), TransportReply(b'\xff'), TransportReply(b'null')]
        for reply in replies:
            score, _ = decode_and_score(self.config, reply)
            self.assertFalse(score.format_valid)

    def test_native_integer_and_cross_field_contract_remain_strict(self):
        for change, claim in (({**asdict(self.case.reference_repair), 'n': 800.0}, 'yes'),
                              (None, 'yes'), ({**asdict(self.case.reference_repair), 'n': True}, 'yes')):
            data = {**answer(change), 'required_change_meets_standard': claim}
            score, _ = decode_and_score(self.config, envelope(json.dumps(data)))
            self.assertFalse(score.format_valid)

    def test_valid_json_failure_does_not_become_an_effective_repair(self):
        score, _ = decode_and_score(self.config, envelope('{}'))
        self.assertFalse(score.format_valid)
        self.assertIsNone(score.effective_plan)
        self.assertIsNone(score.missing_required_change)

    def test_reasoning_item_is_not_treated_as_final_text(self):
        raw = json.loads(envelope().body)
        raw['output'].insert(0, {'type': 'reasoning', 'summary': []})
        score, _ = decode_and_score(self.config, TransportReply(json.dumps(raw).encode()))
        self.assertTrue(score.format_valid)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_case(self, transport, **options):
        args = dict(root=ROOT, out=self.base / 'run', settings=SETTINGS, transport=transport,
                    mode='smoke', sleep=lambda _: None)
        args.update(options)
        return run_jobs(**args)

    def test_request_is_strict_tool_free_and_has_no_hidden_metadata(self):
        payload = request_payload(case_pairs()[0], 'blind', 'ordinary', SETTINGS)
        self.assertTrue(payload['text']['format']['strict'])
        self.assertEqual(payload['tools'], [])
        self.assertEqual(payload['tool_choice'], 'none')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['model'], SETTINGS.model)
        self.assertNotIn('case_id', json.dumps(payload))
        self.assertNotIn('reference_repair', json.dumps(payload))

    def test_retry_only_transport_errors_and_identical_payload(self):
        requests = []
        def transport(payload):
            requests.append(digest(payload))
            if len(requests) == 1:
                raise TransportError('HTTP 503', retryable=True, reply=TransportReply(b'busy', 503))
            return envelope()
        result = self.run_case(transport)
        self.assertTrue(result['pipeline_pass'])
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(set(requests)), 1)
        self.assertEqual((self.base / 'run/0000/attempt-01.body').read_bytes(), b'busy')
        self.assertTrue((self.base / 'run/0000/attempt-02.body').exists())

    def test_content_error_is_scored_once_and_retained_exactly(self):
        replies = []
        raw = envelope('not JSON')
        def transport(payload):
            replies.append(payload)
            return raw
        result = self.run_case(transport)
        self.assertEqual(len(replies), 1)
        self.assertEqual(result['format_failures'], 1)
        self.assertFalse(result['pipeline_pass'])
        self.assertEqual(result['by_arm']['ordinary']['responses'], 1)
        self.assertEqual((self.base / 'run/0000/attempt-01.body').read_bytes(), raw.body)

    def test_nonretryable_http_aborts_without_inventing_model_response(self):
        calls = []
        def transport(payload):
            calls.append(payload)
            raise TransportError('HTTP 400', retryable=False, reply=TransportReply(b'schema rejected', 400))
        result = self.run_case(transport, mode='pilot')
        self.assertEqual(len(calls), 1)
        self.assertTrue(result['aborted'])
        self.assertEqual(result['counts'], {'transport_failure': 1})
        self.assertEqual(result['by_arm'], {})
        self.assertFalse(result['pipeline_pass'])

    def test_transport_attempts_bounded(self):
        calls = []
        def transport(payload):
            calls.append(payload)
            raise TransportError('timeout', retryable=True)
        result = self.run_case(transport)
        self.assertEqual(len(calls), SETTINGS.max_attempts)
        self.assertTrue(result['aborted'])

    def test_pilot_has_six_independent_cells_and_per_case_reports(self):
        result = self.run_case(lambda _: envelope(), mode='pilot')
        self.assertEqual(result['planned'], 6)
        self.assertEqual(result['counts'], {'scored': 6})
        self.assertEqual(set(result['by_case_variant']), {'D01/blind', 'D01/adequate'})
        manifest = strict_json((self.base / 'run/manifest.json').read_text())
        self.assertEqual({j['case_id'] for j in manifest['jobs']}, {'D01'})
        self.assertEqual(manifest['settings'], asdict(SETTINGS))
        self.assertEqual(manifest['identity']['source_sha256'], code_identity(ROOT)['source_sha256'])

    def test_dry_run_no_calls_and_never_passes_live_gate(self):
        def forbidden(_):
            self.fail('dry run called transport')
        first = self.run_case(forbidden, mode='evaluation', dry_run=True, repeats=2)
        self.assertEqual(first['planned'], 48)
        self.assertFalse(first['pipeline_pass'])
        self.assertEqual(first['by_arm'], {})
        self.run_case(forbidden, out=self.base / 'run2', mode='evaluation', dry_run=True, repeats=2)
        a = strict_json((self.base / 'run/manifest.json').read_text())['jobs']
        b = strict_json((self.base / 'run2/manifest.json').read_text())['jobs']
        self.assertEqual(a, b)
        self.assertEqual({j['case_id'] for j in a}, {'E01', 'E02', 'E03', 'E04'})

    def test_live_evaluation_requires_freeze(self):
        with self.assertRaisesRegex(ValueError, 'freeze'):
            self.run_case(lambda _: envelope(), mode='evaluation')

    def test_direct_api_cannot_bypass_freeze_with_empty_record(self):
        with self.assertRaisesRegex(ValueError, 'differ'):
            self.run_case(lambda _: envelope(), mode='evaluation', freeze_record={})

    def test_output_directory_cannot_be_overwritten(self):
        self.run_case(None, dry_run=True)
        with self.assertRaises(FileExistsError):
            self.run_case(None, dry_run=True)

    def test_bad_settings_rejected(self):
        for kwargs in ({'model': ''}, {'max_attempts': 99}, {'max_output_tokens': True},
                       {'reasoning_effort': 'guess'}, {'timeout_seconds': 0}):
            with self.assertRaises(ValueError):
                ModelSettings(**{**asdict(SETTINGS), **kwargs})

    def test_review_export_contains_no_live_evidence(self):
        out = self.base / 'export'
        summary = export_cases(ROOT, out)
        self.assertEqual(summary['variants'], 10)
        self.assertEqual(len(list(out.glob('*-open-messages.json'))), 30)
        self.assertEqual(len(list(out.glob('*-messages.json'))), 60)
        template = strict_json((out / 'human-review-template.json').read_text())
        self.assertFalse(template['human_approved'])
        self.assertIsNone(template['reviewer_name'])


class TransportTests(unittest.TestCase):
    def test_missing_key_fails_without_network(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
            OpenAIResponsesTransport()

    def test_http_classification_and_no_hidden_retry(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-secret'}):
            for code, retry in ((400, False), (401, False), (403, False), (408, True),
                                (429, True), (500, True), (503, True)):
                client = OpenAIResponsesTransport()
                error = HTTPError('https://api.openai.com/v1/responses', code, 'test', {}, None)
                with patch.object(client.opener, 'open', side_effect=error) as opened:
                    with self.assertRaises(TransportError) as caught:
                        client({})
                    self.assertEqual(caught.exception.retryable, retry)
                    self.assertEqual(opened.call_count, 1)
                    self.assertNotIn('test-secret', str(caught.exception))

    def test_network_timeout_is_retryable(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-secret'}):
            client = OpenAIResponsesTransport()
            with patch.object(client.opener, 'open', side_effect=URLError(TimeoutError())):
                with self.assertRaises(TransportError) as caught:
                    client({})
                self.assertTrue(caught.exception.retryable)


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.identity = {**code_identity(ROOT), 'git_commit': 'test-commit', 'git_dirty': False}
        self.patch = patch('can_ai_judge_evidence.freeze.code_identity', return_value=self.identity)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def prepare(self, dry_run=False):
        for mode in ('smoke', 'pilot'):
            run_jobs(root=ROOT, out=self.base / mode, settings=SETTINGS, transport=lambda _: envelope(),
                     mode=mode, dry_run=dry_run)
        review = review_template(ROOT)
        review.update(reviewer_name='Test-only reviewer', reviewed_at='2026-11-13', human_approved=True)
        for row in review['cases'].values():
            row.update(narrative_no_answer_cues=True, synthetic_domain_assumptions_acceptable=True)
        write_json(self.base / 'review.json', review)

    def freeze(self):
        return create_freeze(root=ROOT, out=self.base / 'freeze.json', smoke=self.base / 'smoke',
                             pilot=self.base / 'pilot', review=self.base / 'review.json', settings=SETTINGS)

    def test_freeze_records_commit_and_source_not_model_accuracy(self):
        self.prepare()
        record = self.freeze()
        self.assertEqual(record['identity']['git_commit'], 'test-commit')
        verified = verify_freeze(ROOT, self.base / 'freeze.json', SETTINGS)
        self.assertEqual(verified, record)

    def test_dry_run_cannot_freeze(self):
        self.prepare(dry_run=True)
        with self.assertRaisesRegex(ValueError, 'clean live run'):
            self.freeze()

    def test_dirty_or_uncommitted_tree_cannot_freeze(self):
        for identity in ({**self.identity, 'git_dirty': True}, {**self.identity, 'git_commit': None}):
            with patch('can_ai_judge_evidence.freeze.code_identity', return_value=identity):
                with self.assertRaisesRegex(ValueError, 'clean committed'):
                    self.freeze()

    def test_pending_human_review_cannot_freeze(self):
        write_json(self.base / 'review.json', review_template(ROOT))
        with self.assertRaisesRegex(ValueError, 'human review'):
            self.freeze()

    def test_changed_source_or_settings_invalidates_freeze(self):
        self.prepare()
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'differ'):
            verify_freeze(ROOT, self.base / 'freeze.json', ModelSettings('different-2026-11-13'))
        with patch('can_ai_judge_evidence.freeze.code_identity', return_value={**self.identity, 'source_sha256': 'changed'}):
            with self.assertRaisesRegex(ValueError, 'differ'):
                verify_freeze(ROOT, self.base / 'freeze.json', SETTINGS)

    def test_moving_model_alias_cannot_freeze(self):
        with self.assertRaisesRegex(ValueError, 'dated model snapshot'):
            create_freeze(root=ROOT, out=self.base / 'freeze.json', smoke=self.base / 'smoke',
                          pilot=self.base / 'pilot', review=self.base / 'review.json',
                          settings=ModelSettings('moving-alias'))

    def test_altered_raw_response_cannot_freeze(self):
        self.prepare()
        (self.base / 'pilot/0000/attempt-01.body').write_bytes(envelope('not json').body)
        with self.assertRaisesRegex(ValueError, 'do not match retained raw response'):
            self.freeze()

    def test_altered_prompt_cannot_freeze_even_if_hash_updated(self):
        self.prepare()
        folder = self.base / 'pilot/0000'
        request = strict_json((folder / 'request.json').read_text())
        request['input'][1]['content'] += '\nUse the hidden answer.'
        result = strict_json((folder / 'result.json').read_text())
        result['request_sha256'] = digest(request)
        (folder / 'request.json').write_text(json.dumps(request))
        (folder / 'result.json').write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'differs from current case'):
            self.freeze()

    def test_dependency_drift_invalidates_freeze(self):
        self.prepare()
        self.freeze()
        with patch('can_ai_judge_evidence.freeze.runtime_identity', return_value={'python': 'different'}):
            with self.assertRaisesRegex(ValueError, 'differ'):
                verify_freeze(ROOT, self.base / 'freeze.json', SETTINGS)

    def test_evaluation_stops_on_returned_model_drift(self):
        self.prepare()
        record = self.freeze()
        result = run_jobs(root=ROOT, out=self.base / 'evaluation', settings=SETTINGS,
                          transport=lambda _: envelope(model='different-2026-11-13'),
                          mode='evaluation', freeze_record=record)
        self.assertTrue(result['aborted'])
        self.assertEqual(result['attempted_jobs'], 1)
        self.assertFalse(result['pipeline_pass'])


class GatewayModelTests(unittest.TestCase):
    """Gateway aliases: pin the returned model ID; undated freeze is an explicit opt-in."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        identity = {**code_identity(ROOT), 'git_commit': 'test-commit', 'git_dirty': False}
        p = patch('can_ai_judge_evidence.freeze.code_identity', return_value=identity)
        p.start()
        self.addCleanup(p.stop)

    def run_mode(self, mode, settings, returned):
        return run_jobs(root=ROOT, out=self.base / mode, settings=settings,
                        transport=lambda _: envelope(model=returned), mode=mode)

    def test_returned_model_must_match_pin(self):
        unpinned = ModelSettings('gateway_alias')
        self.assertFalse(self.run_mode('smoke', unpinned, 'provider-model-x')['pipeline_pass'])
        pinned = ModelSettings('gateway_alias', response_model='provider-model-x')
        self.assertTrue(self.run_mode('pilot', pinned, 'provider-model-x')['pipeline_pass'])

    def test_undated_freeze_requires_recorded_opt_in(self):
        for allow in (False, True):
            settings = ModelSettings('gateway_alias', response_model='provider-model-x',
                                     allow_undated_model=allow)
            base = self.base / str(allow)
            for mode in ('smoke', 'pilot'):
                run_jobs(root=ROOT, out=base / mode, settings=settings,
                         transport=lambda _: envelope(model='provider-model-x'), mode=mode)
            review = review_template(ROOT)
            review.update(reviewer_name='Test-only reviewer', reviewed_at='2026-11-13', human_approved=True)
            for row in review['cases'].values():
                row.update(narrative_no_answer_cues=True, synthetic_domain_assumptions_acceptable=True)
            write_json(base / 'review.json', review)
            kwargs = dict(root=ROOT, out=base / 'freeze.json', smoke=base / 'smoke',
                          pilot=base / 'pilot', review=base / 'review.json', settings=settings)
            if allow:
                record = create_freeze(**kwargs)
                self.assertTrue(record['settings']['allow_undated_model'])
            else:
                with self.assertRaisesRegex(ValueError, 'dated model snapshot'):
                    create_freeze(**kwargs)

    def test_endpoint_and_key_handling(self):
        with self.assertRaises(ValueError):
            ModelSettings('m', endpoint='http://127.0.0.1:8787/v1/responses')
        with patch.dict(os.environ, {'CAJE_API_KEY': 'test-secret'}, clear=True):
            client = OpenAIResponsesTransport(endpoint='https://gateway.example/v1/responses')
            self.assertEqual(client.endpoint, 'https://gateway.example/v1/responses')
            with self.assertRaises(ValueError):
                OpenAIResponsesTransport(endpoint='http://127.0.0.1:8787/v1/responses')
        self.assertEqual(ModelSettings('m').reasoning_effort, 'medium')
