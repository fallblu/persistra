# Connect Alpha Vantage

Use Alpha Vantage when a strategy needs provider-backed market, quote, option, currency,
commodity, economic, or reference data. Prototype downstream logic with synthetic results first;
then replace acquisition while keeping the normalized consumer contracts unchanged.

## Configure the client

Store the key in the environment variable read by `AlphaVantageClient.from_env`:

```bash
export PERSISTRA_ALPHAVANTAGE_API_KEY="your-key"
```

```python
from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env()
```

Persistra removes `apikey` from normalized request metadata and cache identities. You remain
responsible for environment variables, shell output, cache permissions, and diagnostic logs.

## Acquire strategy inputs

Security bars require an explicit instrument kind:

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env()
bars = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    outputsize="compact",
)

print(bars.instrument.instrument_id)
print(bars.frame.tail())
print(bars.metadata.cache_status)
```

The result is a normalized `BarSet`, not a bare frame. Keep its identity and provenance until a
research boundary deliberately pivots several instruments into a date-by-asset panel.

## Configure repeatable acquisition

```python
from datetime import timedelta
from pathlib import Path

client = AlphaVantageClient.from_env(
    cache_directory=Path(".cache/persistra"),
    requests_per_minute=150,
    timeout=30,
    strict_schema=False,
    cache_ages={"TIME_SERIES_DAILY": timedelta(hours=6)},
)
```

Set a request rate allowed by your provider plan. `strict_schema=False` records safely ignored
source fields as diagnostics; it does not permit missing required fields, malformed values, or
contradictory OHLC observations.

For reproducible research, persist selected normalized results in `DuckDBStore`, record the
retrieval cutoff used by a run, and prefer `offline=True` after the raw response cache is complete.
Acquisition never writes to normalized storage automatically.

## Understand strategy limitations

Provider availability and entitlements vary by endpoint and account. A retrieved daily calendar
label is not enough to infer an executable intraday clock. Trading Engine scenarios require raw,
unadjusted, synchronized intraday bars with explicit availability and receipt rules. Do not use
adjusted daily bars as share-and-cash execution histories.

Continue with [Acquire data](../guides/acquisition.md),
[Work offline](../guides/cache-offline.md), [Data and feature examples](../examples/data-and-features.md),
or [Replay a strategy](../guides/trading-engine.md).
