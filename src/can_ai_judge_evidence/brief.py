"""Public case facts, separate from evaluator profiles and derived answers.

The weekend authoring path supports one changing adverse outcome in one group,
balanced by one residual outcome. Other probabilities are fixed. Reject more
complex worlds rather than silently omitting facts needed to derive a rate.
"""
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from math import isclose

from .case_builder import (ChannelBinding, WorldEndpoint, WorldGroup, WorldModel,
                           WorldOutcome, WorldPopulation, build_config)
from .domain import (ConfigurationError, EvaluationConfig, Instrument, Plan,
                     Standard, require_probability)


@dataclass(frozen=True)
class BriefTarget:
    endpoint: str
    population: str
    changing_group: str
    residual_outcome: str


def _keys(value, expected, name):
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ConfigurationError(f'{name} has missing or forbidden fields')


def _probability(value):
    require_probability(value, 'public probability')
    return Fraction(str(value))


def _check_same_config(expected, actual):
    # Reconstructing from a displayed marginal probability may round at the last
    # bit. This tolerance is ONLY for authoring consistency, never plan scoring.
    if replace(actual, profiles=expected.profiles) != expected:
        raise ConfigurationError('public facts differ from evaluator configuration')
    originals = {(p.channel, p.population): p for p in expected.profiles}
    reconstructed = {(p.channel, p.population): p for p in actual.profiles}
    if originals.keys() != reconstructed.keys():
        raise ConfigurationError('public offered pairs differ from evaluator profiles')
    for pair, p in originals.items():
        r = reconstructed[pair]
        if (replace(r, p0=p.p0, p1=p.p1) != p
                or not isclose(r.p0, p.p0, abs_tol=1e-12, rel_tol=0)
                or not isclose(r.p1, p.p1, abs_tol=1e-12, rel_tol=0)):
            raise ConfigurationError(f'public facts do not reconstruct profile {pair}')


def public_case_data(config: EvaluationConfig, *, world: WorldModel,
                     bindings: tuple[ChannelBinding, ...], target: BriefTarget) -> dict:
    """Build an allowlisted public projection and verify its sufficiency.

    The standard appears once. No per-pair p0/p1, power, validity labels,
    blindness labels or reference repair is exported. Numeric coincidence with
    a hidden derived rate is allowed; the field's provenance is what matters.
    """
    rebuilt = build_config(world, config.instruments, bindings,
                           existing_plan=config.existing_plan, budget=config.budget,
                           deadline_month=config.deadline_month, standard=config.standard)
    _check_same_config(config, rebuilt)
    endpoints = {e.endpoint: e for e in world.endpoints}
    populations = {p.population: p for p in world.populations}
    groups = {g.group: g for g in world.groups}
    endpoint = endpoints.get(target.endpoint)
    population = populations.get(target.population)
    if (endpoint is None or len(endpoint.adverse_outcomes) != 1
            or population is None or target.changing_group not in population.groups):
        raise ConfigurationError('public target requires one atomic endpoint and a member changing group')
    event = endpoint.adverse_outcomes[0]
    residual = target.residual_outcome
    outcome_ids = {o.outcome for o in world.groups[0].outcomes}
    if residual not in outcome_ids or residual == event:
        raise ConfigurationError('public target requires a distinct known residual outcome')
    for group in world.groups:
        for o in group.outcomes:
            may_change = group.group == target.changing_group and o.outcome in (event, residual)
            if not may_change and o.p0 != o.p1:
                raise ConfigurationError('public brief supports only the declared single-group deterioration')

    # Derive the target standard, not a menu of channel-specific rates.
    size = sum(groups[g].size for g in population.groups)
    rates = []
    for name in ('p0', 'p1'):
        total = Fraction(0)
        for group_id in population.groups:
            group = groups[group_id]
            probs = {o.outcome: _probability(getattr(o, name)) for o in group.outcomes}
            total += group.size * probs[event] / sum(probs.values())
        rates.append(float(total / size))
    if rates[1] <= rates[0]:
        raise ConfigurationError('target standard must specify an increased adverse-event rate')
    bound = {b.channel: b for b in bindings}
    data = {
        'standard': {'endpoint': target.endpoint, 'population': target.population,
                     'acceptable_rate': rates[0], 'deterioration_to_detect': rates[1],
                     'alpha_limit': config.standard.alpha_limit,
                     'target_power': config.standard.target_power},
        'deterioration_structure': {'changing_group': target.changing_group,
                                    'changing_outcome': event, 'residual_outcome': residual},
        'groups': [
            {'group': g.group, 'size': g.size,
             'fixed_probabilities': {o.outcome: o.p0 for o in g.outcomes
                                     if o.outcome != residual and not
                                     (g.group == target.changing_group and o.outcome == event)}}
            for g in world.groups],
        'populations': [asdict(p) for p in world.populations],
        'endpoints': [asdict(e) for e in world.endpoints],
        'channels': [{**asdict(i), 'endpoint': bound[i.channel].endpoint,
                      'populations': bound[i.channel].populations} for i in config.instruments],
        'existing_plan': asdict(config.existing_plan),
        'outcome_window_months': world.outcome_window_months,
        'budget': config.budget, 'deadline_month': config.deadline_month,
    }
    validate_public_case(config, data)
    return data


def config_from_public_case(data: Mapping) -> EvaluationConfig:
    """Reconstruct using ONLY public facts; also enforce the projection allowlist.

    This is a case gate, not a tool provided to the evaluated model.
    """
    try:
        _keys(data, ('standard', 'deterioration_structure', 'groups', 'populations',
                     'endpoints', 'channels', 'existing_plan', 'outcome_window_months',
                     'budget', 'deadline_month'), 'public case')
        standard = data['standard']
        _keys(standard, ('endpoint', 'population', 'acceptable_rate', 'deterioration_to_detect',
                         'alpha_limit', 'target_power'), 'standard')
        change = data['deterioration_structure']
        _keys(change, ('changing_group', 'changing_outcome', 'residual_outcome'), 'deterioration structure')
        event, residual = change['changing_outcome'], change['residual_outcome']
        if event == residual:
            raise ConfigurationError('changing and residual outcomes must differ')
        populations = []
        for p in data['populations']:
            _keys(p, ('population', 'groups', 'sampling_model'), 'population')
            populations.append(WorldPopulation(p['population'], tuple(p['groups']), p['sampling_model']))
        endpoints = []
        for e in data['endpoints']:
            _keys(e, ('endpoint', 'adverse_outcomes'), 'endpoint')
            endpoints.append(WorldEndpoint(e['endpoint'], tuple(e['adverse_outcomes'])))
        target_population = next(p for p in populations if p.population == standard['population'])
        target_endpoint = next(e for e in endpoints if e.endpoint == standard['endpoint'])
        if (target_endpoint.adverse_outcomes != (event,)
                or change['changing_group'] not in target_population.groups):
            raise ConfigurationError('inconsistent public target')
        group_inputs = {}
        for g in data['groups']:
            _keys(g, ('group', 'size', 'fixed_probabilities'), 'group')
            if g['group'] in group_inputs or not isinstance(g['fixed_probabilities'], Mapping):
                raise ConfigurationError('duplicate group or malformed fixed probabilities')
            group_inputs[g['group']] = g
        all_outcomes = {event, residual}
        for g in group_inputs.values():
            all_outcomes.update(g['fixed_probabilities'])
        for g in group_inputs.values():
            expected = all_outcomes - {residual}
            if g['group'] == change['changing_group']:
                expected = expected - {event}
            _keys(g['fixed_probabilities'], expected, 'fixed probabilities')
            for probability in g['fixed_probabilities'].values():
                _probability(probability)

        changed = group_inputs[change['changing_group']]
        total_size = sum(group_inputs[g]['size'] for g in target_population.groups)
        fixed_mass = sum(group_inputs[g]['size'] * _probability(group_inputs[g]['fixed_probabilities'][event])
                         for g in target_population.groups if g != change['changing_group'])
        target_rates = [_probability(standard[k]) for k in ('acceptable_rate', 'deterioration_to_detect')]
        if target_rates[1] <= target_rates[0]:
            raise ConfigurationError('target deterioration must increase')
        changing_rates = [(r * total_size - fixed_mass) / changed['size'] for r in target_rates]
        groups = []
        for g in group_inputs.values():
            worlds = []
            for w in (0, 1):
                probabilities = {o: _probability(p) for o, p in g['fixed_probabilities'].items()}
                if g['group'] == change['changing_group']:
                    probabilities[event] = changing_rates[w]
                probabilities[residual] = 1 - sum(probabilities.values())
                worlds.append(probabilities)
            groups.append(WorldGroup(g['group'], g['size'], tuple(
                WorldOutcome(o, float(worlds[0][o]), float(worlds[1][o])) for o in sorted(all_outcomes))))
        instruments, bindings = [], []
        instrument_keys = tuple(Instrument.__dataclass_fields__)
        for i in data['channels']:
            _keys(i, (*instrument_keys, 'endpoint', 'populations'), 'channel')
            instruments.append(Instrument(**{k: i[k] for k in instrument_keys}))
            bindings.append(ChannelBinding(i['channel'], i['endpoint'], tuple(i['populations'])))
        _keys(data['existing_plan'], ('channel', 'population', 'n', 'analysis_month'), 'existing plan')
        return build_config(
            WorldModel(tuple(groups), tuple(populations), tuple(endpoints), data['outcome_window_months']),
            tuple(instruments), tuple(bindings), existing_plan=Plan(**data['existing_plan']),
            budget=data['budget'], deadline_month=data['deadline_month'],
            standard=Standard(standard['alpha_limit'], standard['target_power']))
    except (ValueError, TypeError, KeyError, StopIteration, ZeroDivisionError) as exc:
        raise ConfigurationError(f'invalid public case: {exc}') from exc


def validate_public_case(config: EvaluationConfig, data: Mapping) -> None:
    """Fail on forbidden fields, missing assumptions or inconsistent public facts."""
    _check_same_config(config, config_from_public_case(data))
