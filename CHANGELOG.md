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
- Raised the coverage gate to 85%.
- Rebuilt the documentation set into a Diátaxis structure with a generated API reference,
  a single authoritative release-governance page, and condensed per-subsystem design
  references.

### Multi-asset ingestion

- Added the `AssetClass` taxonomy (equity, fx, crypto, commodity, index, rate, macro)
  and pair-shaped instrument support: non-equity `SecurityKind`s, `base_currency` /
  `quote_currency` on `InstrumentDefinition`, a reserved market-convention issuer per
  pair-shaped asset class, and the shared synthetic OTC venue.
- Added synthetic trading calendars — `CalendarDefinition.always_open()` (24×7, crypto)
  and `CalendarDefinition.fx_24x5()` (24×5 weekdays, FX) — with midnight-to-midnight
  UTC sessions, and volume-less priced bars (`BarState.NO_VOLUME`) for spot FX.
  Market bar/trade/quote contracts accept any registered currency.
- Added the bundled Alpha Vantage adapter (`persistra.sources.alphavantage`): a
  stdlib-only rate-limited HTTP client, pure endpoint parsers for equity bars and
  corporate actions, crypto and FX pair bars, indicative FX quotes, macro and
  commodity series, treasury/fed-funds risk-free curves, and index benchmark series,
  plus catalog registration and a typed-direct ingest boundary. Every family carries
  `ingestion_bounded` availability (Alpha Vantage serves latest snapshots without
  vintages) and `redistributable=False` licensing on the source definition.
- Non-USD market data is supported for research; the accounting/results layer remains
  single-reporting-currency (USD), so pair instruments are not simulation or
  accounting inputs.

No version, tag, package publication, or release has been made from this entry.
