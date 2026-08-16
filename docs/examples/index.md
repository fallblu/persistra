# Examples by topic

These examples are organized around the path from research inputs to an audited strategy replay.
Each page states the boundary it covers and uses public Persistra APIs. The core factor, portfolio,
and lifecycle pages are executed by the documentation check in isolated temporary directories.

## Strategy workflow

| Topic | Use it for |
|---|---|
| [Data and features](data-and-features.md) | Normalize bars, align panels, build point-in-time features, labels, and offline stores |
| [Factor models](factor-models.md) | Fit static, rolling, and cross-sectional regressions; build risk and forecast objects |
| [Portfolio optimization](portfolio-optimization.md) | Express objectives, constraints, covariance policies, costs, rolling decisions, and backtests |
| [Strategy lifecycle](strategy-lifecycle.md) | Add warm-up, history, filtering, schedules, hooks, and complete target behavior |
| [Composite strategies](composite-strategies.md) | Separate alpha, combination, construction, overlays, and rebalance guards |
| [Trading Engine replay](trading-engine-replay.md) | Build scenarios, host an external strategy, run the engine, and retain artifacts |
| [Analysis and visualization](analysis-and-visualization.md) | Inspect research, portfolio, execution, and audit results without hidden calculations |

## Suggested paths

For a new factor strategy:

1. Fit and diagnose a model in [Factor models](factor-models.md).
2. Convert the forecast into targets in [Portfolio optimization](portfolio-optimization.md).
3. Implement the runtime behavior in [Strategy lifecycle](strategy-lifecycle.md).
4. Split larger systems into components with [Composite strategies](composite-strategies.md).
5. Run the external process through [Trading Engine replay](trading-engine-replay.md).

For a strategy that already emits a target-weight panel, start with
[Portfolio optimization](portfolio-optimization.md) and use the scheduled-target path in
[Trading Engine replay](trading-engine-replay.md).

For point-in-time macro or fundamental signals, begin with [Data and features](data-and-features.md)
before fitting or evaluating any model.

## Reading the examples

Examples favor explicit intermediate objects over compact chaining. Keep these distinctions in
application code:

- retrieval time is provenance, not market availability;
- a feature is not a forward label;
- a forecast is not a target portfolio;
- a requested target is not a filled position;
- a vectorized backtest is not an order-level execution replay;
- a successful engine exit is not enough without a complete verified journal.

Copy the smallest relevant example, replace its synthetic inputs, and retain the validation and
diagnostic checks around it.
