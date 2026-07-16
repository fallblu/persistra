# Focused specification 15: results, analysis, metrics, attribution, comparison, and export

**Status:** Implementation-ready draft  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Primary packages:** `persistra.results`, `persistra.analysis`  
**Required before:** focused specifications 16–18  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines durable result publication and immutable post-run analysis. It
fixes normalized run/result schemas, worker-artifact merge, analysis identity and attempts,
metrics, attribution, execution/capacity analysis, comparison, diagnostics, annotations,
logs, deletion/archive, standalone DuckDB export, and storage compatibility.

Plans 01–14 remain normative. This plan copies and indexes their completed immutable
outputs without recalculating simulator facts, changing order/accounting history, or
substituting compatible reuse identities. Plans 16–17 consume only the public result and
analysis APIs specified here. Plan 18 owns cross-version fixtures and benchmark enforcement.

## 2. Scope

### 2.1 In scope

- Verification, staging, and atomic publication of Plan-14 worker artifacts
- Immutable run/artifact registry and exact normalized result relations
- Bounded result handles and stable dataframe schemas
- Immutable analysis definitions, attempts, artifacts, dependencies, and unavailable states
- Return, risk, benchmark, exposure, turnover, cost, capacity, and stability metrics
- Holdings/transaction, classification, factor, strategy, long/short, cost, and benchmark
  attribution
- Execution analysis with observed-versus-estimated provenance
- Versioned comparison compatibility and normalized differences
- Registered scalar/time-series/cross-sectional/event/tabular diagnostics
- Structured logs, mutable annotations kept outside identity, reference-aware archive/delete
- Self-contained DuckDB exports and optional HTML/static-asset directory handoff
- Versioned Parquet manifest interoperability/recovery bundle; bounded CSV table export

### 2.2 Out of scope

- Re-running a simulator during result import or analysis
- Mutating a completed run or prior analysis artifact
- Computing finance metrics inside Plotly, reports, Streamlit, or SQL views with different
  semantics
- Treating missing observations as estimates without an explicit estimator and provenance
- A generic data lake, arbitrary user DDL, remote artifact registry, or hosted result service
- Guaranteeing arbitrary DuckDB forward compatibility or treating Parquet as native storage
- Plot/report/dashboard layout, static browser rendering, or notebook-only result logic

## 3. Normative decisions

1. A Plan-14 `ArtifactIdentity` is the immutable source-output identity. Publication creates
   a project-local `RunRecordId` and relationship; it never creates a new execution/artifact
   identity or rewrites compatible reuse as exact execution.
2. Only completed, reconciled, verified Plan-12/13 occurrences can publish as runs. Failed or
   interrupted attempts publish experiment outcomes/log evidence, not a completed run.
3. Merge is staged and verified inside one research database transaction after the source
   file is independently verified read-only. Source-file and destination publication are not
   cross-file ACID.
4. Completed run rows, normalized simulator/accounting facts, manifests, and table roots are
   append-only. Corrections create a new execution/attempt/artifact.
5. Post-run metrics, attribution, comparisons, diagnostics, and reports are immutable analysis
   artifacts. Recalculation creates a new artifact and never appends to a run.
6. Analysis identity includes exact input run/analysis artifact identities, definitions,
   policies, selected slices, code/dependencies, safety/fidelity, and output schema. It
   excludes attempt ID and derived output root.
7. Structured unavailable results are first-class. Stored rows retain state/reason/warnings;
   a display-layer `NaN` never erases them.
8. Every financial estimate stores unit, interval, observation count, frequency/annualization,
   required benchmark/risk-free/cash-flow policy, warnings, and method/version.
9. Actual elapsed UTC time is the default performance annualization basis. Statistical
   frequency estimators declare their exact schedule/day convention.
10. External capital flows are distinguished from portfolio income/trading. Time-weighted
    return chains exact subperiod returns split at flow boundaries; money-weighted return uses
    exact dated external flows and terminal value.
11. Attribution reconciles to its declared return/P&L basis within tolerance or is unavailable;
    residual is explicit and never silently redistributed.
12. Execution fields remain observed, estimated, modeled, or unavailable. A missing quote or
    arrival price cannot be replaced by an unmarked estimate.
13. Run comparison is a versioned compatibility decision, not a chart option. Data/fold/
    benchmark/cash-flow/simulator/fidelity differences can make a comparison incompatible.
14. User annotations are the only mutable run-associated data. They live in separate tables,
    carry revision/audit history, and never affect run or analysis identity.
15. Portable export is closed over selected immutable dependencies and contains no unresolved
    local file/relation reference, generated secret, or credential.
16. Export format version and DuckDB storage version are separate. Each Persistra release
    pins a tested storage-compatibility target rather than using `latest` implicitly.
17. A native DuckDB file is readable only within the published Persistra/DuckDB matrix.
    Incompatible files are migrated by verified copy into a new file; originals are unchanged.
18. CSV is table-level interoperability with explicit schema sidecar. Parquet bundles are
    versioned manifest recovery/interoperability outputs, not native run artifacts in 3.0.
19. Queries/materializations are ordered, bounded, and explicit about truncation. Empty frames
    retain schema/dtypes. Public APIs never expose writable DuckDB connections or table names.
20. Safety, licensing, temporal conformance, fidelity, compatibility warnings, and provenance
    propagate monotonically into analysis and export.

## 4. Identity and lifecycle model

### 4.1 Assigned IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `RunRecordId` | `run_record` | Project-local registration of one source artifact |
| `RunPublicationId` | `run_publication` | One staged/verified/committed publication attempt |
| `AnalysisDefinitionId` | `analysis_definition` | Stable versioned analysis lineage |
| `AnalysisAttemptId` | `analysis_attempt` | One calculation attempt |
| `AnalysisArtifactId` | `analysis_artifact` | Assigned occurrence referring to content identity |
| `ComparisonDecisionId` | `comparison_decision` | One immutable compatibility classification |
| `DiagnosticSchemaId` | `diagnostic_schema` | Stable versioned registered diagnostic schema |
| `ExportAttemptId` | `export_attempt` | One portable-export attempt |
| `AnnotationId` | `annotation` | One mutable annotation lineage |

Plan-14 `ArtifactIdentity`, `ExecutionIdentity`, `DesignIdentity`, and `AttemptId` remain
authority. Assigned analysis artifact IDs make relationships ergonomic; each completed row
also has a unique content-addressed `analysis_artifact_content_id` over its manifest.

### 4.2 Lifecycles

- Publication: `planned`, `staging`, `verifying`, `committed`, `failed`
- Analysis attempt: `planned`, `running`, `completed`, `failed`, `cancelled`
- Analysis artifact: published atomically only as `completed`
- Export attempt: `planned`, `writing`, `verifying`, `completed`, `failed`
- Run retention: `active`, `archived`, `deletion_requested`, `deleted_tombstone`

A failed publication/analysis/export retains bounded attempt evidence but no completed content
identity. Completion states are immutable. Retention changes do not edit source facts.

## 5. Package and database ownership

```text
src/persistra/
├── results/
│   ├── models.py
│   ├── repository.py
│   ├── publication.py
│   ├── queries.py
│   ├── annotations.py
│   ├── retention.py
│   ├── exports.py
│   └── compatibility.py
└── analysis/
    ├── models.py
    ├── artifacts.py
    ├── performance.py
    ├── risk.py
    ├── benchmark.py
    ├── exposure.py
    ├── execution.py
    ├── attribution.py
    ├── capacity.py
    ├── comparison.py
    ├── diagnostics.py
    └── scenarios.py
```

The research database owns migration-managed `results`, `result_data`, `analysis`,
`analysis_data`, and `annotations`. Existing Plan-11 `accounting`/`journal_data`, Plan-12/13
`simulation`/`simulation_data`, and Plan-14 `experiments`/`experiment_data` schemas are copied
with their semantics and linked by immutable manifest; they are not flattened into one
untyped result table.

Publication, analysis publication, annotation mutation, archive/delete, and export registry
changes require `RESEARCH_WRITE` and an exclusive research lease. Bounded queries/export
reads may use read-only/shared mode subject to Plan-02 writer exclusion. An export is written
to a staged new file outside the database transaction, verified, then registered atomically.

## 6. Worker artifact publication

### 6.1 Source verification

Plan 14 supplies a closed read-only source file and handoff manifest. Before staging, Plan 15
recomputes database role/disposable state, schema/migration versions, design/execution/attempt/
simulator occurrence/artifact identities, completion state, event/order/fill/accounting
closure, table schemas/counts/logical roots, file checksum/size, safety/licensing/fidelity,
and absence of unresolved external relations.

The source artifact manifest enumerates every authoritative table with schema content ID,
canonical row order/key, row count, chunk roots, aggregate root, and required/optional role.
Unknown required tables/columns or missing declared data reject publication. Versioned optional
forward fields can be preserved only under a registered compatible schema policy.

### 6.2 Transactional staging and commit

Inside one destination transaction:

1. allocate `RunPublicationId` and internal staging namespaces;
2. insert immutable registry/identity/provenance/fidelity/safety manifests;
3. copy each source relation in canonical bounded chunks into fixed destination relations;
4. recompute destination schema/count/chunk/aggregate roots;
5. validate every foreign key, sequence, lifecycle, quantity, journal, valuation, and manifest
   closure required by Plans 11–14;
6. compare destination logical roots with the source manifest;
7. publish `RunRecordId`, artifact-table relationships, and committed transition atomically;
8. remove staging objects before commit.

Any failure rolls back the entire destination transaction. The source file remains intact.
Concurrent publication of the same artifact resolves to one verified run record and one
relationship per run plan; a conflicting root is corruption. Physical row grouping/file bytes
may differ while canonical logical roots remain equal.

### 6.3 Compatible reuse publication

Plan-14 compatible reuse adds a study/run-plan relationship to the original `RunRecordId` and
stores the exact `ReuseDecisionId`, requested execution identity, policy, differences, and
warning. It does not copy output, create a completed attempt for the requested execution, or
change the source run's fidelity/provenance.

## 7. Run registry and normalized result contract

### 7.1 Registry schema

```sql
CREATE TABLE results.runs (
    run_record_id UUID PRIMARY KEY,
    artifact_manifest_content_id VARCHAR NOT NULL UNIQUE,
    source_attempt_id UUID NOT NULL,
    design_identity_content_id VARCHAR NOT NULL,
    execution_identity_content_id VARCHAR NOT NULL,
    simulator_kind VARCHAR NOT NULL CHECK (simulator_kind IN ('vectorized', 'event')),
    simulator_occurrence_id UUID NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('completed')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    fidelity_profile_id UUID NOT NULL,
    provenance_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    table_manifest_content_id VARCHAR NOT NULL,
    warning_manifest_content_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (interval_start <= interval_end)
);

CREATE TABLE results.run_retention (
    run_record_id UUID PRIMARY KEY,
    retention_state VARCHAR NOT NULL CHECK (
        retention_state IN ('active', 'archived', 'deletion_requested', 'deleted_tombstone')
    ),
    current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
    decision_content_id VARCHAR NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE results.run_retention_history (
    run_record_id UUID NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    prior_state VARCHAR,
    new_state VARCHAR NOT NULL CHECK (
        new_state IN ('active', 'archived', 'deletion_requested', 'deleted_tombstone')
    ),
    decision_content_id VARCHAR NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_record_id, revision)
);

CREATE TABLE results.run_relationships (
    run_record_id UUID NOT NULL,
    run_plan_id UUID NOT NULL,
    relationship_kind VARCHAR NOT NULL CHECK (
        relationship_kind IN ('executed', 'reused_exact', 'reused_compatible')
    ),
    reuse_decision_id UUID,
    requested_execution_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR,
    PRIMARY KEY (run_record_id, run_plan_id),
    CHECK ((relationship_kind = 'reused_compatible') = (warning_content_id IS NOT NULL))
);

CREATE TABLE results.artifact_tables (
    run_record_id UUID NOT NULL,
    table_ordinal INTEGER NOT NULL CHECK (table_ordinal >= 1),
    logical_table_kind VARCHAR NOT NULL,
    schema_content_id VARCHAR NOT NULL,
    canonical_order_content_id VARCHAR NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    chunk_manifest_content_id VARCHAR NOT NULL,
    aggregate_content_id VARCHAR NOT NULL,
    required BOOLEAN NOT NULL,
    PRIMARY KEY (run_record_id, table_ordinal),
    UNIQUE (run_record_id, logical_table_kind)
);
```

### 7.2 Fixed result series

All instants are UTC, currencies USD, quantities/prices exact Plan-01 decimals, and floating
analysis inputs stored with explicit finite-state validation. Every row is keyed by
`run_record_id` and stable ordinal/natural key. Core fixed relations are:

- `result_data.equity`: valuation instant, journal prefix, NAV, gross/net/external-flow,
  completeness/quality, valuation and state IDs;
- `result_data.returns`: exact subperiod boundaries, opening/closing NAV, external flows,
  return state/value/basis and source roots;
- `result_data.positions`: instant, instrument, signed settled/unsettled quantity, price,
  market value, long/short/gross/net exposure, mark quality, lot/state roots;
- `result_data.cash`: economic/settled available/restricted/receivable/payable/accrued values;
- `result_data.exposures`: instant, taxonomy/factor/benchmark/strategy component, unit/value,
  source and availability;
- `result_data.targets` and `result_data.rebalances`: Plan-10/12 intent, rounded/scaled/filled
  quantities, constraints, failures, and shortfall without order invention;
- `result_data.orders`, `order_transitions`, and `fills`: exact Plan-13 lifecycle/progress/
  observed-model roots; vectorized runs have no order rows;
- `result_data.synthetic_fills`: exact Plan-12 fill semantics, never projected as orders;
- `result_data.cost_components`: fill/synthetic-fill source, component kind, observed/estimated/
  modeled state, amount/unit/sign/root;
- `result_data.settlements`, `lots`, `borrow`, `margin`, `corporate_actions`, and `cash_flows`:
  exact Plan-11 normalized projections and source IDs;
- authoritative journal/accounting relations remain normalized in their copied fixed schemas;
- `result_data.quality_findings`, `fidelity_findings`, and `lifecycle_events`: bounded structured
  reasons/evidence/counts/roots; and
- study/trial/fold/scenario/attempt relationships remain Plan-14 normalized metadata.

### 7.3 Core series schema

```sql
CREATE TABLE result_data.equity (
    run_record_id UUID NOT NULL,
    sample_ordinal BIGINT NOT NULL CHECK (sample_ordinal >= 1),
    valued_at TIMESTAMPTZ NOT NULL,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    valuation_id UUID NOT NULL,
    portfolio_state_id UUID,
    nav_usd DECIMAL(38, 12),
    external_flow_usd DECIMAL(38, 12) NOT NULL,
    gross_exposure_usd DECIMAL(38, 12),
    net_exposure_usd DECIMAL(38, 12),
    state VARCHAR NOT NULL CHECK (state IN ('complete', 'incomplete', 'unavailable')),
    quality_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (run_record_id, sample_ordinal),
    UNIQUE (run_record_id, valued_at, journal_prefix_sequence),
    CHECK ((state = 'complete') = (nav_usd IS NOT NULL))
);

CREATE TABLE result_data.returns (
    run_record_id UUID NOT NULL,
    return_ordinal BIGINT NOT NULL CHECK (return_ordinal >= 1),
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    opening_nav_usd DECIMAL(38, 12),
    closing_nav_usd DECIMAL(38, 12),
    external_flow_usd DECIMAL(38, 12) NOT NULL,
    return_value DOUBLE,
    state VARCHAR NOT NULL CHECK (
        state IN ('computed', 'missing_opening', 'missing_closing', 'nonpositive_base', 'invalid_numeric')
    ),
    flow_timing_policy_content_id VARCHAR NOT NULL,
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (run_record_id, return_ordinal),
    CHECK (interval_start < interval_end),
    CHECK ((state = 'computed') = (return_value IS NOT NULL))
);

CREATE TABLE result_data.cost_components (
    run_record_id UUID NOT NULL,
    cost_ordinal BIGINT NOT NULL CHECK (cost_ordinal >= 1),
    source_kind VARCHAR NOT NULL CHECK (source_kind IN ('fill', 'synthetic_fill', 'accrual')),
    source_id UUID NOT NULL,
    component_kind VARCHAR NOT NULL CHECK (
        component_kind IN ('commission', 'regulatory_fee', 'spread', 'slippage', 'delay', 'impact', 'borrow', 'financing')
    ),
    evidence_state VARCHAR NOT NULL CHECK (
        evidence_state IN ('observed', 'estimated', 'modeled', 'accounted_direct', 'unavailable')
    ),
    amount_usd DECIMAL(38, 12),
    unit VARCHAR NOT NULL,
    component_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (run_record_id, cost_ordinal),
    CHECK ((evidence_state <> 'unavailable') = (amount_usd IS NOT NULL))
);
```

Run manifests declare whether each logical table is applicable, empty, unavailable, or
present. Absence is never guessed from zero rows. Vectorized order tables are
`not_applicable_vectorized`, while missing required vectorized fills are incomplete.
Equity and external-flow-split return rows are copied from exact Plan-12/13 committed
sampling output; publication does not derive them. Any alternate flow timing, sampling, or
return basis is a separately identified analysis artifact.

## 8. Result query API

```python no-run
run = project.results.get(run_record_id)
run.summary()
run.equity(limit=100_000)
run.positions(at=instant, instruments=ids, limit=100_000)
run.orders(statuses=("cancelled",), limit=100_000)
run.fills(limit=100_000)
run.fidelity()
run.provenance()
```

`RunHandle` is immutable and can represent archived metadata or a deleted tombstone. Queries
have typed filters, canonical order, total/requested/returned counts, pagination cursor bound
to run/table/root, and explicit pandas materialization. `to_pandas()` fails above the direct
frame limit; streaming yields bounded typed chunks. Empty frames preserve exact columns and
dtypes. Preview truncation is labeled and cannot feed analysis without explicit acceptance.

## 9. Immutable analysis artifacts

### 9.1 Request and identity

```python no-run
@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    definition: AnalysisDefinitionRef
    inputs: tuple[RunRef | AnalysisArtifactRef, ...]
    configuration: AnalysisConfig
    output_policy: AnalysisOutputPolicy
    unsafe_override: UnsafeAnalysisOverride | None
    limits: AnalysisLimits
```

Analysis execution content includes exact input artifact/run roots, selected tables/slices,
definition/version/config, metric/attribution/comparison policies, benchmark/rate/taxonomy
inputs and cutoffs, implementation/code/dependencies/platform where behavior-affecting,
numeric/frequency/time conventions, safety/licensing/fidelity folds, limits, and output schema.
It excludes allocated attempt/artifact IDs and derived output roots.

Exact completed replay verifies and returns the existing artifact under the same execution
content. Plan-14 compatible reuse may link only under a dedicated analysis compatibility
policy; it keeps source identity and warning. Analysis attempts execute under one research
transaction or stage bounded outputs and publish them atomically in that database.

### 9.2 Schema

```sql
CREATE TABLE analysis.analysis_artifacts (
    analysis_artifact_id UUID PRIMARY KEY,
    analysis_definition_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    execution_content_id VARCHAR NOT NULL,
    analysis_artifact_content_id VARCHAR NOT NULL UNIQUE,
    artifact_kind VARCHAR NOT NULL CHECK (
        artifact_kind IN ('metrics', 'attribution', 'execution', 'capacity', 'comparison', 'diagnostic', 'scenario_aggregate', 'report')
    ),
    input_manifest_content_id VARCHAR NOT NULL,
    configuration_content_id VARCHAR NOT NULL,
    implementation_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    fidelity_manifest_content_id VARCHAR NOT NULL,
    warning_manifest_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    completed_attempt_id UUID NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analysis.analysis_inputs (
    analysis_artifact_id UUID NOT NULL,
    input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
    input_kind VARCHAR NOT NULL CHECK (input_kind IN ('run', 'analysis')),
    run_record_id UUID,
    input_analysis_artifact_id UUID,
    input_content_id VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    PRIMARY KEY (analysis_artifact_id, input_ordinal),
    CHECK (
        (input_kind = 'run' AND run_record_id IS NOT NULL AND input_analysis_artifact_id IS NULL)
        OR
        (input_kind = 'analysis' AND run_record_id IS NULL AND input_analysis_artifact_id IS NOT NULL)
    )
);

CREATE TABLE analysis.analysis_attempts (
    analysis_attempt_id UUID PRIMARY KEY,
    execution_content_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('planned', 'running', 'completed', 'failed', 'cancelled')),
    analysis_artifact_id UUID,
    failure_content_id VARCHAR,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK ((status = 'completed') = (analysis_artifact_id IS NOT NULL))
);
```

Dependency graph insertion rejects cycles. Deleting/archiving input content observes all
analysis/report/export references.

## 10. Structured metrics

### 10.1 Metric result

```sql
CREATE TABLE analysis_data.metric_results (
    analysis_artifact_id UUID NOT NULL,
    metric_ordinal INTEGER NOT NULL CHECK (metric_ordinal >= 1),
    metric_name VARCHAR NOT NULL,
    metric_version INTEGER NOT NULL CHECK (metric_version >= 1),
    slice_content_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN ('computed', 'insufficient_observations', 'missing_input', 'invalid_base', 'undefined', 'nonunique_solution', 'invalid_numeric', 'incompatible')
    ),
    estimate DOUBLE,
    unit VARCHAR NOT NULL,
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    interval_start TIMESTAMPTZ,
    interval_end TIMESTAMPTZ,
    annualization_content_id VARCHAR NOT NULL,
    requirement_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR NOT NULL,
    confidence_low DOUBLE,
    confidence_high DOUBLE,
    confidence_method_content_id VARCHAR,
    reason_code VARCHAR,
    PRIMARY KEY (analysis_artifact_id, metric_ordinal),
    CHECK ((state = 'computed') = (estimate IS NOT NULL)),
    CHECK ((confidence_low IS NULL) = (confidence_high IS NULL)),
    CHECK (confidence_low IS NULL OR confidence_low <= confidence_high)
);
```

Metric names are qualified registered definitions. `unit` is a versioned controlled value
such as `rate`, `usd`, `days`, `sessions`, `count`, `ratio`, `shares`, or `usd_per_day`.
Convenience scalar access raises/returns structured unavailable by explicit caller policy;
dataframe display may show nullable `Float64`/`NaN` while preserving state/reason.

### 10.2 Return and performance rules

- Subperiod TWR uses exact valuation immediately before/after each external flow under the
  declared flow-timing policy. Each valid subperiod return is chained as
  `product(1 + r_i) - 1`; a missing/nonpositive base makes the affected aggregate unavailable.
- Money-weighted return solves the dated-cash-flow NPV including terminal value using actual
  elapsed year fractions and a registered bounded root finder. No root, multiple material
  roots, or nonconvergence is structured unavailable; selection is never arbitrary.
- Annualized return uses `(1 + total_return) ** (year_duration / elapsed_duration) - 1` only
  when the base is valid. Periods below the registered minimum emit a warning/unavailable
  policy rather than misleading extrapolation.
- Volatility and statistical ratios state sample estimator, observation schedule, missing
  policy, degrees of freedom, and annualization factor. Sharpe/Sortino use an exact aligned
  point-in-time risk-free series or declared zero assumption with warning.
- Drawdown is computed from a declared TWR/NAV index with deterministic peak/tie policy;
  depth, peak/trough/recovery instants, duration basis, and unrecovered state are stored.
- Calmar declares annual-return numerator and maximum-drawdown denominator intervals.
- VaR/expected shortfall state historical/parametric method, confidence, tail, weighting,
  minimum count, and sign convention. They are estimates, not guarantees.

### 10.3 Families

Required families include TWR/MWR, annual return/volatility, Sharpe/Sortino/Calmar, drawdown
depth/duration/recovery, tail loss/VaR/ES/skew/kurtosis, hit/payoff/distribution, alpha/beta/
active return/tracking error/information ratio, gross/net/classification/factor/relative
exposure, turnover/holding period/concentration, all cost categories, capacity/participation,
and fold/trial/scenario/regime stability. Each definition owns exact formula, requirement,
minimum sample, interval, units, version, and golden fixtures.

## 11. Attribution

Attribution requests select exact return/P&L basis, frequency, holdings timing, cash-flow
treatment, benchmark, taxonomy/factor model, strategy-component map, cost allocation, residual
policy, and interval. Point-in-time classifications and factor exposures use exact effective/
availability cutoffs; no current taxonomy backfill.

Initial models are:

- holdings contribution from beginning-of-subperiod exposure and instrument return;
- transaction contribution separated from holdings under exact timing/price policy;
- sector/industry roll-up of instrument contributions using point-in-time membership;
- factor exposure and contribution under a pinned Plan-10 factor/risk definition;
- strategy-component contribution from explicit owned intents/orders/fills/allocations;
- long, short, gross, net, and cash decomposition;
- direct and embedded execution/borrow/financing cost contribution; and
- benchmark-relative contribution with exact aligned benchmark and cash-flow policy.

Exact institutional Brinson variants are not claimed. Classification/factor gaps remain
unclassified/unavailable components. Every period stores portfolio return/P&L, summed
components, explicit residual, tolerance, state, and source root. Aggregated attribution
chains/links through a versioned arithmetic/geometric policy and must reconcile again.

```sql
CREATE TABLE analysis_data.attribution_components (
    analysis_artifact_id UUID NOT NULL,
    period_ordinal BIGINT NOT NULL CHECK (period_ordinal >= 1),
    component_ordinal BIGINT NOT NULL CHECK (component_ordinal >= 1),
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    attribution_kind VARCHAR NOT NULL,
    component_key_content_id VARCHAR NOT NULL,
    contribution DOUBLE,
    unit VARCHAR NOT NULL,
    state VARCHAR NOT NULL CHECK (state IN ('computed', 'unclassified', 'missing_input', 'unreconciled')),
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (analysis_artifact_id, period_ordinal, component_ordinal),
    CHECK (interval_start < interval_end),
    CHECK ((state = 'computed') = (contribution IS NOT NULL))
);
```

## 12. Execution and capacity analysis

For Plan-13 orders, analysis covers arrival-price slippage, spread cost, delay, modeled
impact, participation, fill rate, partial rate, cancellation/expiration/rejection, latency,
and implementation shortfall. For Plan-12, it covers synthetic implementation shortfall,
capacity clipping, target-to-filled shortfall, and modeled components but must not emit order
rates or queue claims.

Arrival is the exact eligible observed quote/trade/bar reference at the declared arrival
instant. If unavailable, the metric is unavailable unless a separately named estimator is
requested; its result stays `estimated`. Spread cost is observed only from an eligible quote;
bar estimator remains estimated. Impact remains modeled. Delay compares exact arrival and
execution references. Direct fees reconcile to general accounting; embedded costs reconcile
to memorandum entries. Cost totals cannot double count fill-price components.

Capacity analysis reports volume source/availability, participation, clipped/remainder,
liquidity regime/calibration, and scale curve assumptions. Daily-open current-session volume
is retrospective and prominently marked; default causal lagged/ADV capacity remains causal.

## 13. Comparison

### 13.1 Compatibility decision

A comparison request pins ordered inputs, comparison-policy version, metric/analysis artifacts,
alignment interval/frequency, benchmark/cash-flow/base-currency policy, and limits. It compares
snapshots, universes, date ranges, folds/roles, trial/scenario, benchmarks/rates, cash flows,
simulation level, fidelity fields, safety/licensing, metric definitions, and data completeness.

The decision is:

- `compatible`: all required identity/semantic fields equal or policy-proven equivalent;
- `comparable_with_warnings`: listed differences permit descriptive comparison with stored
  warnings and disabled claims; or
- `incompatible`: a material field makes requested inference/aggregation invalid.

Incompatible comparisons still return normalized differences but no authoritative combined
metric/chart-ready series. User override may request a visibly unsafe exploratory artifact;
it does not change classification.

```sql
CREATE TABLE analysis.comparison_decisions (
    comparison_decision_id UUID PRIMARY KEY,
    analysis_artifact_id UUID NOT NULL,
    policy_content_id VARCHAR NOT NULL,
    classification VARCHAR NOT NULL CHECK (
        classification IN ('compatible', 'comparable_with_warnings', 'incompatible')
    ),
    input_manifest_content_id VARCHAR NOT NULL,
    difference_manifest_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR NOT NULL,
    decision_content_id VARCHAR NOT NULL UNIQUE
);

CREATE TABLE analysis_data.comparison_differences (
    comparison_decision_id UUID NOT NULL,
    difference_ordinal INTEGER NOT NULL CHECK (difference_ordinal >= 1),
    field_path VARCHAR NOT NULL,
    left_content_id VARCHAR NOT NULL,
    right_content_id VARCHAR NOT NULL,
    severity VARCHAR NOT NULL CHECK (severity IN ('informational', 'warning', 'incompatible')),
    reason_code VARCHAR NOT NULL,
    PRIMARY KEY (comparison_decision_id, difference_ordinal)
);
```

### 13.2 Study/scenario aggregation

Fold/trial/scenario/Monte Carlo/bootstrap aggregation consumes exact Plan-14 hierarchy and
immutable metric artifacts. It reports coverage, failures/unavailable/not-scheduled outcomes,
distribution/interval method, dependence assumptions, selection/holdout state, and weighting.
It never averages only successful trials without reporting selection and failure counts.

## 14. Diagnostics and logs

Diagnostic definitions register one of `scalar`, `time_series`, `cross_sectional`, `event`,
or `tabular`, exact key/value columns/types/units/nullability/order, semantic version, limits,
and renderer hints that carry no calculations. Outputs live in fixed family relations or
migration-validated controlled tables; there is no universal untyped name/value store.

Run and analysis lifecycle logs are structured with instant, severity, component, event/
attempt IDs, stable reason, bounded safe context content ID, and optional external log-file
manifest. Verbose files must be selected into export or omitted explicitly. Secrets,
credentials, full licensed payloads, raw exception locals, and unrestricted paths are redacted.
Logs are evidence, not state authority.

## 15. Annotations, archive, deletion, and references

Annotations support note, label, and tag lineages. Each mutation requires expected revision,
actor token, instant, reason, and bounded content; immutable revision history is retained.
Annotation current state can change without changing run/analysis/export identity. Portable
export chooses an annotation revision cutoff and records it as mutable supplemental content.

Archive hides content from default lists but retains references and readability. Delete is
confirmation-gated, calculates the full inbound reference graph (studies, reuse edges,
analysis, reports, exports), and rejects unless dependents are selected under an explicit
safe cascade policy. Immutable shared artifacts are content-reference counted. Physical
deletion creates a tombstone containing identity, deletion decision/root, and no financial
payload. No API silently cascades.

```sql
CREATE TABLE annotations.annotations (
    annotation_id UUID PRIMARY KEY,
    subject_kind VARCHAR NOT NULL CHECK (subject_kind IN ('run', 'analysis')),
    run_record_id UUID,
    analysis_artifact_id UUID,
    annotation_kind VARCHAR NOT NULL CHECK (annotation_kind IN ('note', 'label', 'tag')),
    current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (subject_kind = 'run' AND run_record_id IS NOT NULL AND analysis_artifact_id IS NULL)
        OR
        (subject_kind = 'analysis' AND run_record_id IS NULL AND analysis_artifact_id IS NOT NULL)
    )
);

CREATE TABLE annotations.annotation_revisions (
    annotation_id UUID NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    operation VARCHAR NOT NULL CHECK (operation IN ('create', 'replace', 'delete')),
    content_text VARCHAR,
    actor_token VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    revision_content_id VARCHAR NOT NULL,
    PRIMARY KEY (annotation_id, revision)
);
```

## 16. Portable export and DuckDB compatibility

### 16.1 Portable DuckDB artifact

An export request selects exact run records, analysis artifacts, reports, annotation cutoff,
verbose logs, and interoperability outputs. Dependency closure includes every required
identity/config/provenance/safety/licensing/fidelity/table schema, normalized fact, input
manifest, and referenced analysis. Market source payloads are included only when required
and licensed; otherwise immutable source manifests/checksums and a documented non-replayable
inspection boundary are included. The exported selected run/analysis results themselves must
have no unresolved local table/file references.

The staged standalone DuckDB contains `_persistra_export` manifest/schema tables plus the
same fixed result/analysis relations. It records Persistra/export schema versions, DuckDB
library and storage versions, selected storage-compatibility target, required extensions
with versions/checksums, source and logical artifact roots, file checksum/size, reader range,
annotation cutoff, omitted optional content, and license policy. Network-loading extensions
are not required merely to inspect a valid base export.

Verification reopens the file read-only in a new process, checks storage/header and manifest,
disables external access, enumerates no external views/secrets, recomputes schemas/counts/
roots, loads public handles, and runs invariant queries. Only then is `ExportAttemptId`
completed and the staged path atomically renamed where the filesystem supports it.

### 16.2 Compatibility contract

DuckDB documents backward reading from its stable-format era, while forward compatibility is
best effort; it also provides explicit storage-version targeting and copy/export/import paths
for conversion ([storage format and versions](https://duckdb.org/docs/stable/internals/storage),
[`COPY FROM DATABASE`](https://duckdb.org/docs/stable/sql/statements/copy),
[`EXPORT`/`IMPORT DATABASE`](https://duckdb.org/docs/stable/sql/statements/export)). Persistra
therefore adds its own stricter release-tested matrix:

- each export schema version pins a minimum/maximum Persistra 3.x reader range, a DuckDB
  library creation range, and one explicit storage-compatibility target;
- the default target is the oldest supported target that represents all required types/
  features, never implicit `latest`;
- CI retains golden exports for the current format and every prior format still supported and
  opens them with each supported reader environment;
- newer writers never promise older readers unless the matrix explicitly tests the selected
  storage target and export schema;
- unsupported forward files fail before query with required-version guidance; and
- an upgrade opens the source read-only with a compatible reader, copies logical content into
  a new target file/storage version, verifies all logical roots plus new manifest/file root,
  and leaves the source unchanged.

Native DuckDB byte identity is not semantic artifact identity. A copy migration can preserve
all logical run/analysis roots while producing a different file checksum and new export
artifact identity. `EXPORT/IMPORT` is a controlled fallback when direct database copy is not
available in the supported pair; its intermediate directory is temporary, verified, and not
the native artifact.

Plan 18 owns execution of this matrix and its immutable fixture manifest, but Plan 15 remains
the format/reader-range authority. Each retained native fixture is small, redistribution-safe,
checksum-pinned, reproducible from declared source rows and a pinned writer environment, and
covered by public-API open, verified-copy upgrade, source-byte preservation, logical-root, and
unsupported-forward/corruption cases. Changing a library constraint cannot silently regenerate
or bless a fixture. The 24 GiB measured path publishes and reopens a normal Plan-15 result but
does not include export creation or compatibility-matrix execution in its RSS boundary.

### 16.3 Parquet and CSV

A Parquet bundle contains a canonical JSON manifest, table schema files, one or more
canonically ordered Parquet parts per table, row counts/chunk roots/checksums, enum/decimal/
timezone semantics, and dependency graph. It round-trips into a fresh supported Persistra
database under verification. CSV export is per selected table with schema/encoding/null/
decimal/time sidecar and is not guaranteed to round-trip an entire run. Neither format can
claim native exact reuse without re-import verification and a new artifact relationship.

## 17. Public APIs and CLI

```python no-run
run = project.results.get(run_record_id)
metrics = project.analysis.metrics.compute(run, metric_set="persistra.standard@1")
attribution = project.analysis.attribution.compute(run, policy=policy)
comparison = project.analysis.compare((run_a, run_b), policy=policy)
export = project.results.export(
    runs=(run.id,), analyses=(metrics.id, attribution.id), target=path
)
```

CLI commands are `persistra runs list/show/export/delete`, `persistra analysis list/show`,
and `persistra report` only after Plan 16. Delete requires interactive confirmation or exact
noninteractive subject/reference token. All CLI paths invoke the public services and return
structured unavailable/compatibility states; they do not run private SQL.

Exceptions include `ResultPublicationError`, `ArtifactVerificationError`, `ResultQueryLimitError`,
`AnalysisPlanningError`, `AnalysisUnavailableError`, `AttributionReconciliationError`,
`ComparisonIncompatibleError`, `ExportVerificationError`, `ExportCompatibilityError`,
`AnnotationConflictError`, and `ReferencedArtifactError`. Stable reasons distinguish missing/
incomplete inputs, invalid base, insufficient observations, unavailable benchmark/quote,
unreconciled attribution, incompatible fidelity, corrupt roots, unsupported reader/storage,
external reference, licensing refusal, and resource limit.

## 18. Edge cases, security, and resources

| Case | Required outcome |
| --- | --- |
| Worker file checksum matches but logical root differs | Reject publication as corruption |
| Same artifact published for two studies | One run record, two immutable relationships |
| Compatible reuse | Original execution/artifact identity plus requested difference warning |
| Vectorized run queried for orders | Typed not-applicable result, never synthetic orders |
| Missing NAV in return chain | Structured unavailable interval/aggregate |
| Multiple MWR roots | `nonunique_solution`; no arbitrary root |
| Zero volatility ratio | Structured undefined under metric policy |
| Missing quote for spread | Unavailable observed spread; estimator remains estimated |
| Attribution residual exceeds tolerance | Unreconciled artifact/period, not redistributed |
| Comparison has different folds | Warn or incompatible per named policy; never hidden |
| Analysis input is archived | Read if retained; identity unchanged |
| Delete has report/export dependent | Reject and return bounded reference graph |
| Export omits selected dependency | Verification fails before completion |
| Older reader sees newer file | Fail with matrix guidance; do not open read-write |
| Upgrade interrupted | Source intact; incomplete new staging file unregistered |
| Empty query | Exact schema/dtypes and zero count |

Limits cover publication tables/rows/chunks/bytes, query rows/pages/cursors, analysis inputs/
observations/groups/hypotheses/outputs/iterations, attribution components, comparison runs/
differences, diagnostics/log bytes, reference graph, export dependencies/tables/bytes/files,
and direct pandas memory. Wall-time stops at safe boundaries and produces failed attempts,
never partial artifacts.

Export sanitizes filesystem names, refuses symlink/path traversal, writes with restrictive
permissions, redacts secrets/absolute paths, disables external access during verification,
and enforces licensing/redistribution policy. HTML/report assets from Plan 16 are untrusted
content for opening and receive CSP/sanitization there.

## 19. Migration and extension policy

V2 runs/metrics cannot become trusted v3 artifacts. A versioned importer may preserve them as
opaque external evidence with unknown identities/fidelity and no exact reuse/authoritative
comparison. Plan-02 verified copy migrations own research schemas. Completed content is never
edited in place; schema upgrades copy/verify and preserve old logical identities or declare a
new derived artifact.

Custom metric, attribution, execution, capacity, comparison, or diagnostic definitions
register qualified name, semantic/schema version, exact requirements/formula/units, config,
code/dependencies, determinism/resources, output schema, unavailable reasons, fidelity/safety
rules, and conformance fixtures. They receive bounded immutable handles, never project SQL.
Unsafe/opaque custom analyses are visibly classified and exact reuse ineligible when identity
is incomplete.

## 20. Implementation sequence

1. Add identities/models, result/analysis/annotation schemas, manifests, repositories, limits,
   and stable query frames.
2. Implement source verification, staged fixed-table copy, logical-root recomputation,
   invariant closure, atomic publication, compatible-reuse relationships, and faults.
3. Implement immutable analysis definitions/attempts/artifacts/dependency graph and structured
   unavailable result contract.
4. Implement TWR/MWR/performance/risk/benchmark/exposure/turnover/cost/capacity/stability
   metrics with hand-worked golden fixtures.
5. Implement attribution/reconciliation, execution analysis evidence classes, comparisons,
   diagnostics, scenario aggregation, and custom conformance.
6. Implement annotations/audit, reference graph, archive/delete/tombstones, and structured logs.
7. Implement portable DuckDB writer/verifier/reader matrix/copy upgrade, Parquet manifest
   bundle, CSV sidecars, licensing/security/fault tests.
8. Complete docs, strict build, benchmark hooks, and cumulative Plans 01–15 review.

## 21. Acceptance tests and exit criteria

### 21.1 Publication and query

- Source/destination schema/count/chunk/root/identity/reconciliation/fidelity/safety/licensing
  verification detects every injected mismatch and rolls back without visible staging.
- Same artifact concurrency/reuse produces one immutable run and correct executed/exact/
  compatible relationships; compatible requests never gain false execution completion.
- All Plan-11–14 fixed relations map losslessly, including vectorized no-order semantics,
  partial terminal orders, fill cost evidence, journal source links, and failure counts.
- Bounded filter/pagination/chunk/pandas APIs preserve schema/order/state, detect stale cursors,
  label previews, and return typed applicable/empty/unavailable distinctions.

### 21.2 Metrics, attribution, and comparison

- Hand-worked TWR cash-flow timing, MWR roots, annualization, volatility/ratios, drawdowns,
  tails, benchmark/risk-free alignment, exposures, turnover, costs, capacity, and stability
  match exact formulas and every unavailable edge.
- Property tests cover scale, partition/order, missing intervals, nonpositive bases, ties,
  NaN/infinity, elapsed time/DST, and frequency policy without changing roots.
- Attribution period and aggregate sums reconcile or expose exact residual/unavailable cause
  across holdings/transactions/classification/factor/strategy/long-short/cost/benchmark cases.
- Execution analysis never upgrades estimated/modeled/missing evidence to observed and never
  emits Plan-13 order statistics for Plan-12 synthetic fills.
- Comparison matrix covers snapshots/universes/ranges/folds/benchmarks/flows/simulators/
  fidelity/safety/metric versions and blocks invalid combined outputs.
- Recalculation/version/dependency change creates a new immutable analysis artifact; input and
  prior output never mutate.

### 21.3 Export, retention, and compatibility

- Portable export is closed, self-contained for selected outputs, source-root-equivalent,
  externally disconnected, licensed, and reopenable through public APIs after process restart.
- Current and every supported prior export fixture open across the declared Persistra/DuckDB
  matrix; unsupported forward files fail cleanly; verified copy upgrade preserves logical roots
  and source bytes while changing the export/file identity as expected.
- Parquet manifest bundle round-trips exact schemas/decimals/times/enums/nulls/roots; CSV is
  correctly labeled table interoperability only.
- Annotation concurrency/audit does not affect identities. Archive/delete/reference/tombstone
  tests prevent dangling analyses/reports/exports and silent cascade.
- Fault/security/resource tests cover stage/commit/write/fsync/rename/reopen/extension/path/
  checksum failure with no partial completed artifact.
- Docs snippets, strict MkDocs, optional/base imports, migrations/copies/reopen,
  `make lint type test`, and docs checks pass.

### 21.4 End-to-end exit

A documented workflow must publish vectorized and event worker artifacts, query all core
relations, compute structured performance/risk/execution/capacity metrics and reconciled
attribution, compare compatible/warned/incompatible runs, aggregate folds/scenarios including
failures, create/recalculate immutable analyses, annotate/archive/reference-check, export and
reopen a standalone DuckDB plus Parquet bundle, and upgrade a prior supported export using
public APIs only.

Plan 15 is complete only when repository gates, docs checks, strict build, compatibility
matrix, benchmark hooks, and cumulative review find no contradiction with the umbrella or
Plans 01–14.

## 22. Review checklist for dependent plans

Plans 16–18 must preserve:

- original run/design/execution/attempt/artifact and compatible-reuse identities;
- fixed normalized result semantics, Plan-12 order absence, and Plan-13 lifecycle/progress;
- Plan-11 accounting traceability and direct-versus-embedded cost classification;
- immutable analysis artifact/version/dependency identity and structured unavailable states;
- metric units/requirements/interval/annualization/warnings and attribution reconciliation;
- observed/estimated/modeled execution evidence and comparison classification;
- monotone safety/licensing/fidelity/provenance and explicit scenario/failure coverage;
- public bounded result/analysis APIs rather than renderer-owned financial calculations;
- annotation separation, reference-safe retention, and immutable completed content; and
- self-contained export closure and declared Persistra/DuckDB compatibility matrix.

Plan 16 may create immutable report analysis artifacts but cannot change metrics in templates.
Plan 17 opens results read-only and cannot mutate annotations, compute missing analyses/reports,
or register its caches/downloads as artifacts. Plan 18 owns golden compatibility fixtures and
cannot weaken logical-root verification to accommodate library changes.

## 23. Consistency statement

This plan implements the umbrella result, artifact, metric, attribution, comparison, log,
export, and compatibility direction. It keeps completed simulator/accounting facts immutable,
makes all derived work separately identified and reproducible, and treats compatibility as a
tested declared boundary rather than an assumption. No project-level direction is revised.

The cumulative Plan-16 review assigns report-specific rows to the existing immutable
analysis envelope and keeps rendered HTML/bundle bytes as checksum-listed outputs. Reports
may embed or accompany a portable export, but neither template nor figure can recalculate a
run/metric or bypass export dependency closure, licensing, comparison, and reference checks.

The cumulative Plan-17 review treats dashboard filters, session state, cached serialized query
models, and bounded downloads as ephemeral presentation state. They neither enter nor replace
run/analysis/report/export identities. The dashboard can display an existing portable export
or report read-only, but any generation, annotation, retention, or publication action remains
outside its process through this plan's public write services.
