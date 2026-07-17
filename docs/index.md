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
  deterministic exact retry.

These capabilities are reached through `Project.services` and the public contracts in
`persistra.catalog`, `persistra.reference`, `persistra.market`, and
`persistra.research`. Intraday observations, general corporate actions, retrospective
adjustment materialization, SQL/workspaces, and feature/label execution remain assigned to
later phases in the [phase plan](v3/phase-plan.md).
