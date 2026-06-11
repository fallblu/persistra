# Pipeline and Risk

Strategies can emit direct target weights or raw scores. When the strategy emits scores,
`ctx.signal(...)` can route them through allocation, sizing, and risk components.

## Allocation

Allocation rules convert cross-sectional scores into signed weights or directions.

```python no-run
import pandas as pd
from persistra.pipeline import RankWeighted, TopN

scores = pd.Series({"AAPL": 0.8, "MSFT": 0.4, "JPM": -0.2, "TSLA": -0.7})

top_bottom = TopN(n=1, long_short=True).allocate(scores)
ranked = RankWeighted().allocate(scores)
```

Common allocation rules:

- `TopN`: equal-weight the best names and optionally short the worst names.
- `Decile`: equal-weight top and bottom fractions of the universe.
- `RankWeighted`: rank-demeaned long/short weights.
- `Direct`: pass scores through unchanged.

## Sizing

Sizing rules convert directions into target portfolio fractions.

- `EqualWeight`: equal gross exposure across active positions.
- `FixedDollar`: fixed notional per active position.
- `VolTarget`: scales each leg using trailing realized volatility.

```python no-run
from persistra.pipeline import EqualWeight, VolTarget

ctx.signal(scores, allocation=TopN(n=5), sizer=EqualWeight(target_gross=1.0))
ctx.signal(scores, allocation=TopN(n=5), sizer=VolTarget(annual_vol=0.12, lookback=60))
```

## Risk Constraints

Risk constraints project proposed target weights into a permitted exposure set.

- `CashFloor`: keep at least a chosen fraction uninvested.
- `MaxGrossExposure`: cap total absolute exposure.
- `MaxNetExposure`: clamp net exposure to a band.
- `MaxPositionSize`: clip each individual position.

```python no-run
from persistra.pipeline import MaxGrossExposure, MaxPositionSize

ctx.signal(scores, allocation=RankWeighted(), risk=MaxGrossExposure(limit=1.0))
ctx.signal(scores, allocation=TopN(n=10), risk=MaxPositionSize(limit=0.05))
```

For multiple risk constraints, create a small custom `RiskConstraint` that applies them
in the order you want.
