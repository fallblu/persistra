# Changelog

## Unreleased

- Add caller-defined time-series, rolling, cross-sectional, and Fama-MacBeth factor
  regressions with explicit inference, diagnostics, residuals, and factor-risk covariance.
- Add a versioned external strategy protocol for Trading Engine replays. Persistra now hosts
  typed Python strategies over synchronous JSON Lines, validates retained transcripts, and binds
  the strategy executable, declared inputs, transcript, journal, and scenario into the run
  manifest.
- Add a synchronized portfolio-target boundary that builds raw intraday scenarios, validates and
  runs the separate Trading Engine executable, and strictly imports complete terminal journals.
- Add causal JSON Lines scenario export and negotiation. Model-based runs now bind each intent
  batch to its decision slice and stream slices through Trading Engine with bounded input and
  audit memory while retaining strict terminal counts and exact-byte hashes.
- Add negotiated execution-model selection, deterministic causal audit IDs, order-creation
  provenance, and per-instrument position attribution with exact fill, mark, P&L, fee, and
  terminal reconciliation.
- Upgrade the Trading Engine boundary to contract v3 with exact fractional quantities, signed
  long/short positions, explicit currency ledgers and FX marks, splits and cash dividends, borrow
  fees, exposure/leverage/initial-margin controls, and causally reconciled margin liquidation.
- Add order, fill, fee, slippage, event-time performance, execution-comparison, and replay
  visualization diagnostics for imported Trading Engine results.
- Replace the DuckDB version 1 snapshot-blob query schema with version 2 typed cumulative rows.
  Bar and scalar-series queries now accumulate partial acquisitions and choose the latest
  retained revision of each row while exact load methods remain snapshot based.
- Add explicit real-time, first-release, and final-vintage history projections for revision-bias
  studies, and avoid undefined-correlation warnings for constant backtest benchmarks.
- Normalize Alpha Vantage bulk rows that contain only extended-hours quote values.
- Correct v3 Trading Engine CI schema selection, enforce the engine's reducer-cap range,
  defensively copy scenario collections, reject invalid JSON indentation values, and preserve
  subprocess diagnostics that contain malformed UTF-8.
- Raise the Pillow, PyMdown Extensions, Requests, and pytest dependency floors and refresh the
  lock to patched releases.
- Pin CI checkout, uv setup, and OCaml setup actions to current supported releases without
  persisting checkout credentials.
- Consolidate installed-wheel smoke coverage into the complete verification gate. The isolated
  check now covers every public top-level namespace, exact package metadata, and the typing
  marker.
- Correct the 4.0.0 version-assurance statement and add automated agreement checks for project,
  lockfile, changelog, documentation, installed distribution, and release-tag versions.

## 4.0.0 — 2026-08-08

- Version 4 replaces the version 3 research platform with a provider-neutral library for
  primary financial data and explicit quantitative research. The public data model covers
  bars, quotes, top-of-book snapshots, historical options, scalar and vintage series, exchange
  rates, commodity spot quotes, and provider reference data.
- Alpha Vantage acquisition covers the supported primary market and economic families with
  entitlement-aware quotes, strict normalized schemas, redacted diagnostics, bounded rate
  limiting, raw caching, refresh, and offline replay. Provider analytics, fundamentals,
  ownership, news, and textual data remain outside the package boundary.
- FRED and ALFRED acquisition covers series definitions, native-frequency source levels,
  bounded revision histories, and paginated vintage dates. Daily source availability intervals
  preserve revisions, deletions, numeric missingness, and retrieval provenance.
- DuckDB storage persists and filters every normalized result family with content-derived
  snapshot identities and retrieval-time revisions. Explicit transforms reshape, align,
  bounded-as-of join, and resample data without silently filling observations.
- Point-in-time research selects vintages under explicit availability, publication-lag,
  observation-date, and staleness policies. Typed feature panels, forward labels, purged and
  embargoed splits, regime summaries, and portable manifests keep provenance, horizons,
  parameters, environments, randomness, execution state, and artifact checksums visible.
- Cross-sectional research supports ranking, clipping, standardization, exposure and
  time-varying group neutralization, Pearson and rank information coefficients, group
  summaries, equal-weight quantiles, spreads, turnover, capacity diagnostics, benchmark
  comparisons, repeated-search corrections, and controlled stability studies.
- Portfolio research constructs equal and signal-proportional long-only or long-short targets
  with gross, net, position, turnover, covariance, volatility, and cash controls. Vectorized
  backtests enforce causal timing, explicit missing and nontradeable policies, linear costs,
  cash and leverage accounting, attribution reconciliation, and caller-defined benchmarks.
- Matplotlib helpers cover normalized market, option, and economic data; general analysis;
  signal research; portfolio construction; and backtests. Plots use readable temporal labels,
  non-color distinctions, visible coverage, explicit scale handling, and caller-owned axes.
- The documentation suite provides offline tutorials, task-focused guides, a snippet cookbook,
  conceptual explanations, exact normalized schemas, generated public API references, release
  assurance, checked cross-references, and executable offline examples.
- The runtime depends only on NumPy, pandas, Matplotlib, Requests, platformdirs, and DuckDB.

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
