"""Uncertainty for small, clustered evaluation results.

An evaluation here has few challenges (often 5 to 20 per level) and ``k`` runs of each.
Runs of the same challenge are correlated: a model that cannot read a function fails it
on every run. Treating all attempts as independent would overstate precision, so every
interval in this module is computed over *challenges*, with the runs of one challenge
folded into its reliability first. This follows the clustered-standard-error approach in
Miller, "Adding Error Bars to Evals: A Statistical Approach to Language Model
Evaluations" (2024).

Only the standard library is used, so the package keeps a single dependency.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

Z_95 = 1.959963984540054

# Two-sided 95% critical values of Student's t by degrees of freedom. Between table
# entries the next lower df is used, which gives a slightly wider, conservative interval.
_T_95: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
    40: 2.021,
    60: 2.000,
    120: 1.980,
}


def t_critical_95(df: int) -> float:
    """Two-sided 95% critical value of Student's t with *df* degrees of freedom."""

    if df < 1:
        raise ValueError("df must be >= 1")
    if df > max(_T_95):
        return Z_95
    return _T_95[max(d for d in _T_95 if d <= df)]


def wilson_interval(p: float, n: float, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion *p* observed over *n* (possibly fractional)."""

    if n <= 0:
        return (0.0, 1.0)
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass(frozen=True)
class RateEstimate:
    """A solve rate with its uncertainty, computed over challenges."""

    rate: float
    """Mean over challenges of per-challenge reliability."""

    se: float | None
    """Standard error over challenges; ``None`` with fewer than two challenges."""

    n_eff: float
    """Effective number of independent observations behind the interval."""

    ci_low: float
    ci_high: float


def estimate_rate(reliabilities: list[float], n_attempts: int) -> RateEstimate:
    """Solve rate and 95% interval from per-challenge reliabilities.

    The rate is the mean reliability, so every challenge weighs the same however many
    valid runs it has. The standard error is the standard deviation of reliabilities over
    the square root of the number of challenges: the clustered standard error of the mean.

    The interval is a Wilson score interval on an effective sample size, so it stays
    inside [0, 1] and does not collapse to a point at 0% or 100%:

    * ``n_eff = p(1-p) / se^2``, bounded to [1, n_attempts], when that is defined;
    * ``n_attempts`` when every challenge has the same, non-extreme reliability;
    * the number of challenges when the rate is 0% or 100%. More runs of the same
      challenges then cannot narrow the interval; only more challenges can.
    """

    c = len(reliabilities)
    if c == 0:
        return RateEstimate(0.0, None, 0.0, 0.0, 1.0)
    p = statistics.fmean(reliabilities)
    se = statistics.stdev(reliabilities) / math.sqrt(c) if c >= 2 else None
    if se is None or p <= 0.0 or p >= 1.0:
        n_eff = float(c)
    elif se == 0.0:
        n_eff = float(n_attempts)
    else:
        n_eff = min(float(n_attempts), max(1.0, p * (1 - p) / (se * se)))
    low, high = wilson_interval(p, n_eff)
    return RateEstimate(p, se, n_eff, low, high)


@dataclass(frozen=True)
class PairedDifference:
    """Mean difference between two models over the challenges both attempted."""

    n_challenges: int
    diff: float
    se: float | None
    ci_low: float | None
    ci_high: float | None


def paired_difference(a: list[float], b: list[float]) -> PairedDifference:
    """Paired comparison of per-challenge reliabilities ``a[i]`` and ``b[i]``.

    Pairing by challenge removes the variance that comes from which challenges happen to
    be in the set, which is usually most of it. The interval uses Student's t with
    ``n - 1`` degrees of freedom. It is ``None`` with fewer than two challenges, and when
    every challenge gave the same difference: a zero-width interval from a handful of
    challenges would claim far more certainty than the data supports.
    """

    if len(a) != len(b):
        raise ValueError("paired samples must have the same length")
    n = len(a)
    if n == 0:
        return PairedDifference(0, 0.0, None, None, None)
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    mean = statistics.fmean(diffs)
    if n < 2:
        return PairedDifference(n, mean, None, None, None)
    se = statistics.stdev(diffs) / math.sqrt(n)
    if se == 0.0:
        return PairedDifference(n, mean, se, None, None)
    half = t_critical_95(n - 1) * se
    return PairedDifference(n, mean, se, max(-1.0, mean - half), min(1.0, mean + half))
