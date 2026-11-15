"""Inspectable one-channel feasibility checks; no LLMs or Monte Carlo."""
from dataclasses import dataclass, field

from .domain import EvaluationConfig, Plan
from .power import binomial_power
from .validation import ValidationIssue, parse_plan


@dataclass(frozen=True)
class PlanEvaluation:
    valid: bool
    schema_valid: bool
    plan: Plan | None
    validation_errors: tuple[ValidationIssue, ...]
    failures: tuple[str, ...]
    checks: dict[str, bool | None] = field(default_factory=dict)
    endpoint: str | None = None
    denominator: str | None = None
    iid_assumption: str | None = None
    p0: float | None = None
    p1: float | None = None
    coverage: float | None = None
    sensitivity: float | None = None
    q: float | None = None
    theta0: float | None = None
    theta1: float | None = None
    k_star: int | None = None
    actual_alpha: float | None = None
    power: float | None = None
    cost: int | None = None
    ready_month: int | None = None
    eligible_n: int | None = None
    instrument_max_n: int | None = None
    budget: int | None = None
    deadline_month: int | None = None
    alpha_limit: float = 0.05
    target_power: float = 0.80


def evaluate_plan(config: EvaluationConfig, proposal: object) -> PlanEvaluation:
    """Validate one proposed primary plan and retain every computable failure.

    Unknown profiles prevent power calculation but not independent cost/time
    checks. Malformed plans are never coerced into mathematical inputs.
    """
    if not isinstance(config, EvaluationConfig):
        raise TypeError('config must be an EvaluationConfig')
    plan, issues = parse_plan(proposal)
    details = dict(budget=config.budget, deadline_month=config.deadline_month,
                   alpha_limit=config.standard.alpha_limit, target_power=config.standard.target_power)
    if plan is None:
        failures = ('incomplete_plan',) if any(x.code == 'missing_field' for x in issues) else ('malformed_plan',)
        return PlanEvaluation(False, False, None, issues, failures, **details)

    checks: dict[str, bool | None] = dict.fromkeys((
        'channel_supported', 'profile_supported', 'within_instrument_cap',
        'within_pool', 'within_budget', 'outcomes_ready', 'within_deadline',
        'observable_deterioration', 'alpha_controlled', 'adequate_power'))
    failures: list[str] = []

    def record(check: str, passed: bool, failure: str) -> None:
        checks[check] = bool(passed)
        if not passed:
            failures.append(failure)

    instrument = config.instrument(plan.channel)
    profile = config.profile(plan.channel, plan.population)
    record('channel_supported', instrument is not None, 'unsupported_channel')
    record('profile_supported', profile is not None, 'unsupported_profile')
    record('within_deadline', plan.analysis_month <= config.deadline_month, 'after_deadline')
    if instrument is not None:
        cost = instrument.fixed_cost + instrument.per_patient_cost * plan.n
        details.update(coverage=instrument.coverage, sensitivity=instrument.sensitivity,
                       q=instrument.q, cost=cost, ready_month=instrument.ready_month,
                       instrument_max_n=instrument.max_n)
        record('within_instrument_cap', plan.n <= instrument.max_n, 'sample_exceeds_instrument')
        record('within_budget', cost <= config.budget, 'budget')
        record('outcomes_ready', instrument.ready_month <= plan.analysis_month, 'outcome_not_ready')
    if profile is not None:
        details.update(p0=profile.p0, p1=profile.p1, endpoint=profile.endpoint,
                       denominator=profile.denominator, iid_assumption=profile.iid_assumption,
                       eligible_n=profile.eligible_n)
        record('within_pool', plan.n <= profile.eligible_n, 'sample_exceeds_pool')
    if instrument is not None and profile is not None:
        theta0, theta1 = instrument.q * profile.p0, instrument.q * profile.p1
        stats = binomial_power(plan.n, theta0, theta1, config.standard.alpha_limit)
        details.update(theta0=theta0, theta1=theta1, k_star=stats.k_star,
                       actual_alpha=stats.actual_alpha, power=stats.power)
        record('observable_deterioration', theta1 > theta0, 'unobservable_deterioration')
        record('alpha_controlled', stats.actual_alpha <= config.standard.alpha_limit, 'false_alarm')
        record('adequate_power', stats.power >= config.standard.target_power, 'insufficient_power')
    return PlanEvaluation(all(x is True for x in checks.values()), True, plan, (),
                          tuple(failures), checks, **details)
