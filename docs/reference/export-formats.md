# Portable export formats

`project.services.results.exports.create(run, destination, export_format=...)` writes a
dependency-closed portable export in one of three formats. All formats share manifest
format version 2 and the current database schema version, and every table carries a
row count and a content identity computed from its normalized values.

## DuckDB (`duckdb`, default)

One `.duckdb` file containing the 21 normalized result tables plus a
`_persistra_export_manifest` table holding the manifest JSON and its content id.
Verification enforces exact table closure (no extra tables, no views), manifest
uniqueness, per-table row counts, and per-table content identities.

## Parquet / CSV bundles (`parquet`, `csv`)

A directory containing one file per table plus `manifest.json`. The bundle manifest
extends the semantic manifest with its own content id and a closed file list
(name, sha256, byte count). Verification enforces safe relative single-segment file
names, exact file closure, per-file checksums, and the manifest identity.

## Reading exports

```python
from persistra.results import open_export

handle = open_export("/path/to/export.duckdb")
summary = handle.summary()
equity = handle.equity(max_rows=100_000)
```

`open_export` verifies the manifest and every table before returning; each table's
content checksum is trusted for the remaining lifetime of the handle. Bounded queries
raise rather than truncate when a table exceeds `max_rows`. The dashboard's
portable-export source uses this same reader.

Only the current export format version is supported; earlier pre-release exports are
disposable and should be regenerated.
