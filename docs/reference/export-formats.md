# Portable export formats

`project.services.results.exports.create(run, destination, export_format=...)` writes a
closed portable export. Select one of three formats.

All formats use manifest format version 2 and the current database schema version.
Each table has a row count and a content identity. Normalized values give the content
identity.

## DuckDB (`duckdb`, default)

One `.duckdb` file contains the 21 normalized result tables. It also contains the
`_persistra_export_manifest` table. This table contains the manifest JSON and its
content ID.

Verification makes sure that these conditions are true:

- The file contains only the specified tables.
- The file does not contain views.
- The manifest is unique.
- Each row count is correct.
- Each table content identity is correct.

## Parquet / CSV bundles (`parquet`, `csv`)

A directory contains one file for each table and one `manifest.json` file. The bundle
manifest adds its content ID to the semantic manifest.

The bundle manifest also contains a closed file list. Each list item has a name, SHA-256
checksum, and byte count.

Verification makes sure that these conditions are true:

- Each file name is a safe, relative, single-segment name.
- The directory contains only the specified files.
- Each file checksum is correct.
- The manifest identity is correct.

## Reading exports

```python
from persistra.results import open_export

handle = open_export("/path/to/export.duckdb")
summary = handle.summary()
equity = handle.equity(max_rows=100_000)
```

`open_export` verifies the manifest and each table before it returns. After the first
verification, the handle trusts the table checksum for the rest of its life.

A bounded query raises an error when a table is larger than `max_rows`. It does not
truncate the table. The dashboard portable-export source uses the same reader.

Persistra supports only the current export format version. Create new exports to replace
earlier prerelease exports.
