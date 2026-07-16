# Round 2 — Reviewer A (consistency)

Scope: contradictions, terminology drift, and mismatched interfaces/assumptions across the
19 files in `docs/v3/` (`01-*.md` … `18-*.md` plus `v3-spec.md`). Every finding below was
re-verified against the cited owning and consuming contracts. Missing detail that does not
create a cross-contract conflict is outside this reviewer's scope.

---

## A11 — The benchmark RNG does not use Plan 01's mandatory counter-based seed algorithm

**Severity:** major

**Files/sections:**
- `01-domain-identity-time-money-events.md` §9 "Deterministic ordering" (lines ~749–757)
- `18-testing-conformance-properties-benchmark.md` §14.3 "Raw daily bars and actions"
  (lines ~455–461)

**Description:** Plan 01 now says every deterministic-randomness consumer uses
`persistra.seed.sha256_counter@1`, whose draw `k` hashes canonical
`(root, l1, …, ln, k)` bytes. Plan 18 instead defines its own `H(label, parts...)` by hashing
canonical JSON for
`["persistra.benchmark.daily_equity_5000x20@1", 20250300, label, parts...]`; the namespace
precedes the root, there is no separately defined final counter, and the benchmark does not
bind the Plan-01 generator identity. These byte sequences cannot generally be the same
stream. Because Plan 18 requires an independent validator to reproduce exact generated
roots, implementing the owning Plan-01 contract and implementing the benchmark literally
produce different fixtures.

**Proposed fix:** Rewrite Plan 18's `H` as an explicit named-label/counter use of
`SeedSpec(20250300)` and `persistra.seed.sha256_counter@1`, with an exact mapping from every
current `parts` tuple to labels and `k`.

---

## A12 — The shared domain-adapter envelope cannot represent the source-missing state that the builder requires

**Severity:** major

**Files/sections:**
- `07-research-datasets-temporal-joins-sql-workspaces-safety.md` §6.2 "Ordered input
  contract" (`CandidateEnvelope.state`, lines ~295–326)
- `07-…md` §11 "Missing input, row retention, and audit" (lines ~611–632) and §22
  "Required edge-case behavior" (lines ~1950–1961)
- `05-market-bars-trades-quotes-actions-adjustments.md` §4.2/§7.3 (`BarState.no_trade`)
- `06-fundamentals-estimates-macro-benchmarks-rates.md` §7.1 (`is_nil`/`nil_reason_code`)
  and §16 (nil/source-missing query audit)

**Description:** The newly specified `CandidateEnvelope.state` admits only `value`,
`retracted`, `unavailable`, and `conflict`. The same plan requires the builder to emit a
distinct `source_missing` input outcome only when a cutoff-eligible source row explicitly
asserts nil/no-trade/no-value; mere absence must remain `not_available`. Plans 05 and 06 own
exactly those explicit `no_trade` and `is_nil` source rows. The adapter therefore has no
typed state with which to carry the evidence needed for the required distinction. Mapping
nil to `value` forces the builder to infer state from nullable payload fields, while mapping
it to `unavailable` collapses a distinction that §22 expressly requires.

**Proposed fix:** Add `source_missing` (with its reason/evidence identity) to the closed
`CandidateEnvelope` state contract and require Plan-05/06 adapters to use it for eligible
`no_trade`/nil observations.

---

## A13 — Plan 15's blanket "replace the run/book ID" copy rule is not applicable to many mapped source relations

**Severity:** major

**Files/sections:**
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.2 "Fixed result
  series" and §7.4 "Source mapping" (lines ~287–312 and ~394–426)
- `11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md` §15.1
  (`accounting.portfolio_states`, `journal_data.portfolio_state_positions`, and
  `journal_data.portfolio_state_cash`), plus the child relations named by Plan 15 in
  §§8–13
- `12-vectorized-simulator.md` §13 (`simulation.rebalance_decisions` and
  `simulation_data.trade_intents`)
- `13-event-clock-orders-bar-execution-costs-fidelity.md` §15
  (`simulation.order_transitions`)

**Description:** Plan 15 says every mapped relation is column-identical after replacing
"the source's per-run/book/simulation ID column" with `run_record_id`. That assumption is
false for multiple mapped child/state tables. For example,
`journal_data.portfolio_state_positions` and `portfolio_state_cash` contain only
`portfolio_state_id`, not a run/book ID; their required instant lives in the parent
`accounting.portfolio_states.state_at`. Likewise `simulation_data.trade_intents` has only
`rebalance_decision_id`, `simulation.order_transitions` has only `order_id`, and several
Plan-11 transition/component child tables have only their parent IDs. Replacing those IDs
would destroy their parent joins; retaining them without adding `run_record_id` would fail
Plan 15's destination-key contract. The positions mismatch is also semantic: Plan 15 says
the result relation contains an instant and price/exposure fields that are not columns of
the claimed column-identical source relation.

**Proposed fix:** Replace the blanket rule with explicit per-physical-table mappings that
add `run_record_id`, preserve parent IDs, specify required parent joins/denormalized fields,
and give exact destination DDL for each mapped relation.

---

## A14 — Plan 15 assumes copyable per-component cost rows that the event simulator does not persist

**Severity:** major

**Files/sections:**
- `13-event-clock-orders-bar-execution-costs-fidelity.md` §11 "Price and realized costs"
  and §15 "Physical schema" (especially `simulation_data.fills`)
- `12-vectorized-simulator.md` §9 "Synthetic execution and realized costs" and §13
  "Metadata and physical schemas"
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.3 "Core series
  schema" (`result_data.cost_components`, lines ~358–392)

**Description:** Plan 13 requires every spread/slippage/delay/impact component to retain
amount per unit, sign, unit, evidence state, model/version, inputs, and availability, but its
physical schema persists only one `cost_component_content_id` on each fill (plus one total
direct-fee amount); it defines no normalized component-row relation. Plan 15, however,
requires one `result_data.cost_components` row per component with `source_id`,
`component_kind`, `evidence_state`, `amount_usd`, and `unit`, and says simulator facts are
published losslessly rather than derived during publication. Plan 12 says unnamed fixed
relations store realized components and points back to Plan 15 for the mapping, but that
does not close the Plan-13 interface or identify a worker source relation. A content ID
alone cannot be copied column-for-column into Plan 15's normalized rows.

**Proposed fix:** Define one shared Plan-12/13 worker `simulation_data.cost_components`
relation with columns compatible with Plan 15, and map it explicitly by adding
`run_record_id` while preserving the fill/synthetic-fill source identity.

---

## A15 — Plan 06's unit vocabulary conflicts with the exact Plan-01 unit registry consumed by Plan 07

**Severity:** minor

**Files/sections:**
- `01-domain-identity-time-money-events.md` §7.8 "Units" (lines ~556–591)
- `06-fundamentals-estimates-macro-benchmarks-rates.md` §7.1 "Schema"
  (lines ~350–361)
- `07-research-datasets-temporal-joins-sql-workspaces-safety.md` §6.2 "Ordered input
  contract" (adapter `unit_specs`, lines ~295–334)

**Description:** Plan 01 makes unit compatibility exact and requires dimensionless values
to use `ratio`, `rate`, or `bps`; the built-in quantity unit is singular `share`, and
free-text units are rejected. Plan 06 still calls nonmonetary units "UCUM-style/qualified"
and gives `shares` and `pure` as examples. Plan 07 now requires every Plan-06 adapter output
to declare Plan-01 `UnitSpec`s, so a literal Plan-06 adapter either emits units the shared
contract forbids (`pure`) or creates exact-text incompatibility (`shares` versus `share`).

**Proposed fix:** Rewrite Plan 06 to map source units into Plan-01 canonical `share`,
`ratio`, `rate`, or `bps` values (retaining the original source-unit text only as lineage),
and reserve registration for genuinely new compatible dimensions.

---

## Findings summary

| ID | Severity | File(s) | Summary |
| --- | --- | --- | --- |
| A11 | major | 01 vs 18 | Benchmark hash-based RNG is not the mandatory Plan-01 counter stream |
| A12 | major | 07 vs 05, 06 | Adapter envelope omits the explicit source-missing state required for no-trade/nil evidence |
| A13 | major | 15 vs 11–13 | Blanket ID-replacement/column-identical copy rule cannot map child and portfolio-state relations |
| A14 | major | 15 vs 12, 13 | Plan 15 expects normalized cost-component rows absent from the Plan-13 worker schema |
| A15 | minor | 01, 07 vs 06 | `shares`/`pure` unit vocabulary conflicts with exact `share`/`ratio`/`rate` UnitSpecs |

No blockers were found. Other Round-1 consistency findings and their recorded fixes were
rechecked and remain resolved.
