# Data and feature examples

Strategy research starts with explicit identity, observation, availability, and alignment rules.
These examples use synthetic results first and move provider calls into a separate section so the
offline documentation check never requires credentials.

## Create normalized synthetic bars

```python
from persistra.data import synthetic

first = synthetic.bars("FIRST", periods=80, seed=1)
second = synthetic.bars("SECOND", periods=80, seed=2)

print(first.instrument)
print(first.frame.tail())
print(first.metadata)
```

A `BarSet` keeps instrument identity, normalized observations, and acquisition provenance
separate. Synthetic results obey the same schemas as provider-backed results.

## Build a fixed-universe price panel

```python
from persistra.data import pivot_bars

prices = pivot_bars([first, second], field="close")
prices.columns = ["asset-a", "asset-b"]

assert prices.columns.tolist() == ["asset-a", "asset-b"]
print(prices.tail())
```

The original pivot columns are provider and instrument identity pairs. Rename them only at a
deliberate research boundary. Missing observations remain missing.

## Calculate returns without hidden filling

```python
from persistra.analysis import simple_returns

returns = simple_returns(prices)

assert returns.index.equals(prices.index)
print(returns.tail())
```

Choose simple or log returns explicitly. Resampling, alignment, and missing-value choices belong
before model fitting, not inside a regression or optimizer.

## Align independent sources

```python
from persistra.data import align

aligned = align(
    {"prices": prices, "returns": returns},
    how="intersection",
)

assert aligned["prices"].index.equals(aligned["returns"].index)
```

Use an inner join when every downstream row requires every input. Use an outer join when missing
coverage is meaningful and consumers have an explicit missing-data policy.

## Build future labels separately

```python
from persistra.research import forward_returns

labels = forward_returns(prices, horizon=5)

print(labels.frame.tail())
print(labels.label_ends.tail())
```

The final rows remain missing because their future horizon does not exist. `label_ends` makes
purging and embargo decisions inspectable.

## Transform cross-sectional signals

```python
from persistra.research import (
    clip_cross_section,
    rank_cross_section,
    standardize_cross_section,
)

raw_signal = returns.rolling(10, min_periods=10).mean()
clipped_signal = clip_cross_section(raw_signal, lower_quantile=0.05, upper_quantile=0.95)
standard_signal = standardize_cross_section(clipped_signal)
ranked_signal = rank_cross_section(raw_signal, percentile=True)

assert standard_signal.columns.equals(prices.columns)
assert ranked_signal.columns.equals(prices.columns)
```

Cross-sectional operations retain the complete ordered asset axis. A missing cell makes that
asset unavailable for the date; it does not silently change the universe definition.

## Save normalized source results

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore

with TemporaryDirectory() as directory:
    database = Path(directory) / "strategy-inputs.duckdb"
    with DuckDBStore.create(database) as store:
        snapshot_id = store.save(first)
        restored = store.load_bars(first.instrument.instrument_id)

    assert restored is not None
    assert restored.frame.equals(first.frame)
    print(snapshot_id)
```

Acquisition never writes automatically. Save only reviewed normalized results, and keep the
retrieval cutoff or snapshot identity with each research run.

## Provider-backed acquisition

The remaining examples require credentials or previously populated raw caches and are not run by
the documentation smoke check.

### Acquire Alpha Vantage bars

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env()
bars = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    outputsize="full",
)

print(bars.metadata.cache_status)
print(bars.frame.tail())
```

Set `offline=True` after the exact request is cached. Use `refresh=True` only when a run is meant
to retrieve new provider bytes.

### Acquire raw intraday execution inputs

```python
intraday = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="5min",
    adjusted=False,
    outputsize="full",
)
```

Trading Engine scenarios need raw unadjusted bars, an explicit clock policy, synchronized
instruments, and corporate actions. A daily calendar label cannot supply an execution instant.

### Retrieve the latest quote and top of book

```python
quote = client.quotes.latest("IBM", kind=InstrumentKind.EQUITY)
book = client.quotes.top_of_book(["IBM"], kind=InstrumentKind.EQUITY)

print(quote.frame)
print(book.frame)
```

Entitlement and delay fields remain part of the normalized result. Do not treat delayed data as
realtime because it arrived recently.

### Retrieve a historical option chain

```python
from datetime import date

chain = client.options.historical_chain("IBM", date=date(2025, 1, 17))
print(chain.frame[["contract_id", "strike", "expiration", "option_type"]].head())
```

Historical option examples support research and visualization. Persistra does not provide a
realtime option execution model.

### Retrieve current FRED observations

```python
from persistra.data import FredClient

fred = FredClient.from_env()
current_gdp = fred.series.latest("GDPC1", observation_start="2020-01-01")

print(current_gdp.definition)
print(current_gdp.frame.tail())
```

### Retrieve ALFRED revision history

```python
gdp_history = fred.series.vintages(
    "GDPC1",
    realtime_start="2019-01-01",
    observation_start="2018-01-01",
)
```

Use the availability intervals to select the version known at each decision. Retrieval time is
the time Persistra fetched the response, not the time the economic value became knowable.

## Build point-in-time features

`FeatureSpec` binds a vintage source, selection policy, lag, and maximum staleness. Supply
decision dates explicitly:

```python
import pandas as pd

from persistra.research import FeatureSpec, build_feature_panel

decision_dates = pd.date_range("2024-01-31", periods=12, freq="ME")
feature_panel = build_feature_panel(
    [
        FeatureSpec(
            name="real-gdp",
            source=gdp_history,
            publication_lag=pd.Timedelta(days=1),
            maximum_staleness=pd.Timedelta(days=120),
        )
    ],
    decision_dates=decision_dates,
)

print(feature_panel.frame)
print(feature_panel.provenance)
```

An unavailable, stale, deleted, or explicitly missing latest observation stays missing. The
builder does not fall back to an older nonmissing value.

## Prepare reusable experiment inputs

Persist normalized source results, keep feature provenance, create forward labels independently,
and identify external model or configuration artifacts in a research manifest. Then pass only
aligned date-by-asset and date-by-factor panels to model code. This keeps acquisition and vintage
choices reviewable after a strategy target has been produced.
