"""Orthogonal response facts. No text inference or model-based judging."""
from collections.abc import Mapping
from dataclasses import dataclass

from .diagnostic import SampleSizeDiagnostic, diagnose_sample_size
from .domain import EvaluationConfig
from .evaluator import PlanEvaluation, evaluate_plan
from .validation import ValidationIssue, field_issues

_FIELDS = {'existing_plan_meets_standard', 'required_change',
           'required_change_meets_standard', 'optional_suggestions', 'rationale'}
_CLAIMS = ('yes', 'no', 'needs_verification')


@dataclass(frozen=True)
class ResponseScore:
    format_valid: bool
    format_errors: tuple[ValidationIssue, ...]
    claim_assessment: str
    unnecessary_escalation: bool | None
    missing_required_change: bool | None
    internally_inconsistent: bool | None
    existing_plan: PlanEvaluation
    proposed_repair: PlanEvaluation | None
    effective_plan: PlanEvaluation | None
    sample_size_diagnostic: SampleSizeDiagnostic | None
    repair_claim_assessment: str = 'not_evaluated'
    existing_claim: str | None = None
    repair_claim: str | None = None
    change_present: bool | None = None
    failure_category: str | None = None
    effective_plan_failure_category: str | None = None


def classify_failure(evaluation: PlanEvaluation | None,
                     diagnostic: SampleSizeDiagnostic | None) -> str | None:
    """Prespecified descriptive hierarchy; direct failures remain available.

    The residual statistical/search cases are not evidence of a budget failure.
    Budget/capacity refers only to the fixed design, not the whole case.
    """
    if evaluation is not None and evaluation.valid:
        return None
    if (evaluation is None or not evaluation.schema_valid
            or any(x.startswith('unsupported_') for x in evaluation.failures)):
        return 'incomplete_or_unsupported'
    if diagnostic is not None and diagnostic.rescue_exists is True:
        return 'sample_size'
    if 'unobservable_deterioration' in evaluation.failures:
        return 'unobservable_channel'
    if any(x in evaluation.failures for x in ('outcome_not_ready', 'after_deadline')):
        return 'timing'
    if (diagnostic is None or diagnostic.status in ('not_evaluable', 'search_limit_exceeded')
            or 'false_alarm' in evaluation.failures):
        return 'unresolved'
    if diagnostic.status == 'infeasible':
        return 'budget_or_capacity'
    return 'unresolved'


def score_response(config: EvaluationConfig, response: object) -> ResponseScore:
    existing = evaluate_plan(config, config.existing_plan)
    if not isinstance(response, Mapping):
        issue = ValidationIssue('response', 'wrong_type', 'Expected one decoded response object')
        return ResponseScore(False, (issue,), 'not_evaluated', None, None, None,
                             existing, None, None, None,
                             failure_category='incomplete_or_unsupported',
                             effective_plan_failure_category='incomplete_or_unsupported')
    errors = field_issues(response, _FIELDS)
    raw_claim = response.get('existing_plan_meets_standard')
    claim = raw_claim if isinstance(raw_claim, str) and raw_claim in _CLAIMS else None
    if 'existing_plan_meets_standard' in response and claim is None:
        errors.append(ValidationIssue('existing_plan_meets_standard', 'invalid_value',
                                      'Expected yes, no, or needs_verification'))
    for name in ('optional_suggestions', 'rationale'):
        if name in response:
            value = response[name]
            if not isinstance(value, str):
                errors.append(ValidationIssue(name, 'wrong_type', 'Expected a string'))
            elif name == 'rationale' and len(value.split()) > 150:
                errors.append(ValidationIssue(name, 'too_long', 'Maximum 150 whitespace-separated words'))

    change_present: bool | None = None
    repair = effective = None
    if 'required_change' in response:
        change_present = response['required_change'] is not None
        if change_present:
            # Internal typed Plans are supported by evaluate_plan, but a model
            # response must contain a decoded JSON object, not a Python object.
            raw_change = response['required_change']
            repair = evaluate_plan(config, raw_change if isinstance(raw_change, Mapping) else None)
            effective = repair
            errors.extend(ValidationIssue('required_change.' + x.field, x.code, x.message)
                          for x in repair.validation_errors)
            if repair.schema_valid:
                for name, check in (('channel', 'channel_supported'),
                                    ('population', 'profile_supported')):
                    if repair.checks[check] is False:
                        errors.append(ValidationIssue('required_change.' + name,
                                                      'unsupported_id', 'Not an offered channel/population pair'))
        else:
            effective = existing

    raw_repair_claim = response.get('required_change_meets_standard')
    repair_claim = (raw_repair_claim if isinstance(raw_repair_claim, str)
                    and raw_repair_claim in ('yes', 'needs_verification') else None)
    repair_assessment = 'not_evaluated'
    if 'required_change_meets_standard' in response:
        if change_present is False:
            if raw_repair_claim is not None:
                errors.append(ValidationIssue('required_change_meets_standard', 'invalid_value',
                                              'Must be null when required_change is null'))
            else:
                repair_assessment = 'not_applicable'
        elif change_present is True:
            if repair_claim is None:
                errors.append(ValidationIssue('required_change_meets_standard', 'invalid_value',
                                              'Expected yes or needs_verification for a proposed change'))
            elif repair_claim == 'needs_verification':
                repair_assessment = 'acknowledged_uncertainty'
            else:
                # Unsupported includes an unevaluable assurance; it does not
                # assert that an unknown design has been disproved statistically.
                repair_assessment = 'correct' if repair.valid else 'unsupported_assurance'

    if claim is None:
        assessment = 'not_evaluated'
    elif claim == 'needs_verification':
        assessment = 'acknowledged_uncertainty'
    elif (claim == 'yes') == existing.valid:
        assessment = 'correct'
    else:
        assessment = 'unsupported_assurance' if claim == 'yes' else 'incorrect_rejection'

    escalation = None if change_present is None else existing.valid and change_present
    missing = None if change_present is None else not existing.valid and not change_present
    inconsistent = None if change_present is None or claim is None else claim == 'yes' and change_present
    diagnostic = None
    if effective is not None and not effective.valid:
        if not effective.schema_valid:
            diagnostic = SampleSizeDiagnostic('not_evaluable', None, obstructions=('malformed_plan',))
        else:
            raw_effective = response['required_change'] if change_present else config.existing_plan
            diagnostic = diagnose_sample_size(config, raw_effective)
    effective_failure = classify_failure(effective, diagnostic)
    # An explicit null on an invalid existing plan is an omitted repair, not a
    # proposed underpowered/blind design. Preserve the retained-plan diagnostic.
    failure = 'no_change_proposed' if missing is True else effective_failure
    return ResponseScore(not errors, tuple(errors), assessment, escalation, missing, inconsistent,
                         existing, repair, effective, diagnostic, repair_assessment, claim,
                         repair_claim, change_present, failure, effective_failure)
