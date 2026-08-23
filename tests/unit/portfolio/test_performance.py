"""Tests for reconciled portfolio performance reports."""

from typing import cast

import numpy as np
import pandas as pd
import pytest

from persistra.portfolio import (
    BacktestResult,
    BacktestTiming,
    backtest_portfolio,
    portfolio_performance_report,
)


def backtest_result() -> BacktestResult:
    """Return a small strategy and benchmark with known paths."""
    index = pd.date_range("2025-01-01", periods=4)
    returns = pd.DataFrame(
        {"a": [0.10, -0.05, 0.02, 0.03], "b": [0.02, 0.01, -0.01, 0.00]},
        index=index,
    )
    targets = pd.DataFrame([[1.0, 0.0]], index=index[:1], columns=returns.columns)
    return backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(0, 0, signal_available_before_trade=True),
        transaction_cost_bps=10.0,
        benchmarks={"asset_b": pd.Series({"a": 0.0, "b": 1.0})},
    )


def test_performance_report_matches_reference_values_and_reconciles() -> None:
    result = backtest_result()
    report = portfolio_performance_report(
        result,
        periods_per_year=4.0,
        risk_free_returns=0.001,
    )
    returns = result.returns.to_numpy()
    excess = returns - 0.001
    expected_annual_return = np.prod(1.0 + returns) - 1.0
    expected_volatility = np.std(returns, ddof=1) * 2.0

    assert report.summary["annualized_return"] == pytest.approx(expected_annual_return)
    assert report.summary["annualized_volatility"] == pytest.approx(expected_volatility)
    assert report.summary["sharpe_ratio"] == pytest.approx(
        np.mean(excess) * 2.0 / np.std(excess, ddof=1)
    )
    assert report.summary["maximum_drawdown"] == pytest.approx(result.drawdown.min())
    assert report.summary["maximum_drawdown_duration"] == 3.0
    assert report.summary["total_turnover"] == pytest.approx(result.turnover.sum())
    assert report.summary["total_cost_drag"] == pytest.approx(result.costs.sum())
    assert report.attribution["gross_return"] - report.attribution["total_cost"] == (
        pytest.approx(report.attribution["net_return"])
    )
    assert report.attribution["asset_return"] + report.attribution["cash_return"] == (
        pytest.approx(report.attribution["gross_return"])
    )
    assert report.coverage["return_coverage"] == 1.0
    assert report.coverage["buy_cost_coverage"] == 1.0
    assert report.risk_free_returns.eq(0.001).all()


def test_benchmark_report_matches_relative_path_statistics() -> None:
    result = backtest_result()
    report = portfolio_performance_report(
        result,
        periods_per_year=4.0,
        risk_free_returns=pd.Series(0.0, index=result.returns.index),
    )
    benchmark = result.benchmark_returns["asset_b"]
    active = result.returns - benchmark
    expected_tracking_error = active.std(ddof=1) * 2.0
    row = report.benchmarks.loc["asset_b"]

    assert cast("float", row["benchmark_annualized_return"]) == pytest.approx(
        np.prod(1.0 + benchmark) - 1.0
    )
    assert cast("float", row["annualized_relative_return"]) == pytest.approx(
        np.prod(1.0 + result.returns) / np.prod(1.0 + benchmark) - 1.0
    )
    assert cast("float", row["tracking_error"]) == pytest.approx(expected_tracking_error)
    assert cast("float", row["information_ratio"]) == pytest.approx(
        active.mean() * 4.0 / expected_tracking_error
    )
    assert cast("float", row["correlation"]) == pytest.approx(
        result.returns.corr(benchmark)
    )


def test_performance_report_requires_explicit_valid_assumptions() -> None:
    result = backtest_result()
    with pytest.raises(ValueError, match="periods_per_year"):
        portfolio_performance_report(
            result, periods_per_year=0.0, risk_free_returns=0.0
        )
    with pytest.raises(ValueError, match="return index"):
        portfolio_performance_report(
            result,
            periods_per_year=252.0,
            risk_free_returns=pd.Series(0.0, index=result.returns.index[::-1]),
        )
    with pytest.raises(ValueError, match="finite"):
        portfolio_performance_report(
            result, periods_per_year=252.0, risk_free_returns=np.nan
        )
    with pytest.raises(TypeError, match="numeric"):
        portfolio_performance_report(
            result, periods_per_year=252.0, risk_free_returns=True
        )


def test_report_owns_outputs_and_handles_no_benchmarks() -> None:
    result = backtest_result()
    no_benchmark = backtest_portfolio(
        result.target_weights,
        returns=pd.DataFrame(
            0.0,
            index=result.returns.index,
            columns=result.target_weights.columns,
        ),
    )
    report = portfolio_performance_report(
        no_benchmark, periods_per_year=12.0, risk_free_returns=0.0
    )
    assert report.benchmarks.empty
    assert pd.isna(report.summary["sharpe_ratio"])
    assert pd.isna(report.summary["sortino_ratio"])
    assert pd.isna(report.summary["calmar_ratio"])
    no_benchmark.returns.iloc[0] = 0.5
    assert report.summary["annualized_return"] == 0.0
