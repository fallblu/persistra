# Persistra

Persistra v3 is a local-first Python library. Use it for point-in-time market research,
strategy development, and event-driven backtesting.

Persistra has explicit information limits and deterministic execution. It gives exact
accounting and reproducible analysis.

The base package contains all Persistra capabilities. There are no optional runtime
extras. One thread-owned `Project` lifecycle gives access to all capabilities. Use the
`project.services` namespaces to get this access.

This site contains these API references:

- **[API overview](reference/api/index.md):** Public API map and generated namespace
  documentation
- **[CLI](reference/cli.md):** `persistra` command reference
- **[Metric catalog](reference/metric-catalog.md):** `persistra.standard@1` metric
  definitions and formulas
- **[Export formats](reference/export-formats.md):** Portable export format contracts
