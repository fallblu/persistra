# Changelog

## Unreleased

- Version 4 replaces the v3 research and backtesting platform with a provider-neutral
  primary market and economic data toolkit.
- The new data model covers bars, quotes, top-of-book data, historical options,
  commodities, economic indicators, currency pairs, and provider reference data.
- Alpha Vantage support targets the primary datasets available on the 150 request per
  minute plan. Provider analytics, fundamentals, ownership, and textual data are out of scope.
- Alpha Vantage quote acquisition accepts delayed quote envelopes and the current realtime
  bulk schema. Bulk quotes and top-of-book snapshots are explicitly realtime-only.
- The runtime now depends only on NumPy, pandas, Matplotlib, Requests, platformdirs,
  and DuckDB.
- Documentation uses short, plain American English without formal controlled-language claims.

## 3.0.2 — 2026-07-20

- The repository documentation contains the index and generated API reference only.
  Guides and explanation pages are not in the repository.
- The README is shorter. The new `CONTRIBUTING.md` contains development,
  verification, and release instructions.
- A small `AGENTS.md` pointer replaces the previous agent configuration.
- The project uses the Git Flow branching model.

## 3.0.1 — 2026-07-20

- The dependency lower bounds support Python 3.12 with `lowest-direct` resolution.
  The new bounds are `cvxpy>=1.5.2`, `streamlit>=1.30`, and `hypothesis>=6.88`.

## 3.0.0 — 2026-07-19

- The release rebuilt managed projects, database identities, leases, copies,
  migrations, diagnostics, catalog ingestion, revisions, quarantine, and immutable
  snapshots.
- Canonical data supports reference, market, fundamental, estimate, macro,
  benchmark, and rate data with point-in-time safety.
- Research has bounded datasets, SQL workspaces, feature and label graphs, temporal
  conformance, purged validation, and alpha diagnostics.
- Portfolio and accounting capabilities include forecasts, risk models, portfolio
  optimization, journals, settlement, margin, borrow, accrual, and corporate actions.
- Simulation includes vectorized and event simulation. Results include experiments,
  reuse, metrics, attribution, comparisons, scenarios, and verified exports.
- Reports include accessible Plotly figures, offline HTML, and checksum-closed
  bundles. A read-only Streamlit dashboard has eight loopback-only pages.
- The release added v2-to-v3 migration, a public workflow, a dashboard ADR,
  compatibility bands, and human-controlled release instructions.

### Release hardening

- All runtime dependencies are necessary. The base package installs numpy, scipy,
  scikit-learn, sqlglot, optuna, cvxpy, plotly, jinja2, and streamlit.
- The release removed all optional capability extras and import-availability guards.
- The `persistra.standard@1` metric catalog agrees with its definitions. The metric
  engine uses vectorized numpy operations.
- Misaligned optional metric inputs cause `AnalysisInputError` at request time.
- Portable export writers clean staging data and retry safely. They also validate
  equity data and verify each handle one time.
- Dashboard backup paths have correct escaping. Public result types and log-key
  redaction are stronger.
- One experiment worker pool runs all batches. Fill tables have
  `CHECK (quantity > 0)`.
- Pure kernels contain the event-simulation decision logic for each bar.
- The minimum coverage is 85 percent.
- The documentation uses a Diátaxis structure. It has a generated API reference and
  one release-governance page.

### Multi-asset ingestion

- The new `AssetClass` taxonomy contains equity, FX, crypto, commodity, index, rate,
  and macro asset classes.
- Pair instruments support non-equity `SecurityKind` values. They also have
  `base_currency` and `quote_currency` fields.
- Each pair-shaped asset class has a reserved market-convention issuer. These asset
  classes use one shared synthetic OTC venue.
- New synthetic calendars support crypto and FX markets. They use
  `CalendarDefinition.always_open()` and `CalendarDefinition.fx_24x5()`.
- UTC sessions run from midnight to midnight. Spot FX uses bars without volume
  (`BarState.NO_VOLUME`).
- Market bar, trade, and quote contracts accept each registered currency.
- The package contains the Alpha Vantage adapter
  (`persistra.sources.alphavantage`). The adapter has a rate-limited HTTP client and
  pure endpoint parsers.
- The adapter supports equity, corporate action, crypto, FX, macro, commodity,
  treasury, policy-rate, and index data.
- Catalog registration and a typed-direct ingest boundary are part of the adapter.
- Each family has `ingestion_bounded` availability because Alpha Vantage supplies
  latest snapshots without vintages.
- The source definition has `redistributable=False`.
- Research supports non-USD market data. The accounting and results layer uses one
  reporting currency, USD.
- Simulation and accounting do not accept pair instruments.
