# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Shared Plotly presentation helpers."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)
_LINE_STYLES = ("solid", "dash", "dashdot", "dot", "longdash", "longdashdot")
_MARKERS = ("circle", "square", "triangle-up", "diamond", "triangle-down", "cross")


def series_style(position: int) -> tuple[str, str, str]:
    """Return one deterministic color, dash style, and marker."""
    return (
        _COLORS[position % len(_COLORS)],
        _LINE_STYLES[position % len(_LINE_STYLES)],
        _MARKERS[position % len(_MARKERS)],
    )


def marker_interval(length: int, *, maximum_markers: int = 18) -> int:
    """Limit visible markers while retaining deterministic positions."""
    return max(1, math.ceil(length / maximum_markers))


def sampled_positions(length: int, *, maximum_ticks: int = 8) -> list[int]:
    """Return evenly sampled positions including both endpoints."""
    if length <= maximum_ticks:
        return list(range(length))
    step = math.ceil((length - 1) / (maximum_ticks - 1))
    positions = list(range(0, length, step))
    if positions[-1] != length - 1:
        positions.append(length - 1)
    return positions


def temporal_values(values: pd.Index) -> pd.Index:
    """Convert period labels to their temporal starts for plotting."""
    if isinstance(values, pd.PeriodIndex):
        return values.to_timestamp()
    return values


def figure(*, title: str | None = None) -> go.Figure:
    """Create one figure with Persistra's local presentation policy."""
    result = go.Figure()
    result.update_layout(
        template="plotly_white",
        hovermode="x unified",
        title=title,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 70, "r": 30, "t": 80 if title else 55, "b": 65},
    )
    return result


def finish_figure(
    result: go.Figure,
    *,
    xlabel: str,
    ylabel: str,
    title: str | None = None,
    showlegend: bool | None = None,
) -> go.Figure:
    """Apply common labels and interaction defaults to a figure."""
    result.update_layout(
        template="plotly_white",
        hovermode="x unified",
        title=title,
        showlegend=showlegend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 70, "r": 30, "t": 80 if title else 55, "b": 65},
    )
    result.update_xaxes(title_text=xlabel, showspikes=True, spikemode="across")
    result.update_yaxes(title_text=ylabel)
    return result


def plot_wide_series(frame: pd.DataFrame, *, ylabel: str) -> go.Figure:
    """Plot wide-frame columns after caller-specific scale validation."""
    result = figure()
    add_wide_series(result, frame)
    return finish_figure(
        result,
        xlabel="Observation",
        ylabel=ylabel,
        showlegend=len(frame.columns) > 1,
    )


def add_wide_series(
    result: go.Figure,
    frame: pd.DataFrame,
    *,
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Add a consistently styled wide frame to a figure or subplot."""
    x_values = temporal_values(frame.index)
    multiple = len(frame.columns) > 1
    for position, column in enumerate(frame):
        color, dash, marker = series_style(position)
        stride = marker_interval(len(frame))
        marker_sizes = [6 if multiple and item % stride == 0 else 0 for item in range(len(frame))]
        trace = go.Scatter(
            x=x_values,
            y=frame[column].to_numpy(dtype=float, na_value=np.nan),
            name=str(column),
            mode="lines+markers" if multiple else "lines",
            connectgaps=False,
            line={"color": color, "dash": dash},
            marker={"symbol": marker, "size": marker_sizes, "color": color},
            hovertemplate=f"{column}: %{{y}}<extra></extra>",
        )
        if row is None or col is None:
            result.add_trace(trace)
        else:
            result.add_trace(trace, row=row, col=col)


def comparison_yscale(
    frame: pd.DataFrame, requested: Literal["auto", "linear", "log"]
) -> Literal["linear", "log"]:
    """Select log scaling when positive terminal values differ by at least 10x."""
    if requested != "auto":
        return requested
    terminal: list[float] = []
    for column in frame:
        values = frame[column].to_numpy(dtype=float, na_value=np.nan)
        observed = values[np.isfinite(values)]
        if observed.size and (observed <= 0).any():
            return "linear"
        if observed.size:
            terminal.append(float(observed[-1]))
    if len(terminal) > 1 and max(terminal) / min(terminal) >= 10:
        return "log"
    return "linear"
