# First Backtest

A persistra backtest has four required inputs:

- market data implementing `MarketData`
- a `Strategy`
- a `Portfolio`
- an inclusive start/end date range

```python
from persistra import BuyAndHold, Engine, ParquetMarketData, Portfolio

data = ParquetMarketData("examples/sample_data")
strategy = BuyAndHold()
portfolio = Portfolio(initial_capital=1_000_000.0)

result = Engine(
    data=data,
    strategy=strategy,
    portfolio=portfolio,
    start="2022-01-03",
    end="2022-12-30",
).run()

print(result.equity_curve.columns.tolist())
print(result.meta["strategy_id"])
```

## Result Outputs

`Result` is the main object you inspect after a run:

- `equity_curve`: equity, cash, gross exposure, and net exposure over time
- `trades`: executed fills
- `positions`: sparse target-weight history
- `diagnostics`: values recorded by strategies with `ctx.record(...)`
- `meta`: run metadata

## Dates and Sessions

The engine normalizes start and end timestamps to dates and iterates exchange sessions
from the configured calendar, `XNYS` by default. Bars dated on non-session days are
rolled to the next available session; bars with no following session are dropped with a
warning.

## Warmup

Every strategy has a `warmup` count. The engine fills rolling history before calling
`on_bar` for the strategy. For example, a 50-day moving-average strategy should use a
warmup of at least 50 bars.

## Execution

The default execution timing is `same_close`: `IdealFill` fills target-weight orders at
the bar close that triggered the signal. For a more conservative assumption, set
`execution_timing="next_open"` or `execution_timing="next_close"`. For studies that need
transaction costs, pass a custom execution model:

```python no-run
from persistra import Engine, ProportionalSlippage

engine = Engine(
    data=data,
    strategy=strategy,
    portfolio=portfolio,
    start="2022-01-03",
    end="2022-12-30",
    execution_model=ProportionalSlippage(bps=2.0, rate=0.0001),
)
```
