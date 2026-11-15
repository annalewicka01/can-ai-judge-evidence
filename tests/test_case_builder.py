"""Synthetic consistency checks, not the four research cases."""
from dataclasses import replace
import unittest

from can_ai_judge_evidence.case_builder import (
    WorldModel, WorldGroup, WorldOutcome, WorldPopulation, WorldEndpoint,
    ChannelBinding, build_config, assert_offered_pairs, validate_case_pair)
from can_ai_judge_evidence.domain import ConfigurationError, Instrument, Plan


def world_fixture():
    world = WorldModel(
        groups=(
            WorldGroup('seen', 1500, (WorldOutcome('local_event', .02, .02),
                                     WorldOutcome('missed_event', 0, 0), WorldOutcome('none', .98, .98))),
            WorldGroup('unseen', 8500, (WorldOutcome('local_event', 0, 0),
                                       WorldOutcome('missed_event', .005, 70/8500),
                                       WorldOutcome('none', .995, 1-70/8500))),
        ),
        populations=(WorldPopulation('observed', ('seen',)),
                     WorldPopulation('non_referred', ('unseen',)),
                     WorldPopulation('all_triaged', ('seen', 'unseen'), 'iid_mixture')),
        endpoints=(WorldEndpoint('missed_event', ('missed_event',)),
                   WorldEndpoint('local_event', ('local_event',)),
                   WorldEndpoint('any_event', ('local_event', 'missed_event'))),
        outcome_window_months=6,
    )
    instruments = (Instrument('audit', 1., 1., 6, 2, 100, 2, 10000),
                   Instrument('local_records', 1., 1., 6, 0, 0, 0, 10000))
    bindings = (ChannelBinding('audit', 'missed_event', ('observed', 'non_referred', 'all_triaged')),
                ChannelBinding('local_records', 'local_event', ('all_triaged',)))
    return world, instruments, bindings


def built_fixture(**kwargs):
    world, instruments, bindings = world_fixture()
    return build_config(world, instruments, bindings,
                        existing_plan=Plan('audit', 'observed', 500, 9), budget=7700,
                        deadline_month=9, blind_pairs=(('audit', 'observed'),), **kwargs)


class CaseBuilderTests(unittest.TestCase):
    def test_rates_and_capacities_derive_from_one_world(self):
        config = built_fixture()
        target = config.profile('audit', 'non_referred')
        all_patients = config.profile('audit', 'all_triaged')
        self.assertEqual(target.eligible_n, 8500)
        self.assertEqual(all_patients.eligible_n, 10000)
        self.assertAlmostEqual(all_patients.p0, .85 * target.p0)
        self.assertAlmostEqual(all_patients.p1, .85 * target.p1)
        self.assertEqual(config.profile('audit', 'observed').p0, config.profile('audit', 'observed').p1)
        self.assertEqual(config.profile('local_records', 'all_triaged').p0,
                         config.profile('local_records', 'all_triaged').p1)
        adequate = replace(config, existing_plan=Plan('audit', 'non_referred', 3800, 9))
        validate_case_pair(config, adequate, adequate.existing_plan)

    def test_heterogeneous_fixed_counts_are_not_silently_binomial(self):
        world, instruments, bindings = world_fixture()
        world = replace(world, populations=(*world.populations[:2],
                                            replace(world.populations[2], sampling_model='fixed_composition')))
        with self.assertRaisesRegex(ConfigurationError, 'not binomial'):
            build_config(world, instruments, bindings, existing_plan=Plan('audit', 'observed', 500, 9),
                         budget=7700, deadline_month=9)

    def test_world_rejects_inconsistent_atomic_probabilities(self):
        world, instruments, bindings = world_fixture()
        bad_group = replace(world.groups[0], outcomes=(WorldOutcome('local_event', .9, .9),
                                                      WorldOutcome('missed_event', .9, .9),
                                                      WorldOutcome('none', .1, .1)))
        with self.assertRaisesRegex(ConfigurationError, 'sum to one'):
            build_config(replace(world, groups=(bad_group, world.groups[1])), instruments, bindings,
                         existing_plan=Plan('audit', 'observed', 500, 9), budget=7700, deadline_month=9)

    def test_declared_blind_channel_must_be_blind(self):
        world, instruments, bindings = world_fixture()
        with self.assertRaisesRegex(ConfigurationError, 'different observable rates'):
            build_config(world, instruments, bindings, existing_plan=Plan('audit', 'observed', 500, 9),
                         budget=7700, deadline_month=9, blind_pairs=(('audit', 'non_referred'),))

    def test_offer_coverage_gate(self):
        config = built_fixture()
        pairs = tuple((p.channel, p.population) for p in config.profiles)
        assert_offered_pairs(config, pairs)
        for invalid in (pairs[:-1], (*pairs, ('local_records', 'non_referred')), (*pairs, pairs[0])):
            with self.assertRaises(ConfigurationError):
                assert_offered_pairs(config, invalid)

    def test_missing_binding_or_population_is_authoring_error(self):
        world, instruments, bindings = world_fixture()
        for bad in (bindings[:1], (replace(bindings[0], populations=('typo',)), bindings[1]),
                    (replace(bindings[0], endpoint='typo'), bindings[1])):
            with self.assertRaises(ConfigurationError):
                build_config(world, instruments, bad, existing_plan=Plan('audit', 'observed', 500, 9),
                             budget=7700, deadline_month=9)

    def test_pair_gate_rejects_changes_in_world_or_inadequate_reference(self):
        config = built_fixture()
        reference = Plan('audit', 'non_referred', 3800, 9)
        adequate = replace(config, existing_plan=reference)
        with self.assertRaises(ConfigurationError):
            validate_case_pair(config, replace(adequate, budget=7701), reference)
        with self.assertRaises(ConfigurationError):
            validate_case_pair(config, config, reference)
        with self.assertRaises(ConfigurationError):
            validate_case_pair(config, adequate, replace(reference, n=500))
        with self.assertRaises(ConfigurationError):
            validate_case_pair(replace(config, existing_plan=replace(reference, n=500)), adequate, reference)
