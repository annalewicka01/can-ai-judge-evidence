import unittest

from can_ai_judge_evidence.reporting import summarize_by_arm
from can_ai_judge_evidence.scoring import score_response
from fixtures import answer, make_config, proposal


class ReportingTests(unittest.TestCase):
    def test_hedging_does_not_count_as_correct_assertion(self):
        config = make_config()
        result = summarize_by_arm({'targeted': [
            score_response(config, answer('needs_verification', proposal(500), 'needs_verification')),
            score_response(config, answer('no', proposal(500), 'yes')),
            score_response(config, answer('needs_verification')),
        ]})['targeted']
        self.assertEqual(result['existing_needs_verification'], {'count': 2, 'denominator': 3, 'rate': 2/3})
        self.assertEqual(result['repair_needs_verification'], {'count': 1, 'denominator': 2, 'rate': .5})
        self.assertEqual(result['unsupported_repair_assurance']['count'], 1)
        self.assertEqual(result['operational_success']['count'], 0)
        self.assertEqual(result['existing_assertion_rate']['rate'], 1/3)

    def test_empty_denominators_are_unavailable_not_zero(self):
        result = summarize_by_arm({'empty': [], 'no_repairs': [score_response(make_config(), answer())]})
        self.assertIsNone(result['empty']['existing_needs_verification']['rate'])
        self.assertIsNone(result['no_repairs']['repair_needs_verification']['rate'])

    def test_bad_format_is_not_operational_success(self):
        response = answer('no', proposal())
        del response['required_change_meets_standard']
        result = summarize_by_arm({'ordinary': [score_response(make_config(), response)]})['ordinary']
        self.assertEqual(result['valid_effective_plan']['count'], 1)
        self.assertEqual(result['operational_success']['count'], 0)
        self.assertEqual(result['repair_claim_unscored']['count'], 1)

    def test_omitted_repairs_do_not_pollute_proposed_design_categories(self):
        missing_field = answer('no')
        del missing_field['required_change']
        scores = [score_response(make_config(), answer('needs_verification')),
                  score_response(make_config(), answer('no', proposal(500))),
                  score_response(make_config(existing_n=3800), answer('yes')),
                  score_response(make_config(), missing_field)]
        result = summarize_by_arm({'ordinary': scores})['ordinary']
        self.assertEqual(result['no_change_proposed'], {'count': 1, 'denominator': 3, 'rate': 1/3})
        self.assertEqual(result['failure_categories']['no_change_proposed']['count'], 1)
        self.assertEqual(result['failure_categories']['sample_size']['count'], 1)
        self.assertEqual(result['failure_categories']['incomplete_or_unsupported']['count'], 1)
        self.assertEqual(result['proposed_repair_failure_categories']['sample_size'],
                         {'count': 1, 'denominator': 1, 'rate': 1.0})
