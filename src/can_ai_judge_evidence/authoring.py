"""Offline authoring gates and answer-key diagnostics; never model input."""
from dataclasses import asdict

from .brief import public_case_data, validate_public_case
from .open_brief import open_case_data
from .case_builder import assert_offered_pairs, validate_case_pair
from .cases import CasePair, case_pairs
from .diagnostic import diagnose_sample_size
from .domain import ConfigurationError, Plan
from .evaluator import evaluate_plan


def audit_case(case: CasePair) -> dict:
    blind, adequate = (case.config(v) for v in ('blind', 'adequate'))
    validate_case_pair(blind, adequate, case.reference_repair)
    public = []
    for config in (blind, adequate):
        assert_offered_pairs(config, case.offered_pairs)
        facts = public_case_data(config, world=case.world, bindings=case.bindings, target=case.target)
        validate_public_case(config, facts)
        public.append({k: v for k, v in facts.items() if k != 'existing_plan'})
    if public[0] != public[1]:
        raise ConfigurationError('public pair differs beyond existing_plan')
    _, open_target = case.brief_inputs('open')
    opened = [{k: v for k, v in open_case_data(c, world=case.world, bindings=case.bindings,
                                               target=open_target).items() if k != 'existing_plan'}
              for c in (blind, adequate)]
    if opened[0] != opened[1]:
        raise ConfigurationError('open pair differs beyond existing_plan')
    diagnostics, feasible = [], []
    for channel, population in case.offered_pairs:
        # Power is unchanged by later analysis. Earliest ready time establishes
        # feasibility over ALL analysis months, not just the reference month.
        instrument = blind.instrument(channel)
        diagnostic = diagnose_sample_size(blind, Plan(channel, population, 1, instrument.ready_month))
        if diagnostic.rescue_exists is None:
            raise ConfigurationError('offered design feasibility was not resolved')
        if diagnostic.rescue_exists:
            feasible.append((channel, population))
        diagnostics.append({'channel': channel, 'population': population, **asdict(diagnostic)})
    if set(feasible) != set(case.expected_feasible_pairs):
        raise ConfigurationError(f'{case.case_id}: feasible pairs {feasible} differ from author assertion')
    reference = evaluate_plan(blind, case.reference_repair)
    adequate_result = evaluate_plan(adequate, adequate.existing_plan)
    if min(reference.power, adequate_result.power) < blind.standard.target_power + .05:
        raise ConfigurationError('reference/adequate power must have at least .05 headroom')
    return {'case_id': case.case_id, 'split': case.split, 'title': case.title,
            'blind': asdict(evaluate_plan(blind, blind.existing_plan)),
            'adequate': asdict(adequate_result), 'reference_repair': asdict(reference),
            'designs': diagnostics, 'feasible_pairs': feasible}


def audit_suite(cases: tuple[CasePair, ...] | None = None) -> dict:
    cases = case_pairs() if cases is None else cases
    if (len(cases) != 5 or sum(c.split == 'development' for c in cases) != 1
            or sum(c.split == 'evaluation' for c in cases) != 4
            or len({c.case_id for c in cases}) != 5):
        raise ConfigurationError('suite requires one development and four evaluation pairs with unique IDs')
    reports = [audit_case(c) for c in cases]
    winners = [r['feasible_pairs'] for r in reports]
    if any(len(w) != 1 for w in winners) or len({w[0][0] for w in winners}) != 5:
        raise ConfigurationError('each case must require a different uniquely feasible channel')
    return {'synthetic': True, 'human_review_complete': False, 'pairs': reports}
