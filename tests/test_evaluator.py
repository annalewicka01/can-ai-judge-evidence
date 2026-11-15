"""Constraint and malformed-input tests, independent of future LLM outputs."""
from dataclasses import asdict, replace
import json
import unittest

from can_ai_judge_evidence.domain import ConfigurationError, Plan, Standard
from can_ai_judge_evidence.evaluator import evaluate_plan
from can_ai_judge_evidence.power import binomial_power
from fixtures import make_config, proposal


class EvaluatorTests(unittest.TestCase):
    def test_canonical_pass_fail(self):
        config = make_config()
        self.assertFalse(evaluate_plan(config, proposal(500)).valid)
        self.assertTrue(evaluate_plan(config, proposal(3800)).valid)
        failed = evaluate_plan(config, proposal(500))
        self.assertEqual(failed.failures, ('insufficient_power',))

    def test_cost_and_deadline_boundaries(self):
        config = make_config()
        result = evaluate_plan(config, proposal())
        self.assertEqual(result.cost, 7700)
        self.assertTrue(result.valid)
        self.assertIn('budget', evaluate_plan(replace(config, budget=7699), proposal()).failures)
        self.assertIn('after_deadline', evaluate_plan(config, proposal(month=10)).failures)
        self.assertTrue(evaluate_plan(config, proposal(month=8)).valid)

    def test_outcome_readiness(self):
        config = make_config()
        self.assertIn('outcome_not_ready', evaluate_plan(config, proposal(month=7)).failures)
        self.assertEqual(evaluate_plan(config, proposal()).ready_month, 8)
        impossible = make_config(deadline=9, instrument_changes={'outcome_window_months': 12})
        result = evaluate_plan(impossible, proposal(month=9))
        self.assertFalse(result.valid)
        self.assertEqual(result.ready_month, 14)
        self.assertIn('outcome_not_ready', result.failures)

    def test_coverage_applied_once(self):
        config = make_config(instrument_changes={'coverage': .5, 'sensitivity': .8})
        result = evaluate_plan(config, proposal())
        expected = binomial_power(3800, .4*.005, .4*(70/8500))
        self.assertEqual(result.q, .4)
        self.assertEqual(result.cost, 7700)
        self.assertEqual(result.plan.n, 3800)
        self.assertEqual(result.k_star, expected.k_star)
        self.assertEqual(result.power, expected.power)

    def test_zero_capture(self):
        for field in ('coverage', 'sensitivity'):
            with self.subTest(field=field):
                result = evaluate_plan(make_config(instrument_changes={field: 0}), proposal())
                self.assertEqual(result.power, 0)
                self.assertIn('unobservable_deterioration', result.failures)

    def test_no_rounding_at_power_threshold(self):
        config = make_config(standard=Standard(target_power=.803303))
        result = evaluate_plan(config, proposal())
        self.assertEqual(round(result.power, 5), round(.803303, 5))
        self.assertFalse(result.valid)
        self.assertIn('insufficient_power', result.failures)

    def test_both_sample_caps(self):
        config = make_config(instrument_changes={'max_n': 3700},
                             profile_changes={'eligible_n': 3600})
        result = evaluate_plan(config, proposal())
        self.assertIn('sample_exceeds_pool', result.failures)
        self.assertIn('sample_exceeds_instrument', result.failures)
        self.assertEqual((result.eligible_n, result.instrument_max_n), (3600, 3700))
        self.assertIsNotNone(result.power)  # Counterfactual, despite infeasible size.

    def test_multiple_failures(self):
        config = make_config(budget=0, deadline=7, instrument_changes={'max_n': 400},
                             profile_changes={'eligible_n': 450})
        result = evaluate_plan(config, proposal(500, month=7))
        self.assertTrue({'sample_exceeds_pool', 'sample_exceeds_instrument', 'budget',
                         'outcome_not_ready', 'insufficient_power'}.issubset(result.failures))

    def test_unknown_ids_keep_independent_checks(self):
        result = evaluate_plan(make_config(budget=0), proposal(population='all_triaged', month=10))
        self.assertIn('unsupported_profile', result.failures)
        self.assertIn('budget', result.failures)
        self.assertIn('after_deadline', result.failures)
        self.assertIsNone(result.power)
        self.assertEqual(result.cost, 7700)
        result = evaluate_plan(make_config(), proposal(channel='unknown', month=10))
        self.assertIn('unsupported_channel', result.failures)
        self.assertIn('after_deadline', result.failures)
        self.assertIsNone(result.cost)

    def test_equal_rates_are_observability_failure(self):
        result = evaluate_plan(make_config(), proposal(population='observed'))
        self.assertEqual(result.power, result.actual_alpha)
        self.assertIn('unobservable_deterioration', result.failures)
        self.assertFalse(result.valid)

    def test_malformed_plans_do_not_crash(self):
        plans = [None, [], [proposal()], 'audit', {}, {'n': 500},
                 {**proposal(), 'extra': 1}, {**proposal(), 'channel': ['audit']}]
        for n in (0, -1, 2.5, True, '3800', 'all', float('nan'), 2**53):
            plans.append(proposal(n=n))
        for month in (-1, True, '9', 9.5, float('inf')):
            plans.append(proposal(month=month))
        for bad in plans:
            with self.subTest(plan=bad):
                result = evaluate_plan(make_config(), bad)
                self.assertFalse(result.schema_valid)
                self.assertFalse(result.valid)
                self.assertTrue(result.validation_errors)
                self.assertIsNone(result.power)

    def test_typed_plan_and_json_serialization(self):
        result = evaluate_plan(make_config(), Plan(**proposal()))
        self.assertTrue(result.valid)
        restored = json.loads(json.dumps(asdict(result), allow_nan=False))
        self.assertEqual(restored['cost'], 7700)


class ConfigurationTests(unittest.TestCase):
    def test_bad_configuration_values(self):
        for changes in ({'coverage': float('nan')}, {'sensitivity': 1.1},
                        {'coverage': True}, {'fixed_cost': -1}, {'per_patient_cost': .5},
                        {'max_n': True}, {'reporting_delay_months': -1}):
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                make_config(instrument_changes=changes)
        for changes in ({'p0': -.1}, {'p1': float('inf')}, {'p1': .001},
                        {'eligible_n': -1}, {'iid_assumption': ''}, {'denominator': ''}):
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                make_config(profile_changes=changes)
        for kwargs in ({'budget': -1}, {'budget': True}, {'deadline': 2.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                make_config(**kwargs)

    def test_structural_configuration_errors(self):
        config = make_config()
        bad_changes = (
            {'instruments': config.instruments*2},
            {'profiles': config.profiles*2},
            {'profiles': (replace(config.profiles[0], channel='unknown'),)},
            {'profiles': (replace(config.profiles[0], outcome_window_months=7),)},
            {'existing_plan': Plan('audit', 'unknown', 500, 9)},
            {'existing_plan': proposal()},
            {'standard': None},
        )
        for changes in bad_changes:
            with self.subTest(changes=changes), self.assertRaises(ConfigurationError):
                replace(config, **changes)

    def test_configuration_defensively_copies_containers(self):
        original = make_config()
        instruments = list(original.instruments)
        config = replace(original, instruments=instruments)
        instruments.clear()
        self.assertEqual(len(config.instruments), 1)

    def test_zero_population_cap_is_valid_config(self):
        config = make_config(profile_changes={'eligible_n': 0})
        self.assertIn('sample_exceeds_pool', evaluate_plan(config, proposal()).failures)

    def test_same_population_different_endpoint_can_be_blind(self):
        config = make_config()
        other_instrument = replace(config.instruments[0], channel='other_endpoint')
        other_profile = replace(config.profiles[0], channel='other_endpoint',
                                endpoint='Different synthetic endpoint', p0=.02, p1=.02)
        config = replace(config, instruments=(*config.instruments, other_instrument),
                         profiles=(*config.profiles, other_profile))
        self.assertTrue(evaluate_plan(config, proposal()).valid)
        self.assertFalse(evaluate_plan(config, proposal(channel='other_endpoint')).valid)

    def test_standard_validation(self):
        for alpha, power in ((0, .8), (.05, .01), (.05, .05), (.05, 1.1),
                             (True, .8), (.05, float('nan'))):
            with self.subTest(alpha=alpha, power=power), self.assertRaises(ConfigurationError):
                Standard(alpha, power)
