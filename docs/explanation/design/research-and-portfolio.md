# Design reference: research and portfolio

This page describes the implemented behavior of the research-dataset, feature/label,
alpha-validation, forecast, risk, and portfolio-construction subsystems.

## Research datasets, features, and labels

Research datasets are immutable tables at exact `(decision_at, instrument_id)` grain.
Each build binds a snapshot, a dual cutoff (public availability and project knowledge),
missing-input policies, and eligibility/input audits, and is addressed by content
identity so an exact retry reuses the existing build. Bounded result handles raise rather
than truncate.

Features and labels form a unified DAG on separate physical schemas. Registered
executable operators must supply an execution kernel; managed operators lacking one are
rejected at registration. Materializations record exact identity and persist
decision-input manifests. Temporal conformance is structural: label values and roots,
retrospective roots, and unreleased fits cannot enter decision data under any override,
and fitted forecast/risk rows require the exact causal-release boundary.

Bounded SQL workspaces parse DuckDB-compatible read-only SQL with SQLGlot, perform static
lineage and safety analysis, and carry resource limits and cancellation. Derived columns
inherit the strictest ancestry classification of their inputs, so label, retrospective,
or opaque ancestry cannot be laundered through SQL.

## Alpha diagnostics and validation

The registered executable alpha diagnostics compute coverage, Pearson/Spearman
information coefficients, quantile spreads, monotonicity, persistence, turnover, decay,
autocorrelation, and exposure/regime slices with dependence-aware inference. Validation
provides expanding, rolling, and combinatorial-purged memberships over exact closed
information intervals. Nested selection, a sealed final-holdout capability with a
contamination ledger, and sklearn splitter adapters are not implemented.

## Forecasts, risk, and construction

Forecasts are registered direct finite linear transforms with row state and safety
lineage — not fitted estimators, preprocessing pipelines, model selection, or forecast
combination. Risk models are sample, EWMA, and fixed-shrinkage covariance estimators with
explicit estimate states and a PSD policy — not factor models or user-supplied
covariance.

Portfolio construction supports rank signals, equal-weight construction, and convex
gross/net/max-weight/risk/turnover optimization through CVXPY. Every solver result is
independently verified; solver failure is structured and visible by default, with
fallbacks only when explicitly configured and recorded. Sector/factor/tracking-error/ADV
constraint families, an expected-cost model, and a multi-strategy allocator are not
implemented. Decision inputs are validated for temporal and opaque-ancestry safety before
construction consumes them.
