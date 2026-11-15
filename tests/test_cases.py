from dataclasses import asdict, replace
import unittest

from can_ai_judge_evidence.authoring import audit_case, audit_suite
from can_ai_judge_evidence.brief import public_case_data, validate_public_case
from can_ai_judge_evidence.cases import case_pairs, smoke_fixture
from can_ai_judge_evidence.domain import ConfigurationError
from can_ai_judge_evidence.evaluator import evaluate_plan
from can_ai_judge_evidence.prompts import ARMS, messages, validate_prompt_arms
from can_ai_judge_evidence.scoring import score_response


class AuthoredCaseTests(unittest.TestCase):
    def test_complete_suite_and_different_winning_channels(self):
        report = audit_suite()
        self.assertEqual(len(report['pairs']), 5)
        self.assertEqual(len({r['feasible_pairs'][0][0] for r in report['pairs']}), 5)
        self.assertFalse(report['human_review_complete'])
        for row in report['pairs']:
            self.assertFalse(row['blind']['valid'])
            self.assertEqual(row['blind']['theta0'], row['blind']['theta1'])
            self.assertTrue(row['adequate']['valid'])
            self.assertGreater(row['reference_repair']['power'], .85)

    def test_pair_diff_only_existing_plan_and_public_facts_reconstruct(self):
        for case in case_pairs():
            with self.subTest(case=case.case_id):
                blind, adequate = case.config('blind'), case.config('adequate')
                self.assertEqual(replace(adequate, existing_plan=blind.existing_plan), blind)
                facts = []
                for cfg in (blind, adequate):
                    data = public_case_data(cfg, world=case.world, bindings=case.bindings, target=case.target)
                    validate_public_case(cfg, data)
                    facts.append(data)
                self.assertEqual({**facts[1], 'existing_plan': facts[0]['existing_plan']}, facts[0])

    def test_reference_answers_and_adequate_retention_score_cleanly(self):
        for case in case_pairs():
            for variant in ('blind', 'adequate'):
                change = asdict(case.reference_repair) if variant == 'blind' else None
                answer = {'existing_plan_meets_standard': 'no' if change else 'yes',
                          'required_change': change, 'required_change_meets_standard': 'yes' if change else None,
                          'rationale': '', 'optional_suggestions': ''}
                score = score_response(case.config(variant), answer)
                self.assertTrue(score.format_valid)
                self.assertTrue(score.effective_plan.valid)
                self.assertEqual(score.claim_assessment, 'correct')
                self.assertFalse(score.unnecessary_escalation)

    def test_bad_case_edits_fail_closed(self):
        case = case_pairs()[0]
        for bad in (replace(case, budget=1), replace(case, deadline_month=0),
                    replace(case, offered_pairs=case.offered_pairs[:-1]),
                    replace(case, expected_feasible_pairs=()),
                    replace(case, adequate_plan=case.blind_plan)):
            with self.assertRaises(ConfigurationError):
                audit_case(bad)
        for bad in (case_pairs()[:-1], (*case_pairs()[:-1], case)):
            with self.assertRaises(ConfigurationError):
                audit_suite(bad)

    def test_poisoned_public_projection_rejected(self):
        case = case_pairs()[0]
        config = case.config('blind')
        facts = public_case_data(config, world=case.world, bindings=case.bindings, target=case.target)
        for key in ('reference_repair', 'profiles', 'power', 'blind'):
            with self.assertRaises(ConfigurationError):
                validate_public_case(config, {**facts, key: 'leak'})

    def test_smoke_fixture_preserves_original_regression(self):
        fixture = smoke_fixture()
        result = evaluate_plan(fixture.config('blind'), fixture.reference_repair)
        self.assertAlmostEqual(result.power, .8033023677614939, places=12)


class PromptArmTests(unittest.TestCase):
    def test_lengths_are_equal_and_pinned(self):
        self.assertEqual(validate_prompt_arms(), 62)
        self.assertEqual({len(v.split()) for v in ARMS.values()}, {62})

    def test_only_arm_paragraph_changes(self):
        for case in case_pairs():
            for variant in ('blind', 'adequate'):
                outputs = [messages(case, variant, arm) for arm in ARMS]
                self.assertEqual(len({o[0]['content'] for o in outputs}), 1)
                common = [o[1]['content'].replace(ARMS[arm], '<ARM>') for arm, o in zip(ARMS, outputs)]
                self.assertEqual(len(set(common)), 1)

    def test_hidden_labels_and_answers_not_rendered(self):
        for case in case_pairs():
            for variant in ('blind', 'adequate'):
                text = messages(case, variant, 'ordinary')[1]['content']
                for forbidden in (case.case_id, 'reference_repair', 'expected_feasible_pairs',
                                  'blind_plan', 'adequate_plan', 'best_power', 'smallest_feasible_n',
                                  '"p0"', '"p1"', '"split"', '"feasible_pairs"'):
                    self.assertNotIn(forbidden, text)
                self.assertIn(case.narrative, text)

    def test_unknown_variant_or_arm_rejected(self):
        with self.assertRaises(ValueError):
            messages(case_pairs()[0], 'typo', 'ordinary')
        with self.assertRaises(KeyError):
            messages(case_pairs()[0], 'blind', 'typo')
