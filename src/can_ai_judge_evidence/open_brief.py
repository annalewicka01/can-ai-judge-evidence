"""Less-scaffolded ("open") public brief.

The scaffolded brief names the changing group and outcome and omits the
changing group's target-outcome probability. The open brief removes both cues:
it lists every group's probabilities in the acceptable world and leaves the
changing group to be inferred from the case narrative, which states which
patients the policy leaves unaffected.

Ground truth must stay derivable. Every open projection is closed again with
the hidden change and must pass the scaffolded reconstruction gate.
"""
from collections.abc import Mapping
from math import isclose

from .brief import BriefTarget, public_case_data, validate_public_case
from .case_builder import ChannelBinding, WorldModel
from .domain import ConfigurationError, EvaluationConfig

OPEN_PROBABILITIES = 'probabilities_if_acceptable'


def open_case_data(config: EvaluationConfig, *, world: WorldModel,
                   bindings: tuple[ChannelBinding, ...], target: BriefTarget) -> dict:
    full = public_case_data(config, world=world, bindings=bindings, target=target)
    change = full['deterioration_structure']
    groups = {g.group: g for g in world.groups}
    data = {k: v for k, v in full.items() if k != 'deterioration_structure'}
    data['groups'] = [
        {'group': g['group'], 'size': g['size'], OPEN_PROBABILITIES: {
            o.outcome: o.p0 for o in groups[g['group']].outcomes if o.outcome != change['residual_outcome']}}
        for g in full['groups']]
    validate_open_case(config, data, change)
    return data


def close_case_data(data: Mapping, change: Mapping) -> dict:
    """Inverse projection for authoring gates only; needs the hidden change."""
    event = change['changing_outcome']
    closed = {k: v for k, v in data.items()}
    closed['deterioration_structure'] = dict(change)
    closed['groups'] = [
        {'group': g['group'], 'size': g['size'], 'fixed_probabilities': {
            o: p for o, p in g[OPEN_PROBABILITIES].items()
            if not (g['group'] == change['changing_group'] and o == event)}}
        for g in data['groups']]
    return closed


def validate_open_case(config: EvaluationConfig, data: Mapping, change: Mapping) -> None:
    if 'deterioration_structure' in data:
        raise ConfigurationError('open brief must not name the changing group')
    keys = [set(g.get(OPEN_PROBABILITIES, {})) for g in data['groups']]
    if any(set(g) != {'group', 'size', OPEN_PROBABILITIES} for g in data['groups']) or len(
            {frozenset(k) for k in keys}) != 1:
        raise ConfigurationError('every open group must list the same outcomes (no omission cue)')
    validate_public_case(config, close_case_data(data, change))
    # The listed acceptable-world probabilities must agree with the standard.
    standard = data['standard']
    members = next(p['groups'] for p in data['populations'] if p['population'] == standard['population'])
    groups = {g['group']: g for g in data['groups']}
    size = sum(groups[m]['size'] for m in members)
    rate = sum(groups[m]['size'] * groups[m][OPEN_PROBABILITIES][change['changing_outcome']]
               for m in members) / size
    if not isclose(rate, standard['acceptable_rate'], abs_tol=1e-12, rel_tol=0):
        raise ConfigurationError('listed acceptable-world probabilities disagree with the standard')
