from __future__ import annotations

from typing import Any, cast

import plotly.graph_objects as go

from persistra.viz.plots import (
    drawdown_plot,
    equity_curve_plot,
    exposure_plot,
    returns_heatmap,
    trade_pnl_histogram,
)


def _assert_figure(fig: go.Figure) -> None:
    assert isinstance(fig, go.Figure)
    assert len(cast("tuple[Any, ...]", fig.data)) >= 1


def test_equity_curve_plot_returns_figure_with_trace(sample_result):
    fig = equity_curve_plot(sample_result)
    _assert_figure(fig)


def test_equity_curve_plot_with_benchmark_adds_second_trace(sample_result):
    import pandas as pd

    equity = sample_result.equity_curve["equity"].astype(float)
    bench = pd.Series(equity.values, index=equity.index)
    fig = equity_curve_plot(sample_result, benchmark=bench)
    assert isinstance(fig, go.Figure)
    assert len(cast("tuple[Any, ...]", fig.data)) == 2


def test_drawdown_plot_returns_figure_with_trace(sample_result):
    fig = drawdown_plot(sample_result)
    _assert_figure(fig)


def test_returns_heatmap_returns_figure_with_trace(sample_result):
    fig = returns_heatmap(sample_result)
    assert isinstance(fig, go.Figure)
    assert len(cast("tuple[Any, ...]", fig.data)) >= 1


def test_trade_pnl_histogram_returns_figure_with_trace(sample_result):
    fig = trade_pnl_histogram(sample_result)
    assert isinstance(fig, go.Figure)
    # trade_pnl_histogram adds a trace only when pnl is non-empty; sample data has trades
    assert len(cast("tuple[Any, ...]", fig.data)) >= 1


def test_exposure_plot_returns_figure_with_two_traces(sample_result):
    fig = exposure_plot(sample_result)
    assert isinstance(fig, go.Figure)
    assert len(cast("tuple[Any, ...]", fig.data)) == 2
