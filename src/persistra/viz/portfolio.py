# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Plotly figures for portfolio construction and vectorized backtests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from persistra.analysis import rolling_volatility
from persistra.portfolio import BacktestResult, PortfolioConstructionResult
from persistra.viz._common import (
    figure,
    finish_figure,
    plot_wide_series,
    set_figure_title,
    temporal_values,
)
from persistra.viz.market import (
    plot_cumulative_returns,
    plot_drawdowns,
    plot_returns,
    plot_rolling_volatility,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

type PortfolioResult = PortfolioConstructionResult | BacktestResult
type WeightKind = Literal["target", "unconstrained", "realized", "ending"]


def plot_portfolio_weights(
    result: PortfolioResult,
    *,
    kind: WeightKind = "target",
    include_cash: bool = True,
) -> go.Figure:
    """Plot one explicit target, unconstrained, realized, or ending weight panel."""
    weights, cash = _weight_panel(result, kind=kind)
    frame = weights.copy(deep=True)
    if include_cash:
        frame["Cash"] = cash
    chart = plot_wide_series(frame, ylabel="Portfolio weight")
    chart.add_hline(y=0, line_color="#222222")
    set_figure_title(chart, f"{kind.title()} weights")
    return chart


def plot_portfolio_exposures(result: PortfolioResult) -> go.Figure:
    """Plot long, short, gross, net, and residual-cash exposures."""
    chart = plot_wide_series(result.exposures, ylabel="Portfolio exposure")
    chart.add_hline(y=0, line_color="#222222")
    return chart


def plot_constraint_utilization(result: PortfolioConstructionResult) -> go.Figure:
    """Plot construction constraint use relative to each implemented limit."""
    observed = result.constraint_utilization.dropna(axis="columns", how="all")
    if observed.empty:
        raise ValueError("construction result has no active constraint utilization")
    chart = plot_wide_series(observed, ylabel="Fraction of limit")
    _add_named_reference(chart, 1, name="Limit", color="#222222", dash="dot")
    chart.update_layout(showlegend=True)
    return chart


def plot_predicted_volatility(result: PortfolioConstructionResult) -> go.Figure:
    """Plot covariance-implied annualized volatility and configured controls."""
    if not result.predicted_volatility.notna().any():
        raise ValueError("construction result has no predicted volatility")
    chart = plot_wide_series(
        result.predicted_volatility.to_frame("Predicted"),
        ylabel="Annualized predicted volatility",
    )
    if result.risk_control is not None:
        if result.risk_control.target_volatility is not None:
            _add_named_reference(
                chart,
                result.risk_control.target_volatility,
                name="Target",
                color="#2ca02c",
                dash="dash",
            )
        if result.risk_control.volatility_limit is not None:
            _add_named_reference(
                chart,
                result.risk_control.volatility_limit,
                name="Limit",
                color="#d62728",
                dash="dot",
            )
        chart.update_layout(showlegend=True)
    return chart


def plot_risk_contributions(result: PortfolioConstructionResult) -> go.Figure:
    """Plot covariance risk contributions reported for target portfolios."""
    if not result.risk_contributions.notna().any(axis=None):
        raise ValueError("construction result has no risk contributions")
    chart = plot_wide_series(
        result.risk_contributions,
        ylabel="Annualized volatility contribution",
    )
    chart.add_hline(y=0, line_color="#222222")
    return chart


def plot_backtest_returns(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
) -> go.Figure:
    """Plot reconciled net returns with optional simulated benchmarks."""
    frame = result.returns.to_frame("Portfolio")
    if include_benchmarks:
        frame = frame.join(result.benchmark_returns)
    chart = plot_returns(frame)
    set_figure_title(chart, _timing_title(result))
    return chart


def plot_backtest_performance(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
    yscale: Literal["auto", "linear", "log"] = "auto",
) -> go.Figure:
    """Plot cumulative net performance with optional simulated benchmarks."""
    frame = result.equity.div(result.initial_equity).sub(1.0).to_frame("Portfolio")
    if include_benchmarks:
        benchmark = result.benchmark_equity.div(result.initial_equity).sub(1.0)
        frame = frame.join(benchmark)
    chart = plot_cumulative_returns(frame, yscale=yscale)
    set_figure_title(chart, _timing_title(result))
    return chart


def plot_backtest_drawdowns(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
) -> go.Figure:
    """Plot strategy drawdown with optional benchmark drawdowns."""
    frame = result.drawdown.to_frame("Portfolio")
    if include_benchmarks and len(result.benchmark_equity.columns):
        peaks = result.benchmark_equity.cummax().clip(lower=result.initial_equity)
        frame = frame.join(result.benchmark_equity.div(peaks).sub(1.0))
    chart = plot_drawdowns(frame)
    set_figure_title(chart, _timing_title(result))
    return chart


def plot_backtest_rolling_volatility(
    result: BacktestResult,
    *,
    window: int,
    periods_per_year: float,
    include_benchmarks: bool = True,
) -> go.Figure:
    """Calculate and plot annualized rolling volatility under explicit parameters."""
    frame = result.returns.to_frame("Portfolio")
    if include_benchmarks:
        frame = frame.join(result.benchmark_returns)
    volatility = rolling_volatility(
        frame,
        window=window,
        periods_per_year=periods_per_year,
    )
    chart = plot_rolling_volatility(volatility)
    set_figure_title(
        chart,
        (
            f"{window}-observation window, {periods_per_year:g} periods per year; "
            f"{_timing_title(result)}"
        ),
    )
    return chart


def plot_portfolio_turnover(result: PortfolioResult) -> go.Figure:
    """Plot reported one-way turnover through time."""
    return plot_wide_series(result.turnover.to_frame("Turnover"), ylabel="One-way turnover")


def plot_transaction_costs(result: BacktestResult) -> go.Figure:
    """Plot total transaction-cost return deductions through time."""
    chart = plot_wide_series(
        result.costs.to_frame("Total cost"),
        ylabel="Return deducted as cost",
    )
    set_figure_title(chart, "Linear transaction costs")
    return chart


def plot_return_attribution(
    result: BacktestResult,
    *,
    groups: Mapping[Any, str] | None = None,
    include_cash: bool = True,
) -> go.Figure:
    """Plot reconciled period gross-return attribution by asset or supplied group."""
    frame = _aggregate_attribution(result.asset_return_attribution, groups=groups)
    if include_cash:
        frame["Cash"] = result.cash_return_attribution
    chart = plot_wide_series(frame, ylabel="Gross-return contribution")
    chart.add_hline(y=0, line_color="#222222")
    set_figure_title(
        chart,
        "Group attribution" if groups is not None else "Asset attribution",
    )
    return chart


def plot_cost_attribution(
    result: BacktestResult,
    *,
    groups: Mapping[Any, str] | None = None,
) -> go.Figure:
    """Plot reconciled transaction-cost attribution by asset or supplied group."""
    frame = _aggregate_attribution(result.cost_attribution, groups=groups)
    chart = plot_wide_series(frame, ylabel="Return deducted as cost")
    set_figure_title(
        chart,
        "Group cost attribution" if groups is not None else "Asset cost attribution",
    )
    return chart


def plot_rebalance_diagnostics(result: BacktestResult) -> go.Figure:
    """Plot target-versus-realized rebalance differences and blocked assets."""
    records: list[dict[str, object]] = []
    for target_position, (_, log_row) in enumerate(result.rebalance_log.iterrows()):
        if log_row["status"] != "executed":
            continue
        holding_start = pd.Timestamp(log_row["holding_start"])
        target = result.target_weights.iloc[target_position]
        realized = result.realized_weights.loc[holding_start]
        target_values = target.to_numpy(dtype=float, na_value=np.nan)
        realized_values = realized.to_numpy(dtype=float, na_value=np.nan)
        target_cash = 1.0 - float(target_values.sum())
        realized_cash = float(result.cash.loc[holding_start])
        difference = 0.5 * (
            float(np.abs(target_values - realized_values).sum()) + abs(target_cash - realized_cash)
        )
        records.append(
            {
                "holding_start": holding_start,
                "difference": difference,
                "blocked_assets": str(log_row["blocked_assets"]),
            }
        )
    if not records:
        raise ValueError("backtest result has no executed rebalances")
    diagnostics = pd.DataFrame(records).set_index("holding_start")
    x_values = temporal_values(diagnostics.index)
    result_figure = figure(title=_timing_title(result))
    result_figure.add_trace(
        go.Scatter(
            x=x_values,
            y=diagnostics["difference"],
            mode="lines+markers",
            name="Target difference",
            connectgaps=False,
        )
    )
    blocked = diagnostics["blocked_assets"].ne("")
    if blocked.any():
        result_figure.add_trace(
            go.Scatter(
                x=x_values[blocked],
                y=diagnostics.loc[blocked, "difference"],
                mode="markers+text",
                marker={"symbol": "x", "size": 11, "color": "#d62728"},
                text=diagnostics.loc[blocked, "blocked_assets"],
                textposition="top right",
                name="Blocked assets",
            )
        )
    finish_figure(
        result_figure,
        xlabel="First holding period",
        ylabel="One-way target-to-realized difference",
        title=_timing_title(result),
        showlegend=True,
    )
    result_figure.update_yaxes(rangemode="tozero")
    return result_figure


def _add_named_reference(
    result: go.Figure,
    value: float,
    *,
    name: str,
    color: str,
    dash: str,
) -> None:
    result.add_hline(y=value, line_color=color, line_dash=dash)
    result.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            name=name,
            line={"color": color, "dash": dash},
            hoverinfo="skip",
        )
    )


def _weight_panel(result: PortfolioResult, *, kind: WeightKind) -> tuple[pd.DataFrame, pd.Series]:
    if isinstance(result, PortfolioConstructionResult):
        if kind == "target":
            return result.weights, result.cash
        if kind == "unconstrained":
            weights = result.unconstrained_weights
            return weights, weights.sum(axis="columns").rsub(1.0).rename("cash")
        raise ValueError("construction weights support target or unconstrained kind")
    if kind == "target":
        weights = result.target_weights
        return weights, weights.sum(axis="columns").rsub(1.0).rename("cash")
    if kind == "realized":
        return result.realized_weights, result.cash
    if kind == "ending":
        return result.ending_weights, result.ending_cash
    raise ValueError("backtest weights support target, realized, or ending kind")


def _aggregate_attribution(
    frame: pd.DataFrame,
    *,
    groups: Mapping[Any, str] | None,
) -> pd.DataFrame:
    if groups is None:
        return frame.copy(deep=True)
    missing = [column for column in frame.columns if column not in groups]
    extra = [asset for asset in groups if asset not in frame.columns]
    if missing or extra:
        raise ValueError("groups must map every attribution asset exactly once")
    labels = [groups[column] for column in frame.columns]
    if any(not label for label in labels):
        raise ValueError("attribution group names must not be empty")
    grouped = frame.T.groupby(labels, sort=False).sum().T
    grouped.columns.name = "group"
    return grouped


def _timing_title(result: BacktestResult) -> str:
    holding = (
        "until next rebalance"
        if result.timing.holding_period is None
        else f"{result.timing.holding_period} observations"
    )
    return (
        f"Decision lag {result.timing.decision_lag}; execution lag "
        f"{result.timing.execution_lag}; holding {holding}"
    )
