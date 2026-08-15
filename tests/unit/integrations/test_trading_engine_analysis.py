# pyright: reportGeneralTypeIssues=false
"""Tests for Trading Engine execution and strategy-performance analysis."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    ExecutionAnalysisPolicy,
    analyze_execution,
    compare_execution,
)
from persistra.portfolio import backtest_portfolio

if TYPE_CHECKING:
    from persistra.integrations.trading_engine.model import ExecutionReplayResult


def test_execution_analysis_reports_lifecycle_quantity_fees_and_slippage(
    execution_replay: ExecutionReplayResult,
) -> None:
    result = analyze_execution(execution_replay)
    lifecycle = result.lifecycle_summary.loc["engine"]

    assert lifecycle["submitted_orders"] == 3
    assert lifecycle["accepted_orders"] == 2
    assert lifecycle["rejected_orders"] == 1
    assert lifecycle["intent_rejections"] == 1
    assert lifecycle["cancelled_orders"] == 1
    assert lifecycle["orders_with_fills"] == 2
    assert lifecycle["completely_filled_orders"] == 1
    assert lifecycle["acceptance_rate"] == pytest.approx(2 / 3)
    assert lifecycle["complete_fill_rate"] == pytest.approx(0.5)
    assert lifecycle["accepted_quantity"] == 14
    assert lifecycle["filled_quantity"] == 10
    assert lifecycle["quantity_fill_rate"] == pytest.approx(10 / 14)
    assert lifecycle["filled_notional"] == 1038
    assert lifecycle["total_fees"] == pytest.approx(1.538)
    assert lifecycle["decision_close_slippage_bps"] == pytest.approx(-6 / 1044 * 10_000)
    assert lifecycle["eligible_open_slippage_bps"] == 0
    assert lifecycle["mean_bars_to_first_fill"] == 1

    orders = result.order_diagnostics.set_index("order_id")
    assert orders.loc["order-1", "final_status"] == "cancelled"
    assert orders.loc["order-1", "unfilled_quantity"] == 4
    assert orders.loc["order-1", "quantity_fill_rate"] == pytest.approx(0.6)
    assert orders.loc["order-rejected", "final_status"] == "rejected"
    assert pd.isna(orders.loc["order-rejected", "quantity_fill_rate"])
    assert orders.loc["order-2", "average_fill_price"] == 105

    fills = result.fill_diagnostics.set_index("fill_id")
    assert fills.loc["fill-1", "decision_close"] == 104
    assert fills.loc["fill-1", "eligible_open"] == 103
    assert fills.loc["fill-1", "decision_to_fill_bar_open_adverse_cost"] == -6
    assert fills.loc[
        "fill-1", "decision_to_fill_bar_open_slippage_bps"
    ] == pytest.approx(-6 / (6 * 104) * 10_000)
    assert fills.loc["fill-1", "eligible_open_adverse_cost"] == 0
    assert fills.loc["fill-1", "bar_volume_participation"] == pytest.approx(0.5)


def test_execution_performance_is_event_time_and_annualization_is_opt_in(
    execution_replay: ExecutionReplayResult,
) -> None:
    unscaled = analyze_execution(execution_replay)
    summary = unscaled.performance_summary.loc["engine"]

    assert summary["valuation_observations"] == 4
    assert summary["return_observations"] == 4
    assert summary["initial_equity"] == 10_000
    assert summary["terminal_equity"] == pytest.approx(10_012.462)
    assert summary["net_pnl"] == pytest.approx(12.462)
    assert summary["total_return"] == pytest.approx(0.0012462)
    assert pd.isna(summary["annualized_return"])
    assert pd.isna(summary["annualized_volatility"])
    assert pd.isna(summary["sharpe_ratio"])
    assert pd.isna(summary["sortino_ratio"])
    assert summary["max_drawdown"] < 0
    assert summary["max_drawdown_duration_observations"] == 2
    assert summary["total_fees"] == pytest.approx(1.538)
    assert summary["fee_reconciliation_difference"] == pytest.approx(0)
    assert unscaled.performance_path.loc[0, "return"] == 0

    first_valuation = analyze_execution(
        execution_replay,
        policy=ExecutionAnalysisPolicy(initial_equity="first_valuation"),
    )
    assert pd.isna(first_valuation.performance_path.loc[0, "return"])
    assert first_valuation.performance_summary.loc["engine", "return_observations"] == 3

    scaled = analyze_execution(
        execution_replay,
        policy=ExecutionAnalysisPolicy(periods_per_year=252),
    ).performance_summary.loc["engine"]
    assert np.isfinite(scaled["annualized_return"])
    assert np.isfinite(scaled["annualized_volatility"])
    assert np.isfinite(scaled["sharpe_ratio"])
    assert np.isfinite(scaled["sortino_ratio"])


def test_execution_performance_supports_explicit_initial_equity_and_turnover(
    execution_replay: ExecutionReplayResult,
) -> None:
    policy = ExecutionAnalysisPolicy(
        initial_equity=9_900.0,
        turnover_denominator="initial_equity",
    )
    result = analyze_execution(execution_replay, policy=policy)
    summary = result.performance_summary.loc["engine"]

    assert result.performance_path.loc[0, "return"] == pytest.approx(100 / 9_900)
    assert summary["return_observations"] == 4
    assert summary["executed_notional_turnover"] == pytest.approx(1038 / 9_900)

    with pytest.raises(ValueError, match="annual rates require periods_per_year"):
        ExecutionAnalysisPolicy(annual_risk_free_rate=0.02)
    with pytest.raises(ValueError, match="initial_equity"):
        ExecutionAnalysisPolicy(initial_equity=0.0)


def test_terminal_comparison_reconciles_currency_pnl_without_calling_residual_slippage(
    execution_replay: ExecutionReplayResult,
) -> None:
    index = pd.date_range("2026-01-02", periods=4)
    returns = pd.DataFrame({"acme": [0.0, 0.002, 0.0, 0.0]}, index=index)
    targets = pd.DataFrame({"acme": [1.0]}, index=index[:1])
    vectorized = backtest_portfolio(targets, returns=returns, initial_equity=100.0)
    execution = analyze_execution(execution_replay)

    comparison = compare_execution(vectorized, execution)

    assert comparison.terminal_summary.loc[
        "vectorized_close_to_close", "terminal_equity"
    ] == pytest.approx(10_020)
    assert comparison.terminal_summary.loc[
        "engine_event_driven", "terminal_equity"
    ] == pytest.approx(10_012.462)
    assert comparison.pnl_bridge.loc[
        "decision_to_fill_bar_open_timing", "pnl"
    ] == pytest.approx(6)
    assert comparison.pnl_bridge.loc["eligible_open_fill_price", "pnl"] == 0
    assert comparison.pnl_bridge.loc["engine_fees", "pnl"] == pytest.approx(-1.538)
    assert comparison.pnl_bridge.loc[
        "unfilled_exposure_and_model_residual", "pnl"
    ] == pytest.approx(-12)
    assert comparison.pnl_bridge["pnl"].sum() == pytest.approx(12.462)
    assert "not pure slippage" in comparison.caveat
    assert comparison.policy.vectorized_return_basis == "persistra_close_to_close"


def test_multi_asset_decision_reference_uses_latest_instrument_bar_at_global_anchor(
    execution_replay: ExecutionReplayResult,
) -> None:
    bars = execution_replay.bars.copy()
    bars["source_sequence"] = pd.array([1, 3, 4, 5], dtype="Int64")
    other = bars.iloc[[0]].copy()
    other["source_sequence"] = pd.array([2], dtype="Int64")
    other["instrument_id"] = "beta"
    other["open"] = 50.0
    other["close"] = 51.0
    bars = pd.concat([bars, other], ignore_index=True).sort_values("source_sequence")
    orders = execution_replay.orders.copy()
    orders["eligible_after_bar_sequence"] = pd.array([2, 2, 4], dtype="Int64")
    fills = execution_replay.fills.copy()
    fills["bar_sequence"] = pd.array([3, 5], dtype="Int64")
    replay = replace(execution_replay, bars=bars, orders=orders, fills=fills)

    result = analyze_execution(replay)
    first_fill = result.fill_diagnostics.set_index("fill_id").loc["fill-1"]
    first_order = result.order_diagnostics.set_index("order_id").loc["order-1"]

    assert first_fill["decision_anchor_sequence"] == 2
    assert first_fill["decision_bar_sequence"] == 1
    assert first_fill["decision_close"] == 104
    assert first_order["bars_to_first_fill"] == 1


def test_analysis_rejects_missing_scenario_cash_and_broken_event_links(
    execution_replay: ExecutionReplayResult,
) -> None:
    no_cash = replace(execution_replay, initial_cash=None)
    with pytest.raises(ValueError, match="scenario initial cash"):
        analyze_execution(no_cash)

    fills = execution_replay.fills.copy()
    fills.loc[0, "order_id"] = "missing"
    broken = replace(execution_replay, fills=fills)
    with pytest.raises(ValueError, match="unknown order_id"):
        analyze_execution(broken)
