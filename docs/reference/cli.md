# CLI

The `persistra` command uses the public project APIs. It does not bypass these APIs.
The command writes all output as JSON to stdout. A failure writes safe, structured
evidence. This evidence has typed reason codes and does not contain secrets or raw
paths.

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

A database selector has one of these forms:

- `research`: The project research database
- `market:NAME`: The configured market database `NAME`
- `path:PATH`: An explicit managed database file for isolated maintenance

A maintenance command opens the project in `MAINTENANCE` mode. The command uses the
applicable intent and gets an exclusive lease on the target database.

## Data

```bash
persistra data validate <project> --market <name> --batch-id <id>
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

Select exactly one source flag. Do not use the source flags together. Persistra rejects
a non-loopback bind unless you set the unsupported network override. The support
boundary does not include this override.
