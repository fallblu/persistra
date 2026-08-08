# Connect Alpha Vantage

Persistra's Alpha Vantage adapter is synchronous and organized into namespaces. This page
shows the safe setup path. The detailed endpoint guide is in [Acquire data](../guides/acquisition.md).

## Set the API key

Put the key in the environment variable expected by `AlphaVantageClient.from_env`:

```bash
export PERSISTRA_ALPHAVANTAGE_API_KEY="your-key"
```

Create the client without passing the secret through application code:

```python
from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env()
```

Persistra removes `apikey` from normalized request metadata and cache keys. You are still
responsible for keeping environment variables, shell logs, caches, and diagnostic output
private.

## Make a first request

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

print(bars.frame.tail())
print(bars.metadata.cache_status)
```

The returned `BarSet` has the same shape as `synthetic.bars`. Provider-specific parsing ends
at the adapter boundary.

## Configure client behavior

Pass configuration to either the constructor or `from_env`:

```python
from datetime import timedelta
from pathlib import Path

from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env(
    cache_directory=Path(".cache/persistra"),
    requests_per_minute=150,
    timeout=30,
    strict_schema=False,
    cache_ages={"TIME_SERIES_DAILY": timedelta(hours=6)},
)
```

Important options include:

| Option | Meaning |
|---|---|
| `cache_directory` | Location for raw provider responses |
| `requests_per_minute` | Smooth request-rate limit |
| `timeout` | HTTP timeout in seconds |
| `strict_schema` | Fail instead of recording safely ignored source fields |
| `cache_ages` | Per-operation raw-cache reuse policy |

The adapter defaults to 150 requests per minute. Set a rate allowed by your own provider
plan. Client configuration does not grant an entitlement.

## Understand the namespaces

The client exposes these task-oriented attributes:

| Namespace | Purpose |
|---|---|
| `client.securities` | Equity, ETF, and mutual-fund bars |
| `client.quotes` | Latest quotes, bulk quotes, and top of book |
| `client.indices` | Index bars and the index catalog |
| `client.options` | Historical option chains |
| `client.fx` | Fiat-pair exchange rates and bars |
| `client.crypto` | Crypto-pair exchange rates and bars |
| `client.commodities` | Commodity series and precious-metal spot quotes |
| `client.economics` | Economic and interest-rate series |
| `client.reference` | Symbol search and market status |

## Test an acquired response before storing it

Inspect the normalized frame and provenance before persistence:

```python
assert bars.metadata.provider == "alphavantage"
assert not bars.frame.empty
assert bars.frame["instrument_id"].nunique() == 1

if bars.metadata.diagnostics:
    for diagnostic in bars.metadata.diagnostics:
        print(diagnostic.field, diagnostic.message)
```

Nonfatal source fields appear as schema diagnostics when a safe parse is still possible.
Missing required fields, malformed values, and contradictory OHLC observations fail rather
than being repaired.

## Respect access and source terms

Historical, delayed, and realtime availability depends on the provider account and dataset.
Some operations require a specific entitlement. Alpha Vantage and any named upstream source
terms govern use and redistribution. Confirm those terms for the data you request.

Continue with [Acquire data](../guides/acquisition.md) for namespace examples or
[Work offline and manage the cache](../guides/cache-offline.md) for reproducible acquisition.
