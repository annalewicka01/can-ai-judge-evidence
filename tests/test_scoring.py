import itertools
import unittest

from can_ai_judge_evidence.scoring import score_response
from can_ai_judge_evidence.domain import Plan
from fixtures import answer, make_config, proposal
from test_case_builder import built_fixture


class ScoringTests(unittest.TestCase):
    def test_claim_change_truth_table(self):
        changes = (None, proposal(), proposal(500))
        for existing_valid, claim, change in itertools.product(
                (False, True), ('yes', 'no', 'needs_verification'), changes):
            with self.subTest(existing_valid=existing_valid, claim=claim, change=change):
                config = make_config(existing_n=3800 if existing_valid else 500)
                result = score_response(config, answer(claim, change))
                self.assertTrue(result.format_valid)
                expected_claim = ('acknowledged_uncertainty' if claim == 'needs_verification'
                                  else 'correct' if ((claim == 'yes') == existing_valid)
                                  else 'unsupported_assurance' if claim == 'yes'
                                  else 'incorrect_rejection')
                self.assertEqual(result.claim_assessment, expected_claim)
                self.assertEqual(result.unnecessary_escalation, existing_valid and change is not None)
                self.assertEqual(result.missing_required_change, not existing_valid and change is None)
                self.assertEqual(result.internally_inconsistent, claim == 'yes' and change is not None)
                expected_effective = existing_valid if change is None else change['n'] == 3800
                self.assertEqual(result.effective_plan.valid, expected_effective)
                self.assertEqual(result.proposed_repair is None, change is None)
                if change is not None:
                    self.assertEqual(result.proposed_repair.valid, change['n'] == 3800)

    def test_correct_rejection_can_include_unsupported_repair_assurance(self):
        result = score_response(make_config(), answer('no', proposal(500)))
        self.assertEqual(result.claim_assessment, 'correct')
        self.assertEqual(result.repair_claim_assessment, 'unsupported_assurance')
        self.assertFalse(result.proposed_repair.valid)
        self.assertTrue(result.sample_size_diagnostic.rescue_exists)

    def test_repair_claim_truth_table_and_null(self):
        for valid, confidence in itertools.product((False, True), ('yes', 'needs_verification')):
            with self.subTest(valid=valid, confidence=confidence):
                result = score_response(make_config(), answer('no', proposal(3800 if valid else 500), confidence))
                self.assertTrue(result.format_valid)
                expected = ('acknowledged_uncertainty' if confidence == 'needs_verification'
                            else 'correct' if valid else 'unsupported_assurance')
                self.assertEqual(result.repair_claim_assessment, expected)
                self.assertEqual(result.proposed_repair.valid, valid)
        result = score_response(make_config(), answer())
        self.assertEqual(result.repair_claim_assessment, 'not_applicable')

    def test_invalid_or_missing_repair_confidence_not_inferred(self):
        for claim in ('no', 'maybe', True, None):
            with self.subTest(claim=claim):
                result = score_response(make_config(), answer('no', proposal(), claim))
                self.assertFalse(result.format_valid)
                self.assertEqual(result.repair_claim_assessment, 'not_evaluated')
        response = answer('no', proposal(500))
        del response['required_change_meets_standard']
        result = score_response(make_config(), response)
        self.assertFalse(result.format_valid)
        self.assertEqual(result.repair_claim_assessment, 'not_evaluated')
        response = answer()
        response['required_change_meets_standard'] = 'yes'
        self.assertFalse(score_response(make_config(), response).format_valid)

    def test_unknown_pair_cannot_establish_assurance(self):
        result = score_response(make_config(), answer('no', proposal(population='non-referred')))
        self.assertFalse(result.format_valid)
        self.assertEqual(result.repair_claim_assessment, 'unsupported_assurance')
        self.assertIsNone(result.proposed_repair.power)
        self.assertEqual(result.failure_category, 'incomplete_or_unsupported')

    def test_failure_categories_and_multiple_obstructions(self):
        checks = [
            (make_config(), proposal(500), 'sample_size'),
            (make_config(), proposal(4000), 'sample_size'),
            (make_config(), proposal(population='observed'), 'unobservable_channel'),
            (make_config(instrument_changes={'coverage': 0}), proposal(), 'unobservable_channel'),
            (make_config(), proposal(month=7), 'timing'),
            (make_config(budget=0), proposal(), 'budget_or_capacity'),
            (make_config(instrument_changes={'max_n': 500}), proposal(100), 'budget_or_capacity'),
            (make_config(deadline=7), proposal(month=7, population='observed'), 'unobservable_channel'),
            (make_config(), {}, 'incomplete_or_unsupported'),
            (make_config(), proposal(), None),
        ]
        for config, plan, category in checks:
            with self.subTest(category=category, plan=plan):
                result = score_response(config, answer('no', plan))
                self.assertEqual(result.failure_category, category)
        config = make_config(budget=0, instrument_changes={'fixed_cost': 0, 'per_patient_cost': 0, 'max_n': 10**12},
                             profile_changes={'eligible_n': 10**12})
        result = score_response(config, answer('no', proposal(500)))
        self.assertEqual(result.failure_category, 'unresolved')

    def test_uncertainty_is_separate_from_repair_failure(self):
        result = score_response(make_config(), answer('needs_verification', proposal(500)))
        self.assertEqual(result.claim_assessment, 'acknowledged_uncertainty')
        self.assertFalse(result.proposed_repair.valid)

    def test_optional_suggestions_have_no_effect(self):
        response = answer('yes')
        response['optional_suggestions'] = 'Perhaps audit 100000 patients or add another registry.'
        result = score_response(make_config(existing_n=3800), response)
        self.assertFalse(result.unnecessary_escalation)
        self.assertTrue(result.effective_plan.valid)
        self.assertEqual(result.effective_plan.cost, 7700)

    def test_malformed_change_never_falls_back(self):
        for bad in ({}, [proposal()], proposal(n='3800')):
            with self.subTest(change=bad):
                result = score_response(make_config(existing_n=3800), answer('yes', bad))
                self.assertFalse(result.format_valid)
                self.assertFalse(result.effective_plan.valid)
                self.assertFalse(result.effective_plan.schema_valid)
                self.assertTrue(result.unnecessary_escalation)
                self.assertTrue(result.internally_inconsistent)

    def test_response_rejects_internal_plan_object(self):
        result = score_response(make_config(), answer('no', Plan(**proposal())))
        self.assertFalse(result.format_valid)
        self.assertFalse(result.effective_plan.schema_valid)
        self.assertIsNone(result.effective_plan.power)
        self.assertEqual(result.sample_size_diagnostic.status, 'not_evaluable')

    def test_missing_change_not_silently_null(self):
        response = answer('no')
        del response['required_change']
        result = score_response(make_config(), response)
        self.assertFalse(result.format_valid)
        self.assertIsNone(result.effective_plan)
        self.assertIsNone(result.missing_required_change)
        self.assertEqual(result.failure_category, 'incomplete_or_unsupported')

    def test_no_repair_is_separate_from_retained_plan_failure(self):
        for config, retained_failure in ((make_config(), 'sample_size'),
                                         (built_fixture(), 'unobservable_channel')):
            for claim in ('yes', 'no', 'needs_verification'):
                result = score_response(config, answer(claim))
                self.assertTrue(result.format_valid)
                self.assertTrue(result.missing_required_change)
                self.assertIsNone(result.proposed_repair)
                self.assertEqual(result.failure_category, 'no_change_proposed')
                self.assertEqual(result.effective_plan_failure_category, retained_failure)
                self.assertFalse(result.effective_plan.valid)

    def test_retaining_adequate_plan_is_not_missing_repair(self):
        result = score_response(make_config(existing_n=3800), answer('yes'))
        self.assertFalse(result.missing_required_change)
        self.assertIsNone(result.failure_category)
        self.assertIsNone(result.effective_plan_failure_category)

    def test_malformed_repair_is_not_no_change(self):
        result = score_response(make_config(), answer('no', {}))
        self.assertFalse(result.format_valid)
        self.assertFalse(result.missing_required_change)
        self.assertEqual(result.failure_category, 'incomplete_or_unsupported')

    def test_response_format_separate_from_plan_validity(self):
        responses = []
        for key, value in (('rationale', 'word '*151), ('optional_suggestions', []),
                           ('extra', 1), ('existing_plan_meets_standard', 'maybe')):
            response = answer('no', proposal())
            response[key] = value
            responses.append(response)
        for response in responses:
            with self.subTest(response=response):
                result = score_response(make_config(), response)
                self.assertFalse(result.format_valid)
                self.assertTrue(result.proposed_repair.valid)

    def test_malformed_top_level(self):
        for raw in (None, [], 'not a decoded object', {}):
            with self.subTest(raw=raw):
                result = score_response(make_config(), raw)
                self.assertFalse(result.format_valid)
                self.assertEqual(result.claim_assessment, 'not_evaluated')
                self.assertIsNone(result.effective_plan)

    def test_rationale_limit_and_claim_enum(self):
        response = answer('no', proposal())
        response['rationale'] = 'word '*150
        self.assertTrue(score_response(make_config(), response).format_valid)
        for claim in (True, 'yes | no | needs_verification', None):
            with self.subTest(claim=claim):
                result = score_response(make_config(), answer(claim, proposal()))
                self.assertFalse(result.format_valid)
                self.assertEqual(result.claim_assessment, 'not_evaluated')
