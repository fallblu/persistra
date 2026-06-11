import math

import numpy as np
import pandas as pd
import pytest

from persistra.metrics import perf


def test_annualized_return_matches_compound_definition():
    r = pd.Series([0.01, -0.02, 0.03])
    expected = (1.01 * 0.98 * 1.03) ** (252 / 3) - 1.0
    assert perf.annualized_return(r) == pytest.approx(expected)


def test_annualized_return_nan_on_empty():
    assert math.isnan(perf.annualized_return(pd.Series([], dtype=float)))


def test_annualized_volatility_matches_std_times_sqrt():
    r = pd.Series([0.01, -0.02, 0.03, 0.0])
    expected = float(np.std(r.to_numpy(), ddof=1)) * math.sqrt(252)
    assert perf.annualized_volatility(r) == pytest.approx(expected)


def test_annualized_volatility_nan_with_one_obs():
    assert math.isnan(perf.annualized_volatility(pd.Series([0.01])))


def test_sharpe_matches_definition():
    r = pd.Series([0.01, -0.02, 0.03])
    mean = float(np.mean(r.to_numpy()))
    std = float(np.std(r.to_numpy(), ddof=1))
    expected = mean / std * math.sqrt(252)
    assert perf.sharpe_ratio(r) == pytest.approx(expected)


def test_sharpe_nan_on_zero_volatility():
    assert math.isnan(perf.sharpe_ratio(pd.Series([0.01, 0.01, 0.01])))


def test_sortino_uses_downside_deviation():
    r = pd.Series([0.02, -0.01, 0.03, -0.02])
    downside = np.minimum(r.to_numpy(), 0.0)
    dd = math.sqrt(float(np.mean(downside**2)))
    expected = float(np.mean(r.to_numpy())) / dd * math.sqrt(252)
    assert perf.sortino_ratio(r) == pytest.approx(expected)


def test_max_drawdown_depth_peak_trough():
    eq = pd.Series([100.0, 120.0, 90.0, 150.0], index=pd.date_range("2022-01-03", periods=4))
    depth, peak, trough = perf.max_drawdown(eq)
    assert depth == pytest.approx(-0.25)
    assert peak == eq.index[1]
    assert trough == eq.index[2]


def test_calmar_is_ann_return_over_abs_drawdown():
    r = pd.Series([0.05, -0.20, 0.10, 0.03])
    equity = (1 + r).cumprod()
    depth, _, _ = perf.max_drawdown(equity)
    expected = perf.annualized_return(r) / abs(depth)
    assert perf.calmar_ratio(r) == pytest.approx(expected)


def test_hit_rate_fraction_positive():
    assert perf.hit_rate(pd.Series([0.1, -0.1, 0.2, 0.0])) == pytest.approx(0.5)


def test_turnover_first_row_nan_then_abs_weight_change():
    positions = pd.DataFrame(
        {
            "bar_time": pd.to_datetime(["2022-01-03", "2022-01-03", "2022-01-04", "2022-01-04"]),
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "weight": [0.5, 0.5, 0.7, 0.3],
        }
    )
    t = perf.turnover(positions)
    assert math.isnan(t.iloc[0])
    # |0.7-0.5| + |0.3-0.5| = 0.4
    assert t.iloc[1] == pytest.approx(0.4)


def test_tail_metrics_var_and_cvar():
    r = pd.Series([-0.05, -0.02, 0.0, 0.01, 0.03])
    out = perf.tail_metrics(r, alpha=0.2)
    var = float(np.quantile(r.to_numpy(), 0.2, method="lower"))
    tail = r[r <= var]
    assert out["var"] == pytest.approx(var)
    assert out["cvar"] == pytest.approx(float(tail.mean()))


def test_information_ratio_zero_when_identical_to_benchmark():
    r = pd.Series([0.01, 0.02, -0.01, 0.03])
    assert math.isnan(perf.information_ratio(r, r.copy()))  # zero tracking error -> nan


def test_tracking_error_annualizes_active_return_std():
    r = pd.Series([0.02, -0.01, 0.03, 0.00])
    b = pd.Series([0.01, -0.02, 0.01, 0.01])
    active = r - b
    expected = float(active.std(ddof=1) * math.sqrt(252))
    assert perf.tracking_error(r, b) == pytest.approx(expected)


def test_beta_matches_covariance_over_benchmark_variance():
    r = pd.Series([0.02, -0.01, 0.03, 0.00])
    b = pd.Series([0.01, -0.02, 0.01, 0.01])
    expected = float(r.cov(b) / b.var(ddof=1))
    assert perf.beta(r, b) == pytest.approx(expected)


def test_alpha_matches_annualized_capm_definition():
    r = pd.Series([0.02, -0.01, 0.03, 0.00])
    b = pd.Series([0.01, -0.02, 0.01, 0.01])
    rf = 0.03
    expected = (perf.annualized_return(r) - rf) - perf.beta(r, b) * (perf.annualized_return(b) - rf)
    assert perf.alpha(r, b, risk_free_rate=rf) == pytest.approx(expected)


def test_benchmark_summary_contains_active_metrics():
    strategy_equity = pd.Series([100.0, 102.0, 101.0, 104.0])
    benchmark = pd.Series([100.0, 101.0, 99.0, 100.0])
    out = perf.benchmark_summary(strategy_equity, benchmark)
    assert set(out) == {
        "active_ann_return",
        "alpha",
        "beta",
        "information_ratio",
        "tracking_error",
    }
    assert out["beta"] == pytest.approx(
        perf.beta(strategy_equity.pct_change().dropna(), benchmark.pct_change().dropna())
    )


def test_exposure_stats_keys_and_means():
    ec = pd.DataFrame({"gross_exposure": [1.0, 1.0], "net_exposure": [0.0, 0.2]})
    out = perf.exposure_stats(ec)
    assert set(out) == {"gross_mean", "gross_std", "net_mean", "net_std"}
    assert out["gross_mean"] == pytest.approx(1.0)
    assert out["net_mean"] == pytest.approx(0.1)
