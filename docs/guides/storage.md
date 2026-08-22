# Store and query results

`DuckDBStore` persists validated acquisition snapshots and cumulative research datasets. It
opens one explicit DuckDB connection and is intended for one-process use.

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
database in place. Acquisition occurrence history requires store schema version 3; create a new
store instead of reusing an earlier-version file.

## Verify complete store integrity

`open` checks the schema version needed for normal operations. Use `verify_store` for a complete
read-only audit before archival, transfer, or incident diagnosis:

```python
from persistra.data import verify_store

verification = verify_store("research.duckdb")
for finding in verification.findings:
    print(finding.code, finding.message)

if not verification.is_valid:
    raise RuntimeError("store integrity verification failed")
```

The verifier opens DuckDB in read-only mode. It checks required tables, columns, keys, references,
and the supported schema version. It then recomputes every content hash and snapshot ID, decodes
every family at every acquisition occurrence, checks retrieval chronology and snapshot inventory,
and reconciles bar, scalar-series, and vintage-series payloads with their typed cumulative rows.
It never repairs, migrates, or rewrites the database.

`StoreVerification.to_dict()` returns `verification_version = 1`, the absolute store path,
validity, snapshot and occurrence counts when schema inspection succeeds, and ordered findings.
All current store findings have error severity. Codes use these stable categories:

| Codes | Meaning |
|---|---|
| `store.path.missing`, `store.open.invalid` | The requested path is absent or is not a readable DuckDB database. |
| `store.schema.missing`, `store.schema.shape`, `store.schema.constraints` | A required schema object or contract is absent or changed. |
| `store.schema.version`, `store.schema.version_unsupported` | The version inventory is malformed or unsupported. |
| `store.inventory.order`, `store.reference.orphan` | Global occurrence order or a foreign reference is inconsistent. |
| `store.snapshot.occurrence_missing`, `store.snapshot.hash`, `store.snapshot.identity` | Snapshot inventory, content identity, or occurrence ownership is inconsistent. |
| `store.snapshot.payload`, `store.snapshot.family`, `store.snapshot.scope` | A stored payload cannot reproduce its declared family or scope. |
| `store.occurrence.decode`, `store.occurrence.chronology` | Occurrence metadata cannot decode or disagrees with retrieval chronology. |
| `store.rows.orphan`, `store.rows.family`, `store.rows.mismatch` | Typed rows are orphaned, stored in the wrong family table, or differ from the payload. |
| `store.audit.failed` | An unexpected database failure prevented the audit from completing. |

Use `list_datasets`, `list_snapshots`, and `load_snapshot` for generic read-only inspection.
These methods expose immutable dataset and snapshot identities without requiring callers to
query private DuckDB tables. The [local inspector](inspection.md) uses only this public API.

Each save records an acquisition occurrence even when its normalized content matches an existing
snapshot. Snapshots deduplicate immutable content; `snapshot_count` therefore counts distinct
contents, while `first_seen` and `last_seen` cover all linked occurrences. Latest loads and
cumulative row revisions follow retrieval time, with save order breaking equal-time ties.
`StoredSnapshot.saved_order` records when distinct content first entered the store, while snapshot
lists follow each content's most recent occurrence. `load_snapshot` returns the content with its
earliest observed acquisition provenance.

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

Saving an unsupported object raises `TypeError`.

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

Quote and top-of-book loads use the exact symbol batch scope and order used at save time. Every
load method returns one exact acquisition snapshot. It does not combine partial downloads.
Load methods return `None` when the scope has no stored snapshot.

## Query bars inside DuckDB

`query_bars` combines every retained partial download for one instrument. For each bar identity,
it returns the row from the latest acquisition that contained that identity. Interval and
temporal filters are inclusive:

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
Use `date` bounds for daily rows and timezone-aware `datetime` bounds for intraday rows. Mixed
bound types and naive datetimes are rejected.

This lets separate intervals or date windows form one research dataset without making an
acquisition snapshot pretend to be complete. A later overlapping row supersedes the earlier
row; nonoverlapping rows remain available. Use `load_bars` when the exact latest provider result
is required instead.

## Query scalar series

Period-label filters are inclusive and applied inside DuckDB. Separate retained period ranges
accumulate under the series identity, and a later observation of the same normalized row
supersedes its earlier value:

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
`available_from`. Separate retained observation ranges and newly observed provider versions
accumulate. If Persistra observes the same provider-version identity again, the latest retained
row wins. `load_vintage_series` still returns one exact acquisition snapshot.

## Page cumulative queries

Use the page variants when a cumulative result may be too large to materialize in application
memory or send to a browser. `query_bars_page`, `query_series_page`, and
`query_vintage_series_page` apply their family filters and sorting inside DuckDB:

```python
with DuckDBStore.open("research.duckdb", read_only=True) as store:
    page = store.query_bars_page(
        bars.instrument.instrument_id,
        interval="daily",
        limit=100,
        offset=0,
        sort_by="close",
        descending=True,
    )

print(page.total_count)
print(page.frame)
```

`StoredPage.frame` contains at most `limit` rows. `total_count` is the exact count after filters,
while `has_previous` and `has_next` support explicit navigation. Limits must be between 1 and
1,000, offsets must be nonnegative, and sort columns are restricted to the normalized schema.
Every order adds the dataset identity columns as deterministic tie-breakers, so adjacent pages do
not overlap or drift while the store remains unchanged. An offset beyond the final row returns an
empty typed frame and preserves the exact total.

The non-page query methods remain useful when callers intentionally need the complete cumulative
frame. Both forms use the same latest-observed row-revision and point-in-time cutoff rules.

## Reconstruct what Persistra had observed

Changed values create a new retrieval-time revision. Pass a timezone-aware
`retrieved_before` value to reconstruct the retained state at or before that time:

```python
from datetime import UTC, datetime

cutoff = datetime(2025, 2, 1, tzinfo=UTC)

with DuckDBStore.open("research.duckdb", read_only=True) as store:
    historical_snapshot = store.load_bars(
        bars.instrument.instrument_id,
        retrieved_before=cutoff,
    )
    historical_dataset = store.query_bars(
        bars.instrument.instrument_id,
        retrieved_before=cutoff,
    )
```

The load selects one exact snapshot. The query chooses the latest eligible revision of every
retained row and keeps nonoverlapping rows from earlier partial acquisitions. Both are records
of what Persistra had observed, not claims that the provider offered point-in-time or unrevised
historical data. Naive cutoffs are rejected.

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
