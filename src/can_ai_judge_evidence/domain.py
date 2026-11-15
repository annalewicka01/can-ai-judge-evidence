"""Validated mathematical inputs. No clinical rate inference or case generation."""
from dataclasses import dataclass, field
from math import isfinite

MAX_COUNT = 2**53 - 1


class ConfigurationError(ValueError):
    """The authored mathematical configuration is inconsistent or malformed."""


def require_integer(value: object, name: str, minimum: int = 0,
                    maximum: int | None = None) -> None:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum or 'unbounded'}], excluding bool")


def require_probability(value: object, name: str) -> None:
    if type(value) not in (int, float) or not 0 <= value <= 1 or not isfinite(value):
        raise ValueError(f"{name} must be a finite probability in [0, 1], excluding bool")


def require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


@dataclass(frozen=True)
class Standard:
    alpha_limit: float = 0.05
    target_power: float = 0.80

    def __post_init__(self) -> None:
        try:
            require_probability(self.alpha_limit, 'alpha_limit')
            require_probability(self.target_power, 'target_power')
            if not 0 < self.alpha_limit < self.target_power <= 1:
                raise ValueError('require 0 < alpha_limit < target_power <= 1')
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc


@dataclass(frozen=True)
class Instrument:
    channel: str
    coverage: float
    sensitivity: float
    outcome_window_months: int
    reporting_delay_months: int
    fixed_cost: int
    per_patient_cost: int
    max_n: int

    def __post_init__(self) -> None:
        try:
            require_text(self.channel, 'channel')
            require_probability(self.coverage, 'coverage')
            require_probability(self.sensitivity, 'sensitivity')
            for name in ('outcome_window_months', 'reporting_delay_months',
                         'fixed_cost', 'per_patient_cost'):
                require_integer(getattr(self, name), name)
            require_integer(self.max_n, 'max_n', maximum=MAX_COUNT)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

    @property
    def q(self) -> float:
        return self.coverage * self.sensitivity

    @property
    def ready_month(self) -> int:
        return self.outcome_window_months + self.reporting_delay_months


@dataclass(frozen=True)
class ObservationProfile:
    channel: str
    population: str
    endpoint: str
    denominator: str
    iid_assumption: str
    outcome_window_months: int
    p0: float
    p1: float
    eligible_n: int

    def __post_init__(self) -> None:
        try:
            for name in ('channel', 'population', 'endpoint', 'denominator', 'iid_assumption'):
                require_text(getattr(self, name), name)
            require_probability(self.p0, 'p0')
            require_probability(self.p1, 'p1')
            if self.p1 < self.p0:
                raise ValueError('p1 must be at least p0')
            require_integer(self.outcome_window_months, 'outcome_window_months')
            require_integer(self.eligible_n, 'eligible_n', maximum=MAX_COUNT)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc


@dataclass(frozen=True)
class Plan:
    channel: str
    population: str
    n: int
    analysis_month: int

    def __post_init__(self) -> None:
        require_text(self.channel, 'channel')
        require_text(self.population, 'population')
        require_integer(self.n, 'n', minimum=1, maximum=MAX_COUNT)
        require_integer(self.analysis_month, 'analysis_month')


@dataclass(frozen=True)
class EvaluationConfig:
    instruments: tuple[Instrument, ...]
    profiles: tuple[ObservationProfile, ...]
    existing_plan: Plan
    budget: int
    deadline_month: int
    standard: Standard = field(default_factory=Standard)

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.instruments, (tuple, list)) or not isinstance(self.profiles, (tuple, list)):
                raise ValueError('instruments and profiles must be sequences')
            object.__setattr__(self, 'instruments', tuple(self.instruments))
            object.__setattr__(self, 'profiles', tuple(self.profiles))
            if not all(isinstance(x, Instrument) for x in self.instruments):
                raise ValueError('instruments must contain Instrument objects')
            if not all(isinstance(x, ObservationProfile) for x in self.profiles):
                raise ValueError('profiles must contain ObservationProfile objects')
            if not isinstance(self.existing_plan, Plan):
                raise ValueError('existing_plan must be a validated Plan')
            if not isinstance(self.standard, Standard):
                raise ValueError('standard must be a validated Standard')
            require_integer(self.budget, 'budget')
            require_integer(self.deadline_month, 'deadline_month')
            ids = [x.channel for x in self.instruments]
            if len(ids) != len(set(ids)):
                raise ValueError('duplicate instrument channel')
            keys = [(x.channel, x.population) for x in self.profiles]
            if len(keys) != len(set(keys)):
                raise ValueError('duplicate observation profile')
            for profile in self.profiles:
                instrument = self.instrument(profile.channel)
                if instrument is None:
                    raise ValueError('profile references unknown instrument')
                if instrument.outcome_window_months != profile.outcome_window_months:
                    raise ValueError('profile and instrument outcome windows differ')
            if self.profile(self.existing_plan.channel, self.existing_plan.population) is None:
                raise ValueError('existing_plan requires a supported observation profile')
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

    def instrument(self, channel: str) -> Instrument | None:
        return next((x for x in self.instruments if x.channel == channel), None)

    def profile(self, channel: str, population: str) -> ObservationProfile | None:
        return next((x for x in self.profiles
                     if x.channel == channel and x.population == population), None)
