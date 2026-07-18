# Architecture

Persistra is organized as one lifecycle root over a set of typed capability namespaces,
all backed by managed DuckDB storage.

## Lifecycle and capability ownership

`Project` is thread-owned and process-bound. `Project.open(path, mode=...)` resolves the
immutable TOML configuration, acquires every required lease, opens the databases the
mode needs, and exposes capabilities through `project.services`. Crossing a thread or
process boundary, or using a closed project, raises a typed error. The top-level package
exports only `Project`, `ProjectMode`, `ProjectOverrides`, and version metadata; domain
capabilities live below `project.services` and their named namespaces.

Four modes gate mutation:

- `READ_ONLY` — shared research lease, read-only market attachments;
- `RESEARCH_WRITE` — exclusive research lease for research/portfolio/simulation/analysis
  writes;
- `MARKET_WRITE` — exclusive lease on one named market database for ingestion;
- `MAINTENANCE` — exclusive lease on one target for backup/restore/fork/migrate.

A capability unavailable in the selected mode fails before any mutation.

## Data platform

Managed databases carry role-specific schemas and checksum-verified, gap-free forward
migrations. Catalog ingestion stages batches, assigns per-record dispositions, records
revisions and quarantine, and publishes immutable content-addressed snapshots. Readers
pin snapshots, so later ingestion cannot alter an existing query result.

## Research and decision layers

Research datasets, features, labels, and SQL workspaces are immutable and
content-addressed, with structural temporal safety: label and retrospective ancestry
cannot enter decision data, and opaque inputs stay visibly tainted. Portfolio
construction consumes validated decision inputs to produce target weights; forecasts and
risk models are explicit transforms and covariance estimators, not fitted systems.

## Execution and results

The accounting core is an immutable double-entry journal with FIFO lots, borrow, and
settlement. The vectorized and event simulators both post to that journal and publish
the same normalized result tables, queried through engine-independent bounded handles.
Experiments coordinate spawned local workers with verified isolated DuckDB handoffs.
Analyses, reports, and portable exports are immutable artifacts bound to their source
roots.

## Determinism and provenance

Semantic identities exclude allocated IDs, paths, PIDs, and completion time, so the same
inputs produce the same identity. Every reusable artifact binds its source identities,
exact definitions, configuration, dependency-relevant facts, and output root. "Latest"
is resolved before execution and never left inside an immutable plan. Results carrying
unknown material code, unsafe overrides, compatibility reuse, or fidelity limitations
retain those findings and must not be represented as clean exact evidence.

The condensed design references describe the implemented behavior of each subsystem:
[data platform](design/data-platform.md),
[research and portfolio](design/research-and-portfolio.md),
[simulation and accounting](design/simulation-and-accounting.md), and
[experiments and results](design/experiments-and-results.md).
