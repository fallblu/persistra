# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportArgumentType=false
"""Plotly diagnostics for Trading Engine replay analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

if TYPE_CHECKING:
    from persistra.integrations.trading_engine.analysis import ExecutionAnalysisResult


def plot_execution_performance(result: ExecutionAnalysisResult) -> go.Figure:
    """Plot event-time equity and drawdown without implying a calendar frequency."""
    path = result.performance_path
    if path.empty:
        raise ValueError("execution analysis has no performance observations")
    x_values = pd.to_datetime(path["recorded_at"], utc=True)
    chart = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.65, 0.35],
        subplot_titles=("Equity", "Drawdown"),
    )
    chart.add_trace(
        go.Scatter(
            x=x_values,
            y=path["equity"],
            mode="lines",
            name="Engine equity",
            connectgaps=False,
        ),
        row=1,
        col=1,
    )
    chart.add_trace(
        go.Scatter(
            x=x_values,
            y=path["drawdown"],
            mode="lines",
            name="Engine drawdown",
            connectgaps=False,
            line={"color": "#d62728", "dash": "dash"},
        ),
        row=2,
        col=1,
    )
    chart.add_hline(y=0, line_color="#222222", row=2, col=1)
    chart.update_yaxes(title_text="Equity", row=1, col=1)
    chart.update_yaxes(title_text="Drawdown", row=2, col=1)
    chart.update_xaxes(title_text="Valuation event", row=2, col=1)
    chart.update_layout(
        template="plotly_white",
        hovermode="x unified",
        title="Trading Engine event-time performance",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 70, "r": 30, "t": 100, "b": 65},
    )
    return chart


def plot_execution_diagnostics(result: ExecutionAnalysisResult) -> go.Figure:
    """Plot requested and filled quantities with adverse fill slippage."""
    orders = result.order_diagnostics
    fills = result.fill_diagnostics
    if orders.empty:
        raise ValueError("execution analysis has no order observations")
    chart = make_subplots(
        rows=2,
        cols=1,
        vertical_spacing=0.14,
        subplot_titles=("Order completion", "Fill slippage"),
    )
    order_labels = _compact_identifier_labels(orders["order_id"], prefix="O")
    chart.add_trace(
        go.Bar(
            x=order_labels,
            y=orders["requested_quantity"],
            name="Requested",
            offsetgroup="requested",
        ),
        row=1,
        col=1,
    )
    chart.add_trace(
        go.Bar(
            x=order_labels,
            y=orders["filled_quantity"],
            name="Filled",
            offsetgroup="filled",
            marker={"pattern": {"shape": "/"}},
        ),
        row=1,
        col=1,
    )
    chart.update_yaxes(title_text="Quantity", row=1, col=1)
    chart.update_xaxes(tickangle=-30, row=1, col=1)
    if fills.empty:
        chart.add_annotation(
            x=0.5,
            y=0.5,
            xref="x2 domain",
            yref="y2 domain",
            text="No fill events",
            showarrow=False,
        )
    else:
        fill_labels = _compact_identifier_labels(fills["fill_id"], prefix="F")
        chart.add_trace(
            go.Bar(
                x=fill_labels,
                y=fills["decision_close_slippage_bps"],
                name="Decision close",
                offsetgroup="decision",
                marker={"pattern": {"shape": "/"}},
            ),
            row=2,
            col=1,
        )
        chart.add_trace(
            go.Bar(
                x=fill_labels,
                y=fills["eligible_open_slippage_bps"],
                name="Fill-slice open",
                offsetgroup="eligible",
                marker={"pattern": {"shape": "."}},
            ),
            row=2,
            col=1,
        )
        chart.add_hline(y=0, line_color="#222222", row=2, col=1)
        chart.update_xaxes(tickangle=-30, row=2, col=1)
    chart.update_xaxes(title_text="Fill", row=2, col=1)
    chart.update_yaxes(title_text="Adverse slippage (bps)", row=2, col=1)
    chart.update_layout(
        template="plotly_white",
        barmode="group",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 70, "r": 30, "t": 90, "b": 80},
    )
    return chart


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
