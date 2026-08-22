"""Cross-sectional signal evaluation with explicit label and sample semantics."""

from __future__ import annotations

from numbers import Real
from statistics import NormalDist
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.research._validation import aligned_panel, cross_sectional_frame, numeric_frame
from persistra.research.model import (
    BenchmarkComparison,
    ForwardReturnLabels,
    GroupSignalResult,
    InformationCoefficientResult,
    MultipleTestingResult,
    QuantilePortfolioResult,
    SharpeSelectionDiagnostic,
    SharpeSelectionSuccess,
    SharpeSelectionUnavailable,
)

CorrectionMethod = Literal["bonferroni", "benjamini-hochberg"]
_STANDARD_NORMAL = NormalDist()


def information_coefficients(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    *,
    groups: pd.DataFrame | None = None,
    minimum_count: int = 3,
) -> InformationCoefficientResult:
    """Calculate per-date Pearson and rank ICs with pairwise sample counts."""
    data, forward, classifications = _evaluation_inputs(signals, labels, groups=groups)
    minimum_count = require_integer(minimum_count, name="minimum_count", minimum=2)
    rows: list[dict[str, Any]] = []
    if classifications is None:
        for position, date in enumerate(data.index):
            signal_row = data.iloc[position]
            return_row = forward.iloc[position]
            count, pearson, rank = _correlations(signal_row, return_row, minimum_count)
            rows.append(
                {"date": date, "count": count, "pearson": pearson, "rank": rank}
            )
        statistics = _information_coefficient_statistics(
            rows,
            cast("pd.DatetimeIndex", data.index),
        )
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
        statistics = _grouped_statistics(
            rows,
            ["count", "pearson", "rank"],
            date_index=cast("pd.DatetimeIndex", data.index),
        )
    statistics = statistics[["count", "pearson", "rank"]]
    return InformationCoefficientResult(statistics, labels.horizon, classifications is not None)


def quantile_portfolios(
    signals: pd.DataFrame,
    labels: ForwardReturnLabels,
    *,
    quantiles: int = 5,
    groups: pd.DataFrame | None = None,
    volumes: pd.DataFrame | None = None,
    weights: pd.DataFrame | None = None,
    costs: float | pd.Series | pd.DataFrame = 0.0,
) -> QuantilePortfolioResult:
    """Form weighted signal quantiles and report gross, cost, and net results.

    Quantiles are assigned within each date and, when supplied, within each classification.
    Signal ties remain together. A cross-section or group with fewer assets than requested
    quantiles is left unassigned instead of creating misleading sparse portfolios. Costs are
    decimal return charges per unit of absolute asset weight traded.
    """
    data, forward, classifications = _evaluation_inputs(signals, labels, groups=groups)
    quantiles = require_integer(quantiles, name="quantiles", minimum=2)
    volume_data = None
    if volumes is not None:
        volume_data = numeric_frame(aligned_panel(volumes, data, name="volumes"))
        if volume_data.lt(0).any(axis=None):
            raise AnalysisError("volumes must not be negative")
    raw_weights = pd.DataFrame(1.0, index=data.index, columns=data.columns)
    weighting: Literal["equal", "caller"] = "equal"
    if weights is not None:
        raw_weights = numeric_frame(aligned_panel(weights, data, name="weights"))
        if raw_weights.lt(0).any(axis=None):
            raise AnalysisError("weights must not be negative")
        weighting = "caller"
    cost_data = _linear_cost_panel(costs, data)

    assignments = _quantile_assignments(data, quantiles, classifications)
    columns = pd.Index(range(1, quantiles + 1), name="quantile")
    returns = pd.DataFrame(np.nan, index=data.index, columns=columns, dtype=float)
    modeled_costs = pd.DataFrame(0.0, index=data.index, columns=columns, dtype=float)
    counts = pd.DataFrame(0, index=data.index, columns=columns, dtype="int64")
    turnover = pd.DataFrame(0.0, index=data.index, columns=columns, dtype=float)
    capacity_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    quantile_weights: dict[int, pd.DataFrame] = {}
    formation_weights = pd.DataFrame(0.0, index=data.index, columns=data.columns)

    for quantile in columns:
        membership = assignments.eq(quantile).fillna(False)
        weight = _normalize_quantile_weights(membership, raw_weights, classifications)
        return_weight = _normalize_quantile_weights(
            membership & forward.notna(), raw_weights, classifications
        )
        quantile_weights[int(quantile)] = weight
        formation_weights = formation_weights.add(weight, fill_value=0.0)
        counts[quantile] = return_weight.gt(0).sum(axis="columns")
        weighted_returns = forward.fillna(0.0).mul(return_weight).sum(axis="columns")
        returns[quantile] = weighted_returns.mask(return_weight.sum(axis="columns").eq(0))
        for position, date in enumerate(data.index):
            membership_row = membership.iloc[position]
            observed = (
                None
                if volume_data is None
                else volume_data.iloc[position].where(membership_row)
            )
            capacity_rows.append(_capacity_row(date, int(quantile), observed))
            assigned = raw_weights.iloc[position].where(membership_row)
            diagnostic_rows.append(
                _weight_diagnostic_row(
                    date,
                    int(quantile),
                    assigned,
                    int(membership_row.sum()),
                    int(return_weight.iloc[position].gt(0).sum()),
                )
            )

    for quantile, weight in quantile_weights.items():
        previous = pd.Series(0.0, index=data.columns)
        previous_cash = 1.0
        for position in range(len(data.index)):
            current = weight.iloc[position]
            current_cash = 1.0 - float(current.sum())
            absolute_trade = current.sub(previous).abs()
            turnover.iloc[position, quantile - 1] = (
                float(absolute_trade.sum()) + abs(current_cash - previous_cash)
            ) / 2.0
            modeled_costs.iloc[position, quantile - 1] = float(
                absolute_trade.mul(cost_data.iloc[position]).sum()
            )
            previous = current
            previous_cash = current_cash

    capacity = _quantile_capacity(
        capacity_rows,
        cast("pd.DatetimeIndex", data.index),
    )
    weight_diagnostics = _quantile_weight_diagnostics(
        diagnostic_rows, cast("pd.DatetimeIndex", data.index)
    )
    net_returns = returns.sub(modeled_costs).where(returns.notna())
    spread = returns[quantiles].sub(returns[1]).rename("top_minus_bottom")
    spread_costs = modeled_costs[quantiles].add(modeled_costs[1]).rename("spread_costs")
    net_spread = spread.sub(spread_costs).rename("net_top_minus_bottom")
    summary = _quantile_summary(
        returns,
        modeled_costs,
        net_returns,
        counts,
        turnover,
        capacity,
        spread,
        spread_costs,
        net_spread,
        horizon=labels.horizon,
    )
    return QuantilePortfolioResult(
        assignments,
        formation_weights,
        weight_diagnostics,
        returns,
        modeled_costs,
        net_returns,
        counts,
        turnover,
        capacity,
        spread,
        spread_costs,
        net_spread,
        summary,
        labels.horizon,
        quantiles,
        weighting,
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
    minimum_count = require_integer(minimum_count, name="minimum_count", minimum=2)
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
    return GroupSignalResult(
        _grouped_statistics(
            rows,
            columns,
            date_index=cast("pd.DatetimeIndex", data.index),
        ),
        labels.horizon,
    )


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


def probabilistic_sharpe_ratio(
    returns: pd.Series,
    *,
    periods_per_year: float,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
) -> SharpeSelectionDiagnostic:
    """Estimate the probability that Sharpe exceeds a caller-declared benchmark.

    ``skewness`` and ``kurtosis`` are caller-supplied standardized population moments;
    kurtosis uses the Pearson convention where a normal distribution has value three.
    """
    annualization, benchmark, declared_skewness, declared_kurtosis = _sharpe_selection_policy(
        periods_per_year=periods_per_year,
        benchmark_sharpe=benchmark_sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
    )
    return _sharpe_selection_diagnostic(
        returns,
        method="probabilistic_sharpe",
        periods_per_year=annualization,
        trial_count=1,
        benchmark_sharpe=benchmark,
        skewness=declared_skewness,
        kurtosis=declared_kurtosis,
        trial_sharpe_standard_deviation=None,
    )


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    periods_per_year: float,
    trial_count: int,
    trial_sharpe_standard_deviation: float,
    skewness: float,
    kurtosis: float,
) -> SharpeSelectionDiagnostic:
    """Estimate Sharpe significance after an explicit repeated strategy search.

    ``trial_sharpe_standard_deviation`` is the dispersion of annualized Sharpe ratios across
    the declared trials. The expected maximum independent-trial Sharpe becomes the benchmark.
    """
    trial_count = require_integer(trial_count, name="trial_count", minimum=2)
    trial_dispersion = _finite_scalar(
        trial_sharpe_standard_deviation,
        name="trial_sharpe_standard_deviation",
        minimum=0.0,
    )
    expected_maximum = trial_dispersion * (
        (1.0 - np.euler_gamma) * _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / trial_count)
        + np.euler_gamma * _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / (trial_count * np.e))
    )
    annualization, benchmark, declared_skewness, declared_kurtosis = _sharpe_selection_policy(
        periods_per_year=periods_per_year,
        benchmark_sharpe=float(expected_maximum),
        skewness=skewness,
        kurtosis=kurtosis,
    )
    return _sharpe_selection_diagnostic(
        returns,
        method="deflated_sharpe",
        periods_per_year=annualization,
        trial_count=trial_count,
        benchmark_sharpe=benchmark,
        skewness=declared_skewness,
        kurtosis=declared_kurtosis,
        trial_sharpe_standard_deviation=trial_dispersion,
    )


def _sharpe_selection_policy(
    *,
    periods_per_year: float,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
) -> tuple[float, float, float, float]:
    annualization = _finite_scalar(periods_per_year, name="periods_per_year", minimum=0.0)
    if annualization == 0:
        raise ValueError("periods_per_year must be positive")
    benchmark = _finite_scalar(benchmark_sharpe, name="benchmark_sharpe")
    declared_skewness = _finite_scalar(skewness, name="skewness")
    declared_kurtosis = _finite_scalar(kurtosis, name="kurtosis", minimum=1.0)
    return annualization, benchmark, declared_skewness, declared_kurtosis


def _sharpe_selection_diagnostic(
    returns: pd.Series,
    *,
    method: Literal["probabilistic_sharpe", "deflated_sharpe"],
    periods_per_year: float,
    trial_count: int,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
    trial_sharpe_standard_deviation: float | None,
) -> SharpeSelectionDiagnostic:
    if not pd.api.types.is_numeric_dtype(returns.dtype):
        raise AnalysisError("returns must be numeric")
    sample = returns.astype(float).copy(deep=True)
    if np.isinf(sample.to_numpy(dtype=float, na_value=np.nan)).any():
        raise AnalysisError("returns must not contain infinite values")
    observed = sample.dropna()
    if len(observed) < 2:
        return _unavailable_sharpe_selection(
            reason="at least two returns are required",
            method=method,
            sample_count=len(observed),
            periods_per_year=periods_per_year,
            trial_count=trial_count,
            benchmark_sharpe=benchmark_sharpe,
            skewness=skewness,
            kurtosis=kurtosis,
            trial_sharpe_standard_deviation=trial_sharpe_standard_deviation,
        )
    standard_deviation = float(observed.std(ddof=1))
    if standard_deviation == 0.0:
        return _unavailable_sharpe_selection(
            reason="return standard deviation is zero",
            method=method,
            sample_count=len(observed),
            periods_per_year=periods_per_year,
            trial_count=trial_count,
            benchmark_sharpe=benchmark_sharpe,
            skewness=skewness,
            kurtosis=kurtosis,
            trial_sharpe_standard_deviation=trial_sharpe_standard_deviation,
        )
    mean_return = float(observed.mean())
    period_sharpe = mean_return / standard_deviation
    observed_sharpe = period_sharpe * np.sqrt(periods_per_year)
    variance_term = 1.0 - skewness * period_sharpe + (
        (kurtosis - 1.0) * period_sharpe**2 / 4.0
    )
    if variance_term <= 0.0:
        return _unavailable_sharpe_selection(
            reason="declared moments imply a nonpositive Sharpe sampling variance",
            method=method,
            sample_count=len(observed),
            periods_per_year=periods_per_year,
            trial_count=trial_count,
            benchmark_sharpe=benchmark_sharpe,
            skewness=skewness,
            kurtosis=kurtosis,
            trial_sharpe_standard_deviation=trial_sharpe_standard_deviation,
        )
    standard_error = np.sqrt(periods_per_year * variance_term / (len(observed) - 1))
    test_statistic = (observed_sharpe - benchmark_sharpe) / standard_error
    return SharpeSelectionSuccess(
        method=method,
        sample_count=len(observed),
        periods_per_year=periods_per_year,
        trial_count=trial_count,
        mean_return=mean_return,
        standard_deviation=standard_deviation,
        observed_sharpe=float(observed_sharpe),
        benchmark_sharpe=benchmark_sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
        standard_error=float(standard_error),
        test_statistic=float(test_statistic),
        probability=_STANDARD_NORMAL.cdf(float(test_statistic)),
        trial_sharpe_standard_deviation=trial_sharpe_standard_deviation,
    )


def _unavailable_sharpe_selection(
    *,
    reason: str,
    method: Literal["probabilistic_sharpe", "deflated_sharpe"],
    sample_count: int,
    periods_per_year: float,
    trial_count: int,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
    trial_sharpe_standard_deviation: float | None,
) -> SharpeSelectionUnavailable:
    return SharpeSelectionUnavailable(
        method=method,
        reason=reason,
        sample_count=sample_count,
        periods_per_year=periods_per_year,
        trial_count=trial_count,
        benchmark_sharpe=benchmark_sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
        trial_sharpe_standard_deviation=trial_sharpe_standard_deviation,
    )


def _finite_scalar(value: object, *, name: str, minimum: float | None = None) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite scalar")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


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


def _information_coefficient_statistics(
    rows: list[dict[str, Any]],
    date_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    columns = ["count", "pearson", "rank"]
    if rows:
        return pd.DataFrame(rows).set_index("date")[columns]
    index = pd.DatetimeIndex([], tz=date_index.tz, name="date")
    return pd.DataFrame(
        {
            "count": pd.Series(index=index, dtype="int64"),
            "pearson": pd.Series(index=index, dtype=float),
            "rank": pd.Series(index=index, dtype=float),
        }
    )


def _grouped_statistics(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    date_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    if rows:
        return pd.DataFrame(rows).set_index(["date", "group"])[columns]
    index = pd.MultiIndex.from_arrays(
        [
            pd.DatetimeIndex([], tz=date_index.tz),
            pd.Index([], dtype=object),
        ],
        names=["date", "group"],
    )
    data = {
        column: pd.Series(index=index, dtype="int64" if column == "count" else float)
        for column in columns
    }
    return pd.DataFrame(data)


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


def _linear_cost_panel(
    costs: float | pd.Series | pd.DataFrame,
    reference: pd.DataFrame,
) -> pd.DataFrame:
    if isinstance(costs, pd.DataFrame):
        result = numeric_frame(aligned_panel(costs, reference, name="costs"))
    elif isinstance(costs, pd.Series):
        if not costs.index.equals(reference.columns):
            raise ValueError("asset costs must use the signal columns")
        if not pd.api.types.is_numeric_dtype(costs.dtype):
            raise AnalysisError("costs must be numeric")
        values = costs.to_numpy(dtype=float, na_value=np.nan)
        if np.isnan(values).any() or np.isinf(values).any():
            raise AnalysisError("costs must be finite and complete")
        result = pd.DataFrame(
            np.broadcast_to(values, reference.shape),
            index=reference.index,
            columns=reference.columns,
        )
    else:
        if isinstance(costs, (bool, np.bool_)) or not np.isscalar(costs):
            raise TypeError("costs must be a scalar, Series, or DataFrame")
        value = float(cast("float", costs))
        if not np.isfinite(value):
            raise AnalysisError("costs must be finite and complete")
        result = pd.DataFrame(value, index=reference.index, columns=reference.columns)
    if result.isna().any(axis=None):
        raise AnalysisError("costs must be finite and complete")
    if result.lt(0).any(axis=None):
        raise AnalysisError("costs must not be negative")
    return result


def _normalize_quantile_weights(
    membership: pd.DataFrame,
    raw_weights: pd.DataFrame,
    groups: pd.DataFrame | None,
) -> pd.DataFrame:
    result = pd.DataFrame(0.0, index=membership.index, columns=membership.columns)
    for position in range(len(membership.index)):
        member_row = membership.iloc[position]
        raw_row = raw_weights.iloc[position]
        if groups is None:
            normalized = _normalize_weight_sleeve(raw_row.where(member_row))
            result.iloc[position] = normalized
            continue
        group_row = groups.iloc[position]
        sleeves: list[pd.Series] = []
        for group in group_row.where(member_row).dropna().drop_duplicates():
            group_members = member_row & group_row.eq(group).fillna(False)
            sleeve = _normalize_weight_sleeve(raw_row.where(group_members))
            if sleeve.sum() > 0:
                sleeves.append(sleeve)
        if sleeves:
            combined = sum(sleeves, start=pd.Series(0.0, index=membership.columns))
            result.iloc[position] = combined.div(len(sleeves))
    return result


def _normalize_weight_sleeve(weights: pd.Series) -> pd.Series:
    observed = weights.fillna(0.0)
    total = float(observed.sum())
    return observed if total == 0 else observed.div(total)


def _weight_diagnostic_row(
    date: object,
    quantile: int,
    weights: pd.Series,
    assigned_count: int,
    effective_membership: int,
) -> dict[str, Any]:
    observed = weights.dropna()
    raw_weight_count = len(observed)
    return {
        "date": date,
        "quantile": quantile,
        "assigned_count": assigned_count,
        "raw_weight_count": raw_weight_count,
        "raw_weight_coverage": (
            raw_weight_count / assigned_count if assigned_count else np.nan
        ),
        "positive_weight_count": int(observed.gt(0).sum()),
        "raw_weight_total": observed.sum(min_count=1),
        "effective_membership": effective_membership,
    }


def _quantile_weight_diagnostics(
    rows: list[dict[str, Any]],
    date_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    columns = [
        "assigned_count",
        "raw_weight_count",
        "raw_weight_coverage",
        "positive_weight_count",
        "raw_weight_total",
        "effective_membership",
    ]
    if rows:
        return pd.DataFrame(rows).set_index(["date", "quantile"])[columns]
    index = pd.MultiIndex.from_arrays(
        [pd.DatetimeIndex([], tz=date_index.tz), pd.Index([], dtype="int64")],
        names=["date", "quantile"],
    )
    integer_columns = {
        "assigned_count",
        "raw_weight_count",
        "positive_weight_count",
        "effective_membership",
    }
    return pd.DataFrame(
        {
            column: pd.Series(index=index, dtype="int64" if column in integer_columns else float)
            for column in columns
        }
    )


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


def _quantile_capacity(
    rows: list[dict[str, Any]],
    date_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    columns = ["volume_count", "total_volume", "median_volume", "minimum_volume"]
    if rows:
        return pd.DataFrame(rows).set_index(["date", "quantile"])[columns]
    index = pd.MultiIndex.from_arrays(
        [
            pd.DatetimeIndex([], tz=date_index.tz),
            pd.Index([], dtype="int64"),
        ],
        names=["date", "quantile"],
    )
    return pd.DataFrame(
        {
            "volume_count": pd.Series(index=index, dtype="int64"),
            "total_volume": pd.Series(index=index, dtype=float),
            "median_volume": pd.Series(index=index, dtype=float),
            "minimum_volume": pd.Series(index=index, dtype=float),
        }
    )


def _quantile_summary(
    returns: pd.DataFrame,
    costs: pd.DataFrame,
    net_returns: pd.DataFrame,
    counts: pd.DataFrame,
    turnover: pd.DataFrame,
    capacity: pd.DataFrame,
    spread: pd.Series,
    spread_costs: pd.Series,
    net_spread: pd.Series,
    *,
    horizon: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for quantile in returns.columns:
        values = returns[quantile].dropna()
        median_total_volume = (
            np.nan
            if capacity.empty
            else capacity.xs(quantile, level="quantile")["total_volume"].median()
        )
        rows.append(
            {
                "portfolio": f"q{quantile}",
                "periods": len(values),
                "mean_return": values.mean(),
                "mean_cost": costs[quantile].mean(),
                "mean_net_return": net_returns[quantile].mean(),
                "cumulative_return": _cumulative_return(values, horizon),
                "cumulative_net_return": _cumulative_return(
                    net_returns[quantile].dropna(), horizon
                ),
                "volatility": values.std(ddof=1),
                "positive_rate": values.gt(0).mean(),
                "mean_turnover": turnover[quantile].mean(),
                "median_assets": counts[quantile].median(),
                "median_total_volume": median_total_volume,
            }
        )
    spread_values = spread.dropna()
    rows.append(
        {
            "portfolio": "top_minus_bottom",
            "periods": len(spread_values),
            "mean_return": spread_values.mean(),
            "mean_cost": spread_costs.mean(),
            "mean_net_return": net_spread.mean(),
            "cumulative_return": _cumulative_return(spread_values, horizon),
            "cumulative_net_return": _cumulative_return(net_spread.dropna(), horizon),
            "volatility": spread_values.std(ddof=1),
            "positive_rate": spread_values.gt(0).mean(),
            "mean_turnover": np.nan,
            "median_assets": np.nan,
            "median_total_volume": np.nan,
        }
    )
    return pd.DataFrame(rows).set_index("portfolio")


def _cumulative_return(returns: pd.Series, horizon: int) -> float:
    if horizon != 1 or returns.empty:
        return float("nan")
    values = returns.to_numpy(dtype=float, na_value=np.nan)
    return float(np.prod(values + 1.0) - 1.0)
