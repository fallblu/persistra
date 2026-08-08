# pyright: reportUnknownMemberType=false
"""Matplotlib plots for scalar and yield-curve data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from persistra.viz._common import (
    format_date_axis,
    line_style,
    marker_interval,
    sampled_positions,
)
from persistra.viz.general import plot_series

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from persistra.model import SeriesSet


def plot_scalar_series(series: SeriesSet, *, ax: Axes | None = None) -> Axes:
    """Plot one normalized commodity or economic series."""
    axes = _axes(ax)
    periods = series.frame["period_start"]
    axes.plot(
        periods,
        series.frame["value"],
        marker="o",
        markevery=marker_interval(len(series.frame)),
        markersize=3,
    )
    axes.set(xlabel="Period", ylabel=series.definition.unit)
    format_date_axis(axes, periods)
    return axes


def plot_series_change(
    values: pd.DataFrame, *, ylabel: str = "Change", ax: Axes | None = None
) -> Axes:
    """Plot already calculated scalar-series changes."""
    axes = plot_series(values, ax=ax, ylabel=ylabel)
    axes.set_xlabel("Period")
    for position, (line, column) in enumerate(zip(axes.lines, values.columns, strict=True)):
        observed = np.flatnonzero(values[column].notna().to_numpy())
        if len(observed) > 1 and (np.diff(observed) > 1).any():
            _, marker = line_style(position)
            line.set_marker(marker)
            line.set_markevery(1)
    return axes


def plot_yield_curve(curve: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot one observed yield curve without interpolation."""
    axes = _axes(ax)
    axes.plot(curve["maturity_years"], curve["value"], marker="o")
    axes.set(xlabel="Maturity (years)", ylabel="Yield")
    return axes


def plot_yield_curve_history(history: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot observed yield history as a noninterpolated heatmap."""
    axes = _axes(ax)
    image = axes.imshow(
        np.ma.masked_invalid(history.to_numpy(dtype=float)),
        aspect="auto",
        interpolation="none",
        origin="lower",
    )
    maturity_ticks = sampled_positions(len(history.columns), maximum_ticks=6)
    period_ticks = sampled_positions(len(history.index))
    axes.set_xticks(
        maturity_ticks,
        labels=[str(history.columns[position]) for position in maturity_ticks],
        rotation=45,
        ha="right",
    )
    axes.set_yticks(
        period_ticks,
        labels=[_period_label(history.index[position]) for position in period_ticks],
    )
    axes.set(xlabel="Maturity", ylabel="Period")
    axes.figure.colorbar(image, ax=axes, label="Yield")
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]


def _period_label(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return pd.Timestamp(value).date().isoformat()
    return str(value)
