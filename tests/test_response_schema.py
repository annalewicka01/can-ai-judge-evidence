import unittest

from jsonschema import Draft202012Validator

from can_ai_judge_evidence.response_schema import response_schema, model_contract
from can_ai_judge_evidence.scoring import score_response
from can_ai_judge_evidence.brief import BriefTarget
from fixtures import answer
from test_case_builder import built_fixture, world_fixture


class ResponseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.config = built_fixture()
        schema = response_schema(self.config)
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)
        self.plan = dict(channel='audit', population='non_referred', n=3800, analysis_month=9)

    def test_supported_ids_and_conditional_repair_claim(self):
        for response in (answer('no', self.plan), answer('no', self.plan, 'needs_verification'), answer('yes')):
            self.assertTrue(self.validator.is_valid(response))
            self.assertTrue(score_response(self.config, response).format_valid)
        bad_claim = answer('yes')
        bad_claim['required_change_meets_standard'] = 'yes'
        # Cross-field dependence belongs to runtime validation; portable schema
        # deliberately allows these values individually.
        for response in (bad_claim, answer('no', self.plan, None)):
            self.assertTrue(self.validator.is_valid(response))
            self.assertFalse(score_response(self.config, response).format_valid)
        invalid = [answer('no', self.plan, 'no'),
                   answer('no', {**self.plan, 'population': 'non-referred'}),
                   answer('no', {**self.plan, 'channel': 'local_records'}),  # Known IDs, unsupported pair.
                   answer('no', {**self.plan, 'n': 'all'}),
                   answer('no', {**self.plan, 'n': True})]
        for response in invalid:
            with self.subTest(response=response):
                self.assertFalse(self.validator.is_valid(response))
                self.assertFalse(score_response(self.config, response).format_valid)

    def test_every_offered_pair_is_encodable(self):
        for profile in self.config.profiles:
            response = answer('no', dict(channel=profile.channel, population=profile.population,
                                         n=profile.eligible_n, analysis_month=9))
            self.assertTrue(self.validator.is_valid(response))

    def test_runtime_checks_stricter_integer_lexical_contract(self):
        # Standard JSON Schema treats 3800.0 as integer-valued; the decoded
        # Python API deliberately requires an int. Both checks are necessary.
        response = answer('no', {**self.plan, 'n': 3800.0})
        self.assertTrue(self.validator.is_valid(response))
        self.assertFalse(score_response(self.config, response).format_valid)

    def test_generated_contract_contains_actual_counts_and_constraints(self):
        world, _, bindings = world_fixture()
        contract = model_contract(self.config, world=world, bindings=bindings,
                                  target=BriefTarget('missed_event', 'non_referred', 'unseen', 'none'))
        for text in ('month 0', '"size": 8500', '"size": 1500',
                     'not "all"', 'replacement', 'one-sided', '"budget": 7700',
                     '"deadline_month": 9', '"coverage": 1.0', 'required_change_meets_standard'):
            self.assertIn(text, contract)

    def test_transport_uses_small_common_schema_subset(self):
        # Offline structural check, NOT a live provider acceptance test.
        allowed = {'type', 'properties', 'required', 'additionalProperties',
                   'enum', 'description', 'anyOf'}
        def visit(node):
            self.assertLessEqual(set(node), allowed)
            if node.get('type') == 'object':
                self.assertIs(node['additionalProperties'], False)
                self.assertEqual(set(node['required']), set(node['properties']))
                for child in node['properties'].values():
                    visit(child)
            for branch in node.get('anyOf', []):
                visit(branch)
        schema = response_schema(self.config)
        self.assertEqual(schema['type'], 'object')
        self.assertNotIn('anyOf', schema)
        visit(schema)

    def test_portable_schema_does_not_hide_numeric_failures(self):
        for plan in ({**self.plan, 'n': 0}, {**self.plan, 'analysis_month': -1}):
            response = answer('no', plan)
            self.assertTrue(self.validator.is_valid(response))
            self.assertFalse(score_response(self.config, response).format_valid)

    def test_every_cross_pair_rejected_unless_offered(self):
        pairs = {(p.channel, p.population) for p in self.config.profiles}
        for channel in {c for c, _ in pairs}:
            for population in {p for _, p in pairs}:
                response = answer('no', {**self.plan, 'channel': channel, 'population': population})
                self.assertEqual(self.validator.is_valid(response), (channel, population) in pairs)
