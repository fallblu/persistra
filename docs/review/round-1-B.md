# Round 1 — Reviewer B: implementation readiness

**Scope:** Could a competent engineer implement each component from the spec alone (no author access)?
Focus: missing data schemas, missing/incomplete interfaces, missing error handling, missing
dependencies/wiring, missing acceptance criteria.

**Method:** All files in `docs/v3/` (01–18 plus `v3-spec.md`) were read in full. Every finding
below was verified by searching the remaining files for the missing definition before inclusion.

**Overall assessment:** This is an unusually implementation-ready specification set. Schemas
carry exact DDL, enums are closed and enumerated, error/reason codes are tabulated, failure and
concurrency paths are specified at each transaction boundary, and every plan has explicit
acceptance tests and exit criteria. I found **no blockers**. The findings below are places where
a referenced type, catalog, formula, or wiring step is never defined anywhere in the set, so an
implementer would have to invent nontrivial design.

---

## B1 — Unit system (`UnitSpec` / `Unit`) is referenced everywhere but defined nowhere

- **Severity:** major
- **Files/sections:** `10-signals-...md` §4.3 (line 239); `08-features-...md` §6.3 output contract and §7.1 (`required_unit: Unit`); `07-research-...md` §6.2 ("unit/numeric-kind contract"); `15-results-...md` §10.1 (controlled `unit` values); `01-domain-...md` §4 (public API list).
- **Description:** Plan 10 states "Every scalar output uses a plan-01 `UnitSpec`", but plan 01's
  public surface (section 4) exports no `UnitSpec` and defines no unit model at all. Plan 08
  requires every output/input to declare "unit and numeric kind" via an undefined `Unit` type;
  plan 07 requires a "unit/numeric-kind contract" per projected value; plan 15 lists a few
  controlled unit strings (`rate`, `usd`, `days`, …) for metric rows only. There is no grammar,
  registry, canonical serialization, or compatibility/conversion rule for units anywhere,
  despite units being identity-bearing (they enter content IDs) and validation-bearing
  (unit-mismatch is a rejection reason in plans 08/10).
- **Fix:** Add a unit registry/grammar (fields, canonical text, equality/compatibility rules) to plan 01 (or a shared appendix) and make plans 07/08/10/15 reference it.

## B2 — `UnsafeRunOverride` / `UnsafeAnalysisOverride` never given a schema or acceptance semantics

- **Severity:** major
- **Files/sections:** `12-vectorized-simulator.md` §4.3 (line 181) and §6; `13-event-...md` §4.3 (line 173); `15-results-...md` §9.1 (line 415); umbrella `v3-spec.md` §7.1.
- **Description:** Plans 07–10 repeatedly defer to "the plan-12/13 run-level unsafe override"
  as the sole mechanism admitting unsafe/opaque inputs to simulation, and the umbrella (§7.1)
  requires the override to "set a run-level unsafe flag, list every unsafe dataset and reason,
  … propagate into derived …". But `UnsafeRunOverride` appears only as an untyped field in the
  request dataclasses. No plan defines its fields (which finding content IDs must be
  acknowledged? per-finding or blanket? per-input scope?), its validation rule (what happens if
  a new unsafe finding appears that was not acknowledged?), or its persisted form.
  `UnsafeAnalysisOverride` in plan 15 has the same gap. An implementer must invent the central
  safety-override contract.
- **Fix:** In plan 12, define the `UnsafeRunOverride` dataclass (acknowledged finding content IDs/reason codes, per-input scope, persistence) and the mismatch/rejection rule; have plans 13/15 reference it.

## B3 — Domain "bounded query adapter" / "common candidate envelope" protocol is never specified

- **Severity:** major
- **Files/sections:** `07-research-...md` §6.2 (lines 289–292) and §9; `04/05/06` review-checklist sections referencing "domain query adapters".
- **Description:** The dataset builder's entire input surface depends on this contract: "The
  domain owner supplies a registered bounded query adapter that returns a common candidate
  envelope plus typed values." Plans 04–06 each say they own "registered market/domain query
  adapters", and plan 07 §9 gives the 8-step selection order the adapter must execute. But no
  file defines the adapter protocol (method signature, inputs it receives per partition) or the
  candidate-envelope schema (fields for value time, selected revision ID, availability,
  availability quality, state, source, lineage refs). This is the seam every canonical dataset
  crosses to enter research; an implementer must invent it wholesale.
- **Fix:** Add to plan 07 a typed `DomainQueryAdapter` protocol and `CandidateEnvelope` schema (fields + which of plans 04–06 supply which adapter), mirroring the precision of `CanonicalStagingRecord` in plan 03.

## B4 — `leverage` constraint has no defined leverage measure

- **Severity:** major
- **Files/sections:** `10-signals-...md` §12.2 (line 941: "leverage constrains a named plan-11-compatible pretrade leverage measure, not an ambiguous synonym for gross exposure"); `11-journal-...md` §12 (margin).
- **Description:** Plan 10 requires a "named plan-11-compatible pretrade leverage measure" and
  explicitly says it is not gross exposure. Plan 11 defines margin equity/requirements/excess
  and buying power but never defines any named leverage measure (grep confirms no leverage
  definition in plan 11). The `leverage` `ConstraintKind` is in the closed enum and the
  constraint-term tables, so an implementer must supply the formula with no guidance and cannot
  fall back to gross exposure by the spec's own words.
- **Fix:** Define the initial named leverage measure(s) (formula over NAV/positions/cash classifications) in plan 11 §12 and reference them from plan 10 §12.2.

## B5 — Initial metric catalog (`persistra.standard@1`) and most metric formulas are undefined

- **Severity:** major
- **Files/sections:** `15-results-...md` §10.2–10.3 and §17 (line 796: `metric_set="persistra.standard@1"`).
- **Description:** Plan 15 gives exact rules for TWR/MWR/annualization/drawdown, then says the
  remaining required families (Sharpe, Sortino, Calmar, VaR/ES, hit/payoff, alpha/beta/tracking
  error/information ratio, turnover, holding period, concentration, capacity, stability) each
  "own exact formula, requirement, minimum sample, interval, units, version, and golden
  fixtures" — but those definitions are never written, and the `persistra.standard@1` metric
  set invoked in the public API example is never enumerated. Plan 08 sets the precedent of
  writing exact formulas for its built-in catalog; plan 15 does not, so implementers must
  invent, e.g., the Sortino target convention, IR benchmark alignment, and concentration
  measure.
- **Fix:** Enumerate the initial metric definitions (name, version, exact formula, requirements, units) and the membership of `persistra.standard@1`, following plan 08's catalog style.

## B6 — Most `result_data` relations and the plan-12/13→plan-15 table mapping lack DDL

- **Severity:** major
- **Files/sections:** `15-results-...md` §7.2–7.3; `12-vectorized-simulator.md` §13 ("Their exact Plan-15 final-result mapping is deferred").
- **Description:** Plan 15 provides DDL only for `result_data.equity`, `returns`, and
  `cost_components`. The other fixed relations — `positions`, `cash`, `exposures`, `targets`,
  `rebalances`, `orders`/`order_transitions`/`fills`, `synthetic_fills`, `settlements`, `lots`,
  `borrow`, `margin`, `corporate_actions`, `cash_flows`, `quality_findings`,
  `fidelity_findings`, `lifecycle_events` — are prose bullets without column names, types,
  keys, or state constraints, even though plan 15 is the designated result-storage spec
  (umbrella §24.2: "Exact schemas belong in the result-storage specification"). Plan 12
  explicitly defers "their exact Plan-15 final-result mapping", and plan 15 never supplies the
  source-table→destination-table column mapping that the lossless-publication verification
  (§6.2 step 6) must implement.
- **Fix:** Add full DDL for every `result_data` relation and an explicit source→destination mapping table for plan-12/13 relations.

## B7 — No built-in catalog for event-execution latency, spread-estimator, slippage, or impact models

- **Severity:** major
- **Files/sections:** `13-event-...md` §4.2 (`SpreadSource: … bar_estimator …`), §8 (submission/activation latency), §11 (cost components), §18 (custom policy registration); `12-vectorized-simulator.md` §9; `18-testing-...md` §14.6 (benchmark presumes constant-slippage and per-share commission models).
- **Description:** Plans 12/13 define how cost components are recorded (sign, evidence class,
  roots) and how custom policies register, but no built-in policy definitions exist: the
  `bar_estimator` spread source has no formula (Corwin-Schultz? high-low proxy?), latency has
  only `LatencyRealizationId` and "duration/seeded latency realization" with no built-in policy
  kinds/parameters/defaults, and no built-in slippage or realized-impact model is defined
  (plan 10 defines *expected*-cost impact formulas only, and explicitly separates them from
  realized models). Yet plan 18's benchmark requires "constant 5 basis points one-way embedded
  slippage" and "commission USD 0.005/share with USD 1 minimum", implying built-in constant
  models must exist. Implementers must invent the entire initial execution-model surface.
- **Fix:** Enumerate initial built-in latency/spread/slippage/impact/fee policy definitions (names, parameters, formulas, defaults) in plan 13 (shared with plan 12), including the exact `bar_estimator` formula.

## B8 — Study objective computation is unwired: nobody is specified to compute the Plan-15 metric per run

- **Severity:** major
- **Files/sections:** `14-experiment-...md` §3.18, §6.4 ("An objective names one versioned Plan-15 metric/analysis output"), §2.2 (out of scope: "analysis calculations"); `15-results-...md` (no study-loop hook).
- **Description:** Bayesian search incorporates "only completed eligible objective observations
  through the prior round", and stop policies can depend on objective availability. The
  objective is defined as a Plan-15 metric/analysis output — but Plan-15 analyses are explicit
  post-run artifacts created by `project.analysis.*.compute(...)`, plan 14 declares analysis
  calculation out of scope, and plan 15 never defines a coordinator hook that computes the
  declared objective metric after each merge. So the loop run-completes → merge → objective
  value → next suggestion has a missing step: no plan says who computes the metric artifact,
  under what identity, or how its failure maps to the censor/penalty/ignore policy.
- **Fix:** Specify in plan 14 (or 15) that the coordinator invokes the exact declared Plan-15 metric computation after each publication, with its execution identity, ordering, and failure classification.

## B9 — Per-decision panel adjustment is delegated by plan 05 to plan 07 but never defined there

- **Severity:** major
- **Files/sections:** `05-market-...md` §14.6 ("Plan 07 generalizes this scalar contract to per-decision dataset panels; it may not replace it with one retrospective adjusted history"); `07-research-...md` §6.2 (pins "raw/adjusted mode … adjustment policy" only); `18-testing-...md` §14.4 (features 1–8 require "split-adjusted close" per decision).
- **Description:** Plan 05 adjustment materializations take a single scalar `AsOfContext`
  cutoff/anchor. Point-in-time research needs adjusted prices whose factor set differs at every
  decision row; plan 05 explicitly delegates that generalization to plan 07. Plan 07, however,
  only lists "raw/adjusted mode, action revisions, adjustment policy, and segments" among the
  fields a canonical bar input pins — it never defines the per-decision adjustment algorithm
  (is the anchor each row's decision instant? one materialization per decision? an incremental
  factor join?), its identity, or its cost model. The plan-18 benchmark depends on this
  (split-adjusted close for 8 of 10 features over 5,000 instruments × 20 years), so the gap is
  on the release-critical path.
- **Fix:** Add a plan-07 subsection defining the per-decision adjusted-bar adapter (anchor semantics, factor application, identity, and bounded execution) referencing plan 05 factors.

## B10 — Stateful-strategy registration and state-serialization contract undefined

- **Severity:** major
- **Files/sections:** `13-event-...md` §4.3 (`strategy: StatefulStrategyRef`), §6.4 ("strategy-owned prior state"), §14 (checkpoint binds "strategy state"; execution content includes "strategy/version/state schema"), §4.4 (limit on "bytes of strategy state").
- **Description:** The callback protocol (`on_event`) is defined, but nothing specifies how a
  user's `StatefulStrategy` is registered (qualified name/version? plan-08-style implementation
  capture?), what its "state schema" declaration contains, which types strategy state may hold,
  or how state is canonically serialized so that checkpoints verify and replay reproduces "the
  same state/command roots". Since strategy state is hashed into checkpoints and replay
  eligibility, an unconstrained Python object cannot work; the implementer must invent the
  typed state contract for the event simulator's most user-facing extension point.
- **Fix:** Define `StatefulStrategyRef` registration (identity capture per plan 08) and a closed typed state schema (allowed types, canonical serialization, size bounds) in plan 13.

## B11 — `CompositeAsOfContext` never defined

- **Severity:** minor
- **Files/sections:** `12-vectorized-simulator.md` §4.3 (line 171); `13-event-...md` §4.3 (line 164); `04-reference-...md` §4.3 (defines only single-snapshot `AsOfContext`).
- **Description:** Both simulator requests take `market_context: CompositeAsOfContext`, but the
  type appears nowhere else. Plan 04's `AsOfContext` covers one market snapshot; the composite
  variant's fields (composite snapshot ID, cutoff mode, public-cutoff policy, project cutoff,
  per-member precedence?) must be inferred.
- **Fix:** Define `CompositeAsOfContext` (fields and validation) in plan 04 or 07 and reference it from plans 12/13.

## B12 — `SeedSpec` and the "pinned counter-based generator" algorithm are never specified

- **Severity:** minor
- **Files/sections:** `12-vectorized-simulator.md` §4.3; `13-event-...md` §4.3/§17; `14-experiment-...md` §5 (`SeedSpec(0)`); `08-features-...md` §18.2; `09-alpha-...md` §12.2/§21.5.
- **Description:** Four plans require deterministic namespaced seed streams via a "registered/
  pinned counter-based generator", and requests carry a `SeedSpec`, but no file defines
  `SeedSpec`'s fields (a bare int? namespace map?) or names the generator algorithm (Philox,
  SHA-based, etc.). Plan 18 §14.3 defines its own SHA-256 stream for fixtures only. Since seeds
  and generator identity enter execution identity, any deterministic choice works, but the
  shared contract is a gap each implementer would resolve differently.
- **Fix:** Define `SeedSpec` and name one counter-based generator algorithm/namespacing rule in plan 01 (or 08) for all consumers.

## B13 — Plan 03 `catalog.dataset_state` / `catalog.source_state` have no DDL

- **Severity:** minor
- **Files/sections:** `03-catalog-...md` §15 (lines 849–855).
- **Description:** Every other plan-03 table gets normative DDL; the rolling-state tables that
  snapshot manifests depend on are described only in prose ("revision count, terminal batch
  count, latest catalog sequence, and a rolling chain content ID"). Column names/types/keys
  must be invented, and the snapshot-creation rebuild-verify step (§16.2) reads them.
- **Fix:** Add `CREATE TABLE` DDL for `catalog.dataset_state` and `catalog.source_state`.

## B14 — `RegisteredNaturalKey`, `TemporalFields`, `CanonicalPayload` types undefined

- **Severity:** minor
- **Files/sections:** `03-catalog-...md` §8 (`CanonicalStagingRecord` protocol, lines 505–519).
- **Description:** The staging-record protocol's three return types are never given schemas.
  Their content is mostly inferable from the `catalog.batch_records` columns (§7.4), but the
  value-object contracts (validation, canonical serialization inputs to the three content IDs)
  are what adapters actually implement against.
- **Fix:** Define the three value objects (fields, validation, canonical serialization) in plan 03 §8.

## B15 — Restore/fork have semantics but no invocation surface

- **Severity:** minor
- **Files/sections:** `02-project-...md` §9 (`MaintenanceIntent` includes `restore`, `fork`, `verify_copy`, `inspect`), §13.4, §15.2 (CLI list).
- **Description:** §13.4 fully specifies restore/fork behavior, and the intents exist, but no
  Python service method signature (`databases.restore(...)`? destination/ProjectId parameters)
  and no CLI command (`persistra db restore`/`fork` absent from §15.2) are defined. An
  implementer must invent the API shape for a confirmation-sensitive operation.
- **Fix:** Add `restore()`/`fork()` service signatures and matching CLI commands to §13/§15.

## B16 — `ProjectServices.transactions` and `.diagnostics` namespaces have no interface

- **Severity:** minor
- **Files/sections:** `02-project-...md` §5 ("It initially exposes `databases`, `transactions`, and `diagnostics`").
- **Description:** The `databases` service methods are specified; `transactions` and
  `diagnostics` are named but never given a single method anywhere (transaction *rules* are
  specified in §16, but not the public service surface; `doctor` is CLI-only).
- **Fix:** Enumerate the public methods of the `transactions` and `diagnostics` services (or remove them from the initial surface).

## B17 — Presentation/dashboard limits and reduction-policy parameters unenumerated

- **Severity:** minor
- **Files/sections:** `16-plotly-...md` §5.2 (`FigureLimits()`, `ReportLimits`, `VisualReductionPolicy.none()`), §8, §14; `17-streamlit-...md` §5.1 (`DashboardLimits()`), §12.
- **Description:** Every earlier plan enumerates its limits dataclass fields with defaults
  (e.g., plans 07/08/09/10/11/12). Plans 16/17 reference `FigureLimits`, `ReportLimits`,
  `VisualReductionPolicy` (parameters for envelope/thinning/top-N reductions), and
  `DashboardLimits` but list only prose categories of what limits "cover". Field names and
  defaults must be invented, and limits enter report/execution identity.
- **Fix:** Enumerate the fields/defaults of `FigureLimits`, `ReportLimits`, `VisualReductionPolicy` variants, and `DashboardLimits` as the other plans do.

## B18 — Initial fundamental-mapping content (taxonomy tags → 13 concepts) unspecified

- **Severity:** minor
- **Files/sections:** `06-fundamentals-...md` §8.1.
- **Description:** The 13 curated concepts are named and the mapping *mechanism* (sign/scale/
  dimension policy, versioning) is fully specified, but the actual initial mappings (which
  US-GAAP/source concepts feed `persistra.fundamental.revenue`, etc.) are left entirely open
  even though normalization golden tests (§24.1) and downstream features depend on them. This
  is authorable data, but release-gating; the spec should at least declare the deliverable and
  review criteria.
- **Fix:** Add (or explicitly defer to a named deliverable) the initial per-concept source-taxonomy mapping tables with review criteria.

## B19 — Built-in external-flow timing policy options undefined

- **Severity:** minor
- **Files/sections:** `15-results-...md` §7.3 (`flow_timing_policy_content_id`), §10.2; `12-vectorized-simulator.md` §13 (flow-split return intervals).
- **Description:** TWR chaining requires "exact valuation immediately before/after each
  external flow under the declared flow-timing policy", and every `result_data.returns` row
  pins a flow-timing policy content ID, but no plan enumerates the built-in policy values
  (start-of-interval vs end-of-interval flow treatment, same-instant flow ordering relative to
  valuation). Plan 12's grid priorities partly imply an ordering, but the policy the simulator
  writes and plan 15 interprets is never defined.
- **Fix:** Define the initial named flow-timing policy value(s) and semantics once (plan 12 or 15) and reference from both.

## B20 — Small referenced-enum/value gaps (nits)

- **Severity:** nit
- **Files/sections:** `06-fundamentals-...md` §11.2 (`MacroVintageMode.LATEST_KNOWN` used in code; enum values only in prose); `13-event-...md` §10 ("policy groups" in capacity allocation never defined); `12-vectorized-simulator.md` §4.3 (`AccountingPolicyBundleRef` contents inferable from plan 11 §4.1 policy list but never stated); `05-market-...md` §8 (`staleness_policy` structure for `bars.classify_at` described only as "versioned maximum age/session rule").
- **Description:** Each has an obvious default or is fully inferable from adjacent prose, but a
  one-line definition would remove the need for inference.
- **Fix:** Enumerate `MacroVintageMode` values, define capacity "policy groups", list the required members of `AccountingPolicyBundleRef`, and give `StalenessPolicy` fields.

---

## Explicit non-findings

- **Acceptance criteria:** every plan (01–18) has concrete acceptance tests and exit criteria;
  no missing-acceptance findings.
- **Error handling:** failure/rollback/recovery behavior is specified at essentially every
  transaction, checkpoint, handoff, and rename boundary; I could not verify any silent path an
  implementer must handle without guidance.
- **Umbrella-declared deferrals** (e.g., dependency lower bounds, Streamlit version pins,
  benchmark host runbook details) are explicit implementation-time decisions and were not
  counted as gaps.
