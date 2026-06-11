# Strategies and Pipeline

The strategy layer decides what it wants to own. The pipeline layer helps convert raw
signals into practical target weights.

## Direct Target Weights

The simplest strategy emits weights directly:

```python no-run
ctx.signal({"AAPL": 0.50, "MSFT": 0.50})
```

This is appropriate for baselines, hand-authored allocations, and strategies where
position sizing is part of the strategy itself.

## Score-Based Signals

Score-based strategies produce a `pd.Series` where higher values are more bullish. The
pipeline then maps those scores to weights.

```python no-run
ctx.signal(scores, allocation=TopN(n=5, long_short=True))
```

This keeps the alpha signal separate from allocation, sizing, and risk controls.

## Pipeline Order

When provided, pipeline components run in this order:

1. allocation
2. sizing
3. risk projection

Each step receives the output of the previous step. Omitted steps are skipped.

## Composite Strategies

`CompositeStrategy` can combine child strategy emissions with fixed weights. Use it when
you want to evaluate a blend of simple strategies without writing a new monolithic
strategy class.
