# Metrics and Plots

`Result` is designed to be inspected directly with pandas, metrics helpers, and Plotly
visualizations.

## Benchmark-Free Metrics

```python no-run
from persistra.metrics import benchmark_free_summary

metrics = benchmark_free_summary(result.equity_curve["equity"])
print(metrics["sharpe"])
print(metrics["max_drawdown"])
```

The benchmark-free summary includes annualized return, annualized volatility, Sharpe,
Sortino, Calmar, max drawdown, hit rate, VaR, and CVaR.

## Benchmark-Aware Metrics

```python no-run
from persistra.metrics import benchmark_summary

active = benchmark_summary(
    result.equity_curve["equity"],
    benchmark_result.equity_curve["equity"],
)
```

Benchmark-aware metrics include alpha, beta, active annualized return, tracking error,
and information ratio.

## Plots

Plot helpers return Plotly `Figure` objects.

```python no-run
from persistra.viz import drawdown_plot, equity_curve_plot, exposure_plot

equity_curve_plot(result).show()
drawdown_plot(result).show()
exposure_plot(result).show()
```

Useful plot groups:

- performance: `equity_curve_plot`, `drawdown_plot`, `returns_heatmap`
- portfolio: `exposure_plot`, `weights_plot`
- trades and diagnostics: `trade_pnl_histogram`, `trades_on_price`, `signal_plot`
- market data: `price_plot`, `candlestick_plot`, `correlation_heatmap`

## Diagnostics

Strategy diagnostics recorded with `ctx.record(...)` are stored in long form:

```python no-run
diagnostics = result.diagnostics
momentum = result.diagnostic("momentum")
```

Use diagnostics to audit why a strategy traded, not just how it performed.
