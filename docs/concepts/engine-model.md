# The Engine Model

`Engine` runs one strategy over one market-data source and one portfolio.

At a high level:

1. Resolve symbols active at any point in the requested date range.
2. Load subscribed timeframes and corporate actions.
3. Iterate sessions from the configured exchange calendar.
4. Apply corporate actions before the session's bars.
5. Dispatch bar-close units in effective-close order.
6. Build a point-in-time `StrategyContext`.
7. Call strategy hooks after warmup is satisfied.
8. Reconcile emitted target weights into orders and fills.
9. Record equity, positions, trades, diagnostics, and metadata.

## Dispatch Order

Bars are grouped by `(timeframe, bar_time)`. Within a session, groups are ordered by
effective close time. If two groups have the same effective close, finer timeframes fire
first and coarser timeframes fire later.

## Strategy Hooks

- `on_start(ctx)` runs once before the first session.
- `on_bar(ctx)` runs after a subscribed timeframe closes and warmup is satisfied.
- `on_finish(ctx)` runs once after the last session.

Strategies may emit target weights on any `on_bar` call. If a strategy emits nothing,
existing positions are left unchanged.

## Result

The engine returns a `Result` with equity, trades, positions, diagnostics, and metadata.
If `output_dir` is provided, the result is also persisted as a completed run artifact.
