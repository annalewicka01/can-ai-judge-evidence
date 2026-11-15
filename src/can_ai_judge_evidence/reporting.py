"""Descriptive arm-level counts with explicit denominators; no inference."""
from collections.abc import Mapping, Sequence

from .scoring import ResponseScore

FAILURE_CATEGORIES = ('no_change_proposed', 'incomplete_or_unsupported', 'sample_size',
                      'unobservable_channel', 'timing', 'unresolved', 'budget_or_capacity')


def summarize_by_arm(arms: Mapping[str, Sequence[ResponseScore]]) -> dict:
    def metric(numerator, denominator):
        return {'count': numerator, 'denominator': denominator,
                'rate': numerator / denominator if denominator else None}

    results = {}
    for arm, scores in arms.items():
        total = len(scores)
        repairs = [s for s in scores if s.change_present is True]
        existing_assertions = [s for s in scores if s.existing_claim in ('yes', 'no')]
        repair_assertions = [s for s in repairs if s.repair_claim == 'yes']
        invalid_existing = [s for s in scores if not s.existing_plan.valid]
        results[arm] = {
            'responses': total,
            'no_change_proposed': metric(sum(s.missing_required_change is True for s in invalid_existing),
                                         len(invalid_existing)),
            'failure_categories': {c: metric(sum(s.failure_category == c for s in scores), total)
                                   for c in FAILURE_CATEGORIES},
            'proposed_repair_failure_categories': {
                c: metric(sum(s.failure_category == c for s in repairs), len(repairs))
                for c in FAILURE_CATEGORIES if c != 'no_change_proposed'},
            'format_valid': metric(sum(s.format_valid for s in scores), total),
            'existing_needs_verification': metric(sum(s.existing_claim == 'needs_verification'
                                                       for s in scores), total),
            'repair_needs_verification': metric(sum(s.repair_claim == 'needs_verification'
                                                     for s in repairs), len(repairs)),
            'existing_assertion_rate': metric(len(existing_assertions), total),
            'existing_accuracy_when_asserting': metric(sum(s.claim_assessment == 'correct'
                                                            for s in existing_assertions),
                                                        len(existing_assertions)),
            'repair_assertion_rate': metric(len(repair_assertions), len(repairs)),
            'unsupported_existing_assurance': metric(sum(s.claim_assessment == 'unsupported_assurance'
                                                          for s in scores), total),
            'unsupported_repair_assurance': metric(sum(s.repair_claim_assessment == 'unsupported_assurance'
                                                        for s in repairs), len(repairs)),
            'repair_validity_when_asserting': metric(sum(s.proposed_repair.valid
                                                          for s in repair_assertions),
                                                      len(repair_assertions)),
            'valid_effective_plan': metric(sum(s.effective_plan is not None and s.effective_plan.valid
                                                for s in scores), total),
            'operational_success': metric(sum(s.format_valid and s.effective_plan is not None
                                               and s.effective_plan.valid for s in scores), total),
            'existing_claim_unscored': metric(sum(s.claim_assessment == 'not_evaluated' for s in scores), total),
            'repair_claim_unscored': metric(sum(s.repair_claim_assessment == 'not_evaluated'
                                                 for s in repairs), len(repairs)),
        }
    return results
