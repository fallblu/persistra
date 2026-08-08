"""Artist-level tests for signal-research visualizations."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes

from persistra.research import (
    ForwardReturnLabels,
    compare_benchmark,
    information_coefficients,
    quantile_portfolios,
    rank_cross_section,
    summarize_groups,
)
from persistra.viz import (
    plot_benchmark_comparison,
    plot_cumulative_quantile_returns,
    plot_group_comparison,
    plot_information_coefficient_horizons,
    plot_information_coefficients,
    plot_quantile_capacity,
    plot_quantile_counts,
    plot_quantile_returns,
    plot_quantile_spread,
    plot_quantile_turnover,
    plot_signal_distribution,
    plot_signal_ranks,
    plot_stability_comparison,
)


def research_inputs() -> tuple[pd.DataFrame, ForwardReturnLabels, pd.DataFrame, pd.DataFrame]:
    """Return deterministic cross-sectional research inputs."""
    index = pd.date_range("2025-01-01", periods=5)
    columns = list("abcdef")
    signals = pd.DataFrame(
        [
            np.arange(1.0, 7.0),
            np.arange(6.0, 0.0, -1.0),
            np.arange(1.0, 7.0),
            np.arange(6.0, 0.0, -1.0),
            np.arange(1.0, 7.0),
        ],
        index=index,
        columns=columns,
    )
    returns = signals.div(100.0)
    returns.iloc[-1] = np.nan
    ends = pd.Series(index=index, dtype=index.dtype, name="label_end")
    ends.iloc[:-1] = index[1:]
    labels = ForwardReturnLabels(returns, ends, horizon=1)
    groups = pd.DataFrame(
        [["large"] * 3 + ["small"] * 3] * len(index),
        index=index,
        columns=columns,
    )
    volumes = pd.DataFrame(
        [np.arange(100.0, 700.0, 100.0)] * len(index),
        index=index,
        columns=columns,
    )
    return signals, labels, groups, volumes


def test_cross_sectional_and_group_plots_expose_date_counts_and_caller_axes() -> None:
    signals, labels, groups, _ = research_inputs()
    grouped = summarize_groups(signals, labels, groups, minimum_count=2)
    _, supplied = plt.subplots()

    distribution = plot_signal_distribution(signals, date=signals.index[0], groups=groups)
    ranks = plot_signal_ranks(rank_cross_section(signals), date=signals.index[0], ax=supplied)
    comparison = plot_group_comparison(grouped, statistic="rank")

    assert distribution.patches
    assert "2025-01-01" in distribution.get_title()
    assert ranks is supplied
    assert "n=6/6" in ranks.get_title()
    assert len(comparison.lines) >= 3
    assert "1-observation" in comparison.get_title()
    assert "Sample count" in comparison.texts[0].get_text()
    plt.close("all")


def test_information_coefficient_plots_make_horizons_and_counts_explicit() -> None:
    signals, labels, groups, _ = research_inputs()
    result = information_coefficients(signals, labels)
    grouped = information_coefficients(signals, labels, groups=groups, minimum_count=2)
    horizon_two_returns = labels.frame.copy()
    horizon_two_returns.iloc[-2:] = np.nan
    horizon_two_ends = pd.Series(index=signals.index, dtype=signals.index.dtype)
    horizon_two_ends.iloc[:-2] = signals.index[2:]
    horizon_two = information_coefficients(
        signals,
        ForwardReturnLabels(horizon_two_returns, horizon_two_ends, horizon=2),
    )

    through_time = plot_information_coefficients(result, rolling=2)
    group_time = plot_information_coefficients(grouped)
    horizons = plot_information_coefficient_horizons([horizon_two, result])

    assert "rolling mean" in through_time.get_ylabel()
    assert "Sample count" in through_time.texts[0].get_text()
    assert group_time.get_legend() is not None
    assert [tick.get_text() for tick in horizons.get_xticklabels()] == ["1", "2"]
    assert all("median n=" in text.get_text() for text in horizons.texts)
    plt.close("all")


def test_quantile_plots_cover_returns_spreads_counts_turnover_and_capacity() -> None:
    signals, labels, _, volumes = research_inputs()
    result = quantile_portfolios(signals, labels, quantiles=3, volumes=volumes)

    axes = [
        plot_quantile_returns(result),
        plot_cumulative_quantile_returns(result),
        plot_quantile_spread(result),
        plot_quantile_counts(result),
        plot_quantile_turnover(result),
        plot_quantile_capacity(result, statistic="median_volume"),
    ]

    assert all(isinstance(axis, Axes) for axis in axes)
    assert "3 equal-weight quantiles" in axes[0].get_title()
    assert "Unavailable quantile-dates" in axes[0].texts[0].get_text()
    assert axes[2].get_ylabel() == "Return"
    assert axes[5].get_ylabel() == "Median volume"
    plt.close("all")


def test_stability_and_benchmark_plots_show_dimensions_and_pairwise_counts() -> None:
    index = pd.date_range("2025-01-01", periods=4)
    candidates = pd.DataFrame(
        {"momentum": [0.02, 0.01, -0.01, 0.03], "volume": [0.0, 0.02, 0.01, 0.01]},
        index=index,
    )
    benchmark = pd.Series([0.01, 0.0, -0.02, 0.01], index=index)
    result = compare_benchmark(candidates, benchmark, benchmark_name="Equal weight")
    values = pd.Series({"early": 0.03, "late": 0.01})
    counts = pd.Series({"early": 80, "late": 75})

    stability = plot_stability_comparison(
        values,
        counts=counts,
        statistic_name="Mean rank IC",
        comparison_name="Period",
    )
    comparison = plot_benchmark_comparison(result)

    assert stability.get_xlabel() == "Period"
    assert {text.get_text() for text in stability.texts} == {"n=80", "n=75"}
    assert comparison.get_title() == "Comparison with Equal weight"
    assert len(comparison.texts) == 2
    plt.close("all")


def test_research_plots_reject_ambiguous_or_misleading_inputs() -> None:
    signals, labels, groups, _ = research_inputs()
    result = information_coefficients(signals, labels)
    horizon_two_returns = labels.frame.copy()
    horizon_two_returns.iloc[-2:] = np.nan
    horizon_two_ends = pd.Series(index=signals.index, dtype=signals.index.dtype)
    horizon_two_ends.iloc[:-2] = signals.index[2:]
    quantiles = quantile_portfolios(
        signals,
        ForwardReturnLabels(horizon_two_returns, horizon_two_ends, horizon=2),
        quantiles=3,
    )

    with pytest.raises(ValueError, match="overlapping forward labels"):
        plot_cumulative_quantile_returns(quantiles)
    with pytest.raises(ValueError, match="signal index and columns"):
        plot_signal_distribution(signals, date=signals.index[0], groups=groups.iloc[:, :-1])
    with pytest.raises(ValueError, match="positive integer"):
        plot_information_coefficients(result, rolling=0)
    with pytest.raises(ValueError, match="unique"):
        plot_information_coefficient_horizons([result, result])
    plt.close("all")
