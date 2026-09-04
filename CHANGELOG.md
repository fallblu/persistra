# Changelog

## Unreleased

- Version DuckDB stores independently from normalized frames and provide non-destructive v1-to-v2
  migration with durable snapshot and occurrence lineage.

## 4.3.0 — 2026-08-31

- Produce complete typed Trading Engine initial-state scenarios with financing, settlement, and
  reconciled risk-group exposure evidence.
- Enforce Trading Engine distribution-action and lifecycle-reason semantics before serialization.
- Preserve identifiable factor-model inference when one or more supplied factors are constant.
- Bind resumed acquisition checkpoints to retained store snapshots and enforce causal success
  timestamps.
- Support credential-free provider cache replay and add bounded FRED response-error context.
- Add explicit, auditable quarantine recovery for isolated Alpha Vantage bar and option rows.
- Preserve Alpha Vantage intraday labels and mark their undocumented candle position as
  explicitly unspecified.
- Add bounded property tests and duplicate-field rejection across untrusted JSON artifact
  boundaries.
- Add deterministic runtime and memory benchmarks with controlled regression thresholds.
- Add CycloneDX SBOMs and signed SLSA provenance for human-triggered release builds.
- Add scheduled, redacted live certification for Alpha Vantage, FRED, and ALFRED.

## 4.2.0 — 2026-08-26

- Reset maintained research manifests, DuckDB stores, inspection inventories, and Trading Engine
  adapters to one strict v1 contract; remove historical schemas and the superseded replay,
  strategy-hosting, bundle, journal-analysis, and visualization surfaces.
- Add schema-backed Trading Engine v1 adapters for explicit initial portfolios, instrument and
  grouped risk, fee schedules, financing, settlement, venue calendars, lifecycle events, causal
  quotes and trades, and bounded order books.
- Expand point-in-time research with nested temporal validation, factor covariance and risk
  forecasts, probabilistic diagnostics, Monte Carlo experiments, investable universes, and strict
  model provenance.
- Expand portfolio research with solver-neutral optimization, grouped and factor constraints,
  robust and tail-risk objectives, transaction costs, multi-currency accounting, corporate
  actions, and reconciled performance attribution.
- Expand normalized acquisition and storage with provider reference data, vintage histories,
  import and export, durable request plans, exact cumulative queries, and read-only verification.
- Replace static plotting with caller-owned Plotly figures and improve the local inspector,
  project tooling, documentation, packaging, security checks, and failure diagnostics.

## 4.1.2 — 2026-08-21

- Maintenance release before the v1 contract reset.
