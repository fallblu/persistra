# Strategy Context

`StrategyContext` is the strategy's point-in-time view of the world.

## Properties

- `timestamp`: close time of the bar that just fired
- `timeframe`: timeframe whose bar just closed
- `portfolio`: current portfolio snapshot
- `universe`: active tradable symbols on this bar

## History

```python no-run
closes = ctx.history().closes(60)
daily = ctx.history("1d").closes(252)
hourly = ctx.history("1h").closes(120)
```

`ctx.history()` defaults to the firing timeframe. Pass a timeframe string when the
strategy subscribes to multiple timeframes.

## Signal Emission

```python no-run
ctx.signal({"AAPL": 0.25, "MSFT": 0.25})
```

With no pipeline arguments, values are direct target weights. With pipeline arguments,
values are treated as scores or directions and converted into final weights.

```python no-run
ctx.signal(scores, allocation=allocation, sizer=sizer, risk=risk)
```

## Diagnostics

```python no-run
ctx.record("momentum", scores)
ctx.record("gross_signal", float(scores.abs().sum()))
```

Diagnostics are drained by the engine after `on_bar` and stored in `Result.diagnostics`.
