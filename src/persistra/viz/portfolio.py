# pyright: reportUnknownMemberType=false
"""Matplotlib plots for portfolio construction and vectorized backtests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from persistra.analysis import rolling_volatility
from persistra.portfolio import BacktestResult, PortfolioConstructionResult
from persistra.viz._common import format_date_axis, plot_wide_series, temporal_values
from persistra.viz.market import (
    plot_cumulative_returns,
    plot_drawdowns,
    plot_returns,
    plot_rolling_volatility,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from matplotlib.axes import Axes

type PortfolioResult = PortfolioConstructionResult | BacktestResult
type WeightKind = Literal["target", "unconstrained", "realized", "ending"]


def plot_portfolio_weights(
    result: PortfolioResult,
    *,
    kind: WeightKind = "target",
    include_cash: bool = True,
    ax: Axes | None = None,
) -> Axes:
    """Plot one explicit target, unconstrained, realized, or ending weight panel."""
    weights, cash = _weight_panel(result, kind=kind)
    frame = weights.copy(deep=True)
    if include_cash:
        frame["Cash"] = cash
    axes = plot_wide_series(frame, ax=ax, ylabel="Portfolio weight")
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set_title(f"{kind.title()} weights")
    return axes


def plot_portfolio_exposures(result: PortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot long, short, gross, net, and residual-cash exposures."""
    axes = plot_wide_series(result.exposures, ax=ax, ylabel="Portfolio exposure")
    axes.axhline(0, color="black", linewidth=0.8)
    return axes


def plot_constraint_utilization(
    result: PortfolioConstructionResult, *, ax: Axes | None = None
) -> Axes:
    """Plot construction constraint use relative to each implemented limit."""
    observed = result.constraint_utilization.dropna(axis="columns", how="all")
    if observed.empty:
        raise ValueError("construction result has no active constraint utilization")
    axes = plot_wide_series(observed, ax=ax, ylabel="Fraction of limit")
    axes.axhline(1, color="black", linestyle=":", linewidth=0.9, label="Limit")
    axes.legend()
    return axes


def plot_predicted_volatility(
    result: PortfolioConstructionResult, *, ax: Axes | None = None
) -> Axes:
    """Plot covariance-implied annualized volatility and configured controls."""
    if not result.predicted_volatility.notna().any():
        raise ValueError("construction result has no predicted volatility")
    axes = plot_wide_series(
        result.predicted_volatility.to_frame("Predicted"),
        ax=ax,
        ylabel="Annualized predicted volatility",
    )
    if result.risk_control is not None:
        if result.risk_control.target_volatility is not None:
            axes.axhline(
                result.risk_control.target_volatility,
                color="tab:green",
                linestyle="--",
                label="Target",
            )
        if result.risk_control.volatility_limit is not None:
            axes.axhline(
                result.risk_control.volatility_limit,
                color="tab:red",
                linestyle=":",
                label="Limit",
            )
        axes.legend()
    return axes


def plot_risk_contributions(result: PortfolioConstructionResult, *, ax: Axes | None = None) -> Axes:
    """Plot covariance risk contributions reported for target portfolios."""
    if not result.risk_contributions.notna().any(axis=None):
        raise ValueError("construction result has no risk contributions")
    axes = plot_wide_series(
        result.risk_contributions, ax=ax, ylabel="Annualized volatility contribution"
    )
    axes.axhline(0, color="black", linewidth=0.8)
    return axes


def plot_backtest_returns(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
    ax: Axes | None = None,
) -> Axes:
    """Plot reconciled net returns with optional simulated benchmarks."""
    frame = result.returns.to_frame("Portfolio")
    if include_benchmarks:
        frame = frame.join(result.benchmark_returns)
    axes = plot_returns(frame, ax=ax)
    axes.set_title(_timing_title(result))
    return axes


def plot_backtest_performance(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
    yscale: Literal["auto", "linear", "log"] = "auto",
    ax: Axes | None = None,
) -> Axes:
    """Plot cumulative net performance with optional simulated benchmarks."""
    frame = result.equity.div(result.initial_equity).sub(1.0).to_frame("Portfolio")
    if include_benchmarks:
        benchmark = result.benchmark_equity.div(result.initial_equity).sub(1.0)
        frame = frame.join(benchmark)
    axes = plot_cumulative_returns(frame, yscale=yscale, ax=ax)
    axes.set_title(_timing_title(result))
    return axes


def plot_backtest_drawdowns(
    result: BacktestResult,
    *,
    include_benchmarks: bool = True,
    ax: Axes | None = None,
) -> Axes:
    """Plot strategy drawdown with optional benchmark drawdowns."""
    frame = result.drawdown.to_frame("Portfolio")
    if include_benchmarks and len(result.benchmark_equity.columns):
        peaks = result.benchmark_equity.cummax().clip(lower=result.initial_equity)
        frame = frame.join(result.benchmark_equity.div(peaks).sub(1.0))
    axes = plot_drawdowns(frame, ax=ax)
    axes.set_title(_timing_title(result))
    return axes


def plot_backtest_rolling_volatility(
    result: BacktestResult,
    *,
    window: int,
    periods_per_year: float,
    include_benchmarks: bool = True,
    ax: Axes | None = None,
) -> Axes:
    """Calculate and plot annualized rolling volatility under explicit parameters."""
    frame = result.returns.to_frame("Portfolio")
    if include_benchmarks:
        frame = frame.join(result.benchmark_returns)
    volatility = rolling_volatility(
        frame,
        window=window,
        periods_per_year=periods_per_year,
    )
    axes = plot_rolling_volatility(volatility, ax=ax)
    axes.set_title(
        f"{window}-observation window, {periods_per_year:g} periods per year; "
        f"{_timing_title(result)}"
    )
    return axes


def plot_portfolio_turnover(result: PortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot reported one-way turnover through time."""
    axes = plot_wide_series(result.turnover.to_frame("Turnover"), ax=ax, ylabel="One-way turnover")
    return axes


def plot_transaction_costs(result: BacktestResult, *, ax: Axes | None = None) -> Axes:
    """Plot total transaction-cost return deductions through time."""
    axes = plot_wide_series(
        result.costs.to_frame("Total cost"), ax=ax, ylabel="Return deducted as cost"
    )
    axes.set_title("Linear transaction costs")
    return axes


def plot_return_attribution(
    result: BacktestResult,
    *,
    groups: Mapping[Any, str] | None = None,
    include_cash: bool = True,
    ax: Axes | None = None,
) -> Axes:
    """Plot reconciled period gross-return attribution by asset or supplied group."""
    frame = _aggregate_attribution(result.asset_return_attribution, groups=groups)
    if include_cash:
        frame["Cash"] = result.cash_return_attribution
    axes = plot_wide_series(frame, ax=ax, ylabel="Gross-return contribution")
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set_title("Group attribution" if groups is not None else "Asset attribution")
    return axes


def plot_cost_attribution(
    result: BacktestResult,
    *,
    groups: Mapping[Any, str] | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot reconciled transaction-cost attribution by asset or supplied group."""
    frame = _aggregate_attribution(result.cost_attribution, groups=groups)
    axes = plot_wide_series(frame, ax=ax, ylabel="Return deducted as cost")
    axes.set_title("Group cost attribution" if groups is not None else "Asset cost attribution")
    return axes


def plot_rebalance_diagnostics(result: BacktestResult, *, ax: Axes | None = None) -> Axes:
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
    axes = _axes(ax)
    x_values = temporal_values(diagnostics.index)
    axes.plot(x_values, diagnostics["difference"], marker="o", label="Target difference")
    blocked = diagnostics["blocked_assets"].ne("")
    if blocked.any():
        axes.scatter(
            x_values[blocked],
            diagnostics.loc[blocked, "difference"],
            marker="x",
            s=60,
            color="tab:red",
            label="Blocked assets",
        )
        for date, row in diagnostics.loc[blocked].iterrows():
            axes.annotate(
                str(row["blocked_assets"]),
                (date, row["difference"]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize="small",
            )
    axes.set(
        xlabel="First holding period",
        ylabel="One-way target-to-realized difference",
        title=_timing_title(result),
    )
    format_date_axis(axes, x_values)
    axes.set_ylim(bottom=0)
    axes.legend()
    return axes


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
    frame: pd.DataFrame, *, groups: Mapping[Any, str] | None
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


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]
