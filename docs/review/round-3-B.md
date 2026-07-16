# Round 3 — Reviewer B: implementation readiness

**Scope:** Determine whether a competent engineer could implement every focused component from
the specification alone, with particular attention to data schemas, interfaces, error handling,
dependencies, and acceptance criteria.

**Method:** Reviewed the umbrella and focused specifications 01–18, traced public and persisted
types across the complete `docs/v3/` set, and rechecked the round-1/round-2 ledger before treating
a gap as new. Findings below consolidate related undefined aliases rather than reporting each use
as a separate issue.

**Overall assessment:** Plans 01, 02, 08, 09, and 18 are implementable from their focused
contracts without a significant readiness issue in this review's scope. The round-2 additions
substantially improve interface closure, but several of the new “closed” graphs still terminate
in undefined public references, opaque content IDs, or request variants that cannot carry the
behavior required by their algorithms and identities. Plan 13 also cannot persist its required
event fidelity profile under the only supplied shared DDL.

## Component readiness summary

| Component | Readiness from spec alone | Findings |
| --- | --- | --- |
| 01 — domain identity/time/money/events | Ready | — |
| 02 — project/databases/leases/copies/migrations | Ready | — |
| 03 — catalog/ingestion/snapshots | Needs public contract closure | R3-B1 |
| 04 — reference/calendars/universes | Not independently implementable | R3-B1, R3-B2 |
| 05 — market/actions/adjustments | Needs public contract closure | R3-B1 |
| 06 — fundamentals/estimates/macro/benchmarks/rates | Needs public contract closure | R3-B1 |
| 07 — research datasets/SQL/workspaces | Not independently implementable | R3-B1, R3-B3 |
| 08 — features/labels | Ready | — |
| 09 — alpha/validation | Ready | — |
| 10 — portfolio research | Not independently implementable | R3-B4 |
| 11 — accounting | Not independently implementable | R3-B5 |
| 12 — vectorized simulation | Needs upstream interface closure | R3-B1, R3-B4 |
| 13 — event simulation | Blocked | R3-B1, R3-B6, R3-B7 |
| 14 — experiments | Not independently implementable | R3-B4, R3-B8, R3-B9 |
| 15 — results/analysis/export | Not independently implementable | R3-B10 |
| 16 — visualization/reports | Not independently implementable | R3-B11 |
| 17 — dashboard | Not independently implementable | R3-B11, R3-B12 |
| 18 — testing/benchmark | Ready | — |

## Findings

### R3-B1 — Plans 03–06 expose public reference and query types that have no normative schemas

- **Severity:** major
- **Files/sections:** `docs/v3/03-catalog-ingestion-quarantine-snapshots.md` §§5–6;
  `docs/v3/04-reference-identifiers-calendars-universes.md` §§10.4, 13.3–14.1;
  `docs/v3/05-market-bars-trades-quotes-actions-adjustments.md` §§7.1–8 and 15.2;
  `docs/v3/06-fundamentals-estimates-macro-benchmarks-rates.md` §§11–16;
  `docs/v3/12-vectorized-simulator.md` §4.3;
  `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md` §4.3.
- **Description:** These plans show calls built from `SourceRef`, `DatasetRef`, `ComponentRef`,
  `CalendarRef`, `UniverseRef`, `BarSpecRef`, `BarQuery`, `AdjustmentPolicyRef`,
  `MacroSeriesRef`, `BenchmarkVersionRef`, and `RiskFreeCurveRef`, but never define their
  fields, canonical encodings, or resolution errors. Source/dataset and universe definitions
  are likewise field lists stored as JSON rather than constructible public models. The gap
  becomes cross-component: both simulators require `UniverseEvaluationRef`, which is not
  defined anywhere, although their execution identities require an exact evaluation and its
  manifests. An engineer must invent whether a ref carries only name/version, assigned ID,
  definition content ID, output manifest, or snapshot/safety roots, and later plans cannot
  implement exact-reference validation consistently.
- **One-line fix:** Publish frozen schemas and exact register/resolve/query signatures for every
  public definition/ref/query type in Plans 03–06, including an exact `UniverseEvaluationRef`
  carrying the identity and manifests consumed downstream.

### R3-B2 — The date-resolution registry is assigned to a nonexistent schema and an unwritable mode

- **Severity:** major
- **Files/sections:** `docs/v3/02-project-databases-leases-copies-migrations.md` §§8.1 and 9;
  `docs/v3/04-reference-identifiers-calendars-universes.md` §§6.1 and 7.4.
- **Description:** Plan 04 says reference registries belong to the selected market database and
  only `market_write` may register them; Plan 02 reserves only `catalog`, `canonical`,
  `quality`, and `snapshots` in that role, and a `research_write` project opens market members
  read-only. The new DDL nevertheless creates `reference.date_resolution_policies` and the
  accompanying API explicitly says registration is `research_write`. The migration has no
  defined target schema, while the stated service mode cannot write the required database.
- **One-line fix:** Move the policy registry to the market database's declared registry schema
  (normally `catalog`) and require `market_write` for registration, leaving resolution available
  through bounded read-only/research modes.

### R3-B3 — `DomainQueryRef` is only a hash pointer; no canonical input query can be constructed

- **Severity:** major
- **Files/sections:** `docs/v3/07-research-datasets-temporal-joins-sql-workspaces-safety.md`
  §§6.2–6.3, 13.1, and 24.1–24.2; `docs/v3/04-reference-identifiers-calendars-universes.md`
  §§9–14; `docs/v3/05-market-bars-trades-quotes-actions-adjustments.md` §§6–15;
  `docs/v3/06-fundamentals-estimates-macro-benchmarks-rates.md` §16.
- **Description:** The closed `CanonicalInputRef` stores a `DomainQueryRef` containing only a
  contract name/version and `parameters_content_id`. Plan 07 says that ID resolves a registered,
  schema-validated parameter object and that Plans 04–06 register one adapter per dataset, but
  no plan defines the per-dataset query-parameter models, parameter-object registry/storage,
  registration/resolution API, or adapter registration record. The prose list of possible
  semantics cannot tell an implementer how bar modes, action policies, filing modes, estimate
  targets, macro vintages, benchmark methods, or rate conventions serialize into the ID used by
  definition/build identity. The example's convenience constructor therefore has no specified
  lowering into the supposedly closed graph.
- **One-line fix:** Define and register a discriminated parameter schema plus adapter descriptor
  for every initial canonical dataset, with public constructors and a canonical lowering to
  `DomainQueryRef`.

### R3-B4 — Plan 10 still omits most occurrence requests and has no runtime component parameters

- **Severity:** major
- **Files/sections:** `docs/v3/10-signals-forecasts-risk-models-constraints-optimization.md`
  §§16–18.2 and 25; `docs/v3/12-vectorized-simulator.md` §§4.3 and 6;
  `docs/v3/14-experiment-identity-reuse-parallel-search-resume-scenarios.md` §§5–6.
- **Description:** Section 18.1 invokes signal, forecast, risk, and expected-cost
  `materialize(request)` operations and separate forecast/risk `plan_fit(request)` operations,
  but the normative request catalog defines only `ForecastFitRequest` and
  `ConstructionRequest`. There are no signal/forecast/risk/cost materialization requests or
  risk-fit request. `ConstructionRequest` and Plan 12's `EndogenousConstructionRef` also omit
  `ParameterValues`, even though registry defaults, persistence `parameter_content_id`, study
  parameter slots, and exact retry all require resolved occurrence parameters. Consequently an
  engineer cannot construct the advertised APIs or tune a constructor without inventing a
  request grammar.
- **One-line fix:** Add exact fit/materialization/construction request dataclasses for every
  service, including validated runtime parameters and their content IDs, and reuse that graph in
  endogenous simulation and study templates.

### R3-B5 — The accounting write graph still ends in undefined refs and request payloads

- **Severity:** major
- **Files/sections:**
  `docs/v3/11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md`
  §§4.3, 9, 12, 15.2, 18, and 24.3.
- **Description:** The added graph does not define `BorrowAuthorizationRef`, yet
  `FillAccountingFacts` requires it, and `CurrentPortfolioView` requires an undefined
  `ValuationPolicyRef`. The public API invokes `apply_settlement(book, transition)` and
  `states.create(book, valuation=...)`, but supplies neither a settlement-transition model nor
  a state-creation request/validation contract. Custom settlement, margin, valuation, borrow,
  and other policies are described only as prose declarations with no policy-definition union
  or registration signature. Algorithms and DDL are detailed, but the commands that enter the
  pure kernel and the exact policy refs they resolve remain implementer-designed.
- **One-line fix:** Complete the accounting graph with all missing refs, typed transition/state
  requests, closed policy-definition variants, registration methods, and field-to-error rules.

### R3-B6 — Event fidelity cannot be inserted into the only supplied fidelity-profile table

- **Severity:** blocker
- **Files/sections:** `docs/v3/12-vectorized-simulator.md` §13;
  `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md` §§13 and 15.
- **Description:** Plan 13 requires every `event_runs` row to reference a fidelity profile and
  says the shared envelope records order lifecycle, partial fills, latency, ambiguity, and
  event detail. The only DDL for `simulation.fidelity_profiles`, however, is Plan 12's table,
  whose checks force both `order_model` and `partial_fill_model` to
  `not_modeled_vectorized`. Plan 13 supplies no event-compatible replacement or migration and
  reuses only Plan 12's `simulation_data.published_*` tables explicitly. An event run therefore
  cannot persist a truthful profile satisfying both the event specification and the physical
  schema, so completion and Plan-15 publication cannot be implemented as written.
- **One-line fix:** Define one simulator-discriminated shared fidelity DDL with variant checks,
  or add an event-specific profile table and point `event_runs.fidelity_profile_id` to it.

### R3-B7 — `StatefulStrategyRef` is behavioral prose, not the constructible request member Plan 13 needs

- **Severity:** major
- **Files/sections:** `docs/v3/13-event-clock-orders-bar-execution-costs-fidelity.md`
  §§4.3, 6.4, 14, 16, and 20.1.
- **Description:** `EventSimulationRequest` requires `StatefulStrategyRef`, while §6.4 only
  says it resolves a qualified name, semantic version, parameters, implementation capture, and
  a closed state schema. No ref, definition, state-field schema, registration request/service,
  initial-state value, or parameter-content model is supplied. Those exact values are required
  by execution identity, checkpoint serialization, state-size enforcement, replay, callback
  validation, and temporal/security acceptance tests. The event engine cannot freeze or
  instantiate the strategy boundary from the spec alone.
- **One-line fix:** Add normative strategy definition/ref/registration and initial-state schemas,
  including typed state-field AST, parameters, implementation/conformance roots, validation,
  and exact resolution errors.

### R3-B8 — The parameter-domain model cannot express deterministic log/continuous/normal sampling

- **Severity:** major
- **Files/sections:**
  `docs/v3/14-experiment-identity-reuse-parallel-search-resume-scenarios.md` §§5, 6.1–6.3,
  and 19.2.
- **Description:** One `ParameterDomain` shape is shared by choice, integer range, decimal grid,
  log grid, continuous, distribution, and custom variants, but the spec does not assign exact
  variant fields or algorithms. A log grid has no base/count rule; a continuous domain has no
  sampling transform; and `normal` has no mean, standard deviation, truncation, or rejection
  rule. `values`, `lower`, `upper`, and `step` are untyped strings whose permitted/required
  combinations are not enumerated. Seeded random/search acceptance requires reproducible draws
  and roots, which different reasonable implementations will not share.
- **One-line fix:** Replace `ParameterDomain` with closed variant dataclasses and pin each
  canonical scalar parser, grid formula, inverse-CDF/draw algorithm, boundary rule, and
  exhaustion behavior.

### R3-B9 — Scenario and resampling requests are opaque content IDs rather than executable schemas

- **Severity:** major
- **Files/sections:**
  `docs/v3/14-experiment-identity-reuse-parallel-search-resume-scenarios.md` §§5, 12–13,
  17, and 19.2–19.4.
- **Description:** `ScenarioSpec` contains only name, kind, `perturbation_content_id`, and
  repetitions, while §12 defines a scenario as an ordered tuple of transformations with
  target, scope, operation, parameters, timing, composition/conflict, and safety/fidelity
  effects. Monte Carlo/bootstrap methods require another large set of population, block,
  coupling, boundary, and dependence fields, none of which has a type, reference, registry, or
  installed method schema. A content ID is not enough to create or validate those objects, yet
  the public-only end-to-end acceptance requires all four scenario families.
- **One-line fix:** Define versioned transformation and resampler unions, scenario registration/
  resolution APIs, installed method configs, and make `ScenarioSpec` reference the exact
  ordered executable definitions and realized-input policy.

### R3-B10 — Analysis configs cannot carry several semantics their algorithms and identities require

- **Severity:** major
- **Files/sections:**
  `docs/v3/15-results-analysis-metrics-attribution-comparison-export.md` §§9.1, 10–13,
  17, and 21.2.
- **Description:** The new config union is closed, but its members do not encode the complete
  choices required later. In particular, `AttributionAnalysisConfig` has no return-versus-P&L
  basis, frequency, holdings timing, cash-flow treatment, transaction treatment, cost-allocation
  policy, or strategy-component map even though §11 requires all of them and §9.1 says they
  enter execution identity. Similar behaviors are left behind unversioned `QualifiedName`
  values without a typed policy ref or policy-definition registry. The implementation must
  either hard-code unstated defaults or create identity-affecting fields outside the normative
  request, defeating canonical replay and the golden attribution matrix.
- **One-line fix:** Add every algorithm-required choice to the matching config variant (or an
  exact version/content policy ref) and define the policy registries, defaults, validation, and
  unavailable/error mapping.

### R3-B11 — A reusable report section cannot embed the concrete `AnalysisRequest` type it declares

- **Severity:** major
- **Files/sections:** `docs/v3/15-results-analysis-metrics-attribution-comparison-export.md`
  §9.1; `docs/v3/16-plotly-visualization-html-reports.md` §§5.2, 9.1–9.3, 12, and 17.2.
- **Description:** `ReportSectionDefinition.optional_analysis_requests` is a tuple of Plan-15
  `AnalysisRequest`, whose inputs are concrete `RunRef`/`AnalysisArtifactRef` identities. A
  globally registered standard section cannot embed those report-specific IDs, and the spec
  provides no role-placeholder/binding grammar to instantiate a request from
  `ReportRequest.inputs`. This makes `compute_missing` impossible to implement generically.
  The installed template table also has no `ReportTemplateDefinition` schema that owns its
  ordered section refs, subject compatibility, and content ID; it is only a prose/fixture table.
- **One-line fix:** Introduce a typed `AnalysisRequestTemplate` with role-bound input placeholders
  plus a constructible `ReportTemplateDefinition`, and specify deterministic binding into an
  exact Plan-15 request before report identity freezes.

### R3-B12 — Dashboard source variants are named but never defined

- **Severity:** major
- **Files/sections:** `docs/v3/17-streamlit-dashboard-prototype.md` §§5.1–5.3, 7, 10,
  13, and 15.1.
- **Description:** `DashboardRequest.source` is a union of `ProjectDashboardSource`,
  `BackupDashboardSource`, and `PortableExportSource`, but none has a schema. The public example
  assumes `PortableExportSource(path)`, while project, backup, and export startup require
  materially different path/config selectors, copy/export manifests, schema/reader targets,
  and verification errors. Without exact variant fields and exclusivity rules, the launcher,
  one-use child token, source fingerprint/cache key, CLI lowering, and source-specific
  acceptance tests cannot share a normative representation. The request also inherits the
  undefined `ThemeRef` used by Plan 16.
- **One-line fix:** Define all three frozen source variants (and `ThemeRef`) with canonical path/
  identity/manifest fields, exclusive validation, CLI lowering, verification outcomes, and
  stable error mapping.

## Severity summary

| Severity | Count |
| --- | ---: |
| blocker | 1 |
| major | 11 |
| minor | 0 |
| nit | 0 |
