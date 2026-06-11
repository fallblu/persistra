"""Performance plots and run-comparison visuals (Plotly)."""

from persistra.viz._style import styled_figure
from persistra.viz.benchmark import buy_and_hold_benchmark, equal_weight_benchmark
from persistra.viz.diagnostics import (
    price_with_signal,
    signal_plot,
    trades_on_price,
    weights_plot,
)
from persistra.viz.market import (
    candlestick_plot,
    correlation_heatmap,
    feature_plot,
    price_plot,
)
from persistra.viz.plots import (
    drawdown_plot,
    equity_curve_plot,
    exposure_plot,
    returns_heatmap,
    trade_pnl_histogram,
)

__all__ = [
    "styled_figure",
    "buy_and_hold_benchmark",
    "candlestick_plot",
    "correlation_heatmap",
    "drawdown_plot",
    "equal_weight_benchmark",
    "equity_curve_plot",
    "exposure_plot",
    "feature_plot",
    "price_plot",
    "price_with_signal",
    "returns_heatmap",
    "signal_plot",
    "trade_pnl_histogram",
    "trades_on_price",
    "weights_plot",
]
