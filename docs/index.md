# Persistra

Persistra v3 is a local-first Python library for point-in-time market research, strategy
development, and event-driven backtesting. Its design prioritizes point-in-time
correctness, explicit information boundaries, deterministic execution, exact accounting,
and reproducible analysis.

Everything installs with the base package — research, search, optimization,
visualization, and dashboard capabilities are required dependencies, not optional
extras. All capabilities are reached through one thread-owned `Project` lifecycle and
its `project.services` namespaces.

This documentation is the API reference and nothing more:

- **[API overview](reference/api/index.md)** — the public API map and the generated
  per-namespace documentation.
- **[CLI](reference/cli.md)** — the `persistra` command reference.
- **[Metric catalog](reference/metric-catalog.md)** — the `persistra.standard@1` metric
  definitions and formulas.
- **[Export formats](reference/export-formats.md)** — the portable export format
  contracts.
