# Built-In Strategies

persistra includes small strategy implementations for use as examples and baselines.

## Baselines

- `BuyAndHold`: allocate once, then let the book drift.
- `EqualWeightRebalance`: rebalance the active universe to equal weight every `every`
  bars.

```python no-run
from persistra import BuyAndHold, EqualWeightRebalance

buy_and_hold = BuyAndHold()
monthly_equal_weight = EqualWeightRebalance(every=21)
```

## Cross-Sectional Strategies

- `CrossSectionalMomentum`: ranks symbols by trailing cumulative log return, optionally
  skipping recent bars.
- `MeanReversion`: shorts recent winners and buys recent losers using a cross-sectional
  z-score.

```python no-run
from persistra import CrossSectionalMomentum, MeanReversion
from persistra.pipeline import RankWeighted, TopN

momentum = CrossSectionalMomentum(lookback=126, skip=21, allocation=TopN(n=5))
reversal = MeanReversion(lookback=5, allocation=RankWeighted())
```

## Trend and Risk-Based Strategies

- `SMACrossover`: goes long symbols whose fast moving average is above their slow moving
  average.
- `VolTargetedEqualWeight`: emits long directions over the active universe and sizes legs
  with `VolTarget`.

```python no-run
from persistra import SMACrossover, VolTargetedEqualWeight

trend = SMACrossover(fast=20, slow=50)
vol_targeted = VolTargetedEqualWeight(annual_vol=0.10, lookback=60)
```

The built-ins are intentionally compact. Use them to learn the expected strategy shape,
then subclass `Strategy` for custom research logic.
