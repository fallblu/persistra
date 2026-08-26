# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportArgumentType=false
"""Trace- and layout-level tests for portfolio and backtest visualizations."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

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


def assert_title_and_legend_are_separated(chart: go.Figure) -> None:
    """Require the shared title and legend to occupy distinct top regions."""
    assert chart.layout.title.y == 0.98
    assert chart.layout.title.yanchor == "top"
    assert chart.layout.legend.yref == "container"
    assert chart.layout.legend.y == 0.90
    assert chart.layout.legend.yanchor == "top"
    assert chart.layout.margin.t == 120


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

    figures = [
        plot_portfolio_weights(construction),
        plot_portfolio_weights(construction, kind="unconstrained"),
        plot_portfolio_exposures(construction),
        plot_constraint_utilization(construction),
        plot_predicted_volatility(construction),
        plot_risk_contributions(construction),
        plot_portfolio_turnover(construction),
    ]

    assert all(isinstance(chart, go.Figure) for chart in figures)
    assert {trace.name for trace in figures[0].data[:4]} >= {"a", "b", "c", "Cash"}
    assert "Limit" in {trace.name for trace in figures[3].data}
    assert {trace.name for trace in figures[4].data} >= {"Predicted", "Target", "Limit"}
    assert figures[3].layout.shapes[0].y0 == 1
    assert_title_and_legend_are_separated(figures[0])


def test_backtest_paths_preserve_benchmarks_timing_and_risk_parameters() -> None:
    _, backtest = portfolio_results()

    returns = plot_backtest_returns(backtest)
    performance = plot_backtest_performance(backtest)
    drawdown = plot_backtest_drawdowns(backtest)
    volatility = plot_backtest_rolling_volatility(
        backtest,
        window=3,
        periods_per_year=252,
    )

    assert {trace.name for trace in returns.data[:2]} == {"Portfolio", "Equal weight"}
    assert "execution lag 1" in performance.layout.title.text
    assert len(drawdown.data) == 2
    assert drawdown.layout.shapes
    assert "3-observation window" in volatility.layout.title.text
    assert volatility.layout.yaxis.title.text == "Annualized volatility"
    for chart in (returns, performance, drawdown, volatility):
        assert_title_and_legend_are_separated(chart)


def test_backtest_cost_and_attribution_plots_reconcile_views() -> None:
    _, backtest = portfolio_results()
    groups = {"a": "Growth", "b": "Growth", "c": "Defensive"}

    turnover = plot_portfolio_turnover(backtest)
    costs = plot_transaction_costs(backtest)
    assets = plot_return_attribution(backtest)
    grouped = plot_return_attribution(backtest, groups=groups)
    cost_groups = plot_cost_attribution(backtest, groups=groups)

    assert turnover.layout.yaxis.title.text == "One-way turnover"
    assert costs.layout.title.text == "Linear transaction costs"
    assert {trace.name for trace in assets.data} >= {"a", "b", "c"}
    assert {trace.name for trace in grouped.data} >= {"Growth", "Defensive", "Cash"}
    assert cost_groups.layout.title.text == "Group cost attribution"
    assert_title_and_legend_are_separated(cost_groups)


def test_weight_and_rebalance_diagnostics_distinguish_paths_and_blocks() -> None:
    _, backtest = portfolio_results()

    target = plot_portfolio_weights(backtest, kind="target")
    realized = plot_portfolio_weights(backtest, kind="realized")
    ending = plot_portfolio_weights(backtest, kind="ending")
    diagnostics = plot_rebalance_diagnostics(backtest)

    assert np.asarray(target.data[0].x).size == len(backtest.target_weights)
    assert np.asarray(realized.data[0].x).size == len(backtest.realized_weights)
    assert ending.layout.title.text == "Ending weights"
    assert {trace.name for trace in diagnostics.data} == {
        "Target difference",
        "Blocked assets",
    }
    assert "a" in set(diagnostics.data[1].text)
    assert diagnostics.layout.xaxis.title.text == "First holding period"
    assert pd.api.types.is_datetime64_any_dtype(np.asarray(diagnostics.data[0].x).dtype)


def test_portfolio_plots_reject_unavailable_risk_and_incomplete_groups() -> None:
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
