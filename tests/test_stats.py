from __future__ import annotations

import pytest

from bineval.stats import (
    Z_95,
    estimate_rate,
    paired_difference,
    t_critical_95,
    wilson_interval,
)


@pytest.mark.parametrize(("df", "t"), [(1, 12.706), (4, 2.776), (30, 2.042), (35, 2.042)])
def test_t_critical_uses_table_and_rounds_df_down(df, t):
    assert t_critical_95(df) == t


def test_t_critical_large_df_is_normal():
    assert t_critical_95(10_000) == Z_95


def test_t_critical_rejects_zero_df():
    with pytest.raises(ValueError):
        t_critical_95(0)


def test_wilson_known_value():
    low, high = wilson_interval(0.5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_wilson_at_zero_is_not_a_point():
    low, high = wilson_interval(0.0, 5)
    assert low == 0.0
    assert high == pytest.approx(Z_95**2 / (5 + Z_95**2))


def test_wilson_without_data_is_uninformative():
    assert wilson_interval(0.0, 0) == (0.0, 1.0)


def test_zero_rate_interval_depends_on_challenges_not_runs():
    three_runs = estimate_rate([0.0] * 5, n_attempts=15)
    ten_runs = estimate_rate([0.0] * 5, n_attempts=50)
    assert three_runs.n_eff == ten_runs.n_eff == 5
    assert three_runs.ci_high == ten_runs.ci_high > 0.4
    assert estimate_rate([0.0] * 20, n_attempts=60).ci_high < three_runs.ci_high


def test_rate_is_mean_reliability_with_clustered_se():
    est = estimate_rate([1.0, 0.0], n_attempts=6)
    assert est.rate == 0.5
    assert est.se == pytest.approx(0.5)
    # p(1-p)/se^2 = 1: two perfectly split challenges are worth about one observation.
    assert est.n_eff == pytest.approx(1.0)
    assert est.ci_low < 0.1 and est.ci_high > 0.9


def test_identical_partial_reliabilities_use_all_attempts():
    est = estimate_rate([1 / 3] * 4, n_attempts=12)
    assert est.se == 0.0
    assert est.n_eff == 12


def test_single_challenge_has_no_se():
    est = estimate_rate([2 / 3], n_attempts=3)
    assert est.se is None
    assert est.n_eff == 1


def test_empty_estimate():
    est = estimate_rate([], n_attempts=0)
    assert (est.rate, est.se, est.ci_low, est.ci_high) == (0.0, None, 0.0, 1.0)


def test_paired_difference_known_value_and_clipping():
    d = paired_difference([1.0, 1.0, 0.5], [0.0, 0.5, 0.5])
    assert d.n_challenges == 3
    assert d.diff == pytest.approx(0.5)
    assert d.se == pytest.approx(0.5 / 3**0.5)
    assert d.ci_low == pytest.approx(0.5 - 4.303 * 0.5 / 3**0.5)
    assert d.ci_high == 1.0


def test_paired_difference_without_variation_has_no_interval():
    d = paired_difference([1.0, 1.0], [0.0, 0.0])
    assert d.diff == 1.0 and d.se == 0.0
    assert d.ci_low is None and d.ci_high is None


def test_paired_difference_needs_two_challenges():
    d = paired_difference([1.0], [0.0])
    assert d.se is None and d.ci_low is None


def test_paired_difference_lengths_must_match():
    with pytest.raises(ValueError):
        paired_difference([1.0], [])
