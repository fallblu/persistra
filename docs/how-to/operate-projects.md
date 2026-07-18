# Operate projects

## Modes and leases

`Project.open` acquires every required lease before returning: shared leases for
readers, exclusive leases for the writable database of the selected mode. One
process/thread owns a writable project at a time; lease conflicts fail with typed
errors rather than corrupting state. `project.inspect()` reports databases, roles,
schema versions, and open warnings; `persistra doctor` runs read-only diagnostics.

## Backup, verify, restore, fork

```bash
persistra db backup /path/to/project --database research --destination backup.duckdb
persistra db verify-copy /path/to/project backup.duckdb
persistra db restore /path/to/project /path/to/new.duckdb --backup backup.duckdb
persistra db fork /path/to/project /path/to/fork.duckdb \
  --backup backup.duckdb --destination-project <project-id>
```

Backups are verified published copies carrying a sidecar manifest; `verify-copy`
re-checks the checksum closure. Restore and fork always target a new destination.
Market snapshot copies additionally require `verify_copy_on_open = true` in the
consuming project's configuration.

## Migrate

```bash
persistra db migrate /path/to/project --database research
```

Managed databases carry checksum-verified, gap-free forward migrations. Migration
requires the explicit maintenance mode the CLI selects, records a recovery marker
while in flight, and refuses to open a database mid-recovery outside
restore/fork intents. Back up before maintenance. Pre-release development databases
are disposable: schema steps may be amended in place before 3.0, and such databases
are re-created rather than migrated.

## Configuration

`persistra.toml` holds the project identity, database paths, and optional market
databases:

```toml
[project]
id = "..."
name = "my-project"
state_dir = ".persistra"

[databases.research]
path = ".persistra/research.duckdb"
disposable = false

[databases.markets.primary]
path = ".persistra/market.duckdb"
verify_copy_on_open = false
```

Immutable `ProjectOverrides` may adjust resource limits (threads, memory, temporary
storage) at open time without editing the file.
