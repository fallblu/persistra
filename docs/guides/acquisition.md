# Acquire data

Use `AlphaVantageClient` when you need provider-backed results. The client exposes namespaces
that match data families and returns normalized model objects. It never writes to a
`DuckDBStore`; acquisition and persistence remain separate decisions.

All examples on this page make network requests unless they use `offline=True` and a cached
response already exists.

## Create the client

```python
from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env(
    requests_per_minute=150,
    timeout=30,
)
```

`from_env` reads `PERSISTRA_ALPHAVANTAGE_API_KEY`. See
[Connect Alpha Vantage](../getting-started/alpha-vantage.md) for setup and client options.

## Acquire security bars

Security bars support equities, exchange-traded funds, and mutual funds. The instrument kind
is required because Persistra does not guess it from a symbol.

```python
from persistra.model import InstrumentKind

daily = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    adjusted=True,
    outputsize="full",
)
```

Supported security intervals are `1min`, `5min`, `15min`, `30min`, `60min`, `daily`,
`weekly`, and `monthly`. `adjusted`, `extended_hours`, `month`, and `entitlement` have
interval-specific meaning; invalid combinations raise `ValueError` before a request.

Acquire one intraday month:

```python
from persistra.model import EntitlementMode, InstrumentKind

intraday = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="5min",
    month="2025-01",
    outputsize="full",
    extended_hours=False,
    entitlement=EntitlementMode.HISTORICAL,
)
```

Iterate explicit months without constructing the individual calls yourself:

```python
months = ["2024-11", "2024-12", "2025-01"]

for result in client.securities.iter_intraday_months(
    "IBM",
    months,
    kind=InstrumentKind.EQUITY,
    interval="5min",
):
    print(result.frame["timestamp"].min(), result.frame["timestamp"].max())
```

The iterator follows the caller's month order. It does not fetch months concurrently.

## Acquire latest quotes and top of book

The latest quote method accepts an explicit entitlement mode:

```python
from persistra.model import EntitlementMode

quote = client.quotes.latest(
    "IBM",
    entitlement=EntitlementMode.DELAYED,
)
```

Bulk quotes and top-of-book snapshots are realtime-only provider operations. Their methods
therefore do not accept an entitlement argument:

```python
bulk = client.quotes.bulk(["IBM", "MSFT", "AAPL"])
book = client.quotes.top_of_book(["IBM", "MSFT"])
```

Larger requests are divided into deterministic batches and returned in caller order. Confirm
that your account can access realtime United States market data before using these methods.

## Acquire index data

```python
index_bars = client.indices.bars("SPX", interval="weekly")
catalog = client.indices.catalog()

print(catalog.frame[["provider_symbol", "name"]].head())
```

Index bars support `daily`, `weekly`, and `monthly`. The catalog preserves the provider's
symbol-to-name data and does not invent market or currency fields.

## Acquire fiat and crypto pairs

Pair methods always require separate base and quote currencies:

```python
fx_rate = client.fx.rate("EUR", "USD")
fx_bars = client.fx.bars("EUR", "USD", interval="daily")

crypto_rate = client.crypto.rate("BTC", "USD")
crypto_bars = client.crypto.bars("BTC", "USD", interval="60min")
```

Both pair namespaces support current exchange rates and `1min`, `5min`, `15min`, `30min`,
`60min`, `daily`, `weekly`, and `monthly` bars. The normalized `Instrument` records base and
quote currencies explicitly.

## Acquire historical options

Fetch one historical chain with a date object or ISO date string:

```python
from datetime import date

chain = client.options.historical_chain(
    "IBM",
    date=date(2025, 1, 17),
)
```

Walk an inclusive calendar range:

```python
for chain in client.options.iter_historical_chains(
    "IBM",
    start="2025-01-13",
    end="2025-01-17",
):
    print(chain.chain_date, len(chain.observations))
```

The iterator skips only responses classified unambiguously as no data. It does not infer a
trading calendar, fetch an underlying price, or request a realtime option chain.

## Acquire commodity data

Current spot observations are available for gold and silver:

```python
gold = client.commodities.spot("gold")
```

Historical primary commodity series use the provider operation name and a native frequency:

```python
wti = client.commodities.series("WTI", frequency="weekly")
copper = client.commodities.series("COPPER", frequency="monthly")
gold_history = client.commodities.series(
    "GOLD_SILVER_HISTORY",
    frequency="daily",
    metal="gold",
)
```

Supported commodity identifiers and frequencies are:

| Identifiers | Frequencies |
|---|---|
| `WTI`, `BRENT`, `NATURAL_GAS` | daily, weekly, monthly |
| `GOLD_SILVER_HISTORY` | daily, weekly, monthly |
| `COPPER`, `ALUMINUM`, `WHEAT`, `CORN`, `COTTON`, `SUGAR`, `COFFEE`, `ALL_COMMODITIES` | monthly, quarterly, annual |

## Acquire economic data

```python
gdp = client.economics.series("REAL_GDP", frequency="quarterly")
cpi = client.economics.series("CPI", frequency="monthly")
unemployment = client.economics.series("UNEMPLOYMENT")
treasury = client.economics.series(
    "TREASURY_YIELD",
    frequency="daily",
    maturity="10year",
)
```

Supported indicators are `REAL_GDP`, `REAL_GDP_PER_CAPITA`, `TREASURY_YIELD`,
`FEDERAL_FUNDS_RATE`, `CPI`, `INFLATION`, `RETAIL_SALES`, `DURABLES`, `UNEMPLOYMENT`, and
`NONFARM_PAYROLL`. Treasury maturities are `3month`, `2year`, `5year`, `7year`, `10year`, and
`30year`. Each indicator validates its supported native frequencies.

## Acquire reference data

```python
matches = client.reference.search("International Business Machines")
status = client.reference.market_status()

print(matches.frame.head())
print(status.frame)
```

Search results are provider matches, not inferred canonical identities. Add mappings to a
`Catalog` only when you have decided that a provider symbol identifies your instrument.

## Control cache and network behavior per call

Every acquisition method accepts `refresh` and `offline` keyword arguments:

```python
cached = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    offline=True,
)

fresh = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    refresh=True,
)
```

`offline=True` prohibits network access. `refresh=True` bypasses a reusable cached response.
For complete cache semantics, read [Work offline and manage the cache](cache-offline.md).

## Inspect provenance after every request

```python
metadata = daily.metadata

print(metadata.operation)
print(metadata.request_parameters)
print(metadata.retrieved_at)
print(metadata.provider_as_of)
print(metadata.entitlement)
print(metadata.cache_status)
print(metadata.diagnostics)
```

Request parameters are copied and redacted. Retrieval time records when Persistra observed
the response; it is not substituted for an absent provider event time.
