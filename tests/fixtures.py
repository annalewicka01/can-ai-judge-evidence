"""Synthetic unit-test inputs only. These are NOT benchmark clinical cases."""
from dataclasses import replace

from can_ai_judge_evidence.domain import EvaluationConfig, Instrument, ObservationProfile, Plan, Standard


def make_config(*, existing_n=500, budget=7700, deadline=9,
                instrument_changes=None, profile_changes=None, standard=None):
    instrument = Instrument('audit', 1., 1., 6, 2, 100, 2, 8500)
    instrument = replace(instrument, **(instrument_changes or {}))
    profile = ObservationProfile(
        'audit', 'target', 'Synthetic binary event', 'Attempted target patients',
        'Independent Bernoulli outcomes in hypothetical repeated cohorts.',
        instrument.outcome_window_months, .005, 70/8500, 8500)
    profile = replace(profile, **(profile_changes or {}))
    blind = replace(profile, population='observed', p0=.02, p1=.02,
                    denominator='Attempted observed-group patients')
    return EvaluationConfig((instrument,), (profile, blind),
                            Plan('audit', 'target', existing_n, 9),
                            budget, deadline, standard or Standard())


def proposal(n=3800, month=9, population='target', channel='audit'):
    return dict(channel=channel, population=population, n=n, analysis_month=month)


def answer(claim='no', change=None, repair_claim='yes'):
    return dict(existing_plan_meets_standard=claim, required_change=change,
                required_change_meets_standard=repair_claim if change is not None else None,
                optional_suggestions='', rationale='Synthetic response for unit testing.')
