# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false
"""Plotly figures for scalar and yield-curve data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from persistra.viz._common import figure, finish_figure, marker_interval, sampled_positions
from persistra.viz.general import plot_series

if TYPE_CHECKING:
    from persistra.model import SeriesSet


def plot_scalar_series(series: SeriesSet) -> go.Figure:
    """Plot one normalized commodity or economic series."""
    result = figure()
    length = len(series.frame)
    stride = marker_interval(length)
    result.add_trace(
        go.Scatter(
            x=series.frame["period_start"],
            y=series.frame["value"].to_numpy(dtype=float, na_value=np.nan),
            mode="lines+markers",
            name=series.definition.series_id,
            connectgaps=False,
            marker={"size": [6 if position % stride == 0 else 0 for position in range(length)]},
        )
    )
    return finish_figure(
        result,
        xlabel="Period",
        ylabel=series.definition.unit,
        showlegend=False,
    )


def plot_series_change(values: pd.DataFrame, *, ylabel: str = "Change") -> go.Figure:
    """Plot already calculated scalar-series changes."""
    result = plot_series(values, ylabel=ylabel)
    result.update_xaxes(title_text="Period")
    for position, column in enumerate(values.columns):
        observed = np.flatnonzero(values[column].notna().to_numpy())
        if len(observed) > 1 and (np.diff(observed) > 1).any():
            result.data[position].mode = "lines+markers"
            result.data[position].marker.size = [6] * len(values)
    return result


def plot_yield_curve(curve: pd.DataFrame) -> go.Figure:
    """Plot one observed yield curve without interpolation."""
    result = figure()
    result.add_trace(
        go.Scatter(
            x=curve["maturity_years"],
            y=curve["value"].to_numpy(dtype=float, na_value=np.nan),
            mode="lines+markers",
            name="Yield",
            connectgaps=False,
        )
    )
    return finish_figure(
        result,
        xlabel="Maturity (years)",
        ylabel="Yield",
        showlegend=False,
    )


def plot_yield_curve_history(history: pd.DataFrame) -> go.Figure:
    """Plot observed yield history as a noninterpolated heatmap."""
    maturity_ticks = sampled_positions(len(history.columns), maximum_ticks=6)
    period_ticks = sampled_positions(len(history.index))
    periods = [_period_label(value) for value in history.index]
    columns = [str(value) for value in history.columns]
    result = figure()
    result.add_trace(
        go.Heatmap(
            z=history.to_numpy(dtype=float, na_value=np.nan),
            x=np.arange(len(columns)),
            y=np.arange(len(periods)),
            colorbar={"title": {"text": "Yield"}},
            hovertemplate="Maturity %{customdata}<br>Period %{text}<br>Yield %{z}<extra></extra>",
            customdata=np.broadcast_to(np.asarray(columns)[None, :], history.shape),
            text=np.broadcast_to(np.asarray(periods)[:, None], history.shape),
        )
    )
    result.update_xaxes(
        tickmode="array",
        tickvals=maturity_ticks,
        ticktext=[columns[position] for position in maturity_ticks],
        tickangle=-45,
    )
    result.update_yaxes(
        tickmode="array",
        tickvals=period_ticks,
        ticktext=[periods[position] for position in period_ticks],
    )
    return finish_figure(
        result,
        xlabel="Maturity",
        ylabel="Period",
        showlegend=False,
    )


def _period_label(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return pd.Timestamp(value).date().isoformat()
    return str(value)
