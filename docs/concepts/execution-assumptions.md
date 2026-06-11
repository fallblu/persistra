# Execution Assumptions

persistra is a research backtester, not a live order router. The default fill model is
intentionally simple so execution assumptions are visible.

## Default Model

`IdealFill` fills target-weight orders at the same bar close that triggered the strategy.
This is a close-to-close rebalance assumption.

Use it for:

- API examples
- strategy-shape debugging
- first-pass research

Do not mistake it for a conservative live-trading simulation.

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
