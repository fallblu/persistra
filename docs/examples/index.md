# Examples

The examples use public Persistra APIs and explicit intermediate objects.

| Topic | Use it for |
|---|---|
| [Monte Carlo research](monte-carlo.md) | Generate reproducible paths and inspect convergence |
| [Data and features](data-and-features.md) | Normalize data and build point-in-time inputs |
| [Factor models](factor-models.md) | Fit regressions and build risk and forecast objects |
| [Portfolio optimization](portfolio-optimization.md) | Express objectives, constraints, costs, and backtests |
| [Analysis and visualization](analysis-and-visualization.md) | Inspect research and portfolio results |

For a factor workflow, move from data and features to factor models, then portfolio optimization.
For distributional research, begin with Monte Carlo. Use the
[Trading Engine guide](../guides/trading-engine.md) when a completed scenario needs deterministic
execution replay.

Keep these distinctions visible in application code:

- retrieval time is provenance, not market availability;
- a feature is not a forward label;
- a forecast is not a target portfolio;
- a vectorized backtest is not an order-level replay.
