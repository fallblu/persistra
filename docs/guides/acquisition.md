# Acquire data

Use `AlphaVantageClient` for supported primary market datasets and `FredClient` for focused
FRED and ALFRED series acquisition. Both clients return normalized model objects and never
write to a `DuckDBStore`; acquisition and persistence remain separate decisions.

All examples on this page make network requests unless they use `offline=True` and a cached
response already exists.

## Import caller-owned files

Use `LocalDataAdapter` to turn a complete CSV, Arrow IPC, or Parquet file into the same
normalized result models returned by provider clients. Declare the target family, every source
column, and the semantics that cannot be inferred safely from rows:

```python
from persistra.data import LocalDataAdapter, LocalFamily, LocalImportSpec

columns = {
    "series_id": "series_id",
    "provider": "provider",
    "provider_series": "provider_series",
    "series_kind": "series_kind",
    "frequency": "frequency",
    "period_label": "period_label",
    "period_start": "period_start",
    "period_end": "period_end",
    "value": "value",
    "unit": "unit",
    "geography": "geography",
    "seasonal_adjustment": "seasonal_adjustment",
    "maturity": "maturity",
    "provider_as_of": "provider_as_of",
}
spec = LocalImportSpec(
    family=LocalFamily.SERIES,
    columns=columns,
    semantics={
        "provider": "internal",
        "series_id": "series_internal_gdp_monthly",
        "series_kind": "economic",
        "display_name": "Internal monthly GDP",
        "provider_series": "GDP_MONTHLY",
        "frequency": "monthly",
        "unit": "index",
        "geography": "United States",
        "seasonal_adjustment": None,
        "maturity": None,
    },
)

adapter = LocalDataAdapter()
validation = adapter.validate("exports/gdp.parquet", spec)
if validation.is_valid:
    series = adapter.import_file("exports/gdp.parquet", spec)
else:
    for finding in validation.findings:
        print(finding.code, finding.message)
```

The adapter supports bars, quotes, top of book, options, current and vintage series, vintage
dates, instrument search, market status, index catalogs, exchange rates, and commodity spot
quotes. The mapping names are the normalized schema columns except `retrieved_at`, which records
the import time. Extra source columns are ignored. Existing model contracts validate timestamp,
identity, currency, adjustment, entitlement, and dtype policies; the adapter does not guess or
fill invalid values.

`validate()` reads and constructs the result without returning or persisting it. `import_file()`
returns the normalized model and records the resolved source path, byte size, modification time,
SHA-256 checksum, column mapping, caller semantics, and import time in its provenance. This makes
an exported Parquet or Arrow dataset importable again with an explicit mapping while retaining
the identity of the exact bytes used.

## Run resumable acquisition plans

Use an `AcquisitionPlan` when a collection of provider calls must survive interruption or partial
failure. Plans contain only portable JSON values. Provider clients and credentials stay in
caller-owned handlers:

```python
from pathlib import Path

from persistra.data import (
    AcquisitionCachePolicy,
    AcquisitionFamily,
    AcquisitionPlan,
    AcquisitionRequest,
    AcquisitionRunner,
    DuckDBStore,
    FredClient,
)

request = AcquisitionRequest(
    request_id="gdp-current",
    provider="fred",
    operation="series.latest",
    scope={"provider_series": "GDPC1"},
    parameters={"series_id": "GDPC1", "observation_start": "2020-01-01"},
    cache_policy=AcquisitionCachePolicy.OFFLINE,
    expected_family=AcquisitionFamily.SERIES,
)
plan = AcquisitionPlan("daily-macro", (request,))

fred = FredClient.from_env(cache_directory=Path("raw-cache"))

def acquire_latest(item: AcquisitionRequest):
    return fred.series.latest(**item.call_parameters)

with DuckDBStore.open("research.duckdb") as store:
    report = AcquisitionRunner(
        {("fred", "series.latest"): acquire_latest},
        "checkpoints/daily-macro.json",
        store=store,
        manifest_path="artifacts/daily-macro-acquisition.json",
    ).run(plan)

fred.close()
if not report.is_complete:
    for failure in report.failures:
        print(failure.request_id, failure.error_type, failure.message)
```

Handlers run one at a time in plan order. Provider clients therefore retain their configured rate
limit and bounded retry behavior, and Persistra does not introduce hidden concurrency. A handler
receives the complete request; `call_parameters` adds `refresh` and `offline` from the declared
cache policy. Use handler code to convert other portable strings to any provider-specific enum
types required by that operation.

Each successful request is checkpointed immediately after optional store persistence. Running the
same unchanged plan again skips checkpointed requests and retries pending failures. An interruption
propagates to the caller after retaining earlier checkpoints. A changed plan cannot reuse the old
checkpoint because the runner verifies the plan identifier and SHA-256 digest.

When a runner has a store, it resumes a success only when that success has a snapshot identifier
that the same store can load and validate. A checkpoint created without a store, or against a
different store that lacks the snapshot, causes the request to run again. Without a store, the
checkpoint remains the durable resume boundary.

The report always distinguishes successes, resumed requests, and failures instead of assembling a
silent partial dataset. When `manifest_path` is set, each completed run attempt atomically publishes
the plan, digest, store snapshot identifiers, timestamps, failures, and completeness. Serialize a
plan for review or transport with `acquisition_plan_to_json()` and restore it with
`acquisition_plan_from_json()`.

For every success, `retrieved_at` records the normalized result's retrieval time and
`completed_at` records the acquisition completion. Persistra enforces
`retrieved_at <= completed_at`, including when the retrieval timestamp is ahead of the runner
clock.

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

Create the economic-series client separately:

```python
from persistra.data import FredClient

fred = FredClient.from_env(timeout=30)
```

`FredClient.from_env` reads `PERSISTRA_FRED_API_KEY`. See
[Connect FRED and ALFRED](../getting-started/fred.md) for setup and client options.

Use either client as a context manager when its acquisition phase has a clear lifetime:

```python
with AlphaVantageClient.from_env() as client:
    status = client.reference.market_status()
```

`close()` is idempotent. Persistra closes the HTTP session it creates, while a session passed by
the caller remains caller-owned. Provider namespaces reject new work after the client closes.
For direct `TokenRateLimiter` use, `capacity` is measured in one-request tokens and must be at
least one; `requests_per_minute` and `capacity` must both be finite.

Retryable transport failures remain bounded by the configured retry count. For HTTP 429 and 5xx
responses, Persistra honors valid delta-second or HTTP-date `Retry-After` values up to one minute
and combines them with local backoff and jitter. Malformed, negative, or longer guidance is
ignored rather than causing an unbounded sleep.

## Acquire FRED definitions and current observations

Retrieve the source definition directly when you need its identity, native frequency, units,
or seasonal adjustment:

```python
definition = fred.series.definition("GDPC1")
```

Retrieve current source levels as a `SeriesSet`:

```python
from datetime import date

gdp = fred.series.latest(
    "GDPC1",
    observation_start=date(2020, 1, 1),
)
```

Observation bounds are inclusive. The adapter does not expose FRED's transformations or
frequency aggregation, so the definition and rows retain the source frequency and units. FRED
observations whose value is `"."` remain dated rows with a missing numeric value. A missing
latest value is not a deletion.

## Discover FRED series and release context

Search for series without constructing observations:

```python
matches = fred.discovery.search(
    "consumer price index",
    tag_names=("usa",),
    exclude_tag_names=("discontinued",),
)
```

The search result preserves provider order, source identifiers, frequency, units, observation
bounds, popularity, and update time. Use `search_type="series_id"` for identifier substring
matching. Included tags are joined with FRED's semicolon convention; excluded tags require at
least one included tag, matching the provider contract.

After selecting a provider series, retrieve its categories, owning release, and tags:

```python
categories = fred.discovery.categories("CPIAUCSL")
release = fred.discovery.release("CPIAUCSL")
tags = fred.discovery.tags("CPIAUCSL")
```

These immutable discovery results carry `ResultMetadata` but remain separate from `SeriesSet` and
`VintageSeriesSet`. Pagination, raw caching, offline replay, normalized errors, and schema-drift
diagnostics use the same transport policy as observation acquisition.

## Acquire ALFRED revisions

Retrieve a bounded or open-ended real-time history as a `VintageSeriesSet`:

```python
history = fred.series.vintages(
    "GDPC1",
    realtime_start="2019-01-01",
    realtime_end="2020-12-31",
    observation_start="2018-01-01",
)

open_history = fred.series.vintages(
    "GDPC1",
    realtime_start="2019-01-01",
)
```

An omitted real-time end requests the provider's open-ended interval. Explicit historical
views use `vintage_dates` instead of real-time bounds:

```python
selected = fred.series.vintages(
    "GDPC1",
    vintage_dates=["2020-01-30", "2020-04-29"],
)
```

List the dates on which a series added or revised observations:

```python
changes = fred.series.vintage_dates(
    "GDPC1",
    realtime_start="2020-01-01",
    realtime_end="2020-12-31",
)
```

Observation pages and vintage-date pages are followed automatically. Multiple changes cannot
be distinguished below the provider's daily boundary. Exact duplicate rows collapse, while
conflicting rows on the same observation and daily boundary fail validation.

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

Every provider acquisition method accepts `refresh` and `offline` keyword arguments:

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

Request parameters are recursively copied and frozen. Persistra removes case-insensitive
`api_key` and `apikey` fields from mappings at every nesting depth, including mappings inside
sequences. Parameters may contain only strings, integers, finite floats, booleans, nulls,
string-keyed mappings, and sequences. Retrieval time records when Persistra observed the
response; it is not substituted for an absent provider event time.
