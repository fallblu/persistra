# Focused specification 02: project configuration and database lifecycle

**Status:** Implementation-ready draft  
**Umbrella:** [`../v3-spec.md`](../v3-spec.md)  
**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md)  
**Owners:** `persistra.project`, `persistra.config`, `persistra.db`, `persistra.cli`  
**Required before:** focused specifications 03–18  
**Last reviewed:** 2026-07-15

## 1. Purpose

This specification defines the Persistra project boundary and the complete managed
DuckDB lifecycle. It fixes configuration discovery and resolution, optional workspace
layout, database roles and bootstrap metadata, connection ownership, read-only
attachments, Linux shared/exclusive leases, verified physical backups and snapshot
copies, forward schema migrations, inspection, and failure recovery.

The goal is an empty but operational v3 foundation: public APIs and CLI commands can
initialize, create, open, inspect, lease, verify, copy, migrate, and close a project
without exposing raw managed connections or relying on a server.

## 2. Scope and boundaries

### 2.1 In scope

- `persistra.toml` schema, discovery, strict parsing, and path substitution
- Immutable resolved configuration and explicit Python overrides
- Optional project state-directory layout and initialization
- Market and research database roles and reserved schemas
- Project open modes, service lifetime, transactions, and thread ownership
- Read-only market database attachment to a project connection
- Linux `flock`-based application leases with actionable owner metadata
- Local-filesystem checks for active read-write databases
- Verified backup and immutable market snapshot-copy protocols
- Schema metadata, forward migrations, compatibility checks, and verified copy migration
- Database inspection, operational diagnostics, structured lifecycle events, and CLI
- Typed errors, stable reason codes, crash cleanup, and acceptance tests

### 2.2 Out of scope

- Canonical dataset catalog, ingestion batches, quarantine, and logical snapshots
- Market/reference-data schemas and point-in-time query APIs
- Workspace SQL lineage and research materializations
- Study worker scheduling and transactional result merge
- Run deletion, portable run exports, and export-format compatibility
- Dashboard pages and report generation
- Generic database backends, remote services, or shared multi-user operation
- Automatic cloud sync, replication, or network-filesystem correctness

Logical market snapshots are defined by focused specification 03. This plan only defines
how a physical copy pins and verifies one of those snapshot identities.

## 3. Normative decisions

1. DuckDB is the only managed database engine.
2. A `Project` owns every managed connection and lease it opens.
3. One `Project` is synchronous, bound to its creating thread, and not reusable after
   close.
4. Research writes and market writes use distinct open modes and never share a connection.
5. Market databases are attached read-only to research connections under stable logical
   aliases.
6. Every managed database access holds an application lease in addition to DuckDB's lock.
7. Active read-write database files must reside on a supported local filesystem.
8. Migration never occurs implicitly during ordinary `Project.open()`.
9. Supported migrations are forward-only and verified-backup-first by default.
10. Physical backup and snapshot-copy publication is atomic at the destination path.
11. A logical snapshot ID never bypasses file locking; concurrency uses a verified
    physical copy.
12. No public API returns the raw DuckDB connection.

## 4. Package and identity surface

The initial implementation boundary is:

```text
src/persistra/
├── project.py
├── config/
│   ├── __init__.py
│   ├── loading.py
│   └── models.py
├── db/
│   ├── __init__.py
│   ├── connection.py
│   ├── inspection.py
│   ├── leases.py
│   ├── copies.py
│   ├── migrations.py
│   └── migration_steps/
└── cli/
    ├── main.py
    └── db.py
```

This plan adds these typed UUID identities under the rules of focused specification 01:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `ProjectId` | `project` | One initialized project |
| `DatabaseId` | `database` | One managed database lineage |
| `LeaseId` | `lease` | One process-level lease acquisition |
| `CopyId` | `copy` | One verified physical-copy operation |

Copying a database preserves `DatabaseId` because the destination is a physical image of
the same database lineage. A writable restore or fork must allocate a new `DatabaseId`
and record the source copy in lineage metadata. File paths, inode numbers, project names,
and DuckDB catalog names are never database identities.

`DatabaseName` is a frozen validated string value using the grammar in section 6.2.
`DatabaseSelector` is the tagged union `ResearchDatabase | MarketDatabase(DatabaseName) |`
`PathDatabase(Path)`; the path form is accepted only by explicit maintenance APIs and
still requires managed bootstrap metadata.

## 5. Public API

Top-level `persistra` exports `Project`. Supporting immutable types are exported from
`persistra.config` and `persistra.db`:

```python no-run
class Project:
    @classmethod
    def init(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        create_research_database: bool = True,
    ) -> ProjectLayout: ...

    @classmethod
    def open(
        cls,
        path: str | Path = ".",
        *,
        mode: ProjectMode = ProjectMode.RESEARCH_WRITE,
        writable_market: DatabaseName | None = None,
        maintenance_database: DatabaseSelector | None = None,
        maintenance_intent: MaintenanceIntent | None = None,
        overrides: ProjectOverrides | None = None,
        allow_verified_remote_read: bool = False,
        wait_timeout: Duration = Duration(0),
        clock: Clock = SystemClock(),
    ) -> Self: ...

    @property
    def config(self) -> ResolvedProjectConfig: ...

    @property
    def services(self) -> ProjectServices: ...

    def inspect(self) -> ProjectInspection: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc_info: object) -> None: ...
```

`Project.open()` returns only after configuration, lease acquisition, compatibility
checks, connection creation, attachment, and service construction all succeed. A partial
open releases connections and leases in reverse order before re-raising. `close()` is
idempotent. Every service method after close raises `ProjectClosedError`.

`Project.services` is a frozen namespace populated only with capabilities valid for the
open mode. It initially exposes `databases`, `transactions`, and `diagnostics`; later plans
add namespaced services. Accessing a write capability in a read-only mode raises
`CapabilityUnavailableError` with the required mode and does not attempt a lease upgrade.

`ProjectLayout` contains `project_id`, resolved root/config/state paths, optional research
database path, tuple of created paths, and `complete: bool`. `ProjectInspection` contains
only the structured fields defined in section 15.1. Neither object owns live resources.
`allow_verified_remote_read` is a per-open exception defined in section 12; it is recorded
in resolved provenance and cannot enable any write.

## 6. Configuration contract

### 6.1 Discovery

If `Project.open(path)` receives a file, it must be named `persistra.toml`. If it receives
a directory, discovery checks that directory and then each resolved parent directory for
`persistra.toml`; the nearest file wins. Discovery stops at the filesystem root. It does
not consult the current working directory after an explicit path, an environment-selected
config file, a user-global config directory, or a Git setting.

Symlinks are resolved before selecting the project root. Failure to find a config is
`ProjectConfigNotFoundError` and includes the searched directories. A config found through
a parent is recorded as the resolved project root so relative paths never depend on the
caller's working directory.

### 6.2 Exact TOML schema

The v3 schema is:

```toml
[project]
id = "project:7f22b7c8-07f8-4a4b-bab3-a6ae90c70fb4"
name = "momentum-research"
state_dir = ".persistra"

[databases.research]
path = ".persistra/research.duckdb"
disposable = false

[databases.markets.primary]
path = "${PERSISTRA_MARKET_ROOT}/us-equities.duckdb"
verify_copy_on_open = false

[paths]
artifacts = ".persistra/artifacts"
logs = ".persistra/logs"
temporary = ".persistra/tmp"

[defaults]
calendar = "persistra.calendar.xnys"
universe = "project.universe.research"
benchmark = "persistra.benchmark.sp500"
risk_free = "persistra.risk_free.usd_3m"

[resources]
threads = 4
memory_limit = "8GiB"
temporary_limit = "32GiB"

[logging]
level = "INFO"
format = "console"
```

Allowed keys and values are exact:

| Section/key | Type | Default | Constraint |
| --- | --- | --- | --- |
| `project.id` | typed `ProjectId` string | required | nonzero UUID under plan 01 |
| `project.name` | string | required | `[a-z][a-z0-9_-]{0,63}` |
| `project.state_dir` | path string | `.persistra` | path rules below |
| `databases.research.path` | path string | `<state_dir>/research.duckdb` | `.duckdb` suffix |
| `databases.research.disposable` | bool | `false` | permits explicit no-backup migration only |
| `databases.markets.<name>.path` | path string | none | unique resolved `.duckdb` path |
| `databases.markets.<name>.verify_copy_on_open` | bool | `false` | must be true for declared immutable copies |
| `paths.artifacts` | path string | `<state_dir>/artifacts` | writable in write mode |
| `paths.logs` | path string | `<state_dir>/logs` | writable in write mode |
| `paths.temporary` | path string | `<state_dir>/tmp` | supported local filesystem |
| `defaults.*` | string or absent | absent | qualified name from plan 01 |
| `resources.threads` | integer | DuckDB default | `1..1024` |
| `resources.memory_limit` | byte-size string | DuckDB default | positive |
| `resources.temporary_limit` | byte-size string | unset | positive |
| `logging.level` | string | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `logging.format` | string | `console` | `console` or `json` |

Research defaults are qualified-name references, not unversioned facts copied into a run.
Each consumer resolves the reference under its exact snapshot and records the resulting
typed ID/version in execution provenance. At consumption, the `risk_free` default must
resolve to a plan-06 fixed-tenor definition with exactly one required tenor; multi-tenor
curves require an explicit consumer selection and cannot become an ambiguous scalar default.

Market database names use `[a-z][a-z0-9_]{0,31}` and are case-sensitive after validation.
The reserved names `research`, `temp`, `system`, and `main` are invalid. At most 64 market
databases may be registered in one project.

Byte sizes use an integer followed by one of `B`, `KiB`, `MiB`, `GiB`, or `TiB`; decimal
SI suffixes and fractional quantities are rejected. Resolution checks for unsigned
64-bit overflow and passes the canonical byte count to DuckDB.

Unknown sections, unknown keys, duplicate TOML keys, wrong types, and invalid enum strings
are errors. TOML parser messages are wrapped without echoing unrelated file contents.
There is no configuration version key: within 3.x the schema evolves additively with
defaults as required by the umbrella specification.

### 6.3 Path substitution and normalization

Only fields marked as paths accept `${NAME}` substitutions, where `NAME` matches
`[A-Z_][A-Z0-9_]*`. Operators such as `${NAME:-value}`, command substitution, `%VAR%`, and
bare `$NAME` are rejected. Missing or empty variables are errors. Substitution occurs once;
the resulting value is not recursively expanded.

Tilde expansion is rejected so portable configuration uses an explicit environment path.
Relative paths resolve against the directory containing `persistra.toml`. Paths are made
absolute, normalized, and resolved through existing symlink components. A path's canonical
identity is rechecked after file creation to detect a symlink swap.

The research path, every market path, artifact directory, log directory, and temporary
directory must be pairwise role-compatible. One database file cannot be registered under
two names or as both research and market. A database path cannot be a directory, and a
managed directory cannot alias the config file.

### 6.4 Immutable models and overrides

`ProjectConfig` mirrors parsed TOML. `ResolvedProjectConfig` contains only absolute paths,
canonical byte counts, validated names, and explicit defaults. Both are frozen, slotted
dataclasses with immutable mappings.

`ProjectOverrides` permits only `threads`, `memory_limit`, `temporary_limit`, `logging_level`,
the four research defaults, and path replacements for the research database, registered
market databases, artifacts, logs, and temporary directory. It cannot alter project
identity or name.
Overrides pass through the same validation, are recorded in resolved provenance, and do
not mutate either config object or process-global state.

Secrets and provider credentials have no fields in this schema. A value whose key or
location is not defined here cannot be smuggled through an `extra` mapping.

## 7. Initialization and workspace layout

`Project.init(path)` accepts a new directory or an existing project directory whose
managed destinations do not exist. Unrelated files are preserved. It creates:

```text
<path>/
├── persistra.toml
└── .persistra/
    ├── .gitignore
    ├── artifacts/
    ├── logs/
    ├── tmp/
    └── research.duckdb
```

`.persistra/.gitignore` contains `*` followed by `!.gitignore` so local databases and
artifacts are not committed accidentally. The optional code, notebook, report, strategy,
and test directories in the umbrella specification are documentation conventions and are
not created without a later template option.

Initialization writes an operation manifest in a sibling temporary directory, stages the
entire state directory there, creates and verifies the research database, and fsyncs all
content. It atomically publishes the state directory, then publishes `persistra.toml` last
as the commit marker. It refuses an existing config, state directory, or destination
database and never merges partial managed state. A handled failure removes only paths
whose identities match that invocation's manifest. If the process dies between renames,
the absence of `persistra.toml` means no valid project is exposed; a repeated init detects
the matching manifest and reports exact cleanup instructions rather than deleting
unrecognized content. There is no `force` behavior in the Python API.

Initialization allocates a new `ProjectId` and writes its typed wire form into committed
configuration. `name=None` derives a candidate from the final directory name by
lowercasing ASCII, replacing runs outside `[a-z0-9_-]` with `-`, and stripping separators.
An invalid or empty candidate requires an explicit name.

`create_research_database=False` writes configuration and directories but marks the
returned layout as incomplete; ordinary `Project.open()` then raises
`DatabaseNotFoundError` until `persistra db create --role research` succeeds. The normal
CLI default creates the database.

## 8. Database roles and bootstrap schema

### 8.1 Roles

A **market** database owns canonical observations, reference data, catalog state, quality
findings, quarantine, and logical snapshots. A **research** database owns workspace data,
research materializations, experiments, results, analyses, annotations, and artifact
manifests. Role is immutable for one `DatabaseId`.

New databases reserve these schemas:

| Role | Schemas |
| --- | --- |
| Both | `_persistra` |
| Market | `catalog`, `canonical`, `quality`, `snapshots` |
| Research | `workspace`, `research`, `experiments`, `results`, `analysis`, `annotations` |

Users cannot create objects in `_persistra` or other managed schemas through supported
SQL. Later plans may add schemas only through migration. The `workspace` schema permits
controlled materializations, not direct connection access.

Focused specification 07 uses `research` for dataset/workspace metadata, adds
`research_data` through a research-role migration for immutable dataset output relations,
and uses the existing `workspace` schema for controlled immutable workspace relations.
Neither dynamic schema exposes caller DDL or a physical-name query API.

### 8.2 Bootstrap tables

Every managed database contains exactly one row in:

```sql
CREATE TABLE _persistra.database_info (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    database_id UUID NOT NULL,
    role VARCHAR NOT NULL CHECK (role IN ('market', 'research')),
    owner_project_id UUID,
    created_at TIMESTAMPTZ NOT NULL,
    created_by_version VARCHAR NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    disposable BOOLEAN NOT NULL DEFAULT false
);
```

`owner_project_id` is required exactly when `role='research'` and must equal the resolved
configuration's `ProjectId` on ordinary project open. It is null for reusable market
databases. The bootstrap migration enforces this role-dependent invariant through its
writer and verification query because DuckDB `CHECK` behavior must remain portable across
the supported engine matrix.

Applied migrations are recorded in:

```sql
CREATE TABLE _persistra.schema_migrations (
    migration_number INTEGER PRIMARY KEY CHECK (migration_number >= 1),
    migration_name VARCHAR NOT NULL UNIQUE,
    migration_checksum VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    applied_by_version VARCHAR NOT NULL,
    backup_copy_id UUID,
    duration_us BIGINT NOT NULL CHECK (duration_us >= 0)
);
```

Writable restores and forks also record their origin in the bootstrap table:

```sql
CREATE TABLE _persistra.database_lineage (
    lineage_id UUID PRIMARY KEY,
    parent_database_id UUID NOT NULL,
    source_copy_id UUID NOT NULL,
    relation VARCHAR NOT NULL CHECK (relation IN ('restore', 'fork')),
    recorded_at TIMESTAMPTZ NOT NULL
);
```

Both database roles persist plan-01 event envelopes in:

```sql
CREATE TABLE _persistra.domain_events (
    event_id UUID PRIMARY KEY,
    event_name VARCHAR NOT NULL,
    event_schema_version INTEGER NOT NULL CHECK (event_schema_version >= 1),
    event_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    aggregate_kind VARCHAR NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_sequence BIGINT NOT NULL CHECK (aggregate_sequence >= 1),
    correlation_id UUID,
    causation_id UUID,
    payload_content_id VARCHAR NOT NULL,
    payload_json_utf8 BLOB NOT NULL,
    UNIQUE (aggregate_kind, aggregate_id, aggregate_sequence)
);
```

`event_name` and `event_schema_version` form the plan-01 `EventType`; payload bytes follow
its registered canonical codec. This audit table is append-only and transactional with an
owning normalized change. It does not replace catalog, order, fill, journal, result, or
other authoritative domain tables. A BLOB preserves exact canonical UTF-8 JSON bytes for
content verification and unknown-version inspection instead of relying on engine JSON
reserialization.

`migration_checksum` is the canonical plan-01 `ContentId` text. The bootstrap migration is
number 1 and inserts both metadata rows in the transaction that creates all initial
schemas. `database_info.schema_version` must equal the greatest applied migration number.

A managed open validates singleton cardinality, role, database ID, monotone gap-free
migration numbers, checksums against the installed registry, and schema version before
exposing services. A file without valid metadata is unmanaged and is never adopted merely
because it has a `.duckdb` suffix.

### 8.3 Database creation

```python no-run
project.services.databases.create(
    role=DatabaseRole.MARKET,
    path=Path("/data/us-equities.duckdb"),
    disposable=False,
)
```

The service is available only from maintenance mode with
`maintenance_intent=MaintenanceIntent.CREATE`; that intent is the sole maintenance case
in which the selected target may be absent. Creation requires an exclusive lease on the
absent destination path, a supported local filesystem, and a nonexistent destination. It
builds a sibling temporary database,
applies the current role-specific migration stream, verifies metadata and expected
schemas read-only, fsyncs, and atomically renames it. It never publishes an empty or
partially migrated DuckDB file.

A research database records the opening project's ID as `owner_project_id`. A market
database records null. The service does not edit `persistra.toml`; a configured selector
must match the destination unless an explicit path selector is used by a provider or
administrative workflow.

## 9. Project modes and lifecycle

`ProjectMode` has stable values:

| Mode | Research database | Market databases | Intended use |
| --- | --- | --- | --- |
| `read_only` | shared lease, read-only | shared lease, read-only | inspection, notebooks, dashboard/export readers |
| `research_write` | exclusive lease, read-write | shared lease, read-only | features, simulations, studies coordinator, analyses |
| `market_write` | unopened | one named market under exclusive lease, read-write | ingestion and market migration |
| `maintenance` | only selected target | selected target under exclusive lease | create, backup, verify, migrate, restore |

`writable_market` is required only in `market_write`, forbidden in other modes, and must
name one configured market database. `maintenance_database` and `maintenance_intent` are
required only in `maintenance`, forbidden in other modes, and select exactly one target
and operation. `MaintenanceIntent` has stable values `create`, `inspect`, `backup`,
`snapshot_copy`, `verify_copy`, `migrate`, `restore`, and `fork`. All intents except
`create` require an existing managed target. Maintenance mode does not attach unrelated
databases or expose operations other than its declared intent.

Ordinary `read_only` and `research_write` opens acquire all configured database leases in
ascending canonical-path byte order before opening any DuckDB connection. This makes
multi-database acquisition deterministic and prevents cyclical waits. On failure, all
acquired leases are released in reverse order.

A project records its creating process ID and thread ID. Crossing a process boundary,
including use after `fork`, raises `ProjectProcessError`. Calling a connection-owning
service from another thread raises `ProjectThreadError`. Parallel work creates isolated
worker projects under the experiment plan; it does not share this object.

## 10. Connection and attachment ownership

### 10.1 Connection manager

The internal connection manager is the only code allowed to call `duckdb.connect` for a
managed file. It configures resource limits, sets UTC as the session timezone, validates
the bootstrap schema, and exposes narrow repository and parameterized-query interfaces.
It never places a connection on `Project`, `ProjectServices`, or a public result object.

Closing order is:

1. reject new operations;
2. finish or roll back the current transaction;
3. close repositories and bounded callbacks;
4. detach market databases where supported;
5. close DuckDB connections;
6. remove owner metadata and release leases; and
7. mark the project closed.

An exception during close is accumulated into `ProjectCloseError` after all remaining
resources receive a close attempt. Context-manager exit preserves the original body
exception and attaches close failures as notes rather than replacing it.

### 10.2 Attachment aliases

In `read_only` and `research_write`, the research connection is primary. Each configured
market database is attached read-only as `market_<database_name>`. The alias is generated
only from validated names and quoted as an identifier by internal helpers. User input is
never interpolated into `ATTACH` SQL.

The attachment sequence validates that every attached file reports role `market` and a
distinct configured path and `DatabaseId`. A project cannot attach the same database
lineage twice, attach its research database as market data, or mix writable and read-only
handles to one file.

Each public operation begins an explicit transaction when it needs a stable view across
queries. Services do not rely on connection-global autocommit for multi-statement state
changes. Nested public transactions are rejected; internal repositories may share the
owning transaction token.

### 10.3 SQL boundary

Public read-only SQL is added by the research dataset plan. This foundation provides no
raw SQL method. Internal SQL uses positional parameters for values and allowlisted,
quoted identifiers for managed names. Extensions are disabled unless an owning focused
specification explicitly requires and allowlists one; automatic extension installation or
network access is forbidden during database open.

## 11. Shared/exclusive lease protocol

### 11.1 Sidecar layout

For `/data/market.duckdb`, the permanent lease directory is:

```text
/data/market.duckdb.persistra-lock/
├── guard
└── owners/
    └── <typed-lease-id>.json
```

`guard` is never deleted because replacing its inode would split the lock domain. The
parent directory must permit creation of the sidecar even for read-only database users.
Administrators may pre-create it with group permissions. If sidecar coordination is not
possible, managed access fails; there is no fallback to a project-local or `/tmp` lock
that other projects might not share.

### 11.2 Kernel lock

Persistra opens `guard` with `O_CLOEXEC` and acquires Linux `fcntl.flock`:

- shared lease: `LOCK_SH | LOCK_NB`;
- exclusive lease: `LOCK_EX | LOCK_NB`.

The descriptor remains open for the lease lifetime. The kernel releases it on clean close
or process death. An in-process registry keyed by canonical database path owns one guard
descriptor and reference count, preventing `flock` conversion surprises across multiple
descriptors in one process. Reentrant acquisition of the same mode increments the count.
Any shared-to-exclusive or exclusive-to-shared conversion request raises
`LeaseUpgradeError`; callers must close and reacquire through a new project lifecycle.

### 11.3 Owner metadata

After acquiring the kernel lock and before opening DuckDB, the process atomically writes
one canonical JSON owner file containing:

- lease ID, mode, canonical database path hash, and database ID when known;
- PID, Linux process-start token from `/proc/<pid>/stat`, hostname, and creating thread;
- project ID and project name when available;
- executable basename and sanitized operation name;
- acquired UTC instant and requested timeout; and
- Persistra and Python versions.

The file contains no full command line, environment, username, credentials, SQL, or
strategy configuration. Failure to publish metadata releases the kernel lock and fails
acquisition.

Clean release removes the process's owner file before unlocking. A crash may leave stale
metadata but cannot leave the kernel lock. Only a process holding the exclusive kernel
lock may delete stale owner files, after comparing PID and process-start token where
available. There is no public force-break operation.

### 11.4 Waiting and diagnostics

The default zero timeout makes one nonblocking attempt. A positive timeout uses
`time.monotonic_ns()`, sleeps 50 ms after the first failure, doubles up to 500 ms, and
never sleeps past the deadline. It rereads owner metadata after each failure. Signal
interrupts abort without extending the deadline.

On timeout, `DatabaseLeaseConflictError` reports requested mode, logical database name,
elapsed duration, and sanitized owner records. Missing metadata is reported as an unknown
external or racing owner rather than asserting that no owner exists.

An exclusive lock is required even when DuckDB itself would permit an operation. A shared
market lease held by a study therefore blocks ingestion for the study lifetime. A research
writer blocks dashboard and notebook readers. This restriction is visible and is not
weakened to improve convenience.

## 12. Filesystem support

Before active read-write open, creation, migration, or copy publication, Persistra maps the
resolved path to the longest matching entry in `/proc/self/mountinfo`. It rejects known
remote, distributed, or userspace-network filesystems including `nfs`, `nfs4`, `cifs`,
`smb3`, `sshfs`, `fuse.sshfs`, `ceph`, `glusterfs`, and `lustre`. Unknown filesystem types
fail closed for read-write use unless added to the versioned allowlist by a release.

Supported initial local types are `ext2`, `ext3`, `ext4`, `xfs`, `btrfs`, `zfs`, `tmpfs`,
and `overlay`. `tmpfs` and `overlay` emit durability warnings. The benchmark plan may
further restrict its environment.

Read-only access to a verified immutable copy on an otherwise unsupported filesystem may
be explicitly enabled with `allow_verified_remote_read=True`. The project rehashes the
file before opening, records warning `db.storage.remote_read_only`, and never opens it
writable. Ordinary unverified remote reads fail because DuckDB and external synchronization
cannot supply the required immutability guarantee.

Mount detection, permission checks, and lease metadata are diagnostics, not a defense
against a malicious local administrator. Replacing a path or inode during an operation is
detected by comparing device, inode, size, and modification metadata at defined boundaries
and fails the operation.

## 13. Verified physical copies

### 13.1 Copy kinds and API

```python no-run
with Project.open(
    ".",
    mode=ProjectMode.MAINTENANCE,
    maintenance_database=ResearchDatabase(),
    maintenance_intent=MaintenanceIntent.BACKUP,
) as maintenance:
    copy = maintenance.services.databases.backup(
        destination=Path("backups/research-2026-07-15.duckdb"),
    )

with Project.open(
    ".",
    mode=ProjectMode.MAINTENANCE,
    maintenance_database=MarketDatabase(DatabaseName("primary")),
    maintenance_intent=MaintenanceIntent.SNAPSHOT_COPY,
) as maintenance:
    copy = maintenance.services.databases.snapshot_copy(
        snapshot_id=snapshot_id,
        destination=Path("snapshots/us-equities.duckdb"),
    )
```

`backup()` creates an immutable verified physical backup of either role.
`snapshot_copy()` additionally validates and pins one committed logical market snapshot.
Both require an exclusive source lease, close all source connections, and leave the source
unmodified except for a required DuckDB checkpoint before close. A project already holding
a shared source lease cannot upgrade it; the copy is a separate maintenance operation.

### 13.2 Publication algorithm

The operation performs these steps:

1. validate a local, nonexistent destination whose parent already exists;
2. acquire the exclusive source and destination-path leases in canonical order;
3. open the source read-write, validate role/schema, validate the logical snapshot when
   requested, execute `CHECKPOINT`, and close it;
4. capture source device, inode, size, and modification metadata;
5. stream the source in 8 MiB chunks to a sibling `<name>.partial-<copy-id>` file while
   calculating SHA-256;
6. flush and `fsync` the temporary file, then verify source metadata is unchanged;
7. hash the temporary destination independently and require the same digest and size;
8. open the temporary database read-only, validate bootstrap metadata, migration checksums,
   expected role, and pinned snapshot manifest;
9. write and fsync sibling canonical JSON manifest and checksum temporary files;
10. atomically rename the database, then the manifest, then the checksum to their final
    individual paths, treating the checksum rename as the publication commit marker;
11. fsync the directory, set the database file read-only for owner/group/other, reopen by
    final path, rehash, revalidate, record success, and release leases.

POSIX does not provide one atomic rename for all three files. A crash may leave a final
database or manifest without the checksum commit marker; readers must treat that state as
an incomplete, unverified copy and must not open it through managed copy APIs.

A destination is never overwritten by default. Explicit replacement is CLI confirmation-
gated, requires exclusive lease on the old destination, verifies it is a Persistra copy,
and moves it to a timestamped backup before publication. Python callers use a separately
named `replace_verified_copy()` method so replacement cannot result from a boolean typo.

### 13.3 Manifest

`<database>.persistra-copy.json` is canonical JSON under schema
`persistra.database.copy_manifest@1` and contains:

- manifest schema version and copy ID;
- kind `backup` or `market_snapshot`;
- source database ID, role, owner project ID when the role is research, logical configured
  name, and schema version;
- source file size and SHA-256 content ID;
- selected logical snapshot ID and manifest content ID when applicable;
- created instant, Persistra version, Python version, DuckDB library version, and reported
  DuckDB storage version when available;
- required DuckDB extensions, which are empty unless a later plan declares otherwise;
- verification checks performed and their results;
- supported Persistra reader range; and
- optional source-path hash, never the machine-local cleartext path.

The manifest itself is canonicalized and content-addressed; its content ID is stored in a
small sibling `.sha256` file to avoid a self-referential field. That file contains exactly
the plan-01 `sha256:<64-lowercase-hex>` wire value plus one LF byte. Any mismatch makes the
copy unverified.

`verify_copy_on_open=true` acquires the shared lease, then rehashes and revalidates once per
project open before acquiring a shared database connection. A declared `market_snapshot`
copy requires this setting.
Changing file mode is not proof of immutability; the hash and manifest are authoritative.

### 13.4 Restore and fork

A backup is never made writable in place. Restore creates a new sibling temporary file,
verifies the backup, copies it, allocates a new `DatabaseId`, records the source database
and copy IDs in `_persistra.database_lineage`, applies required verified copy migrations,
and atomically publishes a new writable database path. The original backup and source
remain unchanged.

`restore` retains the research database's `owner_project_id` and requires it to match the
opening project. `fork` requires an explicit destination `ProjectId` and replaces the
research owner with that ID. Market restores and forks keep `owner_project_id` null.

## 14. Migration model

### 14.1 Registry

Market and research roles have separate ordered migration registries. A migration declares:

- role, positive gap-free number, stable name, and canonical checksum;
- source and target schema versions;
- transactional SQL and bounded Python transformation callbacks;
- required free space and estimated exclusivity duration;
- whether a native DuckDB storage-version copy migration is required;
- verification queries and expected invariants; and
- minimum Persistra and DuckDB reader/writer versions.

Migration modules are built into the package and registered explicitly, not discovered by
import side effects. Changing an already released migration's canonical bytes or callback
identity is forbidden. The installed checksum must match every applied row.

### 14.2 Open compatibility

Package metadata publishes, per database role:

- current writable schema version;
- minimum and maximum readable schema versions; and
- supported DuckDB library and storage versions.

An exact current schema may open in a permitted mode. An older readable schema may open
read-only only when registered compatibility views make every exposed contract exact.
Writable open of any older schema raises `MigrationRequiredError`. A newer schema or
unsupported storage version raises `DatabaseCompatibilityError`; it is never opened on a
best-effort basis.

Ordinary open does not modify metadata, apply migrations, checkpoint, or create backups.

### 14.3 Forward migration algorithm

`persistra db migrate`:

1. resolves one database target without attaching unrelated files;
2. acquires its exclusive maintenance lease;
3. validates current metadata and the entire installed migration chain;
4. estimates free-space needs and refuses an obviously insufficient filesystem;
5. creates and verifies a physical backup by default;
6. opens the source read-write and applies every pending same-storage migration in one
   DuckDB transaction;
7. after each step, inserts its migration row, updates `database_info.schema_version`, and
   inserts the corresponding gap-free `database.migrated` event;
8. runs all step and final verification queries before commit;
9. commits, checkpoints, closes, reopens read-only, and repeats compatibility validation;
10. records a structured success diagnostic containing the backup copy ID and durations.

Any SQL, Python callback, verification, commit, checkpoint, or reopen failure rolls back
where DuckDB permits, closes the file, preserves the verified backup, records an external
failure log, and raises `MigrationFailedError`. A post-commit verification failure marks
the database `needs_recovery` in a sidecar marker and blocks ordinary open until explicit
restore or a registered recovery action succeeds.

Migrations requiring a new DuckDB storage format use the restore/fork protocol: verified
source copy, transform a new destination, validate, then atomic publication. They never
upgrade the only native file in place.

`--no-backup` is accepted only when database metadata already has `disposable=true`, the
user supplies `--confirm-disposable <database-id>`, and the skipped backup is logged. It is
never available for a supported non-disposable database.

### 14.4 Downgrade and rollback

There are no down migrations. Before commit, transaction rollback returns the source to
its old schema. After a successfully committed migration, rollback means restoring the
verified backup to a new path and reopening with a compatible older Persistra version; it
never means applying reverse DDL to the migrated file.

## 15. Inspection, doctor, and CLI

### 15.1 Inspection result

`Project.inspect()` returns immutable structured records and a versioned pandas dataframe
view with explicit columns for project ID/name/root, open mode, each logical database,
canonical path hash, database ID/role, schema compatibility, DuckDB version, lease mode,
copy verification, filesystem type, and warnings. It does not expose credentials or
cleartext environment values.

### 15.2 CLI surface

This plan implements:

```text
persistra init [PATH] [--name NAME]
persistra db create --database research
persistra db create --database market:NAME
persistra db inspect [--database NAME]
persistra db migrate --database NAME [--wait DURATION]
persistra db backup --database NAME --destination PATH
persistra db snapshot-copy --market NAME --snapshot ID --destination PATH
persistra db verify-copy PATH
persistra doctor
```

Database creation resolves its destination from `persistra.toml` and never edits the
configuration file. Administrative/provider code may use the explicit Python path selector
to create an unregistered managed market database and then register it in a separate,
reviewable configuration edit.

Commands support `--project PATH` and `--format {console,json}`. Successful read commands
write data to stdout; diagnostics and progress use stderr. Stable exit classes are 0
success, 2 usage/configuration, 3 lease conflict, 4 compatibility/migration required, 5
verification failure, and 1 other operational failure. JSON mode emits one documented
object and no console decoration.

CLI durations accept a nonnegative integer followed by `us`, `ms`, `s`, `m`, or `h` and
convert exactly to plan-01 microseconds. Fractions, calendar units, and bare numbers are
rejected.

Destructive replacement and disposable no-backup paths require the explicit confirmations
defined above. There is no `--force-lock`, implicit migration, or raw SQL CLI.

`doctor` performs read-only configuration, path, permission, filesystem, sidecar,
dependency, schema compatibility, copy-manifest, and stale-owner-metadata checks. It never
repairs state. Each finding has stable code, severity, subject, evidence, and remediation.

## 16. Transactions and failure recovery

- One state-changing public service call owns one explicit DuckDB transaction unless its
  contract says it coordinates multiple isolated worker files.
- A transaction captures one `recorded_at` from the injected clock and allocates explicit
  sequences for peers, following plan 01.
- Callbacks cannot commit, roll back, close, attach, detach, or access the connection.
- Cancellation is observed only at documented safe boundaries; an interrupted transaction
  rolls back before cancellation becomes visible.
- Process death relies on DuckDB recovery for the database and kernel release for the
  lease. On next open, Persistra validates metadata and surfaces recovery diagnostics.
- Temporary files include operation IDs, are never treated as completed copies or
  databases, and are cleaned only after proving no active owner metadata references them.
- External mutation of a managed DuckDB file is unsupported. A changed inode, migration
  checksum, role, or bootstrap invariant blocks open rather than attempting repair.

No operation spans market and research databases as one claimed ACID transaction. A later
coordinator may use staged files and verified transactional merge into one research
database, but cross-file atomicity is never implied.

## 17. Structured events and diagnostics

Managed lifecycle operations that create immutable state emit normalized records plus
these initial domain event types under plan 01:

| Event type | Aggregate kind / sequence | When emitted |
| --- | --- | --- |
| `persistra.database.created@1` | `persistra.aggregate.database` / 1 | New managed database publish succeeds |
| `persistra.database.migrated@1` | `persistra.aggregate.database` / next sequence | Each migration step commits with its migration row/schema version |

One migration operation applying several registry steps emits one correlated event per step
inside the same database transaction, with writer-allocated consecutive aggregate
sequences. The payload names the step number/checksum, source/target versions, backup copy
ID, and bounded timing known before commit. Exact retry cannot emit a duplicate step event.
Post-commit reopen verification is a diagnostic/recovery gate; it does not move the event
away from the normalized change it records.

A verified physical copy emits no database-domain event: writing either the source or final
destination after hashing would break the copy's byte-identity contract. Its signed-off
copy manifest and `CopyId` are immutable lifecycle authority, while a coordinator may log
or reference that manifest from a later owning operation.

Project initialization likewise has no domain event because its commit marker is a TOML
file outside the staged research-database transaction. The operation manifest and final
configuration are authority; success/failure is logged only after publication. This avoids
claiming cross-file atomicity that the project layout does not provide.

Database lifecycle events here use the transaction's one injected-clock instant for
`event_at`, `available_at`, and `recorded_at`; source-market information time is not
represented by these operational occurrences.

Project/database open and close, lease acquisition/release, and failed attempts are
structured operational logs rather than durable domain events because no immutable
managed state necessarily changes. Stable log event names include `db.lease.acquired`,
`db.lease.conflict`, `db.lease.released`, `db.opened`, `db.closed`, `db.open.failed`,
`db.copy.failed`, and `db.migration.failed`.

Warnings persist with the operation or artifact manifest when one exists. Console logging
is presentation only. A project installs no root logger handler and does not mutate global
logging configuration.

## 18. Errors and stable reason codes

All errors derive from the eventual `PersistraError`. Required classes include:

| Exception | Reason code |
| --- | --- |
| `ProjectConfigNotFoundError` | `project.config.not_found` |
| `ProjectConfigError` | `project.config.invalid` |
| `ProjectAlreadyExistsError` | `project.init.exists` |
| `ProjectClosedError` | `project.closed` |
| `ProjectThreadError` | `project.wrong_thread` |
| `ProjectProcessError` | `project.wrong_process` |
| `CapabilityUnavailableError` | `project.capability.unavailable` |
| `DatabaseNotFoundError` | `db.not_found` |
| `DatabaseAlreadyExistsError` | `db.already_exists` |
| `UnmanagedDatabaseError` | `db.unmanaged` |
| `DatabaseRoleError` | `db.role_mismatch` |
| `DatabaseLeaseConflictError` | `db.lease.conflict` |
| `LeaseUpgradeError` | `db.lease.upgrade_forbidden` |
| `UnsupportedFilesystemError` | `db.filesystem.unsupported` |
| `DatabaseCompatibilityError` | `db.compatibility.unsupported` |
| `MigrationRequiredError` | `db.migration.required` |
| `MigrationChecksumError` | `db.migration.checksum_mismatch` |
| `MigrationFailedError` | `db.migration.failed` |
| `DatabaseRecoveryRequiredError` | `db.recovery.required` |
| `CopyVerificationError` | `db.copy.verification_failed` |
| `ProjectCloseError` | `project.close.failed` |

Errors include a sanitized subject, operation ID, stable context fields, and actionable
remediation. They do not embed raw TOML, SQL, environment mappings, full command lines, or
database pages.

## 19. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Multiple ancestor configs | Nearest resolved ancestor wins |
| Missing path environment variable | Configuration fails before any lease or file creation |
| Two logical names resolve to one file | Configuration fails |
| Research file reports market role | Open fails with role mismatch |
| Existing unmanaged DuckDB file | Never adopt or overwrite it |
| Read-only directory cannot host lease sidecar | Fail with remediation; no weaker lock fallback |
| Two shared readers in one process | In-process lock entry is reference counted |
| Writer requested while same process reads | Fail with lease-upgrade error even with timeout |
| Process dies while holding a lease | Kernel unlocks; stale metadata is cleaned by next exclusive owner |
| Lock exists without owner metadata | Report unknown/racing external owner |
| Dashboard opens during research writer | Shared lease conflicts and explains verified-copy alternative |
| Ingestion opens during market study | Exclusive lease conflicts for study lifetime |
| Database path is replaced after lease | Identity check fails and closes without using replacement |
| Source changes during copy | Verification fails; final destination is absent |
| Destination exists | Refuse unless separate confirmation-gated replacement workflow is used |
| Copy manifest missing or changed | Copy is unverified and cannot serve a declared snapshot |
| Logical snapshot absent | Snapshot copy fails before byte copying |
| Older readable schema in read-only mode | Open only through exact registered compatibility contract |
| Older schema in write mode | Fail with migration-required error |
| Newer or unknown schema/storage version | Fail closed |
| Previously applied migration checksum differs | Treat as invariant failure; never continue |
| Migration transaction fails | Roll back, preserve backup, record failure |
| Post-commit verification fails | Write recovery marker and block ordinary open |
| Caller changes working directory after open | No effect; every path is resolved already |
| `fork()` occurs after open | Child use fails; child must open its own project |
| Close is called twice | Second call is a no-op |

## 20. Security and resource constraints

- TOML parsing uses Python `tomllib`; no executable configuration or object constructors
  are supported.
- Resolved paths and attachment identifiers are never concatenated from unchecked SQL.
- DuckDB external access, unsigned extension installation, and automatic network reads are
  disabled at open.
- Lease owner metadata is created with mode `0640`, copy manifests with `0644`, and
  temporary files with `0600`, subject to a no-more-permissive process umask.
- State-changing operations use restrictive creation flags and reject symlink destinations.
- Copy and hashing operations stream bounded chunks and report progress through bounded
  callbacks; they do not load database files into memory.
- Configured memory and thread limits apply per connection. Worker aggregate limits belong
  to the experiment plan.
- Log rotation and retention are configurable implementation details, but failure to write
  a required audit manifest is fatal to the owning state change.

## 21. Migration and compatibility effect

This is a greenfield v3 contract. It does not open, import, infer, or migrate v2 Parquet
layouts, v2 artifacts, v2 configuration, or v2 database files. The clean-slate checkpoint
removes those native surfaces.

Within 3.x, configuration changes are additive with defaults. Database schema changes use
the versioned forward protocol here. Native DuckDB incompatibility uses verified copy
migration. A future change to lease location, database identity, attachment role, or copy
manifest canonicalization is a project-wide compatibility change and requires review of
plans 01, 03, 14, and 15.

## 22. Acceptance tests

### 22.1 Configuration and initialization

- Property-test strict TOML parsing over unknown keys, wrong types, duplicate keys, name
  grammar, byte-size bounds, and every permitted path field.
- Test nearest-ancestor discovery through symlinks without dependence on the current
  directory after resolution.
- Test environment substitution success, missing/empty variables, rejected operators,
  nonrecursive expansion, and rejection outside path fields.
- Inject failure and process death after every initialization step; prove no valid config
  exposes partial state, diagnostics identify only manifest-matching orphan paths, and no
  pre-existing file changes.
- Round-trip `ResolvedProjectConfig` through inspection and provenance without exposing
  environment values.

### 22.2 Database and connection lifecycle

- Create both roles and assert exact bootstrap schemas, singleton metadata, migration
  checksums, research ownership, file publication, and role rejection.
- Round-trip plan-01 event envelopes through `_persistra.domain_events`; reject duplicate
  aggregate sequences and prove normalized state/event transaction atomicity.
- Open every valid mode and assert exact connection read/write flags, attachments, resource
  settings, UTC timezone, maintenance-intent capability surface, and deterministic close
  order; reject absent targets except for `create`.
- Prove public objects expose no DuckDB connection and cannot execute unmanaged writes.
- Test rollback at every multi-statement service boundary and reject nested public
  transactions.
- Test use after close, cross-thread use, and post-fork use.

### 22.3 Multi-process lease suite

- On Linux, run independent processes for shared/shared success and every shared/exclusive
  or exclusive/exclusive conflict permutation.
- Test zero-timeout failure, bounded wait success, monotonic deadline, interrupt handling,
  owner diagnostics, and canonical multi-file acquisition order.
- Kill a lease owner without cleanup and prove the kernel lock is released, stale metadata
  is never mistaken for a live lock, and only an exclusive holder removes it.
- Exercise reentrant same-process acquisition and reject mode conversion.
- Assert a study-style shared market lease blocks a market writer and a research writer
  blocks a dashboard-style reader.

### 22.4 Copy and filesystem suite

- Build deterministic databases larger than one copy chunk and verify source/destination
  digests, bootstrap metadata, logical snapshot identity, manifest canonicalization,
  checksum commit marker, permissions, final reopen, and that verification writes no
  database-domain event to either byte-identical file.
- Inject failure at every copy/checkpoint/hash/fsync/rename/verify boundary and prove no
  final path is presented as verified.
- Mutate the source during a deliberately unsupported external-write test and require
  detection without a successful manifest.
- Test restore creates a new database identity and preserves the source backup byte-for-byte.
- Test mount classification fixtures for every allowlisted and denied filesystem; verify
  remote read-only requires a validated immutable copy and persistent warning.

### 22.5 Migration suite

- For every supported prior schema, migrate a deterministic fixture to current and compare
  exact schemas, row content, metadata, checksums, and invariants.
- Assert one transactionally paired, correlated, gap-free event per applied migration step
  and no event for an already-current exact retry.
- Inject failure in every migration step and verification query; prove transactional
  rollback or recovery-marker behavior and backup preservation.
- Reject gaps, duplicate numbers, changed checksums, role mismatches, newer schemas,
  unsupported DuckDB storage, and implicit writable open of an old schema.
- Prove `--no-backup` is impossible for non-disposable databases and identity-confirmed for
  disposable ones.
- Verify copy migration leaves the source byte-identical and publishes only a fully
  validated destination.

### 22.6 CLI and documentation

- Contract-test command arguments, stdout/stderr separation, JSON schemas, exit classes,
  confirmation gates, and redaction.
- Run the empty-project workflow through public Python APIs and again through the CLI.
- Execute documentation snippets once the implementation exists and keep pre-implementation
  signatures marked `no-run`.
- Build the documentation in strict mode and verify all focused-spec links.

### 22.7 Exit criteria

This plan is implementation-complete when:

- an installable base package initializes and opens an empty project in every valid mode;
- market and research databases create, inspect, attach, transact, and close only under
  their required leases;
- verified backups, market snapshot copies, restores, and migrations pass fault injection;
- Linux multi-process tests prove the declared concurrency boundaries;
- no managed write path bypasses role, compatibility, lease, transaction, or filesystem
  checks;
- the CLI surface in section 15 is documented and contract-tested; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 23. Review checklist for dependent plans

Every later focused specification must state:

- which database role and managed schema owns each table;
- which `ProjectMode` and lease mode each operation requires;
- whether a query spans attached market databases and how it pins composite snapshots;
- whether a state change is one-database transactional or uses a staged coordination
  protocol;
- which migration stream owns schema changes and what verifies them;
- whether an artifact is logical, an immutable physical copy, or a portable export;
- what happens when a live writer prevents a reader or dashboard open;
- which paths, callbacks, extensions, and external reads are allowed;
- how failure avoids partially published files or visible rows; and
- which stable errors, events, logs, and recovery instructions apply.

## 24. Umbrella and completed-plan consistency

This plan preserves focused specification 01 by using typed UUID identities, UTC
microsecond instants, injected clocks, fixed `Duration`, content-addressed manifests,
canonical JSON, immutable events, and deterministic explicit ordering.

It resolves the umbrella specification's project, database, concurrency, SQL-boundary,
migration, CLI, and local-first requirements without changing project-level direction.
In particular, it keeps one package and one database engine, rejects networked active
writes, documents DuckDB's reader/writer limit, prevents hidden connection access, and
uses verified physical copies rather than pretending logical snapshots bypass file locks.

The concrete Linux sidecar lease protocol, strict TOML grammar, project modes, bootstrap
schemas, copy manifest, and migration algorithms are local refinements. No umbrella or
focused-specification-01 requirement is relaxed.
