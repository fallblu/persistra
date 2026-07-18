# Persistra v3

Persistra is a local-first quantitative research workbench. Its v3 design prioritizes
point-in-time correctness, explicit information boundaries, deterministic execution,
exact accounting, and reproducible analysis.

The [v3 umbrella specification](v3/v3-spec.md) and its focused specifications are the
normative design documents. The [public workflow](guide.md), [v2-to-v3 migration
guide](migration-guide.md), and [release readiness record](release-readiness.md) describe
the implemented surface. The [implementation matrix](implementation-status.md) is the
authority for what is supported now; the focused specifications also contain planned
capabilities that are not current API promises.

## Supported v3 core

The current public implementation includes:

- managed projects, DuckDB migrations, leases, verified copies, catalog ingestion,
  revisions, quarantine, and immutable market/composite snapshots;
- typed reference identities, external identifiers, effective classifications and
  memberships, reviewed materialized exchange calendars, and point-in-time universe
  evaluation with complete eligibility audits;
- canonical bars, trades, quotes, actions, fundamentals, estimates, macro, benchmarks,
  rates, point-in-time adjustment views, and explicit temporal safety;
- immutable research datasets at exact `(decision_at, instrument_id)` grain with
  snapshot binding, dual cutoffs, missing-input handling, eligibility/input audits, and
  deterministic exact retry, plus bounded SQL workspaces and feature/label graphs;
- purged temporal validation, executable alpha diagnostics, direct forecasts, covariance
  risk models, bounded construction/optimization, and explicit unavailable-capability errors;
- immutable journal accounting, FIFO positions, borrow authorization, settlement,
  supported corporate actions, and reconciliation;
- vectorized simulation and bounded static event-order replay, deterministic local experiment
  workers/search/scenarios, common normalized results, standard metrics, compact analyses,
  structured diagnostics, and checksum-closed portable exports; and
- deterministic Plotly figure families, accessible warning-aware offline HTML reports,
  checksum-closed report bundles, and an eight-page loopback-only read-only dashboard.

These capabilities are reached through `Project.services` and the public contracts in
`persistra.catalog`, `persistra.reference`, `persistra.market`, and
`persistra.research`, `persistra.portfolio`, `persistra.accounting`,
`persistra.simulation`, `persistra.results`, `persistra.analysis`, and
`persistra.reports`.

## Momentum conformance slice

`persistra.flagship.FLAGSHIP_MOMENTUM_V1` is a versioned profile for a small end-to-end
conformance flow, not the final multifactor release flagship. It binds the 12–1 momentum definition, ascending
percentile-rank signal, top-half equal-weight constructor, opening capital, and
execution-cost policy. After building a split-adjusted daily research dataset, the public
workflow is:

1. register and materialize `FLAGSHIP_MOMENTUM_V1.momentum` through
   `project.services.research.features`;
2. register and materialize `FLAGSHIP_MOMENTUM_V1.signal`, then register its constructor
   and call `project.services.portfolio.construct(...)`;
3. plan and run a `VectorizedSimulationRequest` through
   `project.services.simulation.vectorized`;
4. query the returned immutable result handle, compute
   `project.services.analysis.metrics.compute(result)`, and render a
   `ReportRequest` through `project.services.reports`.

Install the `viz` extra before creating a figure or report and `dashboard` before launching
the local UI. Optional namespaces remain importable without their dependencies and fail
with actionable installation guidance only when invoked. Vectorized runs intentionally
record `simulation.vectorized.no_orders`; event runs provide the order lifecycle.

Read [assumptions and limitations](assumptions-and-limitations.md) before interpreting
simulation, scenario, metric, or compatibility-reuse output.
