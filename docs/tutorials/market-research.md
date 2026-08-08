# Tutorial: compare markets

This tutorial builds a small cross-asset study entirely offline. You will create normalized
bars, compare coverage, calculate returns and risk statistics, visualize the results, and
store the original observations.

The synthetic observations are illustrative. They exercise the research workflow but do not
represent real instruments.

## 1. Create four result objects

Use distinct seeds to produce different deterministic paths. Instrument kinds make pair and
index identities explicit.

```python
from persistra.data import synthetic
from persistra.model import InstrumentKind

equity = synthetic.bars("EQUITY", periods=120, seed=1)
index = synthetic.bars(
    "INDEX",
    periods=120,
    seed=2,
    kind=InstrumentKind.INDEX,
)
fx = synthetic.bars(
    "EUR/USD",
    periods=120,
    seed=3,
    kind=InstrumentKind.FIAT_PAIR,
)
crypto = synthetic.bars(
    "BTC/USD",
    periods=120,
    seed=4,
    kind=InstrumentKind.CRYPTO_PAIR,
)

results = [equity, index, fx, crypto]
```

Each item is a `BarSet`. Verify that each frame has the same exact schema while identity stays
outside the observations:

```python
expected_columns = list(equity.frame.columns)

for result in results:
    assert list(result.frame.columns) == expected_columns
    print(result.instrument.kind, result.instrument.display_name)
```

## 2. Pivot close prices

Normalized frames are long and scoped to one instrument. Most multivariate analysis expects
a wide frame with one instrument per column.

```python
from persistra.data import pivot_bars

prices = pivot_bars(results, field="close")
prices.columns = ["Equity", "Index", "FX", "Crypto"]

print(prices.head())
```

`pivot_bars` takes the union of observed labels through pandas concatenation. It does not
fill missing values. Before calculating returns, inspect coverage:

```python
from persistra.analysis import coverage_summary

coverage = coverage_summary(prices)
print(coverage)
```

## 3. Calculate returns and descriptive statistics

Persistra separates level changes from returns. Here, the data are price-like positive
levels, so simple returns are appropriate.

```python
from persistra.analysis import simple_returns, summary_statistics

returns = simple_returns(prices)
statistics = summary_statistics(returns)

print(statistics.round(4))
```

The first row of returns is missing because there is no previous level. Persistra does not
fill that row or bridge missing internal levels.

Calculate pairwise correlation and a 20-observation annualized rolling volatility estimate:

```python
from persistra.analysis import correlation_matrix, rolling_volatility

correlation = correlation_matrix(returns)
volatility = rolling_volatility(
    returns,
    window=20,
    periods_per_year=252,
)

print(correlation.round(3))
print(volatility.tail().round(3))
```

The annualization factor is explicit. Change it when your observation frequency or research
convention differs.

## 4. Compare cumulative paths and drawdowns

`cumulative_returns` and `drawdowns` reject gaps within an observed span because compounding
across an unknown return would invent a path.

```python
from persistra.analysis import cumulative_returns, drawdowns

complete_returns = returns.dropna()
cumulative = cumulative_returns(complete_returns)
underwater = drawdowns(complete_returns)

print(cumulative.tail())
print(underwater.min())
```

Dropping rows is an explicit tutorial choice. In real research, first determine why a label
is missing and whether intersection, union, or another policy matches the question.

## 5. Plot the study

Persistra returns Matplotlib axes so you can own figure layout and presentation.

```python
import matplotlib.pyplot as plt

from persistra.viz import (
    plot_correlation,
    plot_drawdowns,
    plot_rebased,
    plot_rolling_volatility,
)

figure, axes = plt.subplots(2, 2, figsize=(12, 8))

plot_rebased(prices, ax=axes[0, 0])
axes[0, 0].set_title("Rebased levels")

plot_correlation(returns, ax=axes[0, 1])
axes[0, 1].set_title("Return correlation")

plot_rolling_volatility(volatility, ax=axes[1, 0])
axes[1, 0].set_title("20-observation annualized volatility")

plot_drawdowns(underwater, ax=axes[1, 1])
axes[1, 1].set_title("Drawdowns")

figure.tight_layout()
plt.show()
```

`plot_rebased` performs only the named rebasing calculation. The volatility and drawdown
plots accept already calculated inputs so their policy choices remain visible.

## 6. Save the normalized source results

Store the original `BarSet` objects rather than only the derived wide frames. This retains
identity and acquisition metadata.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore

with TemporaryDirectory() as directory:
    path = Path(directory) / "cross-asset.duckdb"
    with DuckDBStore.create(path) as store:
        snapshot_ids = [store.save(result) for result in results]
        restored = store.load_bars(equity.instrument.instrument_id)

    assert restored is not None
    assert restored.frame.equals(equity.frame)
    print(snapshot_ids)
```

The store uses retrieval-time revisions. Saving identical source content again updates its
last-seen time; saving changed content creates another revision.

## What you learned

You used the main research boundary:

1. A provider or synthetic helper produced validated result objects.
2. A transform produced an explicit wide frame.
3. Analysis functions calculated research quantities without fetching data.
4. Plot functions presented already defined calculations.
5. Storage retained normalized source results and provenance.

See [Reshape and align data](../guides/transforms.md) for mismatched calendars and as-of
joins, or the [snippet cookbook](../examples/snippets.md) for shorter patterns.
