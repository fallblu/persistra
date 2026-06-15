# The Engine Model

`Engine` runs one strategy over one market-data source and one portfolio.

An `Engine` instance is single-use. Calling `run()` mutates engine-owned ledgers
and also advances user-owned `Strategy` and `Portfolio` instances, so a second
call on the same instance raises `RuntimeError`. Repeat a backtest by creating
fresh `Engine`, `Strategy`, and `Portfolio` instances.

At a high level:

1. Resolve symbols active at any point in the requested date range.
2. Load subscribed timeframes and corporate actions.
3. Iterate sessions from the configured exchange calendar.
4. Apply corporate actions before the session's bars.
5. Dispatch bar-close units in effective-close order.
6. Build a point-in-time `StrategyContext`.
7. Call strategy hooks after warmup is satisfied.
8. Reconcile emitted target weights into orders and fills.
9. Record equity, positions, orders, trades, diagnostics, and metadata.

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

## Universe Exits

The strategy context only includes symbols that are active in the configured
universe and have printed a usable bar. If a held symbol leaves the active
universe, it is treated as a stale holding and is not offered back to the
strategy as tradable.

The engine attempts to liquidate stale holdings with engine-origin orders. When
a later matching bar appears, the order fills from that market bar. When no
later matching bar appears, the order remains unfilled; the engine does not
fabricate a price or synthetic fill. A membership end date is inclusive: if a
symbol's final market bar is on its membership end date, that bar is still an
active-universe bar, and stale liquidation is attempted only on later sessions.

Stale holdings emit diagnostics named `holding_stale`, `holding_stale_weight`,
and `universe_exit`.

## Result

The engine returns a `Result` with equity, orders, trades, positions,
diagnostics, and metadata. `Result.orders` is the canonical order-status table
for filled, rejected, and unfilled orders. `Result.trades` remains the accepted
fill log. If `output_dir` is provided, the result is also persisted as a
completed run artifact.
