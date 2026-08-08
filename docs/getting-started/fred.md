# Connect FRED and ALFRED

Persistra uses one focused client for current FRED observations and ALFRED revision history.
The adapter covers series definitions, source-level observations, revision intervals, and
series vintage dates. It does not wrap categories, releases, tags, maps, provider
transformations, or frequency aggregation.

## Set the API key

Create a FRED API key, then put it in the environment variable read by
`FredClient.from_env`:

```bash
export PERSISTRA_FRED_API_KEY="your-key"
```

Create the client without putting the secret in application code:

```python
from persistra.data import FredClient

client = FredClient.from_env()
```

Persistra removes both `api_key` and `apikey` spellings from normalized metadata, raw-cache
documents, and cache identities. It never includes the key in provider exceptions or debug
logs. Keep environment variables and shell output private.

## Retrieve current observations

Use the provider series ID. Persistra first retrieves the series definition so the result
keeps the source frequency, units, and seasonal adjustment:

```python
from datetime import date

gdp = client.series.latest(
    "GDPC1",
    observation_start=date(2020, 1, 1),
)

print(gdp.definition)
print(gdp.frame.tail())
```

The result is a `SeriesSet`. Provider sentinel values are omitted because its `value` column
contains finite observations. Persistra does not request a transformation or lower-frequency
aggregation.

## Retrieve revision history

ALFRED real-time bounds describe when source versions applied. An omitted `realtime_end`
requests the open-ended history:

```python
history = client.series.vintages(
    "GDPC1",
    realtime_start=date(2019, 1, 1),
    observation_start=date(2018, 1, 1),
)
```

The returned `VintageSeriesSet` uses inclusive daily `available_from` and
`available_through` intervals. The provider's `9999-12-31` sentinel becomes a missing
`available_through`. A provider missing-value sentinel becomes a row with a missing value and
`is_deleted=True` so a historical coverage change remains visible.

Ask for selected historical views with explicit vintage dates instead:

```python
selected = client.series.vintages(
    "GDPC1",
    vintage_dates=[date(2020, 1, 30), date(2020, 4, 29)],
)
```

Explicit dates and real-time bounds are mutually exclusive. JSON requests accept at most
2,000 explicit vintage dates.

## List change dates

```python
changes = client.series.vintage_dates(
    "GDPC1",
    realtime_start="2020-01-01",
    realtime_end="2020-12-31",
)

print(changes.dates)
print(changes.metadata.cache_status)
```

`VintageDatesResult` retains the provider series key, sorted unique dates, and acquisition
provenance.

## Configure and work offline

```python
from datetime import timedelta
from pathlib import Path

client = FredClient.from_env(
    cache_directory=Path(".cache/persistra"),
    timeout=30,
    strict_schema=False,
    cache_ages={"series_observations": timedelta(hours=6)},
)
```

The operation keys are `series`, `series_observations`, and `series_vintagedates`. Every
method accepts `refresh` and `offline`. Paginated responses are cached one page at a time, so
an offline call succeeds only when the definition and every page for the exact query exist.

Continue with [Acquire data](../guides/acquisition.md),
[Work offline and manage the cache](../guides/cache-offline.md), or
[Store and query results](../guides/storage.md).
