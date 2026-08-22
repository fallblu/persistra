# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""General Plotly figures for explicit wide data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import plotly.graph_objects as go

from persistra.analysis import correlation_matrix, coverage_summary, rebase
from persistra.viz._common import comparison_yscale, figure, finish_figure, plot_wide_series

if TYPE_CHECKING:
    import pandas as pd


def plot_series(frame: pd.DataFrame, *, ylabel: str = "Value") -> go.Figure:
    """Plot each wide-frame column as one line."""
    _require_comparable_scale(frame)
    return plot_wide_series(frame, ylabel=ylabel)


def plot_rebased(
    frame: pd.DataFrame,
    *,
    base: float = 100,
    yscale: Literal["auto", "linear", "log"] = "auto",
) -> go.Figure:
    """Plot rebased columns with automatic or explicit axis scaling."""
    rebased = rebase(frame, base=base)
    result = plot_wide_series(rebased, ylabel=f"Rebased ({base:g})")
    result.update_yaxes(type=comparison_yscale(rebased, yscale))
    return result


def plot_distribution(values: pd.Series, *, bins: int = 30) -> go.Figure:
    """Plot a histogram of finite observed values."""
    result = figure()
    label = str(values.name or "Value")
    result.add_trace(
        go.Histogram(
            x=values.dropna().to_numpy(dtype=float),
            nbinsx=bins,
            name=label,
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    return finish_figure(
        result,
        xlabel=label,
        ylabel="Count",
        showlegend=False,
    )


def plot_rolling_statistic(
    frame: pd.DataFrame,
    *,
    statistic_name: str,
) -> go.Figure:
    """Plot an already calculated rolling statistic."""
    return plot_series(frame, ylabel=statistic_name)


def plot_correlation(frame: pd.DataFrame) -> go.Figure:
    """Plot pairwise correlations with complete-observation counts."""
    correlation = correlation_matrix(frame)
    observed = frame.notna().astype(int)
    counts = observed.T @ observed
    values = correlation.to_numpy(dtype=float)
    count_values = counts.to_numpy(dtype=int)
    labels = [str(column) for column in correlation.columns]
    text = [
        [
            f"{'—' if np.isnan(value) else f'{value:.2f}'}<br>n={count_values[row, column]}"
            for column, value in enumerate(values[row])
        ]
        for row in range(len(labels))
    ]
    result = figure()
    result.add_trace(
        go.Heatmap(
            z=values,
            x=labels,
            y=labels,
            zmin=-1,
            zmax=1,
            zmid=0,
            colorscale="RdBu_r",
            colorbar={"title": {"text": "Correlation"}},
            text=text,
            texttemplate="%{text}",
            hovertemplate="%{x} / %{y}<br>%{text}<extra></extra>",
        )
    )
    return finish_figure(result, xlabel="", ylabel="", showlegend=False)


def plot_coverage(frame: pd.DataFrame) -> go.Figure:
    """Plot observed coverage for each wide-frame column."""
    summary = coverage_summary(frame)
    labels = [str(value) for value in summary.index]
    horizontal = bool(labels and max(map(len, labels)) > 16)
    result = figure()
    result.add_trace(
        go.Bar(
            x=summary["coverage"] if horizontal else labels,
            y=labels if horizontal else summary["coverage"],
            orientation="h" if horizontal else "v",
            name="Coverage",
            hovertemplate="%{y}: %{x:.1%}<extra></extra>"
            if horizontal
            else "%{x}: %{y:.1%}<extra></extra>",
        )
    )
    if horizontal:
        finish_figure(
            result,
            xlabel="Observed fraction",
            ylabel="Series",
            showlegend=False,
        )
        result.update_xaxes(range=[0, 1])
    else:
        finish_figure(
            result,
            xlabel="Series",
            ylabel="Observed fraction",
            showlegend=False,
        )
        result.update_yaxes(range=[0, 1])
    return result


def _require_comparable_scale(frame: pd.DataFrame) -> None:
    scales: list[float] = []
    for column in frame:
        values = np.abs(frame[column].to_numpy(dtype=float, na_value=np.nan))
        observed = values[np.isfinite(values) & (values > 0)]
        if observed.size:
            scales.append(float(np.median(observed)))
    if len(scales) > 1 and max(scales) / min(scales) >= 100:
        raise ValueError(
            "series magnitudes differ by at least 100x; normalize the inputs or use separate axes"
        )
