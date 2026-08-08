"""Tests for cross-sectional signal evaluation."""

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.research import (
    ForwardReturnLabels,
    adjust_pvalues,
    compare_benchmark,
    forward_returns,
    information_coefficients,
    quantile_portfolios,
    summarize_groups,
)


def evaluation_inputs() -> tuple[pd.DataFrame, ForwardReturnLabels, pd.DataFrame, pd.DataFrame]:
    """Return fixed-universe signals, labels, classifications, and volumes."""
    index = pd.date_range("2025-01-01", periods=3)
    columns = list("abcdef")
    signals = pd.DataFrame(
        [np.arange(1.0, 7.0), np.arange(6.0, 0.0, -1.0), np.arange(1.0, 7.0)],
        index=index,
        columns=columns,
    )
    returns = pd.DataFrame(
        [np.arange(0.01, 0.07, 0.01), np.arange(0.06, 0.0, -0.01), [np.nan] * 6],
        index=index,
        columns=columns,
    )
    ends = pd.Series([index[1], index[2], pd.NaT], index=index, name="label_end")
    labels = ForwardReturnLabels(returns, ends, horizon=1)
    groups = pd.DataFrame(
        [
            ["large", "large", "large", "small", "small", "small"],
            ["large", "large", "small", "small", "small", "large"],
            ["large", "large", "small", "small", "small", "large"],
        ],
        index=index,
        columns=columns,
    )
    volumes = pd.DataFrame(
        [np.arange(100.0, 700.0, 100.0)] * 3,
        index=index,
        columns=columns,
    )
    return signals, labels, groups, volumes


def test_information_coefficients_report_methods_counts_and_groups() -> None:
    signals, labels, groups, _ = evaluation_inputs()
    labels.frame.iloc[0, 0] = np.nan

    result = information_coefficients(signals, labels)
    grouped = information_coefficients(signals, labels, groups=groups, minimum_count=2)

    assert result.horizon == 1
    assert result.statistics.iloc[0]["count"] == 5
    assert result.statistics.iloc[0]["pearson"] == pytest.approx(1)
    assert result.statistics.iloc[0]["rank"] == pytest.approx(1)
    assert pd.isna(result.statistics.iloc[-1]["pearson"])
    assert grouped.grouped
    assert grouped.statistics.index.names == ["date", "group"]
    assert grouped.statistics.loc[(signals.index[0], "small"), "rank"] == pytest.approx(1)


def test_quantile_portfolios_report_spreads_turnover_counts_and_capacity() -> None:
    signals, labels, _, volumes = evaluation_inputs()

    result = quantile_portfolios(signals, labels, quantiles=3, volumes=volumes)

    assert result.assignments.iloc[0].tolist() == [1, 1, 2, 2, 3, 3]
    assert result.returns.iloc[0].tolist() == pytest.approx([0.015, 0.035, 0.055])
    assert result.spread.iloc[0] == pytest.approx(0.04)
    assert result.turnover.iloc[1].tolist() == [1, 0, 1]
    assert result.counts.iloc[0].eq(2).all()
    capacity = result.capacity.xs(3, level="quantile").iloc[0]
    assert capacity["total_volume"] == 1100
    assert capacity["minimum_volume"] == 500
    assert result.summary.loc["top_minus_bottom", "periods"] == 2


def test_group_quantiles_and_summaries_use_time_varying_classifications() -> None:
    signals, labels, groups, _ = evaluation_inputs()

    quantiles = quantile_portfolios(signals, labels, quantiles=3, groups=groups)
    summary = summarize_groups(signals, labels, groups, minimum_count=2)

    assert quantiles.assignments.iloc[0].tolist() == [1, 2, 3, 1, 2, 3]
    assert summary.statistics.index.names == ["date", "group"]
    first_small = summary.statistics.iloc[1]
    assert first_small["count"] == 3
    assert first_small["mean_forward_return"] == pytest.approx(0.05)


def test_benchmark_comparisons_and_repeated_search_corrections_are_explicit() -> None:
    index = pd.date_range("2025-01-01", periods=4)
    candidates = pd.DataFrame(
        {"momentum": [0.02, 0.01, -0.01, 0.03], "volume": [0.0, 0.02, 0.01, 0.01]},
        index=index,
    )
    benchmark = pd.Series([0.01, 0.0, -0.02, 0.01], index=index)

    comparison = compare_benchmark(candidates, benchmark, benchmark_name="equal_weight")
    bonferroni = adjust_pvalues(pd.Series({"a": 0.01, "b": 0.04, "c": np.nan}), method="bonferroni")
    fdr = adjust_pvalues(
        pd.Series({"a": 0.01, "b": 0.04, "c": 0.2}),
        method="benjamini-hochberg",
        alpha=0.05,
    )

    assert comparison.benchmark_name == "equal_weight"
    assert comparison.differences["momentum"].iloc[0] == pytest.approx(0.01)
    assert comparison.summary.loc["momentum", "count"] == 4
    assert bonferroni.statistics.loc["a", "adjusted_pvalue"] == pytest.approx(0.02)
    assert pd.isna(bonferroni.statistics.loc["c", "rejected"])
    assert bool(fdr.statistics.loc["a", "rejected"])
    assert not bool(fdr.statistics.loc["b", "rejected"])


def test_evaluation_rejects_misalignment_sparse_groups_and_invalid_values() -> None:
    signals, labels, groups, volumes = evaluation_inputs()
    with pytest.raises(ValueError, match="same index and columns"):
        information_coefficients(signals.iloc[:, :-1], labels)
    with pytest.raises(ValueError, match="same index and columns"):
        summarize_groups(signals, labels, groups.rename(columns={"a": "other"}))
    sparse = quantile_portfolios(signals.iloc[:, :2], ForwardReturnLabels(
        labels.frame.iloc[:, :2], labels.label_ends, labels.horizon
    ), quantiles=3)
    assert sparse.assignments.isna().all(axis=None)
    with pytest.raises(AnalysisError, match="negative"):
        quantile_portfolios(signals, labels, volumes=volumes.mul(-1))
    with pytest.raises(ValueError, match="between 0 and 1"):
        adjust_pvalues(pd.Series([1.1]))


def test_controlled_price_and_volume_signals_are_stable_across_periods_and_universes() -> None:
    index = pd.bdate_range("2024-01-01", periods=80)
    columns = [f"asset_{number}" for number in range(10)]
    trend = np.linspace(-0.001, 0.002, len(columns))
    returns = np.tile(trend, (len(index), 1)) + np.sin(np.arange(len(index)))[:, None] * 0.0001
    prices = pd.DataFrame(100 * np.cumprod(1 + returns, axis=0), index=index, columns=columns)
    growth = np.linspace(0.001, 0.01, len(columns))
    volumes = pd.DataFrame(
        1_000_000 * np.exp(np.arange(len(index))[:, None] * growth),
        index=index,
        columns=columns,
    )
    labels = forward_returns(prices, horizon=1)
    signals = {
        "momentum": prices.pct_change(5).shift(1),
        "volume_trend": volumes.pct_change(5).shift(1),
    }

    for signal in signals.values():
        for period in (slice(index[10], index[39]), slice(index[40], index[-2])):
            for universe in (columns[:5], columns[5:]):
                period_signal = signal.loc[period, universe]
                period_returns = labels.frame.loc[period, universe].copy()
                period_returns.iloc[-1] = np.nan
                period_ends = pd.Series(index=period_signal.index, dtype=period_signal.index.dtype)
                period_ends.iloc[:-1] = period_signal.index[1:]
                period_labels = ForwardReturnLabels(
                    period_returns,
                    period_ends,
                    horizon=1,
                )
                result = information_coefficients(period_signal, period_labels)
                assert result.statistics["rank"].mean() > 0.9
