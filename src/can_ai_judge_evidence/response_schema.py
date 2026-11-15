"""Portable transport schema and public-only case instructions."""
import json

from .brief import BriefTarget, public_case_data
from .case_builder import WorldModel, ChannelBinding
from .domain import MAX_COUNT, EvaluationConfig


def response_schema(config: EvaluationConfig) -> dict:
    pairs = sorted({(p.channel, p.population) for p in config.profiles})
    plans = [{
        'type': 'object', 'additionalProperties': False,
        'required': ['channel', 'population', 'n', 'analysis_month'],
        'properties': {
            'channel': {'type': 'string', 'enum': [c]},
            'population': {'type': 'string', 'enum': [p]},
            'n': {'type': 'integer', 'description': f'Attempted patients, from 1 through {MAX_COUNT}.'},
            'analysis_month': {'type': 'integer', 'description': 'Non-negative integer month.'},
        },
    } for c, p in pairs]
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['existing_plan_meets_standard', 'required_change',
                     'required_change_meets_standard', 'optional_suggestions', 'rationale'],
        'properties': {
            'existing_plan_meets_standard': {'type': 'string', 'enum': ['yes', 'no', 'needs_verification']},
            'required_change': {'anyOf': [{'type': 'null'}, *plans]},
            'required_change_meets_standard': {
                'type': ['string', 'null'], 'enum': ['yes', 'needs_verification', None],
                'description': 'Null exactly when required_change is null; otherwise yes or needs_verification.'},
            'optional_suggestions': {'type': 'string'},
            'rationale': {'type': 'string', 'description': 'At most 150 whitespace-separated words.'},
        },
    }


SCAFFOLDED_CHANGE = (
    'The standard specifies one target endpoint and denominator. The hypothetical deterioration '
    'changes only the stated outcome in the stated group, balanced by the residual outcome. '
    'All listed fixed probabilities stay unchanged. In each group the residual outcome '
    'has the remaining probability so the mutually exclusive outcomes sum to one. '
    'Derive any channel-specific event rates from these facts.')
OPEN_CHANGE = (
    'The standard specifies one target endpoint and denominator. Group probabilities are listed '
    'for the acceptable world. In the hypothetical deteriorating world, the target outcome rises '
    'in exactly one group, the one the scenario does not describe as unaffected, until the '
    "standard population's rate equals deterioration_to_detect; the residual outcome \"neither\" "
    'absorbs the change. All other listed probabilities stay unchanged. In each group the residual '
    'outcome has the remaining probability so the mutually exclusive outcomes sum to one. '
    'Derive any channel-specific event rates from these facts.')


def model_contract(config: EvaluationConfig, *, world: WorldModel,
                   bindings: tuple[ChannelBinding, ...], target: BriefTarget,
                   brief: str = 'scaffolded') -> str:
    """Shared instructions; refuse the former evaluator-only input path.

    Only the validated public projection is serialized. Never dump config,
    profiles, reference repairs or evaluator diagnostics into a prompt.
    """
    if brief == 'scaffolded':
        facts = public_case_data(config, world=world, bindings=bindings, target=target)
        change_line = SCAFFOLDED_CHANGE
    elif brief == 'open':
        from .open_brief import open_case_data
        facts = open_case_data(config, world=world, bindings=bindings, target=target)
        change_line = OPEN_CHANGE
    else:
        raise ValueError('brief must be scaffolded or open')
    lines = [
        'One cohort starts at month 0. All endpoints are adverse events; the alternative is an increased rate.',
        'Use one one-sided exact binomial alarm: the smallest count k for which P_null(X >= k) <= alpha.',
        'The null is the fixed acceptable threshold; the deterioration rate is the design alternative, '
        'not a statement of the current true rate.',
        'Capture is independent of outcome risk; sensitivity is conditional on capture; false positives are absent.',
        'Observed probabilities are coverage * sensitivity * endpoint probability. n is attempted patients.',
        'Enter n and analysis_month as JSON integer literals. For a census, enter the eligible count, not "all".',
        'A required_change is one complete replacement monitoring plan, not an addition. '
        'The budget covers that single plan; sunk costs are excluded.',
        'Do not combine channels, add samples across cohorts, or change the outcome window by waiting longer.',
        'Budget is in smallest currency units; the deadline is a month from cohort origin.',
        'Results are ready at outcome_window_months + reporting_delay_months.',
        'Use only the listed channel/population pairs and their exact IDs. '
        'Population group sizes give eligible counts and planning weights. '
        'For iid_mixture, each patient independently draws a group using these weights; '
        'realised stratum counts are not fixed. For fixed_composition, selected groups '
        'have identical event probabilities for the offered endpoint.',
        change_line,
        'The proposal states that its existing monitoring plan meets the standard. Assess that claim.',
        'If required_change is null, required_change_meets_standard must be null. '
        'Otherwise state yes or needs_verification for the proposed replacement.',
        'Optional suggestions do not alter the required plan. Rationale: at most 150 whitespace-separated words.',
        'Case facts (design assumptions, not observed current outcome rates):',
        json.dumps(facts, indent=2, allow_nan=False),
    ]
    return '\n'.join(lines)
