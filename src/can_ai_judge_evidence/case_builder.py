"""Derive all offered profiles from one explicit, categorical two-world model.

This is case-authoring infrastructure, not a set of benchmark clinical cases.
Every group's mutually exclusive outcomes partition probability one in each
world; endpoints are projections of those same outcomes.
"""
from dataclasses import dataclass, replace
from fractions import Fraction

from .domain import (MAX_COUNT, ConfigurationError, EvaluationConfig, Instrument,
                     ObservationProfile, Plan, Standard, require_integer,
                     require_probability, require_text)
from .evaluator import evaluate_plan


@dataclass(frozen=True)
class WorldOutcome:
    outcome: str
    p0: float
    p1: float


@dataclass(frozen=True)
class WorldGroup:
    group: str
    size: int
    outcomes: tuple[WorldOutcome, ...]


@dataclass(frozen=True)
class WorldEndpoint:
    endpoint: str
    adverse_outcomes: tuple[str, ...]


@dataclass(frozen=True)
class WorldPopulation:
    population: str
    groups: tuple[str, ...]
    sampling_model: str = 'fixed_composition'


@dataclass(frozen=True)
class WorldModel:
    groups: tuple[WorldGroup, ...]
    populations: tuple[WorldPopulation, ...]
    endpoints: tuple[WorldEndpoint, ...]
    outcome_window_months: int


@dataclass(frozen=True)
class ChannelBinding:
    channel: str
    endpoint: str
    populations: tuple[str, ...]


def _unique(items, key, description):
    result = {}
    for item in items:
        name = getattr(item, key)
        require_text(name, description)
        if name in result:
            raise ConfigurationError(f'duplicate {description}: {name}')
        result[name] = item
    if not result:
        raise ConfigurationError(f'empty {description} collection')
    return result


def assert_offered_pairs(config: EvaluationConfig, offered_pairs) -> None:
    """Gate independently declared menu pairs against evaluator support."""
    pairs = tuple(offered_pairs)
    if len(pairs) != len(set(pairs)):
        raise ConfigurationError('duplicate offered channel/population pair')
    actual = {(p.channel, p.population) for p in config.profiles}
    if set(pairs) != actual:
        raise ConfigurationError('offered pairs must exactly match evaluator profiles')


def build_config(world: WorldModel, instruments: tuple[Instrument, ...],
                 bindings: tuple[ChannelBinding, ...], *, existing_plan: Plan,
                 budget: int, deadline_month: int, standard: Standard | None = None,
                 blind_pairs: tuple[tuple[str, str], ...] = ()) -> EvaluationConfig:
    """Rates and caps are derived, never accepted as separate profile inputs.

    Fixed unequal-risk strata cannot be collapsed into an exact binomial.
    iid_mixture must be explicitly selected to use the unconditional marginal
    model (group sizes then provide planning weights/caps, not fixed realised
    stratum counts). All endpoints share one cohort outcome window.
    """
    try:
        require_integer(world.outcome_window_months, 'outcome_window_months')
        groups = _unique(world.groups, 'group', 'group')
        populations = _unique(world.populations, 'population', 'population')
        endpoints = _unique(world.endpoints, 'endpoint', 'endpoint')
        channels = _unique(instruments, 'channel', 'instrument')
        bound_channels = _unique(bindings, 'channel', 'binding')
        if set(channels) != set(bound_channels):
            raise ConfigurationError('every instrument must have exactly one binding')
        distributions = {}
        outcome_ids = None
        for group in groups.values():
            require_integer(group.size, 'group size', minimum=1, maximum=MAX_COUNT)
            outcomes = _unique(group.outcomes, 'outcome', 'outcome')
            if outcome_ids is None:
                outcome_ids = set(outcomes)
            elif set(outcomes) != outcome_ids:
                raise ConfigurationError('all groups must use the same atomic outcome IDs (zero probabilities allowed)')
            for outcome in outcomes.values():
                require_probability(outcome.p0, 'outcome p0')
                require_probability(outcome.p1, 'outcome p1')
            worlds = []
            for name in ('p0', 'p1'):
                probabilities = {k: Fraction(str(getattr(v, name))) for k, v in outcomes.items()}
                total = sum(probabilities.values())
                if abs(total - 1) > Fraction(1, 10**12):
                    raise ConfigurationError('atomic outcome probabilities must sum to one in each group/world')
                # Normalize only rounding-scale deviations, then use rational
                # projection arithmetic so identical distributions stay equal.
                worlds.append({k: v / total for k, v in probabilities.items()})
            distributions[group.group] = worlds
        for endpoint in endpoints.values():
            selected = endpoint.adverse_outcomes
            if (not selected or len(selected) != len(set(selected))
                    or not set(selected) <= outcome_ids):
                raise ConfigurationError('endpoint requires unique known adverse outcome IDs')
        for population in populations.values():
            members = population.groups
            if (not members or len(members) != len(set(members))
                    or not set(members) <= set(groups)):
                raise ConfigurationError('population requires unique known groups')
            if population.sampling_model not in ('fixed_composition', 'iid_mixture'):
                raise ConfigurationError('unknown sampling_model')
        profiles, offered = [], []
        for binding in bindings:
            instrument = channels[binding.channel]
            if instrument.outcome_window_months != world.outcome_window_months:
                raise ConfigurationError('instrument and world outcome windows differ')
            if binding.endpoint not in endpoints:
                raise ConfigurationError('binding has unknown endpoint')
            if (not binding.populations or len(binding.populations) != len(set(binding.populations))
                    or not set(binding.populations) <= set(populations)):
                raise ConfigurationError('binding requires unique known populations')
            endpoint = endpoints[binding.endpoint]
            for pop_id in binding.populations:
                population = populations[pop_id]
                members = [groups[g] for g in population.groups]
                size = sum(g.size for g in members)
                group_rates = [tuple(sum(distributions[g.group][w][o] for o in endpoint.adverse_outcomes)
                                     for w in (0, 1)) for g in members]
                if population.sampling_model == 'fixed_composition' and len(set(group_rates)) > 1:
                    raise ConfigurationError('heterogeneous fixed-composition population is not binomial; '
                                             'use a justified iid_mixture or omit this pair')
                rates = [sum(g.size * p[w] for g, p in zip(members, group_rates)) / size for w in (0, 1)]
                if rates[1] < rates[0]:
                    raise ConfigurationError('offered endpoint must be an adverse event with nondecreasing rate')
                iid = ('Independent patients with group drawn afresh using the stated planning weights; '
                       'not conditional on fixed realised group counts.'
                       if population.sampling_model == 'iid_mixture' else
                       'Independent patients with identical endpoint probabilities across the selected groups.')
                profiles.append(ObservationProfile(
                    binding.channel, pop_id, endpoint.endpoint, f'Attempted patients in {pop_id}',
                    iid, world.outcome_window_months, float(rates[0]), float(rates[1]), size))
                offered.append((binding.channel, pop_id))
        config = EvaluationConfig(instruments, tuple(profiles), existing_plan, budget,
                                  deadline_month, standard or Standard())
        assert_offered_pairs(config, offered)
        for channel, population in blind_pairs:
            profile = config.profile(channel, population)
            instrument = config.instrument(channel)
            if profile is None or instrument is None:
                raise ConfigurationError('declared blind pair must be offered')
            if instrument.q * profile.p0 != instrument.q * profile.p1:
                raise ConfigurationError('declared blind pair has different observable rates across worlds')
        return config
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def validate_case_pair(inadequate: EvaluationConfig, adequate: EvaluationConfig,
                       reference_repair: Plan) -> None:
    """Fail before prompting if paired monitoring proposals violate the design."""
    if replace(adequate, existing_plan=inadequate.existing_plan) != inadequate:
        raise ConfigurationError('paired configurations may differ only in the existing plan')
    flawed = evaluate_plan(inadequate, inadequate.existing_plan)
    if flawed.valid or flawed.theta0 is None or flawed.theta0 != flawed.theta1:
        raise ConfigurationError('flawed monitoring must have identical observable distributions')
    if not evaluate_plan(adequate, adequate.existing_plan).valid:
        raise ConfigurationError('adequate monitoring must meet the standard')
    if not evaluate_plan(inadequate, reference_repair).valid:
        raise ConfigurationError('reference repair must meet budget, timing, population and statistical requirements')
