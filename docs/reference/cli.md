# CLI

The `persistra` command wraps the public project APIs; it never bypasses them. All
output is JSON on stdout, and failures print safe structured evidence (typed reason
codes, no secrets or raw paths in error context).

## Project

```bash
persistra project init <path> [--name NAME] [--no-research]
persistra project inspect [path]
persistra doctor [path]
```

## Database maintenance

```bash
persistra db create <project> <destination> --role {research,market}
persistra db backup <project> --database <selector> --destination <path>
persistra db verify-copy <project> <copy>
persistra db migrate <project> --database <selector>
persistra db snapshot-copy <project> --database <selector> \
  --snapshot-id <id> --destination <path>
persistra db restore <project> <destination> --backup <path>
persistra db fork <project> <destination> --backup <path> \
  --destination-project <project-id>
```

A database selector is `research` or a configured market name. Maintenance commands
open the project in `MAINTENANCE` mode with the matching intent, taking an exclusive
lease on the target database only.

## Data

```bash
persistra data validate <project> --market <name> <batch-id>
persistra data quarantine <project> --market <name> [--batch-id ID]
persistra data snapshot create <project> --market <name>
persistra data snapshot list <project> --market <name>
persistra data snapshot inspect <project> <snapshot-id> --market <name>
```

## Dashboard

```bash
persistra dashboard --project <path> | --backup <path> | --export <path>
                    [--bind 127.0.0.1] [--port 8501] [--open-browser]
```

The three source flags are mutually exclusive and exactly one is required. Non-loopback
binds are rejected unless the unsupported network override is explicitly set, and that
override remains outside the support boundary.
