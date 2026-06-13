# Execution Assumptions

persistra is a research backtester, not a live order router. The default fill model is
intentionally simple so execution assumptions are visible.

## Timing Modes

The default timing mode is `same_close`: target-weight orders fill at the same bar close
that triggered the strategy. This preserves the original close-to-close research
assumption.

Use it for:

- API examples
- strategy-shape debugging
- first-pass research

Do not mistake it for a conservative live-trading simulation.

For more conservative simulations, pass an execution timing mode to the engine:

```python no-run
from persistra import Engine, ExecutionTiming

engine = Engine(
    data=data,
    strategy=strategy,
    portfolio=portfolio,
    start="2020-01-02",
    end="2023-12-29",
    execution_timing=ExecutionTiming.NEXT_OPEN,
)
```

Available modes:

- `same_close`: decide with the current completed bar and fill at that bar's close.
- `next_open`: decide with the current completed bar and fill at the next available
  matching bar's open.
- `next_close`: decide with the current completed bar and fill at the next available
  matching bar's close.
- `delay_bars`: fill at the close after `delay_bars` later matching bars.

```python no-run
engine = Engine(..., execution_timing="delay_bars", delay_bars=2)
```

Pending orders carry across bar and session boundaries until a matching future bar is
available. If no matching bar appears before the backtest ends, the order remains
unfilled.

`result.trades` records both `order_timestamp` and `timestamp`. `order_timestamp` is
when the strategy generated the order; `timestamp` is when the fill occurred.

## Cost Models

Available execution models include:

- `FixedCommission`
- `ProportionalSlippage`
- `VolumeImpact`

```python no-run
from persistra import FixedCommission, ProportionalSlippage, VolumeImpact

commission = FixedCommission(rate=0.0001)
slippage = ProportionalSlippage(bps=2.0, rate=0.0001)
impact = VolumeImpact(impact=0.01, rate=0.0001)
```

Choose the simplest explicit model that matches the research question. For example,
add proportional slippage before comparing high-turnover strategies.

## What Is Not Modeled By Default

The default portfolio layer does not impose margin, borrow availability, financing
costs, tax lots, or broker-specific order constraints. Add those assumptions through a
custom execution model, sizing rule, risk constraint, or portfolio extension.
