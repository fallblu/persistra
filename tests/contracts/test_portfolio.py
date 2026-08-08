"""Contract tests for portfolio construction and backtest accounting."""

import numpy as np
import pandas as pd
import pytest

from persistra.portfolio import (
    BacktestTiming,
    PortfolioConstraints,
    backtest_portfolio,
    construct_portfolio,
)


@pytest.mark.contract
def test_portfolio_result_schemas_and_accounting_reconcile() -> None:
    index = pd.date_range("2025-01-01", periods=5)
    columns = ["a", "b", "c", "d"]
    signals = pd.DataFrame(
        [[1.0, 2.0, -1.0, -2.0], [2.0, 1.0, -2.0, -1.0]],
        index=index[[0, 2]],
        columns=columns,
    )
    returns = pd.DataFrame(
        [
            [0.01, 0.00, -0.01, 0.02],
            [0.02, 0.01, 0.00, -0.01],
            [-0.01, 0.02, 0.01, 0.00],
            [0.00, -0.01, 0.02, 0.01],
            [0.01, 0.01, -0.01, -0.01],
        ],
        index=index,
        columns=columns,
    )
    construction = construct_portfolio(
        signals,
        weighting="signal_proportional",
        configuration="long_short",
        constraints=PortfolioConstraints(
            gross_limit=1.0,
            net_minimum=0.0,
            net_maximum=0.0,
            position_limit=0.4,
        ),
    )
    result = backtest_portfolio(
        construction,
        returns=returns,
        transaction_cost_bps=5.0,
        benchmarks={
            "static_equal_weight": pd.Series(0.25, index=columns),
            "naive_signal": construction.unconstrained_weights,
        },
    )

    assert construction.exposures.columns.tolist() == ["long", "short", "gross", "net", "cash"]
    assert construction.constraint_utilization.columns.tolist() == [
        "gross",
        "net",
        "position",
        "turnover",
        "volatility",
    ]
    assert result.realized_weights.index.equals(returns.index)
    assert result.realized_weights.columns.equals(returns.columns)
    assert result.exposures.columns.tolist() == ["long", "short", "gross", "net", "cash"]
    assert result.rebalance_log.columns.tolist() == [
        "signal_observation",
        "decision",
        "holding_start",
        "holding_end",
        "status",
        "blocked_assets",
    ]
    assert np.allclose(result.realized_weights.sum(axis="columns").add(result.cash), 1.0)
    assert np.allclose(result.ending_weights.sum(axis="columns").add(result.ending_cash), 1.0)
    assert np.allclose(
        result.asset_return_attribution.sum(axis="columns").add(
            result.cash_return_attribution
        ),
        result.gross_returns,
    )
    assert np.allclose(result.gross_returns.sub(result.costs), result.returns)
    assert np.allclose(result.cost_attribution.sum(axis="columns"), result.costs)
    assert np.allclose(
        result.returns.add(1.0).cumprod().mul(result.initial_equity),
        result.equity,
    )


@pytest.mark.contract
def test_target_timing_contract_is_causal_by_default() -> None:
    index = pd.date_range("2025-01-01", periods=3)
    returns = pd.DataFrame([[0.10], [0.20], [0.30]], index=index, columns=["asset"])
    targets = pd.DataFrame([[1.0]], index=index[:1], columns=returns.columns)

    default = backtest_portfolio(targets, returns=returns)
    proved = backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(execution_lag=0, signal_available_before_trade=True),
    )

    assert default.returns.tolist() == pytest.approx([0.0, 0.20, 0.30])
    assert proved.returns.tolist() == pytest.approx([0.10, 0.20, 0.30])
    assert default.rebalance_log.iloc[0]["holding_start"] == index[1]
    assert proved.rebalance_log.iloc[0]["holding_start"] == index[0]
