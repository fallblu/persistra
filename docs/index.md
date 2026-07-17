# Persistra v3

Persistra is a local-first quantitative research workbench. Its v3 design prioritizes
point-in-time correctness, explicit information boundaries, deterministic execution,
exact accounting, and reproducible analysis.

The [v3 umbrella specification](v3/v3-spec.md) and its focused specifications are the
normative design documents while the implementation is developed.

## Implemented foundation

The current public implementation includes:

- managed projects, DuckDB migrations, leases, verified copies, catalog ingestion,
  revisions, quarantine, and immutable market/composite snapshots;
- typed reference identities, external identifiers, effective classifications and
  memberships, reviewed materialized exchange calendars, and point-in-time universe
  evaluation with complete eligibility audits;
- raw regular-session daily bars, orthogonal trading status, split and cash-dividend
  terms, and nonpersistent point-in-time raw/split/total-return adjustment views; and
- immutable daily decision datasets at exact `(decision_at, instrument_id)` grain with
  snapshot binding, dual cutoffs, missing-input handling, eligibility/input audits, and
  deterministic exact retry;
- managed daily returns and momentum, cross-sectional rank signals, monthly equal-weight
  target construction, and a next-open vectorized simulator with explicit commission and
  slippage; and
- immutable double-entry accounting, FIFO long lots, split and cash-dividend processing,
  normalized run results, initial performance metrics, a Plotly equity figure, and a
  self-contained HTML report.

These capabilities are reached through `Project.services` and the public contracts in
`persistra.catalog`, `persistra.reference`, `persistra.market`, and
`persistra.research`, `persistra.portfolio`, `persistra.accounting`,
`persistra.simulation`, `persistra.results`, `persistra.analysis`, and
`persistra.reports`.

## Momentum flagship slice

`persistra.flagship.FLAGSHIP_MOMENTUM_V1` is the versioned profile for the first
end-to-end strategy. It binds the 12–1 momentum definition, ascending percentile-rank
signal, top-half equal-weight constructor, opening capital, and execution-cost policy.
After building a split-adjusted daily research dataset, the public workflow is:

1. register and materialize `FLAGSHIP_MOMENTUM_V1.momentum` through
   `project.services.research.features`;
2. register and materialize `FLAGSHIP_MOMENTUM_V1.signal`, then register its constructor
   and call `project.services.portfolio.construct(...)`;
3. plan and run a `VectorizedSimulationRequest` through
   `project.services.simulation.vectorized`;
4. query the returned immutable result handle, compute
   `project.services.analysis.metrics.compute(result)`, and render a
   `ReportRequest` through `project.services.reports`.

Install the `viz` extra before creating a figure or report. Visualization namespaces
remain importable without it and raise an actionable error only when a Plotly-backed
operation is invoked.

The phase-4 simulator intentionally models monthly target acquisition and next-open
fractional fills rather than an order lifecycle. Its result and report provenance records
`simulation.vectorized.no_orders` so this fidelity limit remains visible. Intraday
observations, retrospective adjustment materialization, general corporate actions,
shorting, settlement, financing, SQL/workspaces, and the complete feature/label DAG remain
assigned to later phases in the [phase plan](v3/phase-plan.md).
