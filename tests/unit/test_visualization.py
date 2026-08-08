"""Artist-level tests for the Matplotlib-only plot surface."""

from datetime import timedelta

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes
from matplotlib.dates import ConciseDateFormatter

from persistra.analysis import (
    cumulative_returns,
    drawdowns,
    rolling_volatility,
    simple_returns,
)
from persistra.data import pivot_bars, synthetic
from persistra.viz import (
    plot_bid_ask_history,
    plot_candlesticks,
    plot_correlation,
    plot_coverage,
    plot_cumulative_returns,
    plot_distribution,
    plot_drawdowns,
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
    plot_option_volume_open_interest,
    plot_rebased,
    plot_returns,
    plot_rolling_statistic,
    plot_rolling_volatility,
    plot_scalar_series,
    plot_series,
    plot_series_change,
    plot_spread_history,
    plot_yield_curve,
    plot_yield_curve_history,
)


def test_general_and_market_plots_return_axes_without_global_style_changes() -> None:
    before = dict(mpl.rcParams)
    bars = synthetic.bars(periods=10)
    wide = pivot_bars([bars], field="close")
    returns = simple_returns(wide)
    functions = [
        plot_series(wide),
        plot_rebased(wide),
        plot_distribution(wide.iloc[:, 0]),
        plot_rolling_statistic(wide.rolling(2).mean(), statistic_name="Mean"),
        plot_correlation(pd.concat([wide, wide * 2], axis=1)),
        plot_coverage(wide),
        plot_returns(returns),
        plot_cumulative_returns(cumulative_returns(returns)),
        plot_drawdowns(drawdowns(returns)),
        plot_rolling_volatility(rolling_volatility(returns, window=2, periods_per_year=12)),
    ]
    assert all(isinstance(axes, Axes) for axes in functions)
    candle = plot_candlesticks(bars)
    assert candle.price.patches
    assert candle.volume.containers
    assert dict(mpl.rcParams) == before
    plt.close("all")


def test_quote_history_and_option_plots_create_expected_artists() -> None:
    history = pd.DataFrame(
        {
            "observed_at": pd.date_range("2025-01-01", periods=2, tz="UTC"),
            "bid_price": [99.0, 100.0],
            "ask_price": [101.0, 102.0],
        }
    )
    assert len(plot_bid_ask_history(history).lines) == 2
    assert len(plot_spread_history(history).lines) == 1
    with pytest.raises(ValueError, match="at least two"):
        plot_bid_ask_history(history.iloc[:1])
    chain = synthetic.option_chain()
    expiration = chain.chain_date + timedelta(days=28)
    assert plot_option_chain_prices(chain).lines
    assert plot_option_volume_open_interest(chain).containers
    assert plot_implied_volatility_smile(chain, expiration=expiration).lines
    assert plot_implied_volatility_surface(chain).images
    assert plot_greek_profile(chain, "delta", expiration=expiration).lines
    plt.close("all")


def test_scalar_and_yield_plots_create_lines_and_heatmap() -> None:
    scalar = synthetic.series(periods=3)
    assert plot_scalar_series(scalar).lines
    changes = scalar.frame.set_index("period_label")[["value"]].diff()
    assert plot_series_change(changes).lines
    curve = pd.DataFrame({"maturity_years": [0.25, 10.0], "value": [4.0, 4.5]})
    assert plot_yield_curve(curve).lines
    history = pd.DataFrame(
        {"3month": [4.0, 4.1], "10year": [4.5, pd.NA]},
        index=["2025-01", "2025-02"],
    ).astype("Float64")
    assert plot_yield_curve_history(history).images
    plt.close("all")


def test_general_plots_format_dates_and_distinguish_multiple_lines() -> None:
    frame = pd.DataFrame(
        {"first": [1.0, 2.0, 3.0], "second": [2.0, 3.0, 4.0]},
        index=pd.date_range("2025-01-01", periods=3),
    )

    axes = plot_rolling_statistic(frame, statistic_name="Mean")

    assert isinstance(axes.xaxis.get_major_formatter(), ConciseDateFormatter)
    assert axes.lines[0].get_linestyle() != axes.lines[1].get_linestyle()
    assert axes.lines[0].get_marker() != axes.lines[1].get_marker()
    plt.close("all")


def test_general_plots_warn_about_magnitude_divergence_and_support_log_rebasing() -> None:
    frame = pd.DataFrame(
        {"price": [100.0, 101.0], "volume": [1_000_000.0, 1_100_000.0]},
        index=pd.date_range("2025-01-01", periods=2),
    )

    with pytest.warns(UserWarning, match="shared axis"):
        plot_series(frame)
    axes = plot_rebased(frame, yscale="log")

    assert axes.get_yscale() == "log"
    plt.close("all")


def test_correlation_annotates_pairwise_counts() -> None:
    frame = pd.DataFrame({"first": [1.0, 2.0, 3.0], "second": [1.0, pd.NA, 4.0]})

    axes = plot_correlation(frame.astype("Float64"))

    assert {text.get_text() for text in axes.texts} >= {"1.00\nn=3", "1.00\nn=2"}
    plt.close("all")


def test_coverage_uses_horizontal_bars_for_long_labels() -> None:
    frame = pd.DataFrame(
        {"A very long descriptive series": [1.0, pd.NA], "Another long series name": [1.0, 2.0]}
    ).astype("Float64")

    axes = plot_coverage(frame)

    assert axes.get_xlabel() == "Observed fraction"
    assert axes.get_ylabel() == "Series"
    assert axes.get_xlim() == pytest.approx((0.0, 1.0))
    plt.close("all")


def test_candlesticks_label_source_dates_and_cue_direction_without_color() -> None:
    axes = plot_candlesticks(synthetic.bars(periods=10))

    assert axes.volume.get_xlabel() == "Date"
    assert axes.volume.get_xticklabels()[0].get_text() == "2025-01-01"
    assert len(axes.volume.get_xticks()) <= 6
    assert axes.volume.get_xticklabels()[0].get_rotation() == 45
    assert {patch.get_hatch() for patch in axes.price.patches} == {None, "//"}
    assert len({str(collection.get_linestyle()) for collection in axes.price.collections}) == 2
    plt.close("all")


def test_returns_mark_internal_missing_observations() -> None:
    values = pd.DataFrame(
        {"first": [0.01, 0.02, 0.03], "second": [0.02, pd.NA, 0.01]},
        index=pd.date_range("2025-01-01", periods=3),
    ).astype("Float64")

    axes = plot_returns(values)

    assert len(axes.collections) == 1
    assert np.asarray(axes.collections[0].get_offsets()).shape == (1, 2)
    plt.close("all")


def test_cumulative_returns_support_log_growth() -> None:
    values = pd.DataFrame(
        {"first": [0.0, 0.2], "second": [0.0, 4.0]},
        index=pd.date_range("2025-01-01", periods=2),
    )

    axes = plot_cumulative_returns(values, yscale="log")

    assert axes.get_yscale() == "log"
    assert axes.get_ylabel() == "Growth of 1"
    assert np.asarray(axes.lines[0].get_ydata()).tolist() == [1.0, 1.2]
    with pytest.raises(ValueError, match="greater than -100"):
        plot_cumulative_returns(pd.DataFrame({"loss": [0.0, -1.0]}), yscale="log")
    plt.close("all")


def test_option_groups_use_readable_labels_and_marker_forward_styles() -> None:
    chain = synthetic.option_chain()

    price_axes = plot_option_chain_prices(chain)
    greek_axes = plot_greek_profile(chain, "theta")

    expected = {
        "2025-02-14 Call",
        "2025-02-14 Put",
        "2025-03-14 Call",
        "2025-03-14 Put",
    }
    price_legend = price_axes.get_legend()
    greek_legend = greek_axes.get_legend()
    assert price_legend is not None
    assert greek_legend is not None
    assert {text.get_text() for text in price_legend.get_texts()} == expected
    assert {text.get_text() for text in greek_legend.get_texts()} == expected
    assert {str(line.get_marker()) for line in greek_axes.lines} == {"o", "s", "^", "D"}
    assert {line.get_linestyle() for line in price_axes.lines} == {"None"}
    plt.close("all")


def test_option_volume_labels_sampled_contract_identities() -> None:
    axes = plot_option_volume_open_interest(synthetic.option_chain())
    labels = [label.get_text() for label in axes.get_xticklabels()]

    assert labels[0] == "2025-02-14\n90 C"
    assert labels[-1] == "2025-03-14\n110 P"
    assert len(labels) <= 6
    assert all(label.splitlines()[1].endswith((" C", " P")) for label in labels)
    plt.close("all")


def test_option_smile_uses_patterned_connections_and_surface_limits_ticks() -> None:
    chain = synthetic.option_chain()
    expiration = chain.chain_date + timedelta(days=28)

    smile_axes = plot_implied_volatility_smile(chain, expiration=expiration)
    surface_axes = plot_implied_volatility_surface(chain)

    assert {line.get_linestyle() for line in smile_axes.lines} == {"--", ":"}
    smile_legend = smile_axes.get_legend()
    assert smile_legend is not None
    assert {text.get_text() for text in smile_legend.get_texts()} == {"Call", "Put"}
    assert len(surface_axes.get_xticks()) <= 8
    assert [label.get_text() for label in surface_axes.get_xticklabels()] == ["90", "100", "110"]
    plt.close("all")


def test_scalar_series_uses_temporal_starts_and_concise_dates() -> None:
    series = synthetic.series(periods=24, frequency="quarterly")

    axes = plot_scalar_series(series)

    assert isinstance(axes.xaxis.get_major_formatter(), ConciseDateFormatter)
    assert pd.api.types.is_datetime64_any_dtype(np.asarray(axes.lines[0].get_xdata()).dtype)
    assert len(axes.get_xticks()) < len(series.frame)
    plt.close("all")


def test_series_change_marks_sparse_observations() -> None:
    quarterly: list[object] = [pd.NA] * 40
    quarterly[::3] = [float(value) for value in range(14)]
    values = pd.DataFrame(
        {
            "quarterly": quarterly,
            "monthly": np.arange(40, dtype=float),
        },
        index=pd.date_range("2025-01-01", periods=40, freq="MS"),
    ).astype("Float64")

    axes = plot_series_change(values)

    assert axes.lines[0].get_markevery() == 1
    assert axes.lines[0].get_marker() == "o"
    assert axes.lines[1].get_markevery() != 1
    plt.close("all")


def test_yield_curve_history_samples_both_axes_and_preserves_missing_cells() -> None:
    history = pd.DataFrame(
        np.arange(200, dtype=float).reshape(20, 10),
        index=pd.date_range("2025-01-01", periods=20, freq="D"),
        columns=[f"{position} years" for position in range(10)],
    )
    history.iloc[3, 4] = np.nan

    axes = plot_yield_curve_history(history)

    assert len(axes.get_xticks()) <= 6
    assert len(axes.get_yticks()) <= 8
    assert axes.get_yticklabels()[0].get_text() == "2025-01-01"
    image_values = axes.images[0].get_array()
    assert image_values is not None
    assert bool(np.ma.getmaskarray(image_values).any())
    plt.close("all")
