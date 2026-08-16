# Inspect local stores

Install the optional browser inspector when you want to examine local Persistra stores:

```console
uv add "persistra[inspect]"
```

Start the inspector with an explicit directory:

```console
uv run persistra inspect .
```

The command starts a local Panel application on `127.0.0.1`, chooses an available port, and
opens your browser. Use `--no-open` to suppress the browser, `--port PORT` to select a port, or
`--recursive` to include descendant directories. Recursive discovery does not follow directory
symlinks.

Without `--recursive`, discovery checks only regular `*.duckdb` files directly inside the
supplied directory. It ignores unrelated files. It reports invalid or unsupported database
candidates as warnings and continues when another supported store is available.

## Navigate stored data

The sidebar follows this hierarchy:

```text
Directory
  Store
    Family
      Dataset scope
```

The Overview view labels the current data as an exact snapshot or cumulative retained data.
The Data view provides read-only paginated, sortable, and filterable tables. Provenance lists
every `ResultMetadata` field. Snapshot history lets you select an exact saved acquisition by
its identity.

Bars, scalar series, and option chains include the applicable Persistra Matplotlib views.
Quotes, top of book, vintage series, reference results, and scalar quotes are table-only in
this release. Visualization errors remain local to the selected view.

## Keep exact and cumulative data distinct

An exact snapshot is one normalized provider response with one provenance record. Snapshot
history always loads the selected snapshot by ID.

Bars, scalar series, and vintage series also offer cumulative mode. That mode combines the
latest retained revision of each stored row across acquisitions. It is tabular and never uses
one snapshot's metadata to describe the combined rows. See [Store and query results](storage.md)
for the cumulative query rules.

## Understand the safety boundary

The inspector opens every store read-only. It cannot acquire data, edit cells, execute SQL,
export data, repair a database, or run Trading Engine. It binds only to the loopback interface
and does not expose arbitrary filesystem paths as static content.

The application does not inspect research manifests, Trading Engine bundles, or unrelated
files. A store that disappears or changes while selected produces an actionable view error and
does not terminate inspection of other stores.
