# Work offline and manage the cache

Persistra can retain raw Alpha Vantage response bodies in an atomic, versioned filesystem
cache. The cache supports reproducible parsing and offline work. It is not a normalized data
store and does not replace `DuckDBStore`.

## Choose a cache directory

Pass an explicit directory when you want project-scoped cache placement:

```python
from pathlib import Path

from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env(
    cache_directory=Path(".cache/persistra"),
)
```

When `cache_directory` is omitted, `RawResponseCache` uses the platform-appropriate user
cache directory.

Keep raw caches out of version control. Provider responses may contain licensed or sensitive
observations even though cache keys exclude the API key.

## Understand cache reuse

Historical operations normally reuse a fresh raw response for 24 hours. Live point
observations use a write-for-offline policy but do not reuse the response during ordinary
online acquisition.

Every normalized result reports the outcome through `metadata.cache_status`:

| Status | Meaning |
|---|---|
| `hit` | A reusable cached response was used |
| `miss` | No reusable response existed before a network request |
| `refreshed` | `refresh=True` bypassed reusable content |
| `offline` | `offline=True` loaded cached content without network access |
| `not_used` | Caching did not apply, such as synthetic data |

## Populate and then use the cache offline

First, make an ordinary request while connected:

```python
from persistra.model import InstrumentKind

online = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
)
```

Later, require the exact request to come from cache:

```python
offline = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    offline=True,
)

print(offline.metadata.cache_status)
```

Cache identity includes the provider operation and its request parameters. Changing the
symbol, interval, output size, entitlement, or another parameter can require a different
entry.

If no matching entry exists, Persistra raises `CacheError` rather than silently contacting
the network.

## Force a new response

Use `refresh=True` to bypass otherwise reusable content:

```python
refreshed = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    refresh=True,
)
```

The successful response replaces or adds the raw cache entry for later use. Do not combine
`refresh=True` with an expectation of an offline-only workflow.

## Override operation-specific ages

`cache_ages` maps provider operation names to a `timedelta` or `None`:

```python
from datetime import timedelta

client = AlphaVantageClient.from_env(
    cache_ages={
        "TIME_SERIES_DAILY": timedelta(hours=6),
        "CPI": timedelta(days=7),
        "CURRENCY_EXCHANGE_RATE": None,
    }
)
```

- A nonnegative duration permits ordinary reuse while the entry is younger than that age.
- `timedelta(0)` effectively requires a new online response while still permitting writes.
- `None` writes a response for later offline use but does not reuse it during a normal online
  call.

Negative ages are rejected during client construction.

## Use the raw cache directly

Most applications should let `AlphaVantageClient` manage raw entries. Direct access is
available for transport integration and controlled diagnostics:

```python
from pathlib import Path

from persistra.data import RawResponseCache

cache = RawResponseCache(Path(".cache/persistra"))
```

The direct API works with `RawCacheEntry` objects and explicit timestamps. Avoid decoding or
editing response bodies outside the adapter unless you are diagnosing provider parsing.

## Separate raw caching from normalized storage

The two persistence layers have different guarantees:

| Raw response cache | DuckDB store |
|---|---|
| Provider bytes and transport provenance | Validated normalized results |
| Request-oriented keys | Result-family scope keys |
| Reuse and offline parsing | Research queries and revisions |
| Safe to delete when reproducibility is not needed | Research data retained by explicit choice |

Deleting a raw cache does not delete normalized DuckDB data. Deleting a DuckDB store does not
clear provider cache entries.

## Build a network-prohibited check

Use `offline=True` in code that must never contact the provider:

```python
def load_daily_offline(client: AlphaVantageClient, symbol: str):
    return client.securities.bars(
        symbol,
        kind=InstrumentKind.EQUITY,
        interval="daily",
        offline=True,
    )
```

For tests and examples that do not need provider payloads at all, prefer
`persistra.data.synthetic`. Synthetic helpers avoid both network and cache dependencies.
