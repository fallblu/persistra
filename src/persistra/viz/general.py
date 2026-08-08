# pyright: reportUnknownMemberType=false
"""General Matplotlib plots for explicit wide data."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Literal

import matplotlib.pyplot as plt
import numpy as np

from persistra.analysis import correlation_matrix, coverage_summary, rebase
from persistra.viz._common import (
    format_date_axis,
    line_style,
    marker_interval,
    temporal_values,
)

if TYPE_CHECKING:
    import pandas as pd
    from matplotlib.axes import Axes


def plot_series(frame: pd.DataFrame, *, ax: Axes | None = None, ylabel: str = "Value") -> Axes:
    """Plot each wide-frame column as one line."""
    axes = _axes(ax)
    x_values = temporal_values(frame.index)
    _warn_scale_divergence(frame)
    for position, column in enumerate(frame):
        style, marker = line_style(position)
        axes.plot(
            x_values,
            frame[column],
            label=str(column),
            linestyle=style,
            marker=marker if len(frame.columns) > 1 else None,
            markevery=marker_interval(len(frame)),
            markersize=4,
        )
    axes.set(xlabel="Observation", ylabel=ylabel)
    format_date_axis(axes, x_values)
    if len(frame.columns) > 1:
        axes.legend()
    return axes


def plot_rebased(
    frame: pd.DataFrame,
    *,
    base: float = 100,
    yscale: Literal["linear", "log"] = "linear",
    ax: Axes | None = None,
) -> Axes:
    """Plot columns rebased to one explicit level on a linear or log scale."""
    axes = plot_series(rebase(frame, base=base), ax=ax, ylabel=f"Rebased ({base:g})")
    axes.set_yscale(yscale)
    return axes


def plot_distribution(
    values: pd.Series,
    *,
    bins: int = 30,
    ax: Axes | None = None,
) -> Axes:
    """Plot a histogram of finite observed values."""
    axes = _axes(ax)
    axes.hist(values.dropna(), bins=bins)
    axes.set(xlabel=values.name or "Value", ylabel="Count")
    return axes


def plot_rolling_statistic(
    frame: pd.DataFrame,
    *,
    statistic_name: str,
    ax: Axes | None = None,
) -> Axes:
    """Plot an already calculated rolling statistic."""
    return plot_series(frame, ax=ax, ylabel=statistic_name)


def plot_correlation(frame: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot pairwise correlations with complete-observation counts."""
    axes = _axes(ax)
    correlation = correlation_matrix(frame)
    observed = frame.notna().astype(int)
    counts = observed.T @ observed
    correlation_values = correlation.to_numpy(dtype=float)
    count_values = counts.to_numpy(dtype=int)
    image = axes.imshow(correlation_values, vmin=-1, vmax=1, cmap="coolwarm")
    labels = [str(column) for column in correlation.columns]
    axes.set_xticks(np.arange(len(labels)), labels=labels, rotation=45, ha="right")
    axes.set_yticks(np.arange(len(labels)), labels=labels)
    for row in range(len(labels)):
        for column in range(len(labels)):
            value = correlation_values[row, column]
            coefficient = "—" if np.isnan(value) else f"{value:.2f}"
            color = "white" if np.isfinite(value) and abs(value) >= 0.55 else "black"
            axes.text(
                column,
                row,
                f"{coefficient}\nn={count_values[row, column]}",
                ha="center",
                va="center",
                color=color,
                fontsize="small",
            )
    axes.figure.colorbar(image, ax=axes, label="Correlation")
    return axes


def plot_coverage(frame: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot observed coverage for each wide-frame column."""
    axes = _axes(ax)
    summary = coverage_summary(frame)
    labels = [str(value) for value in summary.index]
    if labels and max(map(len, labels)) > 16:
        axes.barh(labels, summary["coverage"])
        axes.set(xlabel="Observed fraction", ylabel="Series", xlim=(0, 1))
    else:
        axes.bar(labels, summary["coverage"])
        axes.set(xlabel="Series", ylabel="Observed fraction", ylim=(0, 1))
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]


def _warn_scale_divergence(frame: pd.DataFrame) -> None:
    scales: list[float] = []
    for column in frame:
        values = np.abs(frame[column].to_numpy(dtype=float, na_value=np.nan))
        observed = values[np.isfinite(values) & (values > 0)]
        if observed.size:
            scales.append(float(np.median(observed)))
    if len(scales) > 1 and max(scales) / min(scales) >= 100:
        warnings.warn(
            "series magnitudes differ by at least 100x; a shared axis may obscure smaller "
            "series or imply shared units; normalize the inputs or use separate axes",
            UserWarning,
            stacklevel=2,
        )
