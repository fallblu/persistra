# Migrating from v2 to v3

V3 is a deliberate API and storage rewrite. Do not open a v2 database with v3 code or copy
physical DuckDB tables between versions. Preserve the v2 environment, export source data
through its supported interfaces, initialize a new v3 project, ingest canonical observations,
and rebuild immutable snapshots, research artifacts, simulations, analyses, and reports.

## Public API changes

- Replace broad top-level imports with `Project`, `ProjectMode`, and contracts from explicit
  namespaces such as `persistra.market`, `persistra.research`, or `persistra.results`.
- Replace implicit/global connections with a bounded `with Project.open(...)` lifecycle.
- Select `READ_ONLY`, `RESEARCH_WRITE`, `MARKET_WRITE`, or `MAINTENANCE` explicitly. A
  capability unavailable in the selected mode fails before mutation.
- Replace mutable dataframes as durable state with immutable assigned IDs and content roots.
- Replace ad hoc SQL against managed databases with bounded research SQL workspaces or typed
  public result/analysis queries.
- Replace naive timestamps and floats at domain boundaries with timezone-aware UTC instants,
  explicit source numerics, decimals, currencies, and units.
- Replace a monolithic backtest call with explicit research, portfolio, accounting,
  simulation, experiment, result, and analysis plans.
- Treat vectorized and event simulation fidelity separately. Vectorized results never invent
  order lifecycle data.
- Install capability extras explicitly. Base imports do not pull research, solver, Plotly, or
  Streamlit dependencies.

## Storage migration

V3 managed databases have checksum-verified, gap-free forward migrations. They support only
databases bootstrapped by the v3 project layer. Back up a v3 database before maintenance and
use `persistra db migrate` only with the explicit maintenance mode selected by the CLI.
Downgrade is tested as schema rollback behavior for development fixtures; it is not a
supported conversion path to v2.

## Reproducibility changes

Every reusable artifact now binds its source identities, exact definitions, configuration,
dependency-relevant facts, and output root. “Latest” is resolved before execution and does not
remain inside an immutable plan. Comparisons classify compatibility before combined claims.
Exports and report directories verify their closed file set and checksums before use.

The package version remains unchanged on development branches until a human performs the
release process. No database migration or API behavior should infer release state from the
branch name.
