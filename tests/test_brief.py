from copy import deepcopy
from dataclasses import replace
import json
import unittest

from can_ai_judge_evidence.brief import (BriefTarget, config_from_public_case,
                                  public_case_data, validate_public_case)
from can_ai_judge_evidence.case_builder import build_config
from can_ai_judge_evidence.domain import ConfigurationError, Plan
from can_ai_judge_evidence.response_schema import model_contract
from test_case_builder import built_fixture, world_fixture


class PublicBriefTests(unittest.TestCase):
    def setUp(self):
        self.config = built_fixture()
        self.world, _, self.bindings = world_fixture()
        self.target = BriefTarget('missed_event', 'non_referred', 'unseen', 'none')

    def public(self, **kwargs):
        return public_case_data(self.config, world=self.world, bindings=self.bindings,
                                target=kwargs.get('target', self.target))

    def test_public_facts_reconstruct_every_profile_without_hidden_input(self):
        # JSON round-trip removes Python tuples and guarantees the reconstruction
        # has only what would actually reach a model.
        data = json.loads(json.dumps(self.public()))
        rebuilt = config_from_public_case(data)
        for expected in self.config.profiles:
            actual = rebuilt.profile(expected.channel, expected.population)
            self.assertAlmostEqual(actual.p0, expected.p0, places=14)
            self.assertAlmostEqual(actual.p1, expected.p1, places=14)
            self.assertEqual(actual.eligible_n, expected.eligible_n)
        self.assertAlmostEqual(rebuilt.profile('audit', 'all_triaged').p0, .00425)
        self.assertAlmostEqual(rebuilt.profile('audit', 'all_triaged').p1, .007)
        self.assertEqual(rebuilt.profile('local_records', 'all_triaged').p0,
                         rebuilt.profile('local_records', 'all_triaged').p1)
        validate_public_case(self.config, data)

    def test_derived_rates_and_evaluator_answers_are_not_rendered(self):
        text = model_contract(self.config, world=self.world, bindings=self.bindings, target=self.target)
        self.assertNotIn('0.00425', text)
        self.assertNotIn('0.003', text)
        self.assertNotIn('0.007000000000000001', text)
        self.assertEqual(text.count('"acceptable_rate"'), 1)
        self.assertEqual(text.count('"deterioration_to_detect"'), 1)
        self.assertNotIn('reference_repair', text)
        self.assertNotIn('unobservable_channel', text)
        for channel in self.public()['channels']:
            self.assertNotIn('p0', channel)
            self.assertNotIn('p1', channel)

    def test_legitimate_standard_and_zero_facts_are_not_numeric_leaks(self):
        # Here the board standard legitimately equals a hidden pair rate.
        target = replace(self.target, population='all_triaged')
        data = self.public(target=target)
        self.assertAlmostEqual(data['standard']['acceptable_rate'], .00425)
        self.assertEqual(data['groups'][0]['fixed_probabilities']['missed_event'], 0)
        validate_public_case(self.config, data)

    def test_global_standard_subtracts_fixed_events_in_other_groups(self):
        seen = self.world.groups[0]
        seen = replace(seen, outcomes=(seen.outcomes[0],
                                       replace(seen.outcomes[1], p0=.002, p1=.002),
                                       replace(seen.outcomes[2], p0=.978, p1=.978)))
        world = replace(self.world, groups=(seen, self.world.groups[1]))
        config = build_config(world, self.config.instruments, self.bindings,
                              existing_plan=self.config.existing_plan, budget=self.config.budget,
                              deadline_month=self.config.deadline_month)
        data = public_case_data(config, world=world, bindings=self.bindings,
                                target=replace(self.target, population='all_triaged'))
        self.assertAlmostEqual(data['standard']['acceptable_rate'], .00455)
        self.assertAlmostEqual(data['standard']['deterioration_to_detect'], .0073)
        reconstructed = config_from_public_case(json.loads(json.dumps(data)))
        self.assertAlmostEqual(reconstructed.profile('audit', 'non_referred').p0, .005)
        self.assertAlmostEqual(reconstructed.profile('audit', 'non_referred').p1, 70/8500)

    def test_rejects_leaked_fields_instead_of_matching_numeric_strings(self):
        for path, field, value in (
                ((), 'profiles', []), ((), 'current_true_rate', .01),
                (('channels', 0), 'acceptable_rate', .00425),
                (('channels', 0), 'power', .8),
                (('groups', 0), 'blind', True),
                (('standard',), 'reference_repair', {})):
            with self.subTest(field=field):
                data = self.public()
                node = data
                for key in path:
                    node = node[key]
                node[field] = value
                with self.assertRaises(ConfigurationError):
                    validate_public_case(self.config, data)

    def test_rejects_incomplete_or_inconsistent_public_facts(self):
        original = self.public()
        for edit in ('size', 'fixed_rate', 'cost', 'endpoint', 'missing_fact', 'impossible_target'):
            with self.subTest(edit=edit):
                data = deepcopy(original)
                if edit == 'size':
                    data['groups'][0]['size'] = 2000
                elif edit == 'fixed_rate':
                    data['groups'][0]['fixed_probabilities']['local_event'] = .03
                elif edit == 'cost':
                    data['channels'][0]['per_patient_cost'] = 3
                elif edit == 'endpoint':
                    data['channels'][1]['endpoint'] = 'missed_event'
                elif edit == 'missing_fact':
                    del data['groups'][0]['fixed_probabilities']['missed_event']
                else:
                    data['standard']['deterioration_to_detect'] = 1.5
                with self.assertRaises(ConfigurationError):
                    validate_public_case(self.config, data)

    def test_rejects_stale_evaluator_rates(self):
        bad = replace(self.config, profiles=(replace(self.config.profiles[0], p1=.01),
                                             *self.config.profiles[1:]))
        with self.assertRaises(ConfigurationError):
            public_case_data(bad, world=self.world, bindings=self.bindings, target=self.target)

    def test_complex_deterioration_fails_instead_of_omitting_assumptions(self):
        seen = self.world.groups[0]
        changed = replace(seen, outcomes=(replace(seen.outcomes[0], p1=.03),
                                          seen.outcomes[1], replace(seen.outcomes[2], p1=.97)))
        world = replace(self.world, groups=(changed, self.world.groups[1]))
        config = build_config(world, self.config.instruments, self.bindings,
                              existing_plan=self.config.existing_plan, budget=self.config.budget,
                              deadline_month=self.config.deadline_month)
        with self.assertRaisesRegex(ConfigurationError, 'single-group'):
            public_case_data(config, world=world, bindings=self.bindings, target=self.target)

    def test_invalid_target_definitions_fail(self):
        for target in (replace(self.target, endpoint='any_event'),
                       replace(self.target, population='observed'),
                       replace(self.target, residual_outcome='missed_event')):
            with self.subTest(target=target), self.assertRaises(ConfigurationError):
                self.public(target=target)

    def test_pair_briefs_differ_only_in_existing_plan(self):
        adequate = replace(self.config, existing_plan=Plan('audit', 'non_referred', 3800, 9))
        bad_facts = self.public()
        adequate_facts = public_case_data(adequate, world=self.world,
                                          bindings=self.bindings, target=self.target)
        self.assertNotEqual(bad_facts['existing_plan'], adequate_facts['existing_plan'])
        adequate_facts['existing_plan'] = bad_facts['existing_plan']
        self.assertEqual(bad_facts, adequate_facts)

    def test_old_contract_call_fails_rather_than_exposing_profiles(self):
        with self.assertRaises(TypeError):
            model_contract(self.config)
