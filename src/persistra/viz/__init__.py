"""Matplotlib visualizations for normalized data."""

from persistra.viz.economics import (
    plot_scalar_series,
    plot_series_change,
    plot_yield_curve,
    plot_yield_curve_history,
)
from persistra.viz.general import (
    plot_correlation,
    plot_coverage,
    plot_distribution,
    plot_rebased,
    plot_rolling_statistic,
    plot_series,
)
from persistra.viz.market import (
    PriceVolumeAxes,
    plot_bid_ask_history,
    plot_candlesticks,
    plot_cumulative_returns,
    plot_drawdowns,
    plot_returns,
    plot_rolling_volatility,
    plot_spread_history,
)
from persistra.viz.options import (
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
    plot_option_volume_open_interest,
)

__all__ = [
    "PriceVolumeAxes",
    "plot_bid_ask_history",
    "plot_candlesticks",
    "plot_correlation",
    "plot_coverage",
    "plot_cumulative_returns",
    "plot_distribution",
    "plot_drawdowns",
    "plot_greek_profile",
    "plot_implied_volatility_smile",
    "plot_implied_volatility_surface",
    "plot_option_chain_prices",
    "plot_option_volume_open_interest",
    "plot_rebased",
    "plot_returns",
    "plot_rolling_statistic",
    "plot_rolling_volatility",
    "plot_scalar_series",
    "plot_series",
    "plot_series_change",
    "plot_spread_history",
    "plot_yield_curve",
    "plot_yield_curve_history",
]
