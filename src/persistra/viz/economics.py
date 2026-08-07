# pyright: reportUnknownMemberType=false
"""Matplotlib plots for scalar and yield-curve data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    import pandas as pd
    from matplotlib.axes import Axes

    from persistra.model import SeriesSet


def plot_scalar_series(series: SeriesSet, *, ax: Axes | None = None) -> Axes:
    """Plot one normalized commodity or economic series."""
    axes = _axes(ax)
    axes.plot(series.frame["period_label"], series.frame["value"])
    axes.set(xlabel="Period", ylabel=series.definition.unit)
    return axes


def plot_series_change(
    values: pd.DataFrame, *, ylabel: str = "Change", ax: Axes | None = None
) -> Axes:
    """Plot already calculated scalar-series changes."""
    axes = _axes(ax)
    for column in values:
        axes.plot(values.index, values[column], label=str(column))
    axes.set(xlabel="Period", ylabel=ylabel)
    if len(values.columns) > 1:
        axes.legend()
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
    axes.set_xticks(
        np.arange(len(history.columns)), labels=[str(value) for value in history.columns]
    )
    axes.set_yticks(np.arange(len(history.index)), labels=[str(value) for value in history.index])
    axes.set(xlabel="Maturity", ylabel="Period")
    axes.figure.colorbar(image, ax=axes, label="Yield")
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]
