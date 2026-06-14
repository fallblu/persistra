from __future__ import annotations

from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from persistra.features import RollingMean, SimpleReturn
from persistra.viz.market import (
    candlestick_plot,
    correlation_heatmap,
    feature_plot,
    price_plot,
)


@pytest.fixture
def prices() -> pd.DataFrame:
    idx = pd.bdate_range("2022-01-03", periods=40)
    return pd.DataFrame(
        {
            "AAA": [100.0 + i for i in range(40)],
            "BBB": [50.0 + (i % 5) for i in range(40)],
        },
        index=idx,
    )


def _n_traces(fig: go.Figure) -> int:
    return len(cast("tuple[Any, ...]", fig.data))


def test_price_plot_one_trace_per_symbol(prices):
    fig = price_plot(prices)
    assert isinstance(fig, go.Figure)
    assert _n_traces(fig) == 2


def test_price_plot_normalize_rebases_to_100(prices):
    fig = price_plot(prices, normalize=True)
    first = cast("Any", fig.data)[0]
    assert abs(first.y[0] - 100.0) < 1e-9


def test_candlestick_plot_from_ohlcv(prices):
    ohlcv = pd.DataFrame(
        {
            "open": prices["AAA"],
            "high": prices["AAA"] + 1,
            "low": prices["AAA"] - 1,
            "close": prices["AAA"],
            "volume": 1000.0,
        }
    )
    fig = candlestick_plot(ohlcv, symbol="XYZ", timeframe="1d")
    assert _n_traces(fig) >= 1


def test_correlation_heatmap_returns_one_trace(prices):
    assert _n_traces(correlation_heatmap(prices)) == 1


def test_store_plot_prices_fetches_and_plots_symbols(tiny_store):
    fig = tiny_store.plot_prices(["AAA", "BBB"], "2022-01-03", "2022-01-11")

    assert isinstance(fig, go.Figure)
    assert _n_traces(fig) == 2


def test_store_plot_prices_supports_normalize(tiny_store):
    fig = tiny_store.plot_prices(["AAA"], "2022-01-03", "2022-01-11", normalize=True)
    first = cast("Any", fig.data)[0]

    assert abs(first.y[0] - 100.0) < 1e-9


def test_store_plot_candles_fetches_ohlcv(tiny_store):
    fig = tiny_store.plot_candles("AAA", "2022-01-03", "2022-01-11")

    assert isinstance(fig, go.Figure)
    assert _n_traces(fig) == 1
    trace = cast("go.Candlestick", fig.data[0])
    assert trace.xperiod == 86_400_000


def test_store_plot_correlation_fetches_prices(tiny_store):
    fig = tiny_store.plot_correlation(["AAA", "BBB", "CCC"], "2022-01-03", "2022-01-11")

    assert isinstance(fig, go.Figure)
    assert _n_traces(fig) == 1
    trace = cast("go.Heatmap", fig.data[0])
    assert list(cast("Any", trace.x)) == ["AAA", "BBB", "CCC"]


def test_store_plot_candles_supports_split_adjustment(tmp_path):
    from tests.conftest import build_store

    times = list(pd.bdate_range("2022-01-03", periods=3))
    store = build_store(
        tmp_path / "split-candle-plot",
        {"AAA": (times, [100.0, 100.0, 50.0])},
        actions=[
            {
                "date": str(times[2].date()),
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            }
        ],
    )

    fig = store.plot_candles("AAA", times[0], times[-1], adjustment="split")
    trace = cast("go.Candlestick", fig.data[0])

    assert list(cast("Any", trace.open)) == [50.0, 50.0, 50.0]
    assert list(cast("Any", trace.close)) == [50.0, 50.0, 50.0]


def test_feature_plot_runs_transformer(prices):
    fig = feature_plot(prices, RollingMean(window=5), name="sma5")
    assert _n_traces(fig) == 2


def test_price_plot_empty_frame_degrades(prices):
    fig = price_plot(prices.iloc[:0])
    assert isinstance(fig, go.Figure)


def test_feature_plot_zero_row_output_does_not_crash():
    # SimpleReturn on a single-row frame yields 0 output rows with matching
    # width; feature_plot must degrade gracefully rather than raise on the
    # tail-index assignment (the -len(arr)==-0 slice trap).
    one_row = pd.DataFrame(
        {"AAA": [100.0], "BBB": [50.0]}, index=pd.bdate_range("2022-01-03", periods=1)
    )
    fig = feature_plot(one_row, SimpleReturn(), name="ret")
    assert isinstance(fig, go.Figure)


def test_market_plots_importable_from_viz_namespace():
    from persistra.viz import correlation_heatmap, feature_plot, price_plot  # noqa: F401


def test_candlestick_rangebreaks_empty():
    empty = pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []},
        index=pd.DatetimeIndex([]),
    )
    fig = candlestick_plot(empty, symbol="XYZ", timeframe="1d")
    assert not fig.layout.xaxis.rangebreaks


def test_candlestick_rangebreaks_daily():
    # 2024-01-02 to ~2024-02-27 (40 business days); MLK Day (Jan 15) is a holiday
    idx = pd.bdate_range("2024-01-02", periods=40)
    ohlcv = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=idx,
    )
    fig = candlestick_plot(ohlcv, symbol="XYZ", timeframe="1d")
    breaks = list(fig.layout.xaxis.rangebreaks or [])
    assert len(breaks) >= 1
    # Daily charts must not have an overnight break
    assert not any(rb.pattern == "hour" for rb in breaks)
    # MLK Day must be excluded
    break_values = [v for rb in breaks if rb.values for v in rb.values]
    assert "2024-01-15" in break_values


def test_candlestick_rangebreaks_intraday():
    # Mon 2024-01-08 to Fri 2024-01-12, 5-minute bars
    times = pd.date_range("2024-01-08 09:30", "2024-01-12 16:00", freq="5min")
    ohlcv = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=times,
    )
    fig = candlestick_plot(ohlcv, symbol="XYZ", timeframe="5m")
    breaks = list(fig.layout.xaxis.rangebreaks or [])
    # Must have at least weekend break + overnight break
    assert len(breaks) >= 2
    assert any(rb.pattern == "hour" for rb in breaks)
    # Weekend break must be present
    assert any(rb.bounds and rb.bounds[0] == "sat" for rb in breaks)


def test_candlestick_overnight_bounds_are_numeric():
    # Plotly.js cleanNumber() rejects "HH:MM" strings — bounds must be decimal hours
    times = pd.date_range("2024-01-08 09:30", "2024-01-12 16:00", freq="5min")
    ohlcv = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=times,
    )
    fig = candlestick_plot(ohlcv, symbol="XYZ", timeframe="5m")
    overnight = [rb for rb in (fig.layout.xaxis.rangebreaks or []) if rb.pattern == "hour"]
    assert len(overnight) == 1
    # bounds must be numeric, not "HH:MM" strings
    assert isinstance(overnight[0].bounds[0], (int, float))
    assert isinstance(overnight[0].bounds[1], (int, float))
    # NYSE XNYS: close=16.0, open=9.5
    assert overnight[0].bounds[0] == 16.0
    assert overnight[0].bounds[1] == 9.5


def test_candlestick_xperiod_matches_timeframe():
    # xperiod fills the full bar period so adjacent candles touch
    idx = pd.bdate_range("2024-01-02", periods=20)
    ohlcv_d = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=idx,
    )
    fig_d = candlestick_plot(ohlcv_d, symbol="XYZ", timeframe="1d")
    trace_d = cast("go.Candlestick", fig_d.data[0])
    assert trace_d.xperiod == 86_400_000  # 1 day in ms
    assert trace_d.xperiodalignment == "start"

    times = pd.date_range("2024-01-08 09:30", "2024-01-10 16:00", freq="1h")
    ohlcv_h = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=times,
    )
    fig_h = candlestick_plot(ohlcv_h, symbol="XYZ", timeframe="1h")
    trace_h = cast("go.Candlestick", fig_h.data[0])
    assert trace_h.xperiod == 3_600_000  # 1 hour in ms
    assert trace_h.xperiodalignment == "start"
