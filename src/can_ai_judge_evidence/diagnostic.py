"""Exhaustive integer search at fixed instrument, population and timing."""
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .domain import EvaluationConfig, require_integer
from .evaluator import evaluate_plan
from .power import _power_arrays

DEFAULT_MAX_SEARCH_N = 100_000


@dataclass(frozen=True)
class SampleSizeDiagnostic:
    status: Literal['feasible', 'infeasible', 'not_evaluable', 'search_limit_exceeded']
    rescue_exists: bool | None
    smallest_feasible_n: int | None = None
    best_power: float | None = None
    max_candidate_n: int | None = None
    obstructions: tuple[str, ...] = ()
    eligible_n: int | None = None
    instrument_max_n: int | None = None
    affordable_n: int | None = None
    # affordable_n=None means cost imposes no n cap (zero marginal cost).
    best_power_upper_bound: float | None = None
    search_limit: int = DEFAULT_MAX_SEARCH_N


def diagnose_sample_size(config: EvaluationConfig, proposal: object, *,
                         max_search_n: int = DEFAULT_MAX_SEARCH_N) -> SampleSizeDiagnostic:
    require_integer(max_search_n, 'max_search_n', minimum=1)
    evaluation = evaluate_plan(config, proposal)
    if not evaluation.schema_valid:
        return SampleSizeDiagnostic('not_evaluable', None, obstructions=('malformed_plan',))
    plan = evaluation.plan
    assert plan is not None
    instrument = config.instrument(plan.channel)
    profile = config.profile(plan.channel, plan.population)
    if instrument is None or profile is None:
        reasons = tuple(x for x in evaluation.failures if x.startswith('unsupported_'))
        return SampleSizeDiagnostic('not_evaluable', None, obstructions=reasons)

    obstructions = [x for x in evaluation.failures if x in ('outcome_not_ready', 'after_deadline')]
    remaining = config.budget - instrument.fixed_cost
    if remaining < 0:
        affordable = 0
        obstructions.append('fixed_cost_exceeds_budget')
    elif instrument.per_patient_cost == 0:
        affordable = None
    else:
        affordable = remaining // instrument.per_patient_cost
    caps = [profile.eligible_n, instrument.max_n]
    if affordable is not None:
        caps.append(affordable)
    cap = min(caps)
    details = dict(max_candidate_n=cap, eligible_n=profile.eligible_n,
                   instrument_max_n=instrument.max_n, affordable_n=affordable,
                   search_limit=max_search_n)
    if cap < 1:
        obstructions.append('no_admissible_positive_sample')
    if obstructions:
        return SampleSizeDiagnostic('infeasible', False, obstructions=tuple(obstructions), **details)

    theta0, theta1 = instrument.q * profile.p0, instrument.q * profile.p1
    if theta0 == theta1:
        # This is a proof of infeasibility, not an incomplete numerical search.
        # The maximum attained alpha is unknown without enumeration.
        exact_zero = theta0 in (0., 1.)
        return SampleSizeDiagnostic(
            'infeasible', False, best_power=0. if exact_zero else None,
            best_power_upper_bound=0. if exact_zero else config.standard.alpha_limit,
            obstructions=('unobservable_deterioration',), **details)
    if cap > max_search_n:
        return SampleSizeDiagnostic('search_limit_exceeded', None,
                                    obstructions=('search_limit_exceeded',), **details)
    first: int | None = None
    best = 0.
    for start in range(1, cap + 1, 4096):
        ns = np.arange(start, min(start + 4096, cap + 1), dtype=np.int64)
        _, alphas, powers = _power_arrays(ns, theta0, theta1, config.standard.alpha_limit)
        best = max(best, float(np.max(powers)))
        feasible = (alphas <= config.standard.alpha_limit) & (powers >= config.standard.target_power)
        if first is None and np.any(feasible):
            first = int(ns[np.flatnonzero(feasible)[0]])
    if first is not None:
        return SampleSizeDiagnostic('feasible', True, first, best, **details)
    reasons = ['no_sample_size_meets_standard']
    if theta0 == theta1:
        reasons.append('unobservable_deterioration')
    return SampleSizeDiagnostic('infeasible', False, best_power=best,
                                obstructions=tuple(reasons), **details)
