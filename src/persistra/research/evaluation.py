"""Cross-sectional signal evaluation with explicit label and sample semantics."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError
from persistra.research._validation import aligned_panel, cross_sectional_frame, numeric_frame
from persistra.research.model import (
    BenchmarkComparison,
    ForwardReturnLabels,
    GroupSignalResult,
    InformationCoefficientResult,
    MultipleTestingResult,
    QuantilePortfolioResult,
)

CorrectionMethod = Literal["bonferroni", "benjamini-hochberg"]


def information_coefficients(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    *,
    groups: pd.DataFrame | None = None,
    minimum_count: int = 3,
) -> InformationCoefficientResult:
    """Calculate per-date Pearson and rank ICs with pairwise sample counts."""
    data, forward, classifications = _evaluation_inputs(signals, labels, groups=groups)
    if isinstance(minimum_count, bool) or minimum_count < 2:
        raise ValueError("minimum_count must be an integer of at least 2")
    rows: list[dict[str, Any]] = []
    if classifications is None:
        for position, date in enumerate(data.index):
            signal_row = data.iloc[position]
            return_row = forward.iloc[position]
            count, pearson, rank = _correlations(signal_row, return_row, minimum_count)
            rows.append(
                {"date": date, "count": count, "pearson": pearson, "rank": rank}
            )
        statistics = pd.DataFrame(rows).set_index("date")
    else:
        for position, date in enumerate(data.index):
            signal_row = data.iloc[position]
            return_row = forward.iloc[position]
            group_row = classifications.iloc[position]
            for group in group_row.dropna().drop_duplicates():
                mask = group_row.eq(group).fillna(False)
                count, pearson, rank = _correlations(
                    signal_row.loc[mask], return_row.loc[mask], minimum_count
                )
                rows.append(
                    {
                        "date": date,
                        "group": group,
                        "count": count,
                        "pearson": pearson,
                        "rank": rank,
                    }
                )
        statistics = _grouped_statistics(rows, ["count", "pearson", "rank"])
    statistics = statistics[["count", "pearson", "rank"]]
    return InformationCoefficientResult(statistics, labels.horizon, classifications is not None)


def quantile_portfolios(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    *,
    quantiles: int = 5,
    groups: pd.DataFrame | None = None,
    volumes: pd.DataFrame | None = None,
) -> QuantilePortfolioResult:
    """Form equal-weight signal quantiles and report returns and implementation diagnostics.

    Quantiles are assigned within each date and, when supplied, within each classification.
    Signal ties remain together. A cross-section or group with fewer assets than requested
    quantiles is left unassigned instead of creating misleading sparse portfolios.
    """
    data, forward, classifications = _evaluation_inputs(signals, labels, groups=groups)
    if isinstance(quantiles, bool) or quantiles < 2:
        raise ValueError("quantiles must be an integer of at least 2")
    volume_data = None
    if volumes is not None:
        volume_data = numeric_frame(aligned_panel(volumes, data, name="volumes"))
        if volume_data.lt(0).any(axis=None):
            raise AnalysisError("volumes must not be negative")

    assignments = _quantile_assignments(data, quantiles, classifications)
    columns = pd.Index(range(1, quantiles + 1), name="quantile")
    returns = pd.DataFrame(np.nan, index=data.index, columns=columns, dtype=float)
    counts = pd.DataFrame(0, index=data.index, columns=columns, dtype="int64")
    turnover = pd.DataFrame(np.nan, index=data.index, columns=columns, dtype=float)
    capacity_rows: list[dict[str, Any]] = []
    weights: dict[int, pd.DataFrame] = {}

    for quantile in columns:
        membership = assignments.eq(quantile).fillna(False)
        available = membership & forward.notna()
        counts[quantile] = available.sum(axis="columns")
        returns[quantile] = forward.where(available).mean(axis="columns")
        weight = membership.astype(float)
        weight = weight.div(weight.sum(axis="columns").replace(0, np.nan), axis="index")
        weights[int(quantile)] = weight
        for position, date in enumerate(data.index):
            membership_row = membership.iloc[position]
            observed = (
                None
                if volume_data is None
                else volume_data.iloc[position].where(membership_row)
            )
            capacity_rows.append(_capacity_row(date, int(quantile), observed))

    for quantile, weight in weights.items():
        for position in range(1, len(data.index)):
            current = weight.iloc[position]
            previous = weight.iloc[position - 1]
            if current.notna().any() and previous.notna().any():
                turnover.iloc[position, quantile - 1] = (
                    current.fillna(0).sub(previous.fillna(0)).abs().sum() / 2
                )

    capacity = pd.DataFrame(capacity_rows).set_index(["date", "quantile"])
    spread = returns[quantiles].sub(returns[1]).rename("top_minus_bottom")
    summary = _quantile_summary(returns, counts, turnover, capacity, spread)
    return QuantilePortfolioResult(
        assignments,
        returns,
        counts,
        turnover,
        capacity,
        spread,
        summary,
        labels.horizon,
        quantiles,
    )


def summarize_groups(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    groups: pd.DataFrame,
    *,
    minimum_count: int = 3,
) -> GroupSignalResult:
    """Summarize signal levels, forward returns, and ICs by time-varying group."""
    data, forward, classifications = _evaluation_inputs(signals, labels, groups=groups)
    if classifications is None:
        raise AssertionError("group validation did not preserve classifications")
    if isinstance(minimum_count, bool) or minimum_count < 2:
        raise ValueError("minimum_count must be an integer of at least 2")
    rows: list[dict[str, Any]] = []
    for position, date in enumerate(data.index):
        signal_panel_row = data.iloc[position]
        return_panel_row = forward.iloc[position]
        group_row = classifications.iloc[position]
        for group in group_row.dropna().drop_duplicates():
            mask = group_row.eq(group).fillna(False)
            signal_row = signal_panel_row.loc[mask]
            return_row = return_panel_row.loc[mask]
            count, pearson, rank = _correlations(signal_row, return_row, minimum_count)
            rows.append(
                {
                    "date": date,
                    "group": group,
                    "count": count,
                    "mean_signal": signal_row.mean(),
                    "signal_standard_deviation": signal_row.std(ddof=1),
                    "mean_forward_return": return_row.mean(),
                    "pearson": pearson,
                    "rank": rank,
                }
            )
    columns = [
        "count",
        "mean_signal",
        "signal_standard_deviation",
        "mean_forward_return",
        "pearson",
        "rank",
    ]
    return GroupSignalResult(_grouped_statistics(rows, columns), labels.horizon)


def compare_benchmark(
    candidates: pd.DataFrame,
    benchmark: pd.Series,
    *,
    benchmark_name: str = "benchmark",
) -> BenchmarkComparison:
    """Compare candidate return series with one aligned simple-return benchmark."""
    data = cross_sectional_frame(candidates, name="candidate")
    if not pd.api.types.is_numeric_dtype(benchmark.dtype):
        raise AnalysisError("benchmark must be numeric")
    reference = benchmark.copy(deep=True)
    if not reference.index.equals(data.index):
        raise ValueError("benchmark must use the candidate index")
    values = reference.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise AnalysisError("benchmark must not contain infinite values")
    if data.lt(-1).any(axis=None) or reference.lt(-1).any():
        raise AnalysisError("simple returns must not be less than -1")
    differences = data.sub(reference, axis="index")
    rows: list[dict[str, Any]] = []
    for candidate in data.columns:
        paired = pd.concat([data[candidate], reference], axis="columns", sort=False).dropna()
        paired.columns = ["candidate", "benchmark"]
        difference = paired["candidate"].sub(paired["benchmark"])
        rows.append(
            {
                "candidate": candidate,
                "count": len(paired),
                "mean_candidate": paired["candidate"].mean(),
                "mean_benchmark": paired["benchmark"].mean(),
                "mean_difference": difference.mean(),
                "tracking_error": difference.std(ddof=1),
                "win_rate": difference.gt(0).mean(),
                "correlation": paired["candidate"].corr(paired["benchmark"]),
            }
        )
    columns = [
        "count",
        "mean_candidate",
        "mean_benchmark",
        "mean_difference",
        "tracking_error",
        "win_rate",
        "correlation",
    ]
    if rows:
        summary = pd.DataFrame(rows).set_index("candidate")[columns]
    else:
        summary = pd.DataFrame(columns=columns, index=pd.Index([], name="candidate"))
    return BenchmarkComparison(differences, summary, benchmark_name)


def adjust_pvalues(
    pvalues: pd.Series,
    *,
    method: CorrectionMethod = "benjamini-hochberg",
    alpha: float = 0.05,
) -> MultipleTestingResult:
    """Adjust explicit hypothesis p-values for repeated searches."""
    if method not in {"bonferroni", "benjamini-hochberg"}:
        raise ValueError("unsupported multiple-testing method")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not pvalues.index.is_unique:
        raise ValueError("hypothesis labels must be unique")
    if not pd.api.types.is_numeric_dtype(pvalues.dtype):
        raise AnalysisError("p-values must be numeric")
    raw = pvalues.astype(float).copy(deep=True)
    if raw.dropna().lt(0).any() or raw.dropna().gt(1).any():
        raise ValueError("p-values must be between 0 and 1")
    observed = raw.dropna()
    if method == "bonferroni":
        adjusted_observed = observed.mul(len(observed)).clip(upper=1)
    else:
        order = observed.sort_values(kind="mergesort")
        ranks = np.arange(1, len(order) + 1, dtype=float)
        adjusted_sorted = order.mul(len(order)).div(ranks)
        adjusted_sorted = adjusted_sorted.iloc[::-1].cummin().iloc[::-1].clip(upper=1)
        adjusted_observed = adjusted_sorted.reindex(observed.index)
    adjusted = pd.Series(np.nan, index=raw.index, dtype=float, name="adjusted_pvalue")
    adjusted.loc[adjusted_observed.index] = adjusted_observed
    rejected = adjusted.le(alpha).astype("boolean").mask(raw.isna())
    statistics = pd.concat(
        [raw.rename("raw_pvalue"), adjusted, rejected.rename("rejected")], axis="columns"
    )
    return MultipleTestingResult(statistics, method, alpha)


def _evaluation_inputs(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    *,
    groups: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    data = cross_sectional_frame(signals, name="signal")
    forward = numeric_frame(aligned_panel(labels.frame, data, name="labels"))
    classifications = None if groups is None else aligned_panel(groups, data, name="groups")
    return data, forward, classifications


def _correlations(
    signals: pd.Series, returns: pd.Series, minimum_count: int
) -> tuple[int, float, float]:
    paired = pd.concat([signals, returns], axis="columns").dropna()
    paired.columns = ["signal", "return"]
    count = len(paired)
    if (
        count < minimum_count
        or paired["signal"].nunique() < 2
        or paired["return"].nunique() < 2
    ):
        return count, float("nan"), float("nan")
    pearson = paired["signal"].corr(paired["return"])
    rank = paired["signal"].rank().corr(paired["return"].rank())
    return count, float(pearson), float(rank)


def _grouped_statistics(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame(rows).set_index(["date", "group"])[columns]
    index = pd.MultiIndex.from_arrays([[], []], names=["date", "group"])
    return pd.DataFrame(columns=columns, index=index)


def _quantile_assignments(
    signals: pd.DataFrame,
    quantiles: int,
    groups: pd.DataFrame | None,
) -> pd.DataFrame:
    assignments = pd.DataFrame(index=signals.index, columns=signals.columns, dtype="Int64")
    for position in range(len(signals.index)):
        row = signals.iloc[position]
        if groups is None:
            assignments.iloc[position] = _assign_row(row, quantiles)
            continue
        assigned_row = pd.Series(index=signals.columns, dtype="Int64")
        group_row = groups.iloc[position]
        for group in group_row.dropna().drop_duplicates():
            mask = group_row.eq(group).fillna(False)
            assigned_row.loc[mask] = _assign_row(row.loc[mask], quantiles)
        assignments.iloc[position] = assigned_row
    return assignments


def _assign_row(signals: pd.Series, quantiles: int) -> pd.Series:
    observed = signals.dropna()
    result = pd.Series(index=signals.index, dtype="Int64")
    if len(observed) < quantiles:
        return result
    ranks = observed.rank(method="average")
    labels = ranks.sub(1).mul(quantiles).floordiv(len(observed)).add(1).astype("Int64")
    result.loc[observed.index] = labels
    return result


def _capacity_row(
    date: object,
    quantile: int,
    volumes: pd.Series | None,
) -> dict[str, Any]:
    observed = pd.Series(dtype=float) if volumes is None else volumes.dropna()
    return {
        "date": date,
        "quantile": quantile,
        "volume_count": len(observed),
        "total_volume": observed.sum(min_count=1),
        "median_volume": observed.median(),
        "minimum_volume": observed.min(),
    }


def _quantile_summary(
    returns: pd.DataFrame,
    counts: pd.DataFrame,
    turnover: pd.DataFrame,
    capacity: pd.DataFrame,
    spread: pd.Series,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for quantile in returns.columns:
        values = returns[quantile].dropna()
        capacity_slice = capacity.xs(quantile, level="quantile")
        rows.append(
            {
                "portfolio": f"q{quantile}",
                "periods": len(values),
                "mean_return": values.mean(),
                "volatility": values.std(ddof=1),
                "positive_rate": values.gt(0).mean(),
                "mean_turnover": turnover[quantile].mean(),
                "median_assets": counts[quantile].median(),
                "median_total_volume": capacity_slice["total_volume"].median(),
            }
        )
    spread_values = spread.dropna()
    rows.append(
        {
            "portfolio": "top_minus_bottom",
            "periods": len(spread_values),
            "mean_return": spread_values.mean(),
            "volatility": spread_values.std(ddof=1),
            "positive_rate": spread_values.gt(0).mean(),
            "mean_turnover": np.nan,
            "median_assets": np.nan,
            "median_total_volume": np.nan,
        }
    )
    return pd.DataFrame(rows).set_index("portfolio")
