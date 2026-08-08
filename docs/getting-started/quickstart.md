# Quickstart

This quickstart walks through Persistra's full offline path: create normalized data, inspect
its contract, transform it into research-ready columns, calculate returns, plot the result,
and save it to DuckDB.

## Create normalized bars

Synthetic helpers are deterministic. The same arguments produce the same observations, so
they are useful for tutorials, tests, and reproducible examples.

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO", periods=30, seed=7)

print(bars.instrument)
print(bars.frame[["date", "open", "high", "low", "close", "volume"]].tail())
```

`bars` is a `BarSet`, not a bare `DataFrame`. Its three parts have different jobs:

```python
print(bars.instrument.instrument_id)  # stable identity for this result scope
print(bars.frame.dtypes)              # exact normalized observation schema
print(bars.metadata.provider)         # acquisition provenance
print(bars.metadata.retrieved_at)     # timezone-aware retrieval time
```

The synthetic provider follows the same result contract as Alpha Vantage. Code that consumes
a `BarSet` does not need a separate path for tutorial data.

## Compare two instruments

`pivot_bars` converts one field from several normalized results into a wide numeric frame.
It preserves the source labels and does not fill gaps.

```python
from persistra.analysis import correlation_matrix, simple_returns
from persistra.data import pivot_bars, synthetic

equity = synthetic.bars("EQUITY", periods=60, seed=1)
index = synthetic.bars("INDEX", periods=60, seed=2)

prices = pivot_bars([equity, index], field="close")
returns = simple_returns(prices)
correlation = correlation_matrix(returns)

print(prices.tail())
print(correlation)
```

The wide columns are `(provider, instrument_id)` pairs. Rename them after the pivot when
display labels are more useful in a report:

```python
prices.columns = ["Equity", "Index"]
returns = simple_returns(prices)
```

## Plot explicit calculations

Plotting functions accept prepared data. Calculate returns first so the return definition and
missing-value policy remain visible.

```python
import matplotlib.pyplot as plt

from persistra.viz import plot_returns

ax = plot_returns(returns)
ax.set_title("Synthetic daily returns")
ax.figure.tight_layout()
plt.show()
```

Every plot function returns its axes. You can add titles, labels, annotations, and layout
changes with normal Matplotlib methods.

## Save and restore the normalized result

Acquisition never writes automatically. Create a DuckDB store and save only the results you
intend to retain:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore

with TemporaryDirectory() as directory:
    path = Path(directory) / "research.duckdb"
    with DuckDBStore.create(path) as store:
        snapshot_id = store.save(equity)
        restored = store.load_bars(equity.instrument.instrument_id)

    assert restored is not None
    assert restored.frame.equals(equity.frame)
    print(snapshot_id)
```

`DuckDBStore.create` refuses to overwrite an existing path. Use `DuckDBStore.open` for an
existing compatible database.

## Choose the next step

- Follow [Compare markets](../tutorials/market-research.md) for a longer cross-asset workflow.
- Follow [Explore historical options](../tutorials/options-research.md) for chain filtering,
  moneyness, implied volatility, and plots.
- Follow [Study economic series](../tutorials/economic-research.md) for growth, rate changes,
  and Treasury curves.
- Read [Connect Alpha Vantage](alpha-vantage.md) when you are ready to replace synthetic data
  with provider-backed results.
