from __future__ import annotations

from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import pytest

from persistra import Engine, Portfolio
from persistra.data.views import prices
from persistra.strategies import EqualWeightRebalance
from persistra.viz.diagnostics import trades_on_price, weights_plot


@pytest.fixture
def result_and_prices(tiny_store):
    result = Engine(
        data=tiny_store,
        strategy=EqualWeightRebalance(),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()
    price_frame = prices(
        tiny_store, ["AAA", "BBB", "CCC"], pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11")
    )
    return result, price_frame


def _n(fig: go.Figure) -> int:
    return len(cast("tuple[Any, ...]", fig.data))


def test_trades_on_price_has_price_and_marker_traces(result_and_prices):
    result, prices = result_and_prices
    fig = trades_on_price(result, prices, "AAA")
    assert isinstance(fig, go.Figure)
    assert _n(fig) >= 2  # price line + at least one marker set


def test_weights_plot_returns_figure(result_and_prices):
    result, _ = result_and_prices
    fig = weights_plot(result)
    assert _n(fig) >= 1


def test_weights_plot_subset(result_and_prices):
    result, _ = result_and_prices
    fig = weights_plot(result, symbols=["AAA"])
    assert _n(fig) == 1


@pytest.fixture
def momentum_result_and_prices(tiny_store):
    from persistra.pipeline import TopN
    from persistra.strategies import CrossSectionalMomentum

    result = Engine(
        data=tiny_store,
        strategy=CrossSectionalMomentum(lookback=3, skip=0, allocation=TopN(n=1, long_short=False)),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()
    price_frame = prices(
        tiny_store, ["AAA", "BBB", "CCC"], pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11")
    )
    return result, price_frame


def test_signal_plot_for_recorded_name(momentum_result_and_prices):
    from persistra.viz.diagnostics import signal_plot

    result, _ = momentum_result_and_prices
    fig = signal_plot(result, "momentum")
    assert len(cast("tuple[Any, ...]", fig.data)) >= 1


def test_signal_plot_missing_name_raises_listing_available(momentum_result_and_prices):
    from persistra.viz.diagnostics import signal_plot

    result, _ = momentum_result_and_prices
    with pytest.raises(KeyError):
        signal_plot(result, "not_recorded")


def test_price_with_signal_returns_two_panel_figure(momentum_result_and_prices):
    from persistra.viz.diagnostics import price_with_signal

    result, prices = momentum_result_and_prices
    fig = price_with_signal(result, prices, "AAA", "momentum")
    assert isinstance(fig, go.Figure)
    assert len(cast("tuple[Any, ...]", fig.data)) >= 2


def test_overlay_plots_importable_from_viz_namespace():
    from persistra.viz import (  # noqa: F401
        price_with_signal,
        signal_plot,
        trades_on_price,
        weights_plot,
    )
