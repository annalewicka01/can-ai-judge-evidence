import re
import unittest

from can_ai_judge_evidence.cases import case_pairs, smoke_fixture
from can_ai_judge_evidence.domain import ConfigurationError
from can_ai_judge_evidence.harness import ModelSettings, request_payload
from can_ai_judge_evidence.open_brief import (OPEN_PROBABILITIES, close_case_data, open_case_data,
                                        validate_open_case)
from can_ai_judge_evidence.prompts import ARMS, messages


def opened(case, variant):
    narrative, target = case.brief_inputs('open')
    config = case.config(variant)
    return config, target, open_case_data(config, world=case.world, bindings=case.bindings, target=target)


def change_of(case, target):
    event = next(e for e in case.world.endpoints if e.endpoint == target.endpoint).adverse_outcomes[0]
    return {'changing_group': target.changing_group, 'changing_outcome': event,
            'residual_outcome': target.residual_outcome}


class OpenBriefTests(unittest.TestCase):
    def test_no_changing_group_cue_and_ground_truth_derivable(self):
        for case in (*case_pairs(), smoke_fixture()):
            for variant in ('blind', 'adequate'):
                with self.subTest(case=case.case_id, variant=variant):
                    config, target, data = opened(case, variant)
                    self.assertNotIn('deterioration_structure', data)
                    self.assertEqual(len({frozenset(g[OPEN_PROBABILITIES]) for g in data['groups']}), 1)
                    # Closing with the hidden change reconstructs the evaluator config.
                    validate_open_case(config, data, change_of(case, target))

    def test_every_open_standard_covers_all_patients(self):
        for case in case_pairs():
            _, target = case.brief_inputs('open')
            population = next(p for p in case.world.populations if p.population == target.population)
            self.assertEqual(set(population.groups), {g.group for g in case.world.groups}, case.case_id)

    def test_tampered_open_facts_rejected(self):
        case = case_pairs()[1]
        config, target, data = opened(case, 'blind')
        change = change_of(case, target)
        with self.assertRaises(ConfigurationError):
            validate_open_case(config, {**data, 'deterioration_structure': change}, change)
        cue = [{**g, OPEN_PROBABILITIES: {k: v for k, v in g[OPEN_PROBABILITIES].items()
                                          if not (g['group'] == change['changing_group']
                                                  and k == change['changing_outcome'])}}
               for g in data['groups']]
        with self.assertRaises(ConfigurationError):
            validate_open_case(config, {**data, 'groups': cue}, change)
        wrong = [{**g, OPEN_PROBABILITIES: {**g[OPEN_PROBABILITIES], change['changing_outcome']: .5}}
                 for g in data['groups']]
        with self.assertRaises(ConfigurationError):
            validate_open_case(config, {**data, 'groups': wrong}, change)
        self.assertIn('deterioration_structure', close_case_data(data, change))

    def test_narratives_do_not_name_ids_or_channels(self):
        for case in case_pairs():
            narrative, target = case.brief_inputs('open')
            ids = ({g.group for g in case.world.groups} | {p.population for p in case.world.populations}
                   | {i.channel for i in case.instruments} | {e.endpoint for e in case.world.endpoints})
            for name in ids:
                if '_' in name or name == target.changing_group:
                    self.assertIsNone(re.search(rf'\b{re.escape(name)}\b', narrative), (case.case_id, name))
            for word in ('blind', 'adequate', 'unobservable', 'power', 'sample size', 'linkage',
                         'telephone', 'audit', 'community visit', 'routine records'):
                self.assertNotIn(word, narrative.lower(), (case.case_id, word))
            self.assertIn('unaffected', narrative)

    def test_open_messages_vary_only_by_arm_and_existing_plan(self):
        for case in case_pairs():
            for variant in ('blind', 'adequate'):
                outputs = [messages(case, variant, arm, 'open') for arm in ARMS]
                common = {o[1]['content'].replace(ARMS[arm], '<ARM>') for arm, o in zip(ARMS, outputs)}
                self.assertEqual(len(common), 1)
                text = outputs[0][1]['content']
                self.assertIn(case.open_narrative, text)
                self.assertNotIn(case.narrative, text)
                self.assertNotIn('changing_group', text)
                self.assertNotIn('in the stated group', text)

    def test_brief_setting_selects_request_text(self):
        case = case_pairs()[1]
        scaffolded = request_payload(case, 'blind', 'targeted', ModelSettings('m'))
        opened_request = request_payload(case, 'blind', 'targeted', ModelSettings('m', brief='open'))
        self.assertIn('changing_group', scaffolded['input'][1]['content'])
        self.assertNotIn('changing_group', opened_request['input'][1]['content'])
        self.assertEqual(scaffolded['text'], opened_request['text'])
        with self.assertRaises(ValueError):
            ModelSettings('m', brief='half')
