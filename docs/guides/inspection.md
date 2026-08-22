# Inspect local stores

List local stores from the base installation without Panel or a browser:

```console
uv run persistra inspect . --list
uv run persistra inspect . --list --json
```

List mode uses the same direct or `--recursive` discovery rules as the browser inspector. Human
output writes the project identity, store paths and schema versions, and each dataset's family,
scope, snapshot count, time bounds, and latest snapshot ID to stdout. Discovery warnings go to
stderr. The command returns 0 after inspecting at least one supported store and 1 when discovery
completes without one. Invalid directories and other operational failures return 2.

JSON output stays machine-readable on stdout and includes warnings instead of copying them to
stderr. Its version 1 contract is:

| Field | Value |
|---|---|
| `inventory_version` | Integer `1` |
| `directory` | Absolute inspected directory path |
| `project` | `null` or an object with `name` and `format_version` |
| `warnings` | Ordered discovery warning strings |
| `store_count` | Number of supported stores |
| `stores` | Ordered store objects with absolute `path`, `schema_version`, `dataset_count`, and `datasets` |
| `datasets` | Ordered objects with `family`, `scope_key`, `snapshot_count`, ISO 8601 `first_seen` and `last_seen`, and `latest_snapshot_id` |

`--port` and `--no-open` are server-only options and produce a usage error when combined with
`--list`. `--json` requires `--list`.

Install the optional browser inspector when you want to examine local Persistra stores interactively:

```console
uv add "persistra[inspect]"
```

Start the inspector with an explicit directory:

```console
uv run persistra inspect .
```

The command starts a local Panel application on `127.0.0.1`. By default, the operating system
assigns the port when the server binds, and the command prints the final URL before opening your
browser. Use `--no-open` to suppress the browser, `--port PORT` to require one explicit port, or
`--recursive` to include descendant directories. An occupied explicit port produces an error;
the inspector never silently switches to another port. Recursive discovery does not follow
directory symlinks. It reports inaccessible descendants as warnings while continuing through
independent readable subtrees. If no supported store remains, the final error includes those
traversal warnings.

Without `--recursive`, discovery checks only regular `*.duckdb` files directly inside the
supplied directory. It ignores unrelated files. It reports invalid or unsupported database
candidates as warnings and continues when another supported store is available.

A valid `persistra.toml` adds the [project](projects.md) name and format version to the Overview.
An invalid project manifest produces a warning when a supported store remains available. Project
metadata never expands discovery outside the supplied directory.

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
its identity. Changing a store, family, or scope recomputes every downstream choice together.
The inspector preserves a selection only when it belongs to the complete new context, and it
verifies the selected snapshot against that family and scope before loading it.

Filesystem paths remain `Path` values inside the read-only inspection model. The Panel adapter
converts them to display strings on a copy of table data before it creates browser data sources.
This keeps filesystem access typed without sending nonserializable path objects to Bokeh.

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

Each browser session receives a new view model, widget set, and template. Selections in one tab
do not affect another tab, and the template applies the `theme` query argument independently for
each request.

The application does not inspect research manifests, Trading Engine bundles, or unrelated
files. A store that disappears or changes while selected produces an actionable view error and
does not terminate inspection of other stores.
