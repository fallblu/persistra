# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Matplotlib plots for cross-sectional signal research results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.viz._common import plot_wide_series
from persistra.viz.market import plot_cumulative_returns, plot_returns

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes

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
    ax: Axes | None = None,
) -> Axes:
    """Plot one explicit cross-section as a histogram or group box comparison."""
    data = _panel(signals, name="signals")
    position = _date_position(data.index, date)
    values = data.iloc[position]
    axes = _axes(ax)
    if groups is None:
        observed = values.dropna()
        axes.hist(observed, bins=bins)
        axes.set(xlabel="Signal", ylabel="Asset count")
    else:
        classifications = _aligned_groups(groups, data)
        group_row = classifications.iloc[position]
        labels: list[str] = []
        samples: list[np.ndarray] = []
        for group in group_row.dropna().drop_duplicates():
            sample = values[group_row.eq(group).fillna(False)].dropna()
            if len(sample):
                labels.append(f"{group}\nn={len(sample)}")
                samples.append(sample.to_numpy(dtype=float))
        if not samples:
            raise ValueError("selected cross-section has no observed group samples")
        boxes = axes.boxplot(samples, tick_labels=labels, patch_artist=True)
        for position_number, box in enumerate(boxes["boxes"]):
            box.set_hatch("//" if position_number % 2 else "")
        axes.set(xlabel="Group", ylabel="Signal")
    axes.set_title(
        f"Signal distribution on {_date_label(cast('pd.Timestamp', data.index[position]))} "
        f"(n={int(values.notna().sum())}/{len(values)})"
    )
    return axes


def plot_signal_ranks(
    ranks: pd.DataFrame,
    *,
    date: pd.Timestamp,
    ax: Axes | None = None,
) -> Axes:
    """Plot already calculated cross-sectional ranks for one explicit date."""
    data = _panel(ranks, name="ranks")
    position = _date_position(data.index, date)
    values = data.iloc[position].dropna().sort_values()
    if values.empty:
        raise ValueError("selected cross-section has no observed ranks")
    axes = _axes(ax)
    bars = axes.barh([str(value) for value in values.index], values.to_numpy(dtype=float))
    for bar_position, bar in enumerate(bars):
        bar.set_hatch("//" if bar_position % 2 else "")
    axes.set(
        xlabel="Cross-sectional rank",
        ylabel="Asset",
        title=(
            f"Signal ranks on {_date_label(cast('pd.Timestamp', data.index[position]))} "
            f"(n={len(values)}/{len(data.columns)})"
        ),
    )
    return axes


def plot_group_comparison(
    result: GroupSignalResult,
    *,
    statistic: GroupStatistic = "mean_forward_return",
    ax: Axes | None = None,
) -> Axes:
    """Plot one group statistic through time with explicit horizon and coverage."""
    statistics = result.statistics
    _require_columns(statistics, {"count", statistic}, name="group statistics")
    frame = statistics[statistic].unstack("group")
    if frame.empty or not frame.notna().any(axis=None):
        raise ValueError(f"group result has no observed {statistic} values")
    axes = plot_wide_series(frame, ax=ax, ylabel=_label(statistic))
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set_title(f"Group comparison, {result.horizon}-observation forward horizon")
    _annotate_counts(axes, statistics["count"])
    return axes


def plot_information_coefficients(
    result: InformationCoefficientResult,
    *,
    statistic: InformationCoefficientStatistic = "rank",
    rolling: int | None = None,
    ax: Axes | None = None,
) -> Axes:
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
    axes = plot_wide_series(frame, ax=ax, ylabel=ylabel)
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set_title(f"{result.horizon}-observation forward horizon")
    _annotate_counts(axes, statistics["count"])
    return axes


def plot_information_coefficient_horizons(
    results: Sequence[InformationCoefficientResult],
    *,
    statistic: InformationCoefficientStatistic = "rank",
    aggregation: InformationCoefficientAggregation = "mean",
    ax: Axes | None = None,
) -> Axes:
    """Compare one aggregate IC across explicit, unique forward horizons."""
    if not results:
        raise ValueError("results must contain at least one information coefficient result")
    horizons = [result.horizon for result in results]
    if len(set(horizons)) != len(horizons):
        raise ValueError("information coefficient horizons must be unique")
    if aggregation not in {"mean", "median"}:
        raise ValueError("aggregation must be mean or median")
    values: list[float] = []
    observation_counts: list[int] = []
    pairwise_counts: list[float] = []
    for result in results:
        observed = result.statistics[statistic].dropna()
        values.append(float(getattr(observed, aggregation)()))
        observation_counts.append(len(observed))
        pairwise_counts.append(float(result.statistics.loc[observed.index, "count"].median()))
    order = np.argsort(horizons)
    ordered_horizons = [horizons[int(position)] for position in order]
    ordered_values = [values[int(position)] for position in order]
    axes = _axes(ax)
    bars = axes.bar([str(horizon) for horizon in ordered_horizons], ordered_values)
    for bar_position, (bar, source_position) in enumerate(zip(bars, order, strict=True)):
        bar.set_hatch("//" if bar_position % 2 else "")
        axes.annotate(
            f"dates={observation_counts[int(source_position)]}\n"
            f"median n={pairwise_counts[int(source_position)]:g}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 3 if bar.get_height() >= 0 else -3),
            textcoords="offset points",
            ha="center",
            va="bottom" if bar.get_height() >= 0 else "top",
            fontsize="small",
        )
    axes.margins(y=0.18)
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set(
        xlabel="Forward horizon (observations)",
        ylabel=f"{aggregation.title()} {statistic.title()} IC",
    )
    return axes


def plot_quantile_returns(result: QuantilePortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot equal-weight quantile forward returns with explicit definitions."""
    frame = _quantile_frame(result.returns)
    axes = plot_returns(frame, ax=ax)
    axes.set_title(
        f"{result.quantiles} equal-weight quantiles, {result.horizon}-observation forward horizon"
    )
    _annotate_quantile_coverage(axes, result.counts)
    return axes


def plot_cumulative_quantile_returns(
    result: QuantilePortfolioResult, *, ax: Axes | None = None
) -> Axes:
    """Plot compounded one-observation quantile returns without overlapping labels."""
    if result.horizon != 1:
        raise ValueError(
            "cumulative quantile returns require horizon 1; overlapping forward labels "
            "do not define an investable wealth path"
        )
    compounded = result.returns.add(1.0).cumprod().sub(1.0)
    axes = plot_cumulative_returns(_quantile_frame(compounded), ax=ax)
    axes.set_title(f"Cumulative performance of {result.quantiles} equal-weight quantiles")
    _annotate_quantile_coverage(axes, result.counts)
    return axes


def plot_quantile_spread(result: QuantilePortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot the top-minus-bottom forward-return spread."""
    frame = result.spread.to_frame("Top minus bottom")
    axes = plot_returns(frame, ax=ax)
    axes.set_title(f"Q{result.quantiles} minus Q1, {result.horizon}-observation forward horizon")
    return axes


def plot_quantile_counts(result: QuantilePortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot the available asset count in every quantile through time."""
    axes = plot_wide_series(
        _quantile_frame(result.counts), ax=ax, ylabel="Assets with forward returns"
    )
    axes.set_title(f"{result.quantiles} equal-weight quantiles")
    return axes


def plot_quantile_turnover(result: QuantilePortfolioResult, *, ax: Axes | None = None) -> Axes:
    """Plot one-way turnover for every equal-weight signal quantile."""
    axes = plot_wide_series(_quantile_frame(result.turnover), ax=ax, ylabel="One-way turnover")
    axes.set_title(f"{result.quantiles} equal-weight quantiles")
    return axes


def plot_quantile_capacity(
    result: QuantilePortfolioResult,
    *,
    statistic: CapacityStatistic = "total_volume",
    ax: Axes | None = None,
) -> Axes:
    """Plot one explicit capacity-oriented volume statistic by quantile."""
    _require_columns(result.capacity, {statistic}, name="quantile capacity")
    frame = result.capacity[statistic].unstack("quantile")
    if frame.empty or not frame.notna().any(axis=None):
        raise ValueError(f"quantile result has no observed {statistic} values")
    frame = pd.DataFrame(
        frame.to_numpy(dtype=float, na_value=np.nan),
        index=frame.index,
        columns=frame.columns,
    )
    axes = plot_wide_series(_quantile_frame(frame), ax=ax, ylabel=_label(statistic))
    axes.set_title(f"{result.quantiles} equal-weight quantiles")
    _annotate_counts(axes, result.capacity["volume_count"])
    return axes


def plot_stability_comparison(
    values: pd.Series,
    *,
    statistic_name: str,
    comparison_name: str,
    counts: pd.Series | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot a caller-defined period, universe, split, or benchmark comparison."""
    if not statistic_name or not comparison_name:
        raise ValueError("statistic_name and comparison_name must not be empty")
    data = _numeric_series(values, name="values")
    if counts is not None:
        count_data = _numeric_series(counts, name="counts")
        if not count_data.index.equals(data.index):
            raise ValueError("counts must use the comparison index")
    else:
        count_data = None
    axes = _axes(ax)
    bars = axes.bar([str(value) for value in data.index], data.to_numpy(dtype=float))
    for position, bar in enumerate(bars):
        bar.set_hatch("//" if position % 2 else "")
        if count_data is not None:
            axes.annotate(
                f"n={count_data.iloc[position]:g}",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3 if bar.get_height() >= 0 else -3),
                textcoords="offset points",
                ha="center",
                va="bottom" if bar.get_height() >= 0 else "top",
                fontsize="small",
            )
    axes.margins(y=0.15)
    axes.axhline(0, color="black", linewidth=0.8)
    axes.set(xlabel=comparison_name, ylabel=statistic_name)
    return axes


def plot_benchmark_comparison(
    result: BenchmarkComparison,
    *,
    statistic: BenchmarkStatistic = "mean_difference",
    ax: Axes | None = None,
) -> Axes:
    """Plot one candidate-versus-benchmark summary with pairwise counts."""
    _require_columns(result.summary, {statistic, "count"}, name="benchmark summary")
    axes = plot_stability_comparison(
        result.summary[statistic],
        counts=result.summary["count"],
        statistic_name=_label(statistic),
        comparison_name="Candidate",
        ax=ax,
    )
    axes.set_title(f"Comparison with {result.benchmark_name}")
    return axes


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


def _annotate_counts(axes: Axes, counts: pd.Series) -> None:
    observed = counts.dropna().to_numpy(dtype=float)
    if observed.size:
        text = f"Sample count n={np.min(observed):g}-{np.max(observed):g}"
    else:
        text = "Sample count unavailable"
    axes.text(
        0.5,
        0.98,
        text,
        transform=axes.transAxes,
        ha="center",
        va="top",
        fontsize="small",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75},
    )


def _annotate_quantile_coverage(axes: Axes, counts: pd.DataFrame) -> None:
    observed = counts.to_numpy(dtype=float, na_value=np.nan)
    unavailable = int((observed == 0).sum())
    total = int(observed.size)
    axes.text(
        0.5,
        0.98,
        f"Unavailable quantile-dates: {unavailable}/{total}",
        transform=axes.transAxes,
        ha="center",
        va="top",
        fontsize="small",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75},
    )


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]
