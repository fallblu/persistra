# Changelog

## Unreleased

- Split Trading Engine journal parsing, schema validation, reducer state, and reconciliation into
  focused components, and attach safe line, sequence, event ID, and event type context to journal
  validation failures.
- Add a deterministic, pluggable Monte Carlo research framework with stable per-path random
  streams, calibrated and bootstrap models, bounded metrics, convergence diagnostics, optional
  path retention, threaded batches, and portfolio-backtest evaluation.
- Add probabilistic and deflated Sharpe diagnostics with explicit frequency, search count,
  cross-trial dispersion, nonnormality inputs, intermediate estimates, and unavailable reasons.
- Add sample, shrinkage, Ledoit-Wolf, EWMA, and supplied factor covariance policies plus causal
  rolling and expanding risk forecasts with typed unavailable steps and manifest parameters.
- Add caller-weighted quantile portfolios with explicit coverage and effective membership, plus
  scalar, asset, and dated linear transition costs with gross, net, and spread reconciliation.
- Add nested expanding and rolling temporal validation with explicit outer and inner train,
  evaluation, purge, and embargo indexes that prevent model-selection leakage.
- Model time-varying investable universes with sourced membership intervals, explicit missing and
  delisting policies, panel masking without forward fill, and manifest-ready content identity.
- Publish the strict research-manifest v1 JSON Schema, record overridable Python and platform
  provenance, and verify declared artifacts safely with structured filesystem diagnostics.
- Execute portable provider-request plans sequentially with durable success checkpoints, explicit
  resume and partial-failure reports, optional DuckDB persistence, and acquisition manifests.
- Import caller-owned CSV, Arrow IPC, and Parquet files into every stored normalized result
  family through explicit mappings, caller-declared semantics, dry validation, and file provenance.
- Add paginated FRED series search and typed category, release, and tag context with shared cache,
  error, schema-diagnostic, and provenance behavior.
- Export exact snapshots and cumulative stored datasets to atomic Arrow IPC or Parquet files with
  explicit provenance sidecars, stable hashes, and overwrite protection.
- Add referentially complete instrument catalogs with venue listings, exact provider mappings,
  and explicit idempotent DuckDB persistence.
- Persist FRED vintage-date results and add typed quote, top-of-book, option-chain, and generic
  snapshot-history queries with explicit recurrence, retrieval chronology, and provenance diffs.
- Replace the complete Matplotlib plotting API and browser-inspector rendering path with
  caller-owned interactive Plotly figures, including named subplots for composite views.
- Enforce reviewed `main` and `develop` branch safeguards and align GitHub merge behavior with the
  documented feature, release, and hotfix workflow.
- Add concise issue and pull-request intake, a reviewed component and triage taxonomy, and a
  complete public repository profile while disabling unused wiki and Projects surfaces.
- Establish a security baseline with private reporting guidance, Dependabot proposals, CodeQL
  analysis, and dependency review for newly introduced moderate-or-higher vulnerabilities.
- Pin required Trading Engine compatibility checks to a reviewed commit with an explicit
  advancement process, and cancel superseded pull-request and unprotected-branch CI without
  interrupting tag or protected-branch verification.
- Validate every documented normalized schema against authoritative runtime columns, dtypes,
  required values, keys, ordering, and invariants, and check external HTTPS links on an isolated,
  bounded schedule with a reviewed exception policy.
- Publish the canonical documentation through a develop-only GitHub Pages workflow, retain a
  bounded MkDocs 1 and Material 9 toolchain until migration parity is proven, and modernize
  package licensing, project URLs, and rendered README metadata.
- Add exact-count, stably sorted cumulative store pages and bound inspector table and plot
  payloads, with dependency-aware lazy option rendering and released least-recently-used panes.
- Add family-specific cumulative inspector filters and manual rediscovery that preserves valid
  selections while reporting added, removed, or newly invalid stores.
- Add deterministic human and versioned JSON store inventories to the base command-line package,
  including project metadata, discovery warnings, schema versions, and dataset snapshot bounds.
- Add read-only DuckDB content verification and explicit project validation with stable human and
  versioned JSON diagnostics for manifests, layout, stores, and dependency declarations.
- Split visualization and browser-inspector dependencies from the base package, derive research
  environment inventories from installed package metadata, and verify intentional source archive
  contents plus clean base, visualization, inspector, and source-built wheel installations.
- Quantize the documented cash-reserve overlay toward zero at six decimal places and state the
  engine-representable overlay contract.
- Preserve gaps when plotting nullable quantile-capacity results by converting missing values to
  NumPy floating missingness.
- Normalize compatible datetime resolutions during bounded as-of alignment while preserving
  input timezone and label contracts.
- Reject empty Alpha Vantage JSON objects before caching and retry them with the bounded
  provider-response policy.
- Decode versioned Trading Engine diagnostics by stable code, attach typed context and causes to
  process errors, and retain bounded rejected-response evidence without accepting it as a valid
  transcript exchange.
- Accept additive Trading Engine capability fields, validate versioned resource limits when
  advertised, and preserve those limits in replay manifests.
- Enforce unambiguous identities, labels, indexes, and timestamp conventions across data
  pivoting, alignment, as-of matching, and bar resampling transforms.
- Isolate true-range paths by normalized bar identity and enforce finite, non-boolean economic
  analysis inputs without emitting infinite growth rates.
- Reject portfolio construction, target, and market panels that contain no observation dates.
- Reconcile external strategy portfolio weights with protocol v3 marked values and enforce UTC,
  microsecond-precision timestamps across composite forecasts.
- Reconcile journal scenario models with the canonical JSON Lines artifact identity used by
  model-based Trading Engine runs while preserving exact path-byte validation.
- Preserve every DuckDB acquisition occurrence so recurring content, historical cutoffs, and
  cumulative row revisions follow retrieval chronology without duplicating snapshot content.
- Make DuckDB store creation atomic, close connections after every schema validation failure,
  and preserve primary save errors when transaction rollback fails.
- Normalize raw-cache filesystem failures and cross-provider offline misses as `CacheError`, and
  reject every cache entry timestamped later than the supplied clock.
- Normalize provider error and Requests failure surfaces, honor bounded `Retry-After` guidance,
  add explicit provider-client session lifecycles, and reject invalid request-token capacities.
- Define shared missing, one-sided, locked, and crossed bid-ask semantics across market, option,
  and exchange-rate results while diagnosing exceptional quotes without hiding signed spreads.
- Enforce integer types and explicit bounds for analysis counts, research windows and lags,
  portfolio timing and solver iterations, and synthetic observation counts.
- Publish research manifests through fsynced private files with explicit overwrite control, and
  coordinate Trading Engine journal, transcript, and manifest publication with safe rollback.
- Terminate timed-out Trading Engine process groups gracefully and then forcibly while retaining
  final subprocess output and partial replay diagnostics.
- Restore the pre-command filesystem after interrupted project initialization, including private
  database staging and sidecars, without deleting pre-existing or concurrently replaced paths.
- Make inspector startup use an operating-system-assigned port, report the bound URL, reject
  occupied explicit ports, and create isolated Panel state for every browser session.
- Report recursive inspector discovery failures while continuing through readable sibling
  directories in deterministic order.
- Describe DuckDB store creation and opening against the current supported schema contract.
- Serialize inspector filesystem values at the browser boundary and refresh snapshot choices from
  the complete store, family, and scope context.

## 4.1.2 — 2026-08-21

- Upgrade the external strategy boundary to protocol v3 so callbacks use current slice state and
  strategy responses take effect before matching continues.
- Deeply freeze portable result provenance and research manifests, recursively remove API keys
  from metadata and raw-cache parameters, and reject unsupported values before persistence.
- Enforce nonblank identity fields and coherent normalized result scope, provider, retrieval,
  entitlement, and descriptive fields; revalidate mutable results before DuckDB persistence;
  and reject nonfinite instrument-search scores.
- Preserve explicitly missing FRED latest observations as dated numeric missingness through
  analysis, reshaping, caching, and storage.
- Enforce one aligned temporal sample and a validated point-in-time boundary for factor risk
  models.
- Preserve schema-correct research labels, signal evaluations, and quantile diagnostics for
  zero-date panels.

## 4.1.1 — 2026-08-16

- Add a standardized non-packaged uv project layout, strict versioned project manifest, explicit
  path API, and transactional `persistra init` command.
- Preserve local Persistra checkout paths and editable status in projects created by the
  initializer so `uv sync` resolves the same source.
- Add an optional loopback-only browser inspector for exact acquisition snapshots, cumulative
  retained datasets, normalized tables, visualizations, and provenance in local DuckDB stores.
- Show an informational empty state instead of crashing when the browser inspector opens a store
  that contains no saved datasets.

## 4.1.0 — 2026-08-16

- Reorganize the documentation around strategy development and Trading Engine replay, replace
  the tutorial and snippet sections with categorized executable examples, and add a strategy-first
  getting-started path.
- Add a solver-neutral continuous optimization boundary with SLSQP as the default backend,
  normalized solver statistics, asymmetric linear costs, and quadratic market-impact costs.
- Add named generic linear exposure constraints and explicit covariance shrinkage and eigenvalue
  flooring with recorded conditioning diagnostics.
- Add ordered portfolio optimization paths with carried positions and explicit failure handling,
  plus composite strategy guards for target drift and outstanding orders.
- Add a target-oriented composite strategy pipeline with alpha models, forecast combination,
  portfolio construction, sequential target overlays, aggregated warmup, and decision traces.
- Add point-in-time factor portfolio forecasts with explicit alpha and premia inputs, expected
  return decomposition, and active or absolute factor return and risk attribution.
- Add caller-defined time-series, rolling, cross-sectional, and Fama-MacBeth factor
  regressions with explicit inference, diagnostics, residuals, and factor-risk covariance.
- Add solver-independent portfolio problems with typed variance, expected-return, tracking-error,
  weight, exposure, turnover, factor, and transaction-cost components and verified diagnostics.
- Upgrade external strategies to protocol v2 marked portfolios and add a reusable base strategy
  with bounded history, observation and elapsed warmup, per-security readiness, fixed-catalog
  selection, independent schedules, universe-removal policies, lifecycle hooks, and complete
  target helpers. Persistra validates retained transcripts and binds the strategy executable,
  declared inputs, transcript, journal, and scenario into the run manifest.
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
