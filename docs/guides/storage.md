# Store and query results

`DuckDBStore` persists validated normalized results with retrieval-time revisions. It opens
one explicit DuckDB connection and is intended for one-process use.

Acquisition never writes to the store automatically. This lets you inspect, reject, or
transform a provider result before deciding which normalized source observations to retain.

## Create a new store

```python
from pathlib import Path

from persistra.data import DuckDBStore

store = DuckDBStore.create(Path("research.duckdb"))
store.close()
```

`create` requires an absent path and creates parent directories when needed. It refuses to
replace an existing file. Prefer a context manager so the connection closes on every path:

```python
from persistra.data import DuckDBStore, synthetic

bars = synthetic.bars("DEMO", periods=30)

with DuckDBStore.create("research.duckdb") as store:
    snapshot_id = store.save(bars)
    print(snapshot_id)
```

## Open an existing store

```python
with DuckDBStore.open("research.duckdb") as store:
    restored = store.load_bars(bars.instrument.instrument_id)
```

Use a read-only connection when no writes are needed:

```python
with DuckDBStore.open("research.duckdb", read_only=True) as store:
    restored = store.load_bars(bars.instrument.instrument_id)
```

Opening validates the store schema version. Persistra does not migrate an unsupported
database in place.

## Save supported result families

`save` validates and encodes one normalized result. It supports bars, quotes, top of book,
exchange-rate quotes, commodity spot quotes, option chains, scalar series, vintage series,
market status, symbol search, and index catalogs.

```python
from persistra.data import synthetic

results = [
    synthetic.bars("DEMO"),
    synthetic.quotes(("AAA", "BBB")),
    synthetic.top_of_book(("AAA", "BBB")),
    synthetic.option_chain("DEMO"),
    synthetic.series("CPI"),
    synthetic.vintage_series("GDP"),
    synthetic.exchange_rate("EUR", "USD"),
    synthetic.commodity_spot("gold"),
    synthetic.search("DEMO"),
    synthetic.market_status(),
    synthetic.index_catalog(),
]

with DuckDBStore.create("all-results.duckdb") as store:
    snapshot_ids = [store.save(result) for result in results]
```

Saving an unsupported object raises `StoreError`.

## Load by exact scope

Each result family has an explicit load method:

```python
with DuckDBStore.open("all-results.duckdb") as store:
    loaded_bars = store.load_bars(results[0].instrument.instrument_id)
    loaded_quotes = store.load_quotes(("AAA", "BBB"))
    loaded_options = store.load_options(
        results[3].underlying_instrument_id,
        results[3].chain_date,
    )
    loaded_series = store.load_series(results[4].definition.series_id)
    loaded_vintages = store.load_vintage_series(results[5].definition.series_id)
```

Quote and top-of-book loads use the exact symbol batch scope and order used at save time.
Load methods return `None` when the scope has no stored snapshot.

## Query bars inside DuckDB

`query_bars` filters the latest selected snapshot by interval and inclusive temporal bounds:

```python
from datetime import date

with DuckDBStore.open("research.duckdb") as store:
    frame = store.query_bars(
        bars.instrument.instrument_id,
        interval="daily",
        start=date(2025, 1, 10),
        end=date(2025, 1, 20),
    )

print(frame[["date", "close"]])
```

The method returns an empty frame with the exact bar dtypes when nothing matches.

## Query scalar series

Period-label filters are inclusive and applied inside DuckDB:

```python
series = synthetic.series("CPI", periods=24)

with DuckDBStore.create("series.duckdb") as store:
    store.save(series)
    frame = store.query_series(
        series.definition.series_id,
        start_label="2024-06",
        end_label="2025-01",
    )

print(frame[["period_label", "value"]])
```

Use source-native period labels. Persistra does not reinterpret or coerce their frequency.

## Query a provider-native revision history

`query_vintage_series` filters period labels and can select the version available on an
explicit date:

```python
from datetime import date

history = synthetic.vintage_series("GDP", periods=24)

with DuckDBStore.create("vintages.duckdb") as store:
    store.save(history)
    point_in_time = store.query_vintage_series(
        history.definition.series_id,
        start_label="2023-01-01",
        end_label="2023-12-01",
        available_on=date(2024, 1, 15),
    )
```

Availability bounds are inclusive. A missing `available_through` remains applicable after
`available_from`. The query filters one stored acquisition snapshot; it does not combine
separate retrieval-time snapshots.

## Reconstruct what Persistra had observed

Changed values create a new retrieval-time revision. Pass a timezone-aware
`retrieved_before` value to select the latest snapshot first seen at or before that time:

```python
from datetime import UTC, datetime

cutoff = datetime(2025, 2, 1, tzinfo=UTC)

with DuckDBStore.open("research.duckdb", read_only=True) as store:
    historical = store.load_bars(
        bars.instrument.instrument_id,
        retrieved_before=cutoff,
    )
```

This is a record of what Persistra had observed, not a claim that the provider offered a
point-in-time or unrevised historical dataset. Naive cutoffs are rejected.

Repeated identical content reuses its content-derived snapshot ID and updates `last_seen`.
Changed content creates another snapshot with a new `first_seen` time.

## Inspect a stored payload

`latest_payload` returns a decoded copy for research diagnostics:

```python
with DuckDBStore.open("research.duckdb", read_only=True) as store:
    payload = store.latest_payload(
        "bars",
        bars.instrument.instrument_id,
    )

if payload is not None:
    print(payload.keys())
```

Prefer typed load and query methods in application code. The payload method exposes the
serialized representation and is intentionally lower level.

## Handle store lifecycle safely

- Use one context manager per unit of work.
- Do not share a store connection across processes.
- Open read-only for reporting jobs that do not save results.
- Keep raw provider caches separate from normalized database files.
- Back up the database as ordinary research data; the library does not manage backups.
- Treat unsupported schema errors as a signal to create a new database for the current
  version.
