"""Non-randomised one-sided binomial thresholds, using survival functions."""
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import binom

from .domain import MAX_COUNT, require_integer, require_probability


@dataclass(frozen=True)
class PowerResult:
    n: int
    theta0: float
    theta1: float
    alpha_limit: float
    k_star: int
    actual_alpha: float
    power: float


def _validate_probabilities(theta0: float, theta1: float, alpha_limit: float) -> None:
    require_probability(theta0, 'theta0')
    require_probability(theta1, 'theta1')
    require_probability(alpha_limit, 'alpha_limit')
    if theta1 < theta0:
        raise ValueError('theta1 must be at least theta0')
    if not 0 < alpha_limit < 1:
        raise ValueError('alpha_limit must be strictly between 0 and 1')


def _power_arrays(ns: NDArray[np.int64], theta0: float, theta1: float,
                  alpha_limit: float) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
    """Internal vector core. Callers supply already validated positive integer ns.

    Binary search is over count thresholds, whose tails are monotone. It is
    never over sample-size power, which need not be monotone.
    """
    lo = np.ones_like(ns)
    hi = ns + 1
    while np.any(lo < hi):
        mid = lo + (hi - lo) // 2
        acceptable = binom.sf(mid - 1, ns, theta0) <= alpha_limit
        hi = np.where(acceptable, mid, hi)
        lo = np.where(acceptable, lo, mid + 1)
    thresholds = lo
    actual_alpha = np.asarray(binom.sf(thresholds - 1, ns, theta0), dtype=float)
    power = np.asarray(binom.sf(thresholds - 1, ns, theta1), dtype=float)
    previous_tail = binom.sf(thresholds - 2, ns, theta0)
    if (not np.all(np.isfinite(actual_alpha)) or not np.all(np.isfinite(power))
            or np.any(actual_alpha > alpha_limit)
            or np.any((thresholds > 1) & (previous_tail <= alpha_limit))):
        raise ArithmeticError('binomial threshold failed numerical validity/minimality checks')
    return thresholds, actual_alpha, power


def binomial_power(n: int, theta0: float, theta1: float,
                   alpha_limit: float = 0.05) -> PowerResult:
    """Exact-distribution power with float arithmetic and an n+1 sentinel.

    theta0/theta1 are already observed-event probabilities. The caller, not
    this function, applies coverage and sensitivity once.
    """
    require_integer(n, 'n', minimum=1, maximum=MAX_COUNT)
    _validate_probabilities(theta0, theta1, alpha_limit)
    k, alpha, power = _power_arrays(np.array([n], dtype=np.int64), theta0, theta1, alpha_limit)
    return PowerResult(n, theta0, theta1, alpha_limit, int(k[0]), float(alpha[0]), float(power[0]))
