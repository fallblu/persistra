# V3 spec review — issues ledger

Persistent ledger for the iterative review/revision loop over `docs/v3/`.
Every finding ever raised gets a row. Statuses: open / fixed / rejected / deferred.
Severities: blocker / major / minor / nit. Full reports: `round-N-{A,B,C}.md`.

| ID | Round | File(s) | Severity | Summary | Status | Resolution notes |
|----|-------|---------|----------|---------|--------|------------------|
| A1 | 1 | 02 vs 10–17 | major | Service surface split between `project.services.*` (plans 02–09) and `project.<domain>.*` (plans 10–17) | fixed | All plan 10–16 API snippets rewritten to `project.services.<domain>.*` (plan-02 convention); plan 17 and v3-spec had no direct usages |
| A2 | 1 | 11 vs 12, 13 | major | Plan 11 requires four-value `FillSide` owned by plan 13; plans 12/13 define/persist only `buy`/`sell` | fixed | `FillSide` (`buy`/`sell`/`sell_short`/`buy_to_cover`) defined in 13 §4.2 with derivation rule; fills DDL CHECKs updated in 13 §15 and 12 synthetic_fills; 12 §9 references it |
| A3 | 1 | 10 vs 01, 05, 07–09 | major | Plan-10 frames use `datetime64[ns, UTC]`/nullable `Float64` against project-wide `datetime64[us, UTC]`/finite `float64` | fixed | 10 §19.1 aligned to `datetime64[us, UTC]`, finite `float64` with state/reason rows, plan-01 typed-wire `string` IDs |
| A4 | 1 | 01 vs 08–10, 12 | minor | Plan-01 event-namespace registry omits ~14 namespaces used by later plans' events | fixed | 12 namespaces added to 01 §8.2 (feature, label, component, alpha, validation, signal, forecast, risk_model, expected_cost, constraint_set, portfolio_constructor, simulation) |
| A5 | 1 | v3-spec vs 13 | minor | Umbrella lifecycle diagram shows `partially filled` status forbidden by its own text and plan-13 `OrderStatus` | fixed | Node removed from §21.3 diagram; explicit "partial fills stay `active`" sentence added |
| A6 | 1 | 02, 15 | minor | `experiments`/`results`/`analysis`/`annotations` both bootstrap-reserved and "added" by plan 14/15 migrations | fixed | 02 §8.1 now states bootstrap creates all reserved schemas; plans 14/15 add tables to reserved schemas and add only `*_data` as new schemas |
| A7 | 1 | 02 | minor | CLI flag drift: `db create --role research` (§7) vs `--database research` (§15.2) | fixed | §7 changed to `--database research` |
| A8 | 1 | 03 vs 02, v3-spec | nit | `data doctor` command name vs `persistra doctor` | fixed | 03 §9.2 changed to `persistra doctor` |
| A9 | 1 | 05 | nit | Reference to nonexistent "section 7.5"; content is in §7.3 | fixed | Reference corrected to §7.3 |
| A10 | 1 | 09, 10 vs 14 | nit | Fold ordinal `INTEGER` vs `BIGINT` across schemas binding the same value | fixed | 14 `experiment_folds` ordinals changed to `INTEGER` (matches owning plan 09) |
| B1 | 1 | 01, 07, 08, 10, 15 | major | `UnitSpec`/`Unit` system attributed to plan 01 but never defined anywhere | fixed | New 01 §7.8: `Unit`/`UnitSpec`/`NumericKind`, canonical text grammar, built-in registry, exact-equality compatibility, content-ID participation; exported from `persistra.domain` |
| B2 | 1 | 12, 13, 15, v3-spec | major | `UnsafeRunOverride`/`UnsafeAnalysisOverride` has no schema or acceptance semantics | fixed | Dataclass + per-input/per-finding acknowledgement, rejection, and propagation semantics defined in 12 §4.3; 13 and 15 reference it |
| B3 | 1 | 07, 04–06 | major | Domain query adapter / candidate envelope protocol never specified | fixed | Typed `DomainQueryAdapter` protocol + `CandidateEnvelope` schema added to 07 §6.2 with per-plan adapter ownership and registration validation |
| B4 | 1 | 10, 11 | major | `leverage` constraint's plan-11 leverage measure never defined | fixed | Plan-11 leverage-measure registry added (§12.1) with `persistra.leverage.gross_market_value_over_equity@1` formula; 10 §12.2 references it |
| B5 | 1 | 15 | major | Initial metric catalog (`persistra.standard@1`) and formulas never written | fixed | New 15 §10.4: full catalog table (26 metrics) with formulas, units, minimum samples, shared conventions; stability metrics assigned to comparison analyses |
| B6 | 1 | 15, 12 | major | Most `result_data` relations lack DDL; plan-12/13→15 mapping deferred to nowhere | fixed | New 15 §7.4: column-identical copy contract + full source-mapping table; DDL added for the four sourceless relations (exposures, quality_findings, fidelity_findings, lifecycle_events); 12 §13 deferral replaced by reference |
| B7 | 1 | 13, 12, 18 | major | No built-in latency/spread/slippage/fee model definitions | fixed | New 13 §11.1 built-in catalog: zero/constant latency, constant-bps + Corwin–Schultz spread, zero/constant-bps slippage, delay/impact policy, zero/per-share fees; benchmark bindings named |
| B8 | 1 | 14, 15 | major | Study objective computation unwired | fixed | 14 §6.4 now specifies coordinator-owned plan-15 metric computation after each publication, identity, failure classification, replay behavior |
| B9 | 1 | 05, 07, 18 | major | Per-decision panel adjustment delegated to plan 07 but never defined | fixed | New 07 §9.1: per-decision anchor semantics, factor eligibility under row cutoffs, scalar-equivalence requirement, identity and bounded execution |
| B10 | 1 | 13 | major | `StatefulStrategyRef` registration and state schema/serialization undefined | fixed | 13 §6.4 extended: plan-08-style registration, closed typed state schema, plan-01 canonical serialization, size/versioning rules |
| B11 | 1 | 12, 13, 04 | minor | `CompositeAsOfContext` never defined | fixed | Defined in 04 §4.3 as `AsOfContext` variant pinned to one `CompositeSnapshotId` manifest |
| B12 | 1 | 12–14, 08, 09, 01 | minor | `SeedSpec` and counter-based generator never specified | fixed | Defined in 01 §9: `SeedSpec(root)`, `persistra.seed.sha256_counter@1` SHA-256 counter stream, identity participation; exported |
| B13 | 1 | 03 | minor | `catalog.dataset_state`/`source_state` prose-only, no DDL | fixed | DDL added in 03 §15 |
| B14 | 1 | 03 | minor | `RegisteredNaturalKey`, `TemporalFields`, `CanonicalPayload` undefined | fixed | Value-object contracts defined in 03 §8 |
| B15 | 1 | 02 | minor | Restore/fork have no service signature or CLI command | fixed | `databases.restore()`/`fork()` signatures + `persistra db restore`/`fork` CLI added to §13.4 and §15.2 |
| B16 | 1 | 02 | minor | `transactions`/`diagnostics` namespaces have no interface | fixed | Method lists added in §5 (`in_transaction`/`run`; `doctor`/`events`) |
| B17 | 1 | 16, 17 | minor | `FigureLimits`/`ReportLimits`/`VisualReductionPolicy`/`DashboardLimits` fields unenumerated | fixed | Dataclasses with fields/defaults added in 16 §5.2 and 17 §5.1; four reduction variants defined |
| B18 | 1 | 06 | minor | Initial taxonomy→concept mapping content unspecified | fixed | Declared as named release-gating data deliverable in §8.1 with explicit review criteria (spec-external by design) |
| B19 | 1 | 15, 12 | minor | Built-in external-flow timing policy never defined | fixed | `persistra.flow_timing.pre_flow_valuation@1` defined in 15 §7.3 with same-instant and boundary rules |
| B20 | 1 | 06, 13, 12, 05 | nit | `MacroVintageMode` values, capacity "policy groups", `AccountingPolicyBundleRef` members, `StalenessPolicy` fields | fixed | All four enumerated in their owning plans |
| C1 | 1 | 02 | major | Lease registry: can two in-process Projects both hold the exclusive lease? | fixed | §11.2 now: reentrant counting is shared-mode only; exclusive is owned by exactly one project lifecycle |
| C2 | 1 | 01 | minor | Clock-regression check scope undefined | fixed | §6.7 pinned to greatest `recorded_at` in the same target database, any writer |
| C3 | 1 | 04 | minor | Calendar coverage failure behavior never pinned | fixed | §10.3: direct APIs raise `CalendarCoverageError`; availability surfaces record structured unavailability with same reason code |
| C4 | 1 | 05 | major | Dividend reference close: strict previous session vs walk-back ambiguous | fixed | §14.4 pinned to strictly previous calendar session, no walk-back; missing close → unavailable (consistent with existing failure clause) |
| C5 | 1 | 05 | minor | `observed_through_at` monotonicity across partial revisions unstated | fixed | §7.2: nondecreasing required; regression quarantines |
| C6 | 1 | 13 | major | Non-gap intrabar touch fill price never specified | fixed | §9.2: non-gap limit fills at limit, stop converts at stop; gaps use open/reference; costs never move a limit fill through its limit |
| C7 | 1 | 08 | minor | Triple-barrier touching undefined at exact equality | fixed | §17.5: inclusive (`>=` upper, `<=` lower) |
| C8 | 1 | 11 | major | No defined source of marginability for simplified margin policy | fixed | §12.2: policy-registered effective-dated classification table with stated default; unclassified → unavailable |
| C9 | 1 | 13 | minor | `day` TIF undefined for between-session activation | fixed | §8: belongs to next eligible session, expires at that session's cycle end |
| C10 | 1 | 06 | minor | `original` filing mode silently promotes an amendment when original withdrawn | fixed | §7.2: `original` = earliest accepted `is_amendment = false`; withdrawn → structured unavailable |
| C11 | 1 | 15 | minor | `year_duration` constant never pinned | fixed | §10.2: exactly 365.25 days of elapsed UTC time |
| C12 | 1 | 18 | minor | Benchmark recurrence `p` ambiguous (stored vs unrounded close) | fixed | §14.3: `p` = stored quantized close of previous active session |
| C13 | 1 | 05 | nit | Row-ceiling behavior at exactly 5,000,000 rows undefined | fixed | §6: exactly-at-ceiling succeeds; exceeding raises |
| CC1 | 1* | 12, 15, 02 | major | Round-1 edit regression: plan-12 pointed equity/returns/findings at 15 §7.4, which excludes them / claims findings have "no source relation" | fixed | 12 §13 now points at §7.3+§7.4 with plan-15 return states; 15 §7.4 reworded (DDL owned, rows mapped from worker relations) |
| CC2 | 1* | 02 | major | Round-1 edit regression: "later plans add only `*_data` schemas" contradicts plans 10–13 adding `portfolio`/`accounting`/`simulation` | fixed | Sentence scoped: plans 10–13 add domain schemas; plans 14–15 add only `*_data` as new schemas |
| CC3 | 1* | 16 | major | New closed `VisualReductionPolicy` list omitted the event-preserving thinning §8/§17.1 require | fixed | `event_preserving(stride)` variant added |
| CC4 | 1* | 13 | major | New §9.2 "costs never move a limit fill through its limit" contradicted the "before modeled costs" gap bullet and unconditional §11.1 formulas | fixed | Rule pinned: pre-cost reference respects the limit; modeled costs may worsen the all-in price |
| CC5 | 1* | 15 | minor | New §10.4 cited wrong sections (12 for comparison, 16 for fixtures) | fixed | Corrected to §13 and §10.3 |
| CC6 | 1* | 15 vs 01 | minor | §10.1 unit example `shares` collides with plan-01 built-in `share` under exact-text equality | fixed | Changed to `share`; plan-01 registration requirement noted |
| CC7 | 1* | 15 | minor | §10.3 requires an exposure metric family absent from the "exactly" §10.4 catalog | fixed | Exposure families explicitly served by `result_data.exposures`/attribution, not catalog scalars |
| CC8 | 1* | 07 vs 05 | minor | New §6.2 listed "adjustments" as a plan-05 adapter dataset; plan 05 owns no adjustments dataset | fixed | Dropped; adjusted mode is a bar-adapter mode per §9.1 |
| CC9 | 1* | 02 | nit | New §5 service list cited "(sections 8, 13, 15)" omitting §14 for `migrate` | fixed | Now "(sections 8, 13, 14, 15)" |

## Round log

- **Round 1** (2026-07-16): Reviewers A/B/C returned 10 + 20 + 13 = 43 findings
  (0 blocker, 17 major, 21 minor, 5 nit). All 43 verified against the spec text and
  accepted; no duplicates (reviewer scopes were disjoint); none rejected. All 43 fixed
  (B18 resolved by declaring the mapping content a named release-gating deliverable with
  review criteria rather than inlining provider-specific tag tables). The post-fix
  consistency check (rows CC1–CC9, marked round 1*) found 9 issues in/exposed by the
  edits (4 major, 4 minor, 1 nit); all 9 fixed the same round. Everything else it checked
  — FillSide, qualified-name collisions, the §7.4 source-relation names against plans
  11/12/13 DDL, seeds, dtypes, durations, lifecycle diagram, fold ordinals — verified
  consistent.
