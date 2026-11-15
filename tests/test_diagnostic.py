import unittest

from can_ai_judge_evidence.domain import Standard
from can_ai_judge_evidence.diagnostic import diagnose_sample_size
from can_ai_judge_evidence.evaluator import evaluate_plan
from can_ai_judge_evidence.power import binomial_power
from fixtures import make_config, proposal


class DiagnosticTests(unittest.TestCase):
    def test_small_audit_has_rescue(self):
        config = make_config()
        result = diagnose_sample_size(config, proposal(500))
        self.assertEqual(result.status, 'feasible')
        self.assertTrue(result.rescue_exists)
        self.assertGreater(result.smallest_feasible_n, 500)
        self.assertLessEqual(result.smallest_feasible_n, 3800)
        self.assertTrue(evaluate_plan(config, proposal(result.smallest_feasible_n)).valid)
        # Scalar audit across every earlier n independently checks search minimality.
        self.assertFalse(any(binomial_power(n, .005, 70/8500).power >= .8
                             for n in range(1, result.smallest_feasible_n)))

    def test_nonmonotone_search(self):
        config = make_config(existing_n=3, budget=0,
                             instrument_changes={'max_n': 4, 'fixed_cost': 0, 'per_patient_cost': 0},
                             profile_changes={'p0': .1, 'p1': .2, 'eligible_n': 4},
                             standard=Standard(target_power=.10))
        result = diagnose_sample_size(config, proposal(4))
        self.assertEqual(result.smallest_feasible_n, 3)
        self.assertAlmostEqual(result.best_power, .104, delta=1e-12)
        self.assertEqual(result.max_candidate_n, 4)

    def test_budget_failure_rescued_by_smaller_sample(self):
        config = make_config()
        self.assertIn('budget', evaluate_plan(config, proposal(4000)).failures)
        result = diagnose_sample_size(config, proposal(4000))
        self.assertTrue(result.rescue_exists)
        self.assertLess(result.smallest_feasible_n, 4000)

    def test_zero_marginal_cost_and_fixed_cost(self):
        feasible = make_config(budget=100,
                               instrument_changes={'per_patient_cost': 0, 'max_n': 3800})
        self.assertTrue(diagnose_sample_size(feasible, proposal(500)).rescue_exists)
        infeasible = make_config(budget=99, instrument_changes={'per_patient_cost': 0})
        result = diagnose_sample_size(infeasible, proposal())
        self.assertEqual(result.status, 'infeasible')
        self.assertIn('fixed_cost_exceeds_budget', result.obstructions)

    def test_no_positive_affordable_sample(self):
        result = diagnose_sample_size(make_config(budget=100), proposal())
        self.assertEqual(result.max_candidate_n, 0)
        self.assertFalse(result.rescue_exists)

    def test_impossible_timing_is_fixed(self):
        for month, failure in ((7, 'outcome_not_ready'), (10, 'after_deadline')):
            with self.subTest(month=month):
                result = diagnose_sample_size(make_config(), proposal(month=month))
                self.assertFalse(result.rescue_exists)
                self.assertIn(failure, result.obstructions)
                self.assertIsNone(result.best_power)

    def test_blind_channel_cannot_be_rescued(self):
        result = diagnose_sample_size(make_config(), proposal(population='observed'))
        self.assertFalse(result.rescue_exists)
        self.assertIn('unobservable_deterioration', result.obstructions)
        self.assertIsNone(result.best_power)
        self.assertEqual(result.best_power_upper_bound, .05)

    def test_search_guard_is_unknown_not_infeasible(self):
        config = make_config(budget=0,
                             instrument_changes={'fixed_cost': 0, 'per_patient_cost': 0, 'max_n': 10**12},
                             profile_changes={'eligible_n': 10**12})
        result = diagnose_sample_size(config, proposal(500))
        self.assertEqual(result.status, 'search_limit_exceeded')
        self.assertIsNone(result.rescue_exists)
        self.assertIsNone(result.best_power)
        self.assertEqual(result.max_candidate_n, 10**12)
        self.assertFalse(diagnose_sample_size(config, proposal(population='observed')).rescue_exists)

    def test_search_guard_boundary_and_validation(self):
        config = make_config()
        self.assertEqual(diagnose_sample_size(config, proposal(500), max_search_n=3799).status,
                         'search_limit_exceeded')
        self.assertTrue(diagnose_sample_size(config, proposal(500), max_search_n=3800).rescue_exists)
        for invalid in (0, -1, True, 3.5):
            with self.assertRaises(ValueError):
                diagnose_sample_size(config, proposal(), max_search_n=invalid)

    def test_cap_prevents_rescue(self):
        result = diagnose_sample_size(make_config(instrument_changes={'max_n': 500}), proposal(100))
        self.assertEqual(result.status, 'infeasible')
        self.assertIn('no_sample_size_meets_standard', result.obstructions)
        self.assertLess(result.best_power, .8)

    def test_not_evaluable_is_distinct(self):
        for plan in ({}, proposal(channel='unknown'), proposal(population='unknown')):
            with self.subTest(plan=plan):
                result = diagnose_sample_size(make_config(), plan)
                self.assertEqual(result.status, 'not_evaluable')
                self.assertIsNone(result.rescue_exists)
                self.assertIsNone(result.best_power)
