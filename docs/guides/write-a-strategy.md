# Write a Strategy

Strategies subclass `Strategy` and implement `on_bar`. The engine passes a
`StrategyContext` containing the current timestamp, firing timeframe, rolling history,
portfolio state, and active universe.

```python no-run
from persistra import Strategy


class EqualWeightEveryBar(Strategy):
    warmup = 1

    def on_bar(self, ctx):
        if not ctx.universe:
            return
        weight = 1.0 / len(ctx.universe)
        ctx.signal({symbol: weight for symbol in ctx.universe})
```

`ctx.signal(...)` emits target weights. A strategy can stay silent on a bar; the engine
then leaves existing positions alone.

## Use Rolling History

`ctx.history().closes(n)` returns a wide `bar_time` by `symbol` frame for the active
history window.

```python no-run
from persistra import Strategy


class SimpleTrend(Strategy):
    warmup = 50

    def on_bar(self, ctx):
        closes = ctx.history().closes(50)
        fast = closes.tail(20).mean()
        slow = closes.mean()
        longs = [symbol for symbol in closes.columns if fast[symbol] > slow[symbol]]
        if not longs:
            ctx.signal({})
            return
        ctx.signal({symbol: 1.0 / len(longs) for symbol in longs})
```

## Record Diagnostics

Use `ctx.record(name, value)` to save per-bar values for later inspection.

```python no-run
ctx.record("spread", fast - slow)
```

Diagnostics appear in `result.diagnostics` and can be pivoted with:

```python no-run
spread = result.diagnostic("spread")
```

## Multi-Timeframe Strategies

Declare timeframes on the strategy class. The first timeframe is primary. `on_bar` fires
for each subscribed timeframe after that timeframe's bar closes.

```python no-run
class DailyAndHourlyStrategy(Strategy):
    timeframes = ("1d", "1h")
    warmup = 20

    def on_bar(self, ctx):
        daily = ctx.history("1d").closes(20)
        hourly = ctx.history("1h").closes(20)
```

Keep warmup large enough for the longest lookback you actually read.
