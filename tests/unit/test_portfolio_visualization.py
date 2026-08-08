"""Artist-level tests for portfolio and backtest visualizations."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.dates import ConciseDateFormatter

from persistra.portfolio import (
    BacktestPolicies,
    BacktestResult,
    PortfolioConstructionResult,
    PortfolioRiskControl,
    backtest_portfolio,
    construct_portfolio,
)
from persistra.viz import (
    plot_backtest_drawdowns,
    plot_backtest_performance,
    plot_backtest_returns,
    plot_backtest_rolling_volatility,
    plot_constraint_utilization,
    plot_cost_attribution,
    plot_portfolio_exposures,
    plot_portfolio_turnover,
    plot_portfolio_weights,
    plot_predicted_volatility,
    plot_rebalance_diagnostics,
    plot_return_attribution,
    plot_risk_contributions,
    plot_transaction_costs,
)


def portfolio_results() -> tuple[PortfolioConstructionResult, BacktestResult]:
    """Return deterministic construction and backtest results with all diagnostics."""
    index = pd.bdate_range("2025-01-01", periods=9)
    columns = ["a", "b", "c"]
    signal_dates = index[[0, 3, 5]]
    signals = pd.DataFrame(
        [[1.0, 2.0, 3.0], [3.0, 1.0, 2.0], [1.0, 3.0, 2.0]],
        index=signal_dates,
        columns=columns,
    )
    covariance = pd.DataFrame(np.eye(3) * 0.04, index=columns, columns=columns)
    construction = construct_portfolio(
        signals,
        weighting="signal_proportional",
        covariances={date: covariance for date in signal_dates},
        risk_control=PortfolioRiskControl(
            target_volatility=0.1,
            volatility_limit=0.15,
            periods_per_year=1,
        ),
    )
    returns = pd.DataFrame(
        np.array(
            [
                [0.01, 0.00, -0.01],
                [0.02, 0.01, 0.00],
                [-0.01, 0.02, 0.01],
                [0.00, -0.01, 0.02],
                [0.03, 0.00, -0.01],
                [-0.02, 0.01, 0.00],
                [0.01, 0.02, -0.01],
                [0.00, -0.01, 0.01],
                [0.02, 0.00, 0.01],
            ]
        ),
        index=index,
        columns=columns,
    )
    tradeable = pd.DataFrame(True, index=index, columns=columns)
    tradeable.loc[index[4], "a"] = False
    backtest = backtest_portfolio(
        construction,
        returns=returns,
        transaction_cost_bps=pd.Series({"a": 10.0, "b": 15.0, "c": 20.0}),
        tradeable=tradeable,
        policies=BacktestPolicies(nontradeable="hold"),
        benchmarks={"Equal weight": pd.Series(1 / 3, index=columns)},
        initial_equity=100.0,
    )
    return construction, backtest


def test_construction_plots_cover_weights_exposures_limits_and_risk() -> None:
    construction, _ = portfolio_results()
    _, supplied = plt.subplots()

    axes = [
        plot_portfolio_weights(construction, ax=supplied),
        plot_portfolio_weights(construction, kind="unconstrained"),
        plot_portfolio_exposures(construction),
        plot_constraint_utilization(construction),
        plot_predicted_volatility(construction),
        plot_risk_contributions(construction),
        plot_portfolio_turnover(construction),
    ]

    assert all(isinstance(axis, Axes) for axis in axes)
    assert axes[0] is supplied
    assert {line.get_label() for line in axes[0].lines[:4]} >= {"a", "b", "c", "Cash"}
    assert "Limit" in {
        text.get_text()
        for text in axes[3].get_legend().get_texts()  # type: ignore[union-attr]
    }
    assert {line.get_label() for line in axes[4].lines} >= {"Predicted", "Target", "Limit"}
    plt.close("all")


def test_backtest_path_plots_preserve_benchmarks_timing_and_explicit_risk_parameters() -> None:
    _, backtest = portfolio_results()

    returns = plot_backtest_returns(backtest)
    performance = plot_backtest_performance(backtest)
    drawdowns = plot_backtest_drawdowns(backtest)
    volatility = plot_backtest_rolling_volatility(backtest, window=3, periods_per_year=252)

    assert {line.get_label() for line in returns.lines[:2]} == {"Portfolio", "Equal weight"}
    assert "execution lag 1" in performance.get_title()
    assert len(drawdowns.lines) == 3
    assert "3-observation window" in volatility.get_title()
    assert volatility.get_ylabel() == "Annualized volatility"
    plt.close("all")


def test_backtest_cost_and_attribution_plots_reconcile_asset_and_group_views() -> None:
    _, backtest = portfolio_results()
    groups = {"a": "Growth", "b": "Growth", "c": "Defensive"}

    turnover = plot_portfolio_turnover(backtest)
    costs = plot_transaction_costs(backtest)
    assets = plot_return_attribution(backtest)
    grouped = plot_return_attribution(backtest, groups=groups)
    cost_groups = plot_cost_attribution(backtest, groups=groups)

    assert turnover.get_ylabel() == "One-way turnover"
    assert costs.get_title() == "Linear transaction costs"
    assert {line.get_label() for line in assets.lines[:-1]} >= {"a", "b", "c"}
    assert {line.get_label() for line in grouped.lines[:-1]} >= {
        "Growth",
        "Defensive",
        "Cash",
    }
    assert cost_groups.get_title() == "Group cost attribution"
    plt.close("all")


def test_weight_and_rebalance_diagnostics_distinguish_targets_realized_and_blocks() -> None:
    _, backtest = portfolio_results()

    target = plot_portfolio_weights(backtest, kind="target")
    realized = plot_portfolio_weights(backtest, kind="realized")
    ending = plot_portfolio_weights(backtest, kind="ending")
    diagnostics = plot_rebalance_diagnostics(backtest)

    assert np.asarray(target.lines[0].get_xdata()).size == len(backtest.target_weights)
    assert np.asarray(realized.lines[0].get_xdata()).size == len(backtest.realized_weights)
    assert ending.get_title() == "Ending weights"
    assert diagnostics.collections
    assert "a" in {text.get_text() for text in diagnostics.texts}
    assert diagnostics.get_xlabel() == "First holding period"
    assert isinstance(diagnostics.xaxis.get_major_formatter(), ConciseDateFormatter)
    plt.close("all")


def test_portfolio_plots_reject_unavailable_risk_and_incomplete_group_mappings() -> None:
    construction, backtest = portfolio_results()
    no_risk = construct_portfolio(construction.weights)

    with pytest.raises(ValueError, match="no predicted volatility"):
        plot_predicted_volatility(no_risk)
    with pytest.raises(ValueError, match="no risk contributions"):
        plot_risk_contributions(no_risk)
    with pytest.raises(ValueError, match="map every attribution asset"):
        plot_return_attribution(backtest, groups={"a": "Group"})
    with pytest.raises(ValueError, match="support target or unconstrained"):
        plot_portfolio_weights(construction, kind="realized")
    plt.close("all")
