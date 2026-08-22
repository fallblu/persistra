# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Plotly figures for cross-sectional signal research results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from persistra._validation import require_integer
from persistra.viz._common import figure, finish_figure, plot_wide_series
from persistra.viz.market import plot_cumulative_returns, plot_returns

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.research import (
        BenchmarkComparison,
        GroupSignalResult,
        InformationCoefficientResult,
        QuantilePortfolioResult,
    )

type InformationCoefficientStatistic = Literal["pearson", "rank"]
type InformationCoefficientAggregation = Literal["mean", "median"]
type GroupStatistic = Literal[
    "mean_signal",
    "signal_standard_deviation",
    "mean_forward_return",
    "pearson",
    "rank",
]
type CapacityStatistic = Literal[
    "volume_count",
    "total_volume",
    "median_volume",
    "minimum_volume",
]
type BenchmarkStatistic = Literal[
    "mean_candidate",
    "mean_benchmark",
    "mean_difference",
    "tracking_error",
    "win_rate",
    "correlation",
]


def plot_signal_distribution(
    signals: pd.DataFrame,
    *,
    date: pd.Timestamp,
    groups: pd.DataFrame | None = None,
    bins: int = 20,
) -> go.Figure:
    """Plot one explicit cross-section as a histogram or group box comparison."""
    data = _panel(signals, name="signals")
    position = _date_position(data.index, date)
    values = data.iloc[position]
    result = figure()
    if groups is None:
        result.add_trace(
            go.Histogram(
                x=values.dropna().to_numpy(dtype=float),
                nbinsx=bins,
                name="Signal",
            )
        )
        xlabel, ylabel = "Signal", "Asset count"
        showlegend = False
    else:
        classifications = _aligned_groups(groups, data)
        group_row = classifications.iloc[position]
        samples = 0
        for group_position, group in enumerate(group_row.dropna().drop_duplicates()):
            sample = values[group_row.eq(group).fillna(False)].dropna()
            if len(sample):
                result.add_trace(
                    go.Box(
                        y=sample.to_numpy(dtype=float),
                        name=f"{group}<br>n={len(sample)}",
                        boxpoints="outliers",
                        fillcolor="rgba(31, 119, 180, 0.35)"
                        if group_position % 2 == 0
                        else "rgba(255, 127, 14, 0.15)",
                        line={"width": 1 if group_position % 2 == 0 else 3},
                    )
                )
                samples += 1
        if not samples:
            raise ValueError("selected cross-section has no observed group samples")
        xlabel, ylabel = "Group", "Signal"
        showlegend = False
    title = (
        f"Signal distribution on {_date_label(cast('pd.Timestamp', data.index[position]))} "
        f"(n={int(values.notna().sum())}/{len(values)})"
    )
    return finish_figure(
        result,
        xlabel=xlabel,
        ylabel=ylabel,
        title=title,
        showlegend=showlegend,
    )


def plot_signal_ranks(ranks: pd.DataFrame, *, date: pd.Timestamp) -> go.Figure:
    """Plot already calculated cross-sectional ranks for one explicit date."""
    data = _panel(ranks, name="ranks")
    position = _date_position(data.index, date)
    values = data.iloc[position].dropna().sort_values()
    if values.empty:
        raise ValueError("selected cross-section has no observed ranks")
    result = figure()
    result.add_trace(
        go.Bar(
            x=values.to_numpy(dtype=float),
            y=[str(value) for value in values.index],
            orientation="h",
            marker={"pattern": {"shape": ["/" if item % 2 else "" for item in range(len(values))]}},
            name="Rank",
        )
    )
    return finish_figure(
        result,
        xlabel="Cross-sectional rank",
        ylabel="Asset",
        title=(
            f"Signal ranks on {_date_label(cast('pd.Timestamp', data.index[position]))} "
            f"(n={len(values)}/{len(data.columns)})"
        ),
        showlegend=False,
    )


def plot_group_comparison(
    result: GroupSignalResult,
    *,
    statistic: GroupStatistic = "mean_forward_return",
) -> go.Figure:
    """Plot one group statistic through time with explicit horizon and coverage."""
    statistics = result.statistics
    _require_columns(statistics, {"count", statistic}, name="group statistics")
    frame = statistics[statistic].unstack("group")
    if frame.empty or not frame.notna().any(axis=None):
        raise ValueError(f"group result has no observed {statistic} values")
    chart = plot_wide_series(frame, ylabel=_label(statistic))
    chart.add_hline(y=0, line_color="#222222")
    chart.update_layout(title=f"Group comparison, {result.horizon}-observation forward horizon")
    _annotate_counts(chart, statistics["count"])
    return chart


def plot_information_coefficients(
    result: InformationCoefficientResult,
    *,
    statistic: InformationCoefficientStatistic = "rank",
    rolling: int | None = None,
) -> go.Figure:
    """Plot ICs through time and expose pairwise counts and missing coverage."""
    if rolling is not None:
        rolling = require_integer(rolling, name="rolling", minimum=1)
    statistics = result.statistics
    if result.grouped:
        frame = statistics[statistic].unstack("group")
    else:
        frame = statistics[[statistic]].rename(columns={statistic: statistic.title()})
    if rolling is not None:
        frame = frame.rolling(rolling, min_periods=rolling).mean()
    if frame.empty or not frame.notna().any(axis=None):
        raise ValueError(f"information coefficient result has no observed {statistic} values")
    ylabel = f"{statistic.title()} IC"
    if rolling is not None:
        ylabel = f"{rolling}-observation rolling mean {ylabel}"
    chart = plot_wide_series(frame, ylabel=ylabel)
    chart.add_hline(y=0, line_color="#222222")
    chart.update_layout(title=f"{result.horizon}-observation forward horizon")
    _annotate_counts(chart, statistics["count"])
    return chart


def plot_information_coefficient_horizons(
    results: Sequence[InformationCoefficientResult],
    *,
    statistic: InformationCoefficientStatistic = "rank",
    aggregation: InformationCoefficientAggregation = "mean",
) -> go.Figure:
    """Compare one aggregate IC across explicit, unique forward horizons."""
    if not results:
        raise ValueError("results must contain at least one information coefficient result")
    horizons = [result.horizon for result in results]
    if len(set(horizons)) != len(horizons):
        raise ValueError("information coefficient horizons must be unique")
    if aggregation not in {"mean", "median"}:
        raise ValueError("aggregation must be mean or median")
    values: list[float] = []
    labels: list[str] = []
    for result in results:
        observed = result.statistics[statistic].dropna()
        values.append(float(getattr(observed, aggregation)()))
        median_count = float(result.statistics.loc[observed.index, "count"].median())
        labels.append(f"dates={len(observed)}<br>median n={median_count:g}")
    order = np.argsort(horizons)
    ordered_horizons = [str(horizons[int(position)]) for position in order]
    ordered_values = [values[int(position)] for position in order]
    ordered_labels = [labels[int(position)] for position in order]
    result = figure()
    result.add_trace(
        go.Bar(
            x=ordered_horizons,
            y=ordered_values,
            text=ordered_labels,
            textposition="outside",
            cliponaxis=False,
            marker={
                "pattern": {"shape": ["" if item % 2 == 0 else "/" for item in range(len(order))]}
            },
        )
    )
    result.add_hline(y=0, line_color="#222222")
    return finish_figure(
        result,
        xlabel="Forward horizon (observations)",
        ylabel=f"{aggregation.title()} {statistic.title()} IC",
        showlegend=False,
    )


def plot_quantile_returns(result: QuantilePortfolioResult) -> go.Figure:
    """Plot gross quantile forward returns with explicit definitions."""
    chart = plot_returns(_quantile_frame(result.returns))
    chart.update_layout(
        title=(
            f"{result.quantiles} {_quantile_weighting_label(result)} quantiles, "
            f"{result.horizon}-observation forward horizon"
        )
    )
    _annotate_quantile_coverage(chart, result.counts)
    return chart


def plot_cumulative_quantile_returns(result: QuantilePortfolioResult) -> go.Figure:
    """Plot compounded one-observation quantile returns without overlapping labels."""
    if result.horizon != 1:
        raise ValueError(
            "cumulative quantile returns require horizon 1; overlapping forward labels "
            "do not define an investable wealth path"
        )
    compounded = result.returns.add(1.0).cumprod().sub(1.0)
    chart = plot_cumulative_returns(_quantile_frame(compounded))
    label = _quantile_weighting_label(result)
    chart.update_layout(title=f"Cumulative performance of {result.quantiles} {label} quantiles")
    _annotate_quantile_coverage(chart, result.counts)
    return chart


def plot_quantile_spread(result: QuantilePortfolioResult) -> go.Figure:
    """Plot the top-minus-bottom forward-return spread."""
    chart = plot_returns(result.spread.to_frame("Top minus bottom"))
    chart.update_layout(
        title=f"Q{result.quantiles} minus Q1, {result.horizon}-observation forward horizon"
    )
    return chart


def plot_quantile_counts(result: QuantilePortfolioResult) -> go.Figure:
    """Plot the effective asset count in every quantile through time."""
    chart = plot_wide_series(_quantile_frame(result.counts), ylabel="Assets with forward returns")
    chart.update_layout(
        title=f"{result.quantiles} {_quantile_weighting_label(result)} quantiles"
    )
    return chart


def plot_quantile_turnover(result: QuantilePortfolioResult) -> go.Figure:
    """Plot one-way turnover for every signal quantile."""
    chart = plot_wide_series(_quantile_frame(result.turnover), ylabel="One-way turnover")
    chart.update_layout(
        title=f"{result.quantiles} {_quantile_weighting_label(result)} quantiles"
    )
    return chart


def plot_quantile_capacity(
    result: QuantilePortfolioResult,
    *,
    statistic: CapacityStatistic = "total_volume",
) -> go.Figure:
    """Plot one explicit capacity-oriented volume statistic by quantile."""
    _require_columns(result.capacity, {statistic}, name="quantile capacity")
    frame = result.capacity[statistic].unstack("quantile")
    if frame.empty or not frame.notna().any(axis=None):
        raise ValueError(f"quantile result has no observed {statistic} values")
    numeric = pd.DataFrame(
        frame.to_numpy(dtype=float, na_value=np.nan),
        index=frame.index,
        columns=frame.columns,
    )
    chart = plot_wide_series(_quantile_frame(numeric), ylabel=_label(statistic))
    chart.update_layout(
        title=f"{result.quantiles} {_quantile_weighting_label(result)} quantiles"
    )
    _annotate_counts(chart, result.capacity["volume_count"])
    return chart


def _quantile_weighting_label(result: QuantilePortfolioResult) -> str:
    return "equal-weight" if result.weighting == "equal" else "caller-weighted"


def plot_stability_comparison(
    values: pd.Series,
    *,
    statistic_name: str,
    comparison_name: str,
    counts: pd.Series | None = None,
) -> go.Figure:
    """Plot a caller-defined period, universe, split, or benchmark comparison."""
    if not statistic_name or not comparison_name:
        raise ValueError("statistic_name and comparison_name must not be empty")
    data = _numeric_series(values, name="values")
    if counts is not None:
        count_data = _numeric_series(counts, name="counts")
        if not count_data.index.equals(data.index):
            raise ValueError("counts must use the comparison index")
        text = [f"n={value:g}" for value in count_data]
    else:
        text = None
    result = figure()
    result.add_trace(
        go.Bar(
            x=[str(value) for value in data.index],
            y=data.to_numpy(dtype=float),
            text=text,
            textposition="outside",
            cliponaxis=False,
            marker={
                "pattern": {"shape": ["" if item % 2 == 0 else "/" for item in range(len(data))]}
            },
        )
    )
    result.add_hline(y=0, line_color="#222222")
    return finish_figure(
        result,
        xlabel=comparison_name,
        ylabel=statistic_name,
        showlegend=False,
    )


def plot_benchmark_comparison(
    result: BenchmarkComparison,
    *,
    statistic: BenchmarkStatistic = "mean_difference",
) -> go.Figure:
    """Plot one candidate-versus-benchmark summary with pairwise counts."""
    _require_columns(result.summary, {statistic, "count"}, name="benchmark summary")
    chart = plot_stability_comparison(
        result.summary[statistic],
        counts=result.summary["count"],
        statistic_name=_label(statistic),
        comparison_name="Candidate",
    )
    chart.update_layout(title=f"Comparison with {result.benchmark_name}")
    return chart


def _panel(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    if frame.empty or len(frame.columns) == 0:
        raise ValueError(f"{name} must contain observations and asset columns")
    if not frame.index.is_unique or not frame.columns.is_unique:
        raise ValueError(f"{name} index and columns must be unique")
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
        raise TypeError(f"{name} must be numeric")
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError(f"{name} must not contain infinite values")
    return frame.copy(deep=True)


def _numeric_series(values: pd.Series, *, name: str) -> pd.Series:
    if values.empty:
        raise ValueError(f"{name} must not be empty")
    if not pd.api.types.is_numeric_dtype(values.dtype):
        raise TypeError(f"{name} must be numeric")
    numeric = values.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(numeric).all():
        raise ValueError(f"{name} must contain finite values")
    return values.copy(deep=True)


def _aligned_groups(groups: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    if not groups.index.equals(signals.index) or not groups.columns.equals(signals.columns):
        raise ValueError("groups must use the signal index and columns")
    return groups.copy(deep=True)


def _date_position(index: pd.Index, date: pd.Timestamp) -> int:
    location = index.get_loc(date)
    if not isinstance(location, (int, np.integer)):
        raise ValueError("date must identify exactly one cross-section")
    return int(location)


def _require_columns(frame: pd.DataFrame, columns: set[str], *, name: str) -> None:
    missing = columns.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} does not contain {', '.join(sorted(missing))}")


def _quantile_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=lambda value: f"Q{value}")


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _date_label(value: pd.Timestamp) -> str:
    timestamp = pd.Timestamp(value)
    return str(timestamp.date()) if timestamp == timestamp.normalize() else timestamp.isoformat()


def _annotate_counts(result: go.Figure, counts: pd.Series) -> None:
    observed = counts.dropna().to_numpy(dtype=float)
    text = (
        f"Sample count n={np.min(observed):g}-{np.max(observed):g}"
        if observed.size
        else "Sample count unavailable"
    )
    result.add_annotation(
        x=0.5,
        y=0.98,
        xref="paper",
        yref="paper",
        text=text,
        showarrow=False,
        bgcolor="rgba(255,255,255,0.75)",
        xanchor="center",
        yanchor="top",
    )


def _annotate_quantile_coverage(result: go.Figure, counts: pd.DataFrame) -> None:
    observed = counts.to_numpy(dtype=float, na_value=np.nan)
    unavailable = int((observed == 0).sum())
    total = int(observed.size)
    result.add_annotation(
        x=0.5,
        y=0.98,
        xref="paper",
        yref="paper",
        text=f"Unavailable quantile-dates: {unavailable}/{total}",
        showarrow=False,
        bgcolor="rgba(255,255,255,0.75)",
        xanchor="center",
        yanchor="top",
    )
