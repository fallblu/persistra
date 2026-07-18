# Changelog

## Unreleased — v3 rewrite

- Rebuilt managed projects, database identities, leases, copies, migrations, diagnostics,
  catalog ingestion, revisions, quarantine, and immutable snapshots.
- Added canonical reference, market, fundamental, estimate, macro, benchmark, and rate data
  with point-in-time temporal safety.
- Added bounded research datasets and SQL workspaces, feature/label graphs, temporal
  conformance, purged validation, and alpha diagnostics.
- Added forecasts, risk models, constrained portfolio optimization, immutable journal
  accounting, settlement, margin, borrow, accrual, and corporate actions.
- Added vectorized and event simulation, deterministic experiments, exact/compatible reuse,
  normalized results, metrics, attribution, comparison, scenarios, and verified exports.
- Added deterministic accessible Plotly families, offline HTML reports, checksum-closed report
  bundles, and an eight-page loopback-only read-only Streamlit dashboard.
- Added v2-to-v3 migration, public workflow, dashboard ADR, compatibility bands, and
  human-controlled release-readiness documentation.

### Release hardening

- Made every runtime dependency required: numpy, scipy, scikit-learn, sqlglot, optuna,
  cvxpy, plotly, jinja2, and streamlit now install with the base package, and all
  optional capability extras and their import-availability guards were removed.
- Conformed the `persistra.standard@1` metric catalog to its definitions: per-component
  `cost_total` rows, time-weighted-return-index drawdown and duration, absolute turnover
  notional, and a single-observation active return; misaligned optional metric inputs now
  raise `AnalysisInputError` at request time. The metric engine is vectorized on numpy.
- Hardened portable export writers (staging cleanup and retry, non-empty equity
  validation, once-per-handle verification), escaped dashboard backup configuration paths,
  strengthened public result typing, made log-key redaction collision-safe, reused one
  experiment worker pool across batches, and added `CHECK (quantity > 0)` to the fill
  tables. Extracted the event-simulation per-bar decision logic into pure kernels.
- Rescoped the release benchmark to `persistra.benchmark.daily_equity_1000x10@1`
  (1,000 instruments over ten years, 8 GiB peak-RSS gate) so it runs on the supported
  local host, and raised the coverage gate to 85%.
- Rebuilt the documentation set into a Diátaxis structure with a generated API reference,
  a single authoritative release-governance page, and condensed per-subsystem design
  references.

No version, tag, package publication, or release has been made from this entry.
