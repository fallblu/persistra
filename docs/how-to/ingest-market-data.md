# Ingest market data

Canonical data enters a managed market database through registered sources, staged
batches, per-record dispositions, and immutable snapshots. Ingestion mutates market
storage, so it requires `MARKET_WRITE` mode against a configured market database.

## Register a source and dataset

```python
from persistra import Project, ProjectMode
from persistra.db import DatabaseName

with Project.open(
    "/path/to/project",
    mode=ProjectMode.MARKET_WRITE,
    writable_market=DatabaseName("primary"),
) as project:
    catalog = project.services.catalog
    ingestion = project.services.ingestion
```

Register the source, dataset, and (optionally) source-precedence policy through
`project.services.catalog`, then submit batches of typed observation records through
`project.services.ingestion`. Every record receives an explicit disposition; failed
records land in quarantine with remediation linkage rather than silently disappearing.

## Validate, revise, and quarantine

- `persistra data validate <project> --market <name> <batch-id>` re-runs managed
  validation for a staged batch.
- Revisions and retractions are first-class: corrections create new canonical revisions
  with their own availability instants; they never overwrite published facts.
- `persistra data quarantine <project> --market <name>` lists quarantined records.

## Snapshot

Pinned research reads immutable snapshots, never live tables:

```bash
persistra data snapshot create /path/to/project --market primary
persistra data snapshot list /path/to/project --market primary
```

A snapshot records a content-addressed catalog root. Later ingestion cannot affect
queries pinned to an existing snapshot; composite snapshots combine multiple market
databases into one referenced root.

Provider adapters must pass the conformance kit in `persistra.conformance`
(`standard_provider_suite`) before their data is treated as canonical.
