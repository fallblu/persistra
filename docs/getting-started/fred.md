# Connect FRED and ALFRED

Use FRED for current economic observations and ALFRED for revision history. Revision-aware inputs
are especially important for strategies whose historical signals must reflect only information
available at the decision time.

## Configure the client

```bash
export PERSISTRA_FRED_API_KEY="your-key"
```

```python
from persistra.data import FredClient

client = FredClient.from_env()
```

Persistra removes `api_key` and `apikey` from normalized metadata, raw-cache documents, cache
identities, provider exceptions, and debug logs. Keep environment variables and cache files
private.

## Discover a series

Search FRED before choosing a provider series identifier:

```python
matches = client.discovery.search(
    "real gross domestic product",
    tag_names=("usa",),
)

for item in matches.series:
    print(item.provider_series, item.frequency, item.units)
```

`full_text` search is the default. Pass `search_type="series_id"` for provider-identifier
substring search. Search results are source summaries with their own acquisition metadata; they
are not scalar observations and do not establish canonical instrument identity.

Inspect the selected series' source context separately:

```python
categories = client.discovery.categories("GDPC1")
release = client.discovery.release("GDPC1")
tags = client.discovery.tags("GDPC1")
```

These methods expose the supported FRED `series/categories`, `series/release`, and `series/tags`
endpoints. Search and tag pages are followed automatically. Every result retains exact request,
retrieval, cache, and schema-diagnostic provenance.

## Retrieve current observations

```python
from datetime import date

latest = client.series.latest(
    "GDPC1",
    observation_start=date(2020, 1, 1),
)

print(latest.definition)
print(latest.frame.tail())
```

The returned `SeriesSet` retains source frequency, units, seasonal adjustment, identity, and
acquisition metadata. Persistra does not request provider transformations or aggregation.

## Retrieve point-in-time revisions

```python
history = client.series.vintages(
    "GDPC1",
    realtime_start=date(2019, 1, 1),
    observation_start=date(2018, 1, 1),
)
```

`VintageSeriesSet` records inclusive `available_from` and `available_through` intervals. A
deleted historical observation remains visible as a missing value with `is_deleted=True`.
Select the version known at each strategy decision before calculating growth, surprises, or
other features.

Explicit vintage dates are useful for fixed research snapshots:

```python
selected = client.series.vintages(
    "GDPC1",
    vintage_dates=[date(2020, 1, 30), date(2020, 4, 29)],
)
```

Explicit dates and real-time bounds are mutually exclusive.

## Work repeatably

```python
from datetime import timedelta
from pathlib import Path

client = FredClient.from_env(
    cache_directory=Path(".cache/persistra"),
    timeout=30,
    strict_schema=False,
    cache_ages={
        "series_search": timedelta(hours=6),
        "series_observations": timedelta(hours=6),
    },
)
```

Every method accepts `refresh` and `offline`. Paginated responses are cached one page at a time,
so an offline request succeeds only when every page for the exact query is present.

Continue with [Build point-in-time datasets](../guides/research.md),
[Time and provenance](../concepts/time-provenance.md), or the
[data and feature examples](../examples/data-and-features.md).
