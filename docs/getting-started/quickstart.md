# Quickstart

This runs a complete backtest on the bundled sample dataset.

```python
from persistra import Engine, EqualWeightRebalance, ParquetMarketData, Portfolio
from persistra.metrics import benchmark_free_summary

result = Engine(
    data=ParquetMarketData("examples/sample_data"),
    strategy=EqualWeightRebalance(every=21),
    portfolio=Portfolio(initial_capital=1_000_000.0),
    start="2022-01-03",
    end="2023-12-29",
).run()

summary = benchmark_free_summary(result.equity_curve["equity"])
print(round(summary["sharpe"], 3))
print(len(result.trades) > 0)
```

The important pieces are:

- `ParquetMarketData("examples/sample_data")` loads local bars, corporate actions, and
  universe membership.
- `EqualWeightRebalance(every=21)` rebalances the active universe roughly monthly.
- `Portfolio(initial_capital=...)` holds cash, positions, and equity snapshots.
- `Engine(...).run()` returns a `Result` with equity, trades, positions, diagnostics, and
  metadata.
