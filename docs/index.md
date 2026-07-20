# Persistra

Persistra v3 is a local-first Python library for point-in-time market research, strategy
development, and event-driven backtesting. Its design prioritizes point-in-time
correctness, explicit information boundaries, deterministic execution, exact accounting,
and reproducible analysis.

Everything installs with the base package — research, search, optimization,
visualization, and dashboard capabilities are required dependencies, not optional
extras. All capabilities are reached through one thread-owned `Project` lifecycle and
its `project.services` namespaces.

## Where to go

- **[Getting started](getting-started/installation.md)** — install the package and run
  the flagship momentum workflow end to end.
- **[How-to guides](how-to/ingest-market-data.md)** — task-oriented recipes for
  ingestion, research datasets, simulation, studies, analysis, reporting, the
  dashboard, and project operations.
- **[Reference](reference/api/index.md)** — the public API map, generated namespace
  documentation, the CLI, the standard metric catalog, and export formats.
- **[Explanation](explanation/architecture.md)** — architecture, condensed design
  references, assumptions and limitations, the v2 migration path, and release
  governance.

## Supported core

The current public implementation includes managed projects and DuckDB storage with
leases, migrations, and verified copies; catalog ingestion with revisions, quarantine,
and immutable snapshots; typed reference identities, calendars, and point-in-time
universes; canonical market, fundamental, estimate, macro, benchmark, and rate data
with explicit temporal safety, including multi-asset (equity, crypto, spot FX,
commodity, index, rate) coverage through the bundled Alpha Vantage adapter and its
synthetic pair-instrument calendars; immutable research datasets, bounded SQL workspaces, and
feature/label graphs; purged temporal validation and alpha diagnostics; direct
forecasts, covariance risk models, and constrained portfolio construction; immutable
journal accounting; vectorized and bounded event simulation; deterministic experiment
studies; normalized results with standard metrics and checksum-closed exports; and
deterministic Plotly figures, offline HTML reports, and a loopback-only read-only
dashboard.

Read [assumptions and limitations](explanation/assumptions-and-limitations.md) before
interpreting simulation, scenario, metric, or compatibility-reuse output. The
[release governance page](explanation/release-governance.md) is the single authority for
what "release ready" means; this line remains pre-release code until a human performs
the release process.
