# pyright: reportUnknownMemberType=false
"""General Matplotlib plots for explicit wide data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

from persistra.analysis import correlation_matrix, coverage_summary, rebase

if TYPE_CHECKING:
    import pandas as pd
    from matplotlib.axes import Axes


def plot_series(frame: pd.DataFrame, *, ax: Axes | None = None, ylabel: str = "Value") -> Axes:
    """Plot each wide-frame column as one line."""
    axes = _axes(ax)
    for column in frame:
        axes.plot(frame.index, frame[column], label=str(column))
    axes.set(xlabel="Observation", ylabel=ylabel)
    if len(frame.columns) > 1:
        axes.legend()
    return axes


def plot_rebased(frame: pd.DataFrame, *, base: float = 100, ax: Axes | None = None) -> Axes:
    """Plot columns rebased to one explicit level."""
    return plot_series(rebase(frame, base=base), ax=ax, ylabel=f"Rebased ({base:g})")


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
    """Plot a pairwise correlation heatmap."""
    axes = _axes(ax)
    correlation = correlation_matrix(frame)
    image = axes.imshow(correlation.to_numpy(), vmin=-1, vmax=1, cmap="coolwarm")
    labels = [str(column) for column in correlation.columns]
    axes.set_xticks(np.arange(len(labels)), labels=labels, rotation=45, ha="right")
    axes.set_yticks(np.arange(len(labels)), labels=labels)
    axes.figure.colorbar(image, ax=axes, label="Correlation")
    return axes


def plot_coverage(frame: pd.DataFrame, *, ax: Axes | None = None) -> Axes:
    """Plot observed coverage for each wide-frame column."""
    axes = _axes(ax)
    summary = coverage_summary(frame)
    axes.bar([str(value) for value in summary.index], summary["coverage"])
    axes.set(xlabel="Series", ylabel="Observed fraction", ylim=(0, 1))
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]
