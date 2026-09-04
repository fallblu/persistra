# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportArgumentType=false
"""Trace- and layout-level tests for the Plotly visualization surface."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pytest

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


def test_general_and_market_plots_return_figures_without_global_changes() -> None:
    before_template = pio.templates.default
    before_renderer = pio.renderers.default
    bars = synthetic.bars(periods=10)
    wide = pivot_bars([bars], field="close")
    returns = simple_returns(wide)
    figures = [
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
        plot_candlesticks(bars),
    ]

    assert all(isinstance(chart, go.Figure) for chart in figures)
    assert all(chart.layout.height == 900 for chart in figures)
    assert figures[-1].data[0].type == "candlestick"
    assert figures[-1].data[1].type == "bar"
    assert pio.templates.default == before_template
    assert pio.renderers.default == before_renderer


def test_quote_history_and_option_plots_create_expected_traces() -> None:
    history = pd.DataFrame(
        {
            "observed_at": pd.date_range("2025-01-01", periods=2, tz="UTC"),
            "bid_price": [99.0, 100.0],
            "ask_price": [101.0, 102.0],
        }
    )
    assert [trace.name for trace in plot_bid_ask_history(history).data] == ["Bid", "Ask"]
    assert [trace.name for trace in plot_spread_history(history).data] == ["Spread"]
    with pytest.raises(ValueError, match="at least two"):
        plot_bid_ask_history(history.iloc[:1])

    chain = synthetic.option_chain()
    expiration = chain.chain_date + timedelta(days=28)
    assert all(trace.type == "scatter" for trace in plot_option_chain_prices(chain).data)
    assert all(trace.type == "bar" for trace in plot_option_volume_open_interest(chain).data)
    assert all(
        trace.type == "scatter"
        for trace in plot_implied_volatility_smile(chain, expiration=expiration).data
    )
    assert plot_implied_volatility_surface(chain).data[0].type == "surface"
    assert all(
        trace.type == "scatter"
        for trace in plot_greek_profile(chain, "delta", expiration=expiration).data
    )


def test_scalar_and_yield_plots_create_lines_and_heatmap() -> None:
    scalar = synthetic.series(periods=3)
    assert plot_scalar_series(scalar).data[0].type == "scatter"
    changes = scalar.frame.set_index("period_label")[["value"]].diff()
    assert plot_series_change(changes).data[0].type == "scatter"
    curve = pd.DataFrame({"maturity_years": [0.25, 10.0], "value": [4.0, 4.5]})
    assert plot_yield_curve(curve).data[0].mode == "lines+markers"
    history = pd.DataFrame(
        {"3month": [4.0, 4.1], "10year": [4.5, pd.NA]},
        index=["2025-01", "2025-02"],
    ).astype("Float64")
    assert plot_yield_curve_history(history).data[0].type == "heatmap"


def test_general_plots_preserve_dates_and_distinguish_multiple_lines() -> None:
    frame = pd.DataFrame(
        {"first": [1.0, 2.0, 3.0], "second": [2.0, 3.0, 4.0]},
        index=pd.date_range("2025-01-01", periods=3),
    )
    original = frame.copy(deep=True)

    chart = plot_rolling_statistic(frame, statistic_name="Mean")

    assert pd.api.types.is_datetime64_any_dtype(np.asarray(chart.data[0].x).dtype)
    assert chart.data[0].line.dash != chart.data[1].line.dash
    assert chart.data[0].marker.symbol != chart.data[1].marker.symbol
    assert all(trace.connectgaps is False for trace in chart.data)
    pd.testing.assert_frame_equal(frame, original)


def test_general_plots_reject_magnitude_divergence_and_support_log_rebasing() -> None:
    frame = pd.DataFrame(
        {"price": [100.0, 101.0], "volume": [1_000_000.0, 1_100_000.0]},
        index=pd.date_range("2025-01-01", periods=2),
    )

    with pytest.raises(ValueError, match="normalize the inputs or use separate axes"):
        plot_series(frame)
    comparison = pd.DataFrame(
        {"steady": [100.0, 200.0], "leader": [100.0, 2_100.0]},
        index=frame.index,
    )
    chart = plot_rebased(comparison)
    linear = plot_rebased(comparison, yscale="linear")

    assert chart.layout.yaxis.type == "log"
    assert linear.layout.yaxis.type == "linear"


def test_correlation_annotates_pairwise_counts_and_fixed_color_scale() -> None:
    frame = pd.DataFrame({"first": [1.0, 2.0, 3.0], "second": [1.0, pd.NA, 4.0]})

    chart = plot_correlation(frame.astype("Float64"))
    heatmap = chart.data[0]

    rendered = {text for row in heatmap.text for text in row}
    assert rendered >= {"1.00<br>n=3", "1.00<br>n=2"}
    assert (heatmap.zmin, heatmap.zmax, heatmap.zmid) == (-1, 1, 0)


def test_coverage_uses_horizontal_bars_for_long_labels() -> None:
    frame = pd.DataFrame(
        {
            "A very long descriptive series": [1.0, pd.NA],
            "Another long series name": [1.0, 2.0],
        }
    ).astype("Float64")

    chart = plot_coverage(frame)

    assert chart.data[0].orientation == "h"
    assert chart.layout.xaxis.title.text == "Observed fraction"
    assert chart.layout.yaxis.title.text == "Series"
    assert tuple(chart.layout.xaxis.range) == (0, 1)


def test_candlesticks_label_dates_and_cue_direction_without_color() -> None:
    chart = plot_candlesticks(synthetic.bars(periods=10))
    candle, volume = chart.data

    assert chart.layout.xaxis2.title.text == "Date"
    assert chart.layout.xaxis2.ticktext[0] == "2025-01-01"
    assert len(chart.layout.xaxis2.tickvals) <= 6
    assert chart.layout.xaxis2.tickangle == -45
    assert set(volume.marker.pattern.shape) == {"", "/"}
    assert candle.increasing.fillcolor != candle.decreasing.fillcolor


def test_candlesticks_annotate_split_sized_gaps_and_use_log_scale() -> None:
    bars = synthetic.bars(periods=10)
    frame = bars.frame.copy()
    price_columns = ["open", "high", "low", "close"]
    frame.loc[5:, price_columns] = frame.loc[5:, price_columns] / 4
    discontinuous = replace(bars, frame=frame)

    chart = plot_candlesticks(discontinuous)
    linear = plot_candlesticks(discontinuous, yscale="linear")

    assert chart.layout.yaxis.type == "log"
    assert linear.layout.yaxis.type == "linear"
    assert len(chart.layout.shapes) == 1
    assert "price gap" in chart.layout.annotations[-1].text


def test_returns_preserve_gaps_and_mark_internal_missing_observations() -> None:
    values = pd.DataFrame(
        {"first": [0.01, 0.02, 0.03], "second": [0.02, pd.NA, 0.01]},
        index=pd.date_range("2025-01-01", periods=3),
    ).astype("Float64")

    chart = plot_returns(values)

    assert np.isnan(np.asarray(chart.data[1].y, dtype=float)).sum() == 1
    assert chart.data[1].connectgaps is False
    assert len(chart.layout.shapes) == 1


def test_cumulative_returns_support_log_growth() -> None:
    values = pd.DataFrame(
        {"first": [0.0, 0.2], "second": [0.0, 12.0]},
        index=pd.date_range("2025-01-01", periods=2),
    )

    chart = plot_cumulative_returns(values)
    linear = plot_cumulative_returns(values, yscale="linear")

    assert chart.layout.yaxis.type == "log"
    assert chart.layout.yaxis.title.text == "Growth of 1"
    assert list(chart.data[0].y) == [1.0, 1.2]
    assert linear.layout.yaxis.type == "linear"
    assert linear.layout.yaxis.title.text == "Cumulative return"
    with pytest.raises(ValueError, match="greater than -100"):
        plot_cumulative_returns(pd.DataFrame({"loss": [0.0, -1.0]}), yscale="log")


def test_option_groups_use_readable_labels_and_marker_forward_styles() -> None:
    chain = synthetic.option_chain()
    prices = plot_option_chain_prices(chain)
    greeks = plot_greek_profile(chain, "theta")
    expected = {
        "2025-02-14 Call",
        "2025-02-14 Put",
        "2025-03-14 Call",
        "2025-03-14 Put",
    }

    assert {trace.name for trace in prices.data} == expected
    assert {trace.name for trace in greeks.data} == expected
    assert {trace.marker.symbol for trace in greeks.data} == {
        "circle",
        "square",
        "triangle-up",
        "diamond",
    }
    assert {trace.mode for trace in prices.data} == {"markers"}


def test_option_volume_labels_sample_contract_identities() -> None:
    chart = plot_option_volume_open_interest(synthetic.option_chain())
    labels = list(chart.layout.xaxis.ticktext)

    assert labels[0] == "2025-02-14<br>90 C"
    assert labels[-1] == "2025-03-14<br>110 P"
    assert len(labels) <= 6
    assert all(label.split("<br>")[1].endswith((" C", " P")) for label in labels)


def test_option_smile_patterns_and_surface_axes_are_explicit() -> None:
    chain = synthetic.option_chain()
    expiration = chain.chain_date + timedelta(days=28)

    smile = plot_implied_volatility_smile(chain, expiration=expiration)
    surface = plot_implied_volatility_surface(chain)

    assert {trace.line.dash for trace in smile.data} == {"dash", "dot"}
    assert {trace.name for trace in smile.data} == {"Call", "Put"}
    assert surface.data[0].type == "surface"
    assert list(surface.data[0].x) == [90.0, 100.0, 110.0]
    assert surface.layout.scene.xaxis.title.text == "Strike"
    assert surface.layout.scene.yaxis.title.text == "Expiration"
    assert surface.layout.height == 900


def test_surface_reserves_space_for_final_expiration_label() -> None:
    chain = synthetic.option_chain()
    first_expiration = chain.contracts["expiration"].min()
    contracts = chain.contracts.loc[chain.contracts["expiration"] == first_expiration]
    observations = chain.observations.merge(
        contracts[["provider", "contract_id"]], on=["provider", "contract_id"]
    )
    contract_frames: list[pd.DataFrame] = []
    observation_frames: list[pd.DataFrame] = []
    for position in range(15):
        expiration = pd.Timestamp(chain.chain_date + timedelta(days=28 * (position + 1)))
        contract_frame = contracts.copy()
        observation_frame = observations.copy()
        identifiers = contract_frame["contract_id"] + f"-{position}"
        contract_frame["contract_id"] = identifiers
        contract_frame["expiration"] = expiration
        observation_frame["contract_id"] = identifiers.to_numpy()
        contract_frames.append(contract_frame)
        observation_frames.append(observation_frame)
    expanded = replace(
        chain,
        contracts=pd.concat(contract_frames, ignore_index=True).astype(
            {"expiration": "datetime64[ns]"}
        ),
        observations=pd.concat(observation_frames, ignore_index=True).astype(
            {"contract_id": "string"}
        ).sort_values(["provider", "contract_id"], ignore_index=True),
    )

    surface = plot_implied_volatility_surface(expanded)

    labels = list(surface.layout.scene.yaxis.ticktext)
    assert len(labels) <= 8
    assert labels[-1] == expanded.contracts["expiration"].max().date().isoformat()
    assert surface.layout.scene.yaxis.tickangle == 0
    assert surface.layout.scene.yaxis.range[0] < 0
    assert surface.layout.scene.yaxis.range[1] > 14
    assert surface.layout.margin.b == 110


def test_scalar_series_uses_temporal_starts_and_sparse_markers() -> None:
    series = synthetic.series(periods=24, frequency="quarterly")

    chart = plot_scalar_series(series)

    assert pd.api.types.is_datetime64_any_dtype(np.asarray(chart.data[0].x).dtype)
    sizes = list(chart.data[0].marker.size)
    assert sizes.count(6) <= 18
    assert sizes.count(0) > 0


def test_series_change_marks_sparse_observations() -> None:
    quarterly: list[object] = [pd.NA] * 40
    quarterly[::3] = [float(value) for value in range(14)]
    values = pd.DataFrame(
        {"quarterly": quarterly, "monthly": np.arange(40, dtype=float)},
        index=pd.date_range("2025-01-01", periods=40, freq="MS"),
    ).astype("Float64")

    chart = plot_series_change(values)

    assert chart.data[0].mode == "lines+markers"
    assert chart.data[1].mode == "lines+markers"
    assert np.isnan(np.asarray(chart.data[0].y, dtype=float)).sum() > 0


def test_yield_curve_history_samples_axes_and_preserves_missing_cells() -> None:
    history = pd.DataFrame(
        np.arange(200, dtype=float).reshape(20, 10),
        index=pd.date_range("2025-01-01", periods=20, freq="D"),
        columns=[f"{position} years" for position in range(10)],
    )
    history.iloc[3, 4] = np.nan

    chart = plot_yield_curve_history(history)

    assert len(chart.layout.xaxis.tickvals) <= 6
    assert len(chart.layout.yaxis.tickvals) <= 8
    assert chart.layout.yaxis.ticktext[0] == "2025-01-01"
    assert np.isnan(np.asarray(chart.data[0].z, dtype=float)).sum() == 1
    assert list(chart.data[0].customdata[0]) == list(history.columns)
