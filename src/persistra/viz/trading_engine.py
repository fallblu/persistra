# pyright: reportUnknownMemberType=false
"""Matplotlib diagnostics for Trading Engine replay analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from persistra.viz._common import format_date_axis

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from persistra.integrations.trading_engine.analysis import ExecutionAnalysisResult


@dataclass(frozen=True, slots=True)
class ExecutionPerformanceAxes:
    """Equity and drawdown axes for one event-driven replay."""

    equity: Axes
    drawdown: Axes


@dataclass(frozen=True, slots=True)
class ExecutionDiagnosticsAxes:
    """Requested-versus-filled quantity and fill-slippage axes."""

    quantities: Axes
    slippage: Axes


def plot_execution_performance(
    result: ExecutionAnalysisResult,
    *,
    equity_ax: Axes | None = None,
    drawdown_ax: Axes | None = None,
) -> ExecutionPerformanceAxes:
    """Plot event-time equity and drawdown without implying a calendar frequency."""
    if (equity_ax is None) != (drawdown_ax is None):
        raise ValueError("provide both equity_ax and drawdown_ax, or neither")
    if equity_ax is None or drawdown_ax is None:
        _, created = plt.subplots(2, 1, sharex=True)
        equity_ax, drawdown_ax = created
    assert equity_ax is not None and drawdown_ax is not None
    path = result.performance_path
    if path.empty:
        raise ValueError("execution analysis has no performance observations")
    x_values = pd.to_datetime(path["recorded_at"], utc=True)
    equity_ax.plot(x_values, path["equity"], label="Engine equity")
    equity_ax.set(ylabel="Equity", title="Trading Engine event-time performance")
    equity_ax.legend()
    drawdown_ax.plot(x_values, path["drawdown"], label="Engine drawdown", color="tab:red")
    drawdown_ax.axhline(0, color="black", linewidth=0.8)
    drawdown_ax.set(xlabel="Valuation event", ylabel="Drawdown")
    format_date_axis(equity_ax, x_values)
    format_date_axis(drawdown_ax, x_values)
    return ExecutionPerformanceAxes(equity_ax, drawdown_ax)


def plot_execution_diagnostics(
    result: ExecutionAnalysisResult,
    *,
    quantities_ax: Axes | None = None,
    slippage_ax: Axes | None = None,
) -> ExecutionDiagnosticsAxes:
    """Plot requested and filled quantities with adverse fill slippage in basis points."""
    if (quantities_ax is None) != (slippage_ax is None):
        raise ValueError("provide both quantities_ax and slippage_ax, or neither")
    if quantities_ax is None or slippage_ax is None:
        _, created = plt.subplots(2, 1)
        quantities_ax, slippage_ax = created
    assert quantities_ax is not None and slippage_ax is not None
    orders = result.order_diagnostics
    fills = result.fill_diagnostics
    if orders.empty:
        raise ValueError("execution analysis has no order observations")
    positions = np.arange(len(orders), dtype=float)
    width = 0.38
    quantities_ax.bar(
        positions - width / 2,
        orders["requested_quantity"],
        width,
        label="Requested",
    )
    filled = quantities_ax.bar(
        positions + width / 2,
        orders["filled_quantity"],
        width,
        label="Filled",
    )
    for patch in filled.patches:
        patch.set_hatch("//")
    quantities_ax.set_xticks(
        positions,
        labels=_compact_identifier_labels(orders["order_id"], prefix="O"),
    )
    quantities_ax.tick_params(axis="x", rotation=30)
    quantities_ax.set(ylabel="Quantity", title="Order completion")
    quantities_ax.legend()

    if fills.empty:
        slippage_ax.text(
            0.5,
            0.5,
            "No fill events",
            ha="center",
            va="center",
            transform=slippage_ax.transAxes,
        )
        slippage_ax.set(xlabel="Fill", ylabel="Adverse slippage (bps)")
    else:
        fill_positions = np.arange(len(fills), dtype=float)
        decision = slippage_ax.bar(
            fill_positions - width / 2,
            fills["decision_close_slippage_bps"],
            width,
            label="Decision close",
        )
        eligible = slippage_ax.bar(
            fill_positions + width / 2,
            fills["eligible_open_slippage_bps"],
            width,
            label="Fill-slice open",
        )
        for patch in decision.patches:
            patch.set_hatch("//")
        for patch in eligible.patches:
            patch.set_hatch("..")
        slippage_ax.axhline(0, color="black", linewidth=0.8)
        slippage_ax.set_xticks(
            fill_positions,
            labels=_compact_identifier_labels(fills["fill_id"], prefix="F"),
        )
        slippage_ax.tick_params(axis="x", rotation=30)
        slippage_ax.set(xlabel="Fill", ylabel="Adverse slippage (bps)")
        slippage_ax.legend()
    return ExecutionDiagnosticsAxes(quantities_ax, slippage_ax)


def _compact_identifier_labels(values: pd.Series, *, prefix: str) -> list[str]:
    labels: list[str] = []
    for value in values:
        identifier = str(value)
        suffix = identifier.rsplit("-", maxsplit=1)[-1]
        if suffix.isdecimal():
            labels.append(f"{prefix}{int(suffix)}")
        elif len(identifier) <= 16:
            labels.append(identifier)
        else:
            labels.append(f"{identifier[:7]}…{identifier[-7:]}")
    return labels
