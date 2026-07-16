# Round 2 — Reviewer B: implementation readiness

**Scope:** Determine whether a competent engineer could implement each focused component from
the specification alone, with particular attention to data schemas, interfaces, error handling,
dependencies, and acceptance criteria.

**Method:** Reviewed the umbrella and focused specifications 01–18, then traced every reported
type or relation across the complete `docs/v3/` set before treating it as undefined. Round-1
findings were not repeated unless the round-1 repair still leaves an implementation-blocking
contract.

**Overall assessment:** The specifications remain unusually strong on domain semantics,
algorithms, failure visibility, persistence invariants, and acceptance tests. Plans 01, 02, 08,
09, and 18 are implementable from their focused contracts without a significant readiness issue
in this review's scope. The principal remaining weakness is interface closure: plans 07 and
10–17 often name public reference/configuration types without specifying their fields or canonical
wire forms. One result-publication seam is internally unimplementable as written because required
source relations do not exist and the promised column-identical copy cannot represent sampled
portfolio states.

## Component readiness summary

| Component | Readiness from spec alone | Findings |
| --- | --- | --- |
| 01 — domain identity/time/money/events | Ready | — |
| 02 — project/databases/leases/copies/migrations | Ready | — |
| 03 — catalog/ingestion/snapshots | Needs contract closure | R2-B2 |
| 04 — reference/calendars/universes | Needs contract closure | R2-B2, R2-B4 |
| 05 — market/actions/adjustments | Needs shared dependency closure | R2-B2 |
| 06 — fundamentals/estimates/macro/benchmarks/rates | Needs shared dependency closure | R2-B2 |
| 07 — research datasets/SQL/workspaces | Not independently implementable | R2-B2, R2-B3 |
| 08 — features/labels | Ready | — |
| 09 — alpha/validation | Ready | — |
| 10 — portfolio research | Not independently implementable | R2-B5 |
| 11 — accounting | Not independently implementable | R2-B1, R2-B6 |
| 12 — vectorized simulation | Not independently implementable | R2-B1, R2-B6, R2-B7 |
| 13 — event simulation | Not independently implementable | R2-B1, R2-B6, R2-B7 |
| 14 — experiments | Not independently implementable | R2-B8 |
| 15 — results/analysis/export | Not independently implementable | R2-B1, R2-B9 |
| 16 — visualization/reports | Needs contract closure | R2-B10 |
| 17 — dashboard | Mostly ready; dependency gate incomplete | R2-B11 |
| 18 — testing/benchmark | Mostly ready; dependency matrix incomplete | R2-B11 |

## Findings

### R2-B1 — Simulator result publication has no implementable source schema or lossless mapping

- **Severity:** blocker
- **Files/sections:** `docs/v3/12-vectorized-simulator.md` §13; `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md` §15; `docs/v3/15-results-analysis-metrics-attribution-comparison-export.md` §§7.2–7.4; `docs/v3/11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md` §15.2.
- **Description:** Plan 12 says fixed `simulation_data` relations store cost components,
  sampled equity/state, external-flow-split returns, and fidelity findings and then claims that
  all their row schemas are versioned, but it provides no DDL for those relations. Plan 13's
  physical schema likewise has no equity, return, cost-component, or finding source relation.
  Plan 15 nevertheless requires `result_data.equity` and `returns` to be copied from exact
  Plan-12/13 committed sampling output. Its repair for the other results is also not executable:
  §7.4 promises a column-identical copy with a source run/book/simulation ID replaced by
  `run_record_id`, but `journal_data.portfolio_state_positions` and
  `portfolio_state_cash` are keyed by `portfolio_state_id`, not by run/book/simulation ID.
  Replacing that key collapses every time sample for the same instrument/run and omits the
  `valued_at` semantics promised for `result_data.positions`; retaining it yields rows with no
  required `run_record_id`. Similar paired-source mappings name one logical result kind without
  enumerating all physical destination table names. An engineer cannot construct or verify the
  publication transaction without inventing source relations, destination DDL, and joins.
- **One-line fix:** Add exact Plan-12/13 source DDL for every published series and explicit
  destination DDL plus per-column join/mapping rules that preserve state IDs, sample instants,
  parent/child keys, and `run_record_id`.

### R2-B2 — Multi-provider source precedence is required but has no schema, registry, or initial policy

- **Severity:** major
- **Files/sections:** `docs/v3/03-catalog-ingestion-quarantine-snapshots.md` §12.4;
  `docs/v3/04-reference-identifiers-calendars-universes.md` §6.2;
  `docs/v3/05-market-bars-trades-quotes-actions-adjustments.md` §§5.3 and 6;
  `docs/v3/06-fundamentals-estimates-macro-benchmarks-rates.md` §§5.3 and 16;
  `docs/v3/07-research-datasets-temporal-joins-sql-workspaces-safety.md` §§6.2 and 9.
- **Description:** Plan 03 delegates resolution across sources to a dataset-specific policy;
  plans 04–07 require the policy for every resolved multi-provider view; and Plan 07 exposes
  `SourcePrecedenceRef`. No plan defines that reference, a policy record/registration API, the
  ordered source/tie-break grammar, applicability to dataset versions, canonical identity, or
  even one installed policy. The rule that equal-priority candidates conflict unless a policy
  has a complete deterministic tie-breaker does not say how such a tie-breaker is represented
  or validated. This blocks every multi-provider resolved query and its golden tests.
- **One-line fix:** Define a versioned `SourcePrecedencePolicy`/`SourcePrecedenceRef` schema,
  registration storage/API, deterministic selection grammar, validation/error rules, and at
  least one explicit initial policy or required project-supplied binding per dataset.

### R2-B3 — The research input interface names six value types without defining their fields

- **Severity:** major
- **Files/sections:** `docs/v3/07-research-datasets-temporal-joins-sql-workspaces-safety.md`
  §§6.1–6.3 and 10.
- **Description:** The central `ResearchInputSpec` contains `CanonicalInputRef`,
  `WorkspaceInputRef`, `FeatureInputRef`/`LabelInputRef`, `OutputSchema`, `EntityBridgeSpec`,
  `TemporalJoinSpec`, and `SourcePrecedenceRef`. Apart from the component handles supplied by
  Plan 08, these types are not defined anywhere. Prose explains behavior but does not settle
  fields or discriminators: for example, which anchor a join stores, how `max_age` and
  `explicit_unbounded` are mutually represented, what a global-series bridge names, how a
  projection represents dtype/nullability/unit/state siblings, or which domain-specific union
  fields a canonical input accepts. Canonical serialization and registration validation
  therefore cannot be implemented consistently.
- **One-line fix:** Add complete frozen dataclass/discriminated-union schemas and canonical
  encodings for every `ResearchInputSpec` member, including variant-specific validation and
  constructor signatures used by the example.

### R2-B4 — Civil-date-to-instant resolution is a required registered policy with no contract

- **Severity:** major
- **Files/sections:** `docs/v3/04-reference-identifiers-calendars-universes.md` §7.4 and
  §§16.1–16.4; `docs/v3/06-fundamentals-estimates-macro-benchmarks-rates.md` §§12–13.
- **Description:** Plan 04 requires a registered date-resolution policy to turn source civil
  dates into effective instants, normally at a venue session open, and makes the policy/calendar
  identity part of observation content and safety. Plan 06 depends on the same mechanism for
  benchmark/date conventions. No policy type, variants, inputs/outputs, storage/registration
  surface, initial policy name/version, ambiguity behavior, or non-session-date rule is defined.
  An implementer must choose economically material effective times and content identities,
  while the acceptance suite expects them to be stable.
- **One-line fix:** Specify the initial date-resolution policy variants as typed, versioned
  records with exact calendar lookup, holiday/non-session, timezone, ambiguity, coverage-error,
  registration, and identity rules.

### R2-B5 — Plan 10's public definition/request surface is explicitly only representative

- **Severity:** major
- **Files/sections:** `docs/v3/10-signals-forecasts-risk-models-constraints-optimization.md`
  §§7–15 and 18.2.
- **Description:** Section 18.2 offers a “representative surface,” then says actual values use
  typed references/unions that are not supplied. Core members such as `DecisionInputRef`,
  `SignalTransformSpec`, `OutputSchema`, `ParameterValues`, `ValidationTrainingScope`,
  `DecisionInputBundleRef`, `DecisionSelector`, `ConstraintSetRef`,
  `ExpectedCostMaterializationRef`, and `FallbackSpec` have no schemas elsewhere in the set.
  The behavioral sections are detailed, but they do not define exact constructor/API shapes,
  discriminators, defaults, or canonical encodings needed by registration, execution identity,
  persistence, and conformance tests.
- **One-line fix:** Replace the representative snippets with the complete public dataclass and
  discriminated-union catalog for every definition, reference, request, policy, and selector in
  the Plan-10 workflow.

### R2-B6 — Accounting policy/opening references and write request models are absent

- **Severity:** major
- **Files/sections:** `docs/v3/11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md`
  §§4.3, 8.4, 9–14, 18, and 24.3; `docs/v3/12-vectorized-simulator.md` §4.3;
  `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md` §4.3.
- **Description:** Plan 11 labels its few public dataclasses “representative” and gives its
  public write API only as calls with generic `request` variables. It never defines the request
  schemas for book creation, opening fixtures, cash flows, accruals, valuations, corporate
  actions, or reconciliation, nor the public reference/registration schemas for settlement,
  marks, lot relief, accruals, financing/borrow, margin, rounding, and elections. Consequently
  `AccountingOpeningRef` and `CashFlowScheduleRef` used by both simulators are undefined, and
  `AccountingPolicyBundleRef` has named dimensions but no constructible member types. The
  posting algorithms and DDL are detailed, but the interface that invokes them is not.
- **One-line fix:** Define all accounting request/reference/policy dataclasses, the opening and
  cash-flow schedule schemas, registration/resolution APIs, initial installed policy names, and
  field-level validation/error mappings.

### R2-B7 — Neither simulator request can be constructed from the named policy/reference types

- **Severity:** major
- **Files/sections:** `docs/v3/12-vectorized-simulator.md` §§4.3, 6–11, and 14;
  `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md` §§4.3–4.4, 8–13, and 16.
- **Description:** The vectorized request uses undefined `DecisionScheduleRef`,
  `PrecomputedTargetRef`, `EndogenousConstructionRef`, `RebalancePolicyRef`,
  `VectorizedExecutionPolicyRef`, and `VectorizedFidelitySpec`. The event request similarly uses
  undefined `EventScheduleRef`, `ExecutionPolicyRef`, and `EventFidelitySpec`. The later sections
  explain algorithms and enumerate some kinds, but provide no exact fields/defaults tying timing,
  capacity, ambiguity, latency, spread/slippage/impact/fee components, observations, and fidelity
  assumptions into the request. In addition, `EventSimulationLimits` appears only as a field;
  §4.4 lists categories without field names or defaults. Execution identity and acceptance
  fixtures cannot be built deterministically from this interface.
- **One-line fix:** Add complete request-submodel schemas for both simulators, including policy
  composition, installed defaults, reference resolution, fidelity fields, and an enumerated
  `EventSimulationLimits` dataclass with defaults.

### R2-B8 — The experiment study request is a shell around undefined orchestration models

- **Severity:** major
- **Files/sections:** `docs/v3/14-experiment-identity-reuse-parallel-search-resume-scenarios.md`
  §§5–6, 8–13, and 15.
- **Description:** `StudyRequest` depends on `ResearchDesignRef`, `SearchSpec`, `FoldSetRef`,
  `ScenarioSetRef`, simulator templates, `ObjectiveSpec`, `ReusePolicy`, `RetryPolicy`,
  `StudyStopPolicy`, `LocalWorkerPolicy`, and `ExperimentLimits`; each appears only in that
  signature. The following prose defines behavior, but not exact fields, defaults, union
  discriminators, resource ceilings, or canonical encodings. The domain grammar also does not
  supply constructible models for conditional parameters/distributions/custom generators.
  Planning, retry/resume, stop behavior, and identity hashing would therefore require an
  implementer-designed API rather than implementation of the specified one.
- **One-line fix:** Define the full StudyRequest object graph, parameter-domain AST, simulator
  templates, policy defaults/limits, and canonical validation/serialization for every variant.

### R2-B9 — The analysis request and artifact-specific configurations are untyped placeholders

- **Severity:** major
- **Files/sections:** `docs/v3/15-results-analysis-metrics-attribution-comparison-export.md`
  §§9.1, 10–13, 16, and 17.
- **Description:** `AnalysisRequest` names `AnalysisDefinitionRef`, `AnalysisConfig`,
  `AnalysisOutputPolicy`, and `AnalysisLimits`, but none has a schema anywhere. The convenience
  API then passes untyped `policy` variables for attribution/comparison and an export call with
  no export request/options model. Exact metric formulas are now present, yet an engineer still
  cannot represent metric-set options, slices, benchmark/rate inputs, attribution hierarchy,
  comparison compatibility choices, output policies, or resource bounds in the public identity
  model. Error classes exist, but field-level validation and error mapping cannot be completed
  against an absent request grammar.
- **One-line fix:** Publish exact per-artifact analysis config unions, definition/reference and
  output-policy schemas, limits/defaults, export options, and validation-to-error rules.

### R2-B10 — Standard reports lack an exact template/section catalog and constructible section schema

- **Severity:** major
- **Files/sections:** `docs/v3/16-plotly-visualization-html-reports.md` §§5.2, 9.1–9.2, 12,
  and 17.
- **Description:** `ReportRequest` requires `ReportTemplateRef` and optional
  `ReportSectionSpec`, but neither type is defined. The standard run report is a nine-item topic
  outline rather than an installed template/section catalog: it does not give qualified names,
  versions, exact input/analysis requirements, applicability predicates, failure policy, block
  schemas, or default section order. Acceptance requires standard run/event/vectorized/study/
  comparison reports, but their exact templates are not enumerated. Different engineers could
  satisfy the prose with incompatible manifests and report identities.
- **One-line fix:** Enumerate the installed template and section registry with exact refs,
  `ReportSectionSpec` fields, ordered defaults, requirements/applicability/failure policies, and
  golden manifest expectations for every standard report kind.

### R2-B11 — Required optional-dependency compatibility ranges are deferred to implementation

- **Severity:** minor
- **Files/sections:** `docs/v3/17-streamlit-dashboard-prototype.md` §4;
  `docs/v3/18-testing-conformance-properties-benchmark.md` §11.
- **Description:** Plan 17 says the exact Streamlit lower/upper compatibility range “is pinned
  and tested during implementation,” while Plan 18 requires lower-bound matrices for
  Streamlit, Plotly, solver/search dependencies, and DuckDB without naming those lower bounds
  or where the normative support manifest lives. This lets implementation choose a materially
  different support surface and leaves release acceptance indeterminate until after the choice.
- **One-line fix:** Name a normative version-support manifest/deliverable and require it to pin
  the initial lower/upper ranges before component implementation begins, with Plan-18 matrix
  cases generated from that manifest.

## Severity summary

| Severity | Count |
| --- | ---: |
| blocker | 1 |
| major | 9 |
| minor | 1 |
| nit | 0 |

