"""Performance and risk metrics for backtest evaluation."""

from persistra.metrics.perf import (
    alpha,
    annualized_return,
    annualized_volatility,
    benchmark_free_summary,
    benchmark_summary,
    beta,
    calmar_ratio,
    exposure_stats,
    hit_rate,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    tail_metrics,
    tracking_error,
    turnover,
)
from persistra.metrics.realized import realized_pnl

__all__ = [
    "alpha",
    "annualized_return",
    "annualized_volatility",
    "benchmark_summary",
    "benchmark_free_summary",
    "beta",
    "calmar_ratio",
    "exposure_stats",
    "hit_rate",
    "information_ratio",
    "max_drawdown",
    "realized_pnl",
    "sharpe_ratio",
    "sortino_ratio",
    "tail_metrics",
    "tracking_error",
    "turnover",
]
