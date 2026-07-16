# Round 3 — Reviewer A (consistency)

Scope: contradictions, terminology drift, and mismatched interfaces/assumptions across the
19 files in `docs/v3/` (`01-*.md` … `18-*.md` plus `v3-spec.md`). Every finding below was
checked against both the owning and consuming contracts. Missing detail that does not create
a cross-contract conflict is outside this reviewer's scope.

---

## A16 — `RunRef` names roots that do not exist in the run registry

**Severity:** major

**Files/sections:**
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.1 "Registry schema"
  (`results.runs`)
- `15-results-analysis-metrics-attribution-comparison-export.md` §9.1 "Request and identity"
  (`RunRef`)
- `16-plotly-visualization-html-reports.md` §5.2 "Theme and render values"
  (`FigureRequest.inputs` and `ReportRequest.inputs`)

**Description:** The authoritative run row stores `artifact_manifest_content_id` and
`table_manifest_content_id`. `RunRef` instead requires `artifact_content_id` and
`output_manifest_content_id`; neither field exists in `results.runs`, and no alias or
derivation maps them. Plan 16 consumes this exact type while requiring all friendly inputs to
resolve to exact persisted roots before figure/report identity freezes. An implementation
therefore cannot construct or validate a `RunRef` from the run registry without inventing a
new root or an undocumented field mapping.

**Proposed fix:** Change `RunRef` to carry `artifact_manifest_content_id` and
`table_manifest_content_id` with the exact Plan-15 registry meanings (or add identically named
authoritative columns and a specified mapping to `results.runs`).

---

## A17 — The default accounting bundle assigns a result flow-timing policy to its accrual slot

**Severity:** major

**Files/sections:**
- `11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md` §4.3
  "Public immutable values" (`AccountingPolicyBundleRef.accruals` and the installed bundle)
- `11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md` §10.2
  "Accrual calculation"
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.3 "Core series schema"
  (`persistra.flow_timing.pre_flow_valuation@1`)

**Description:** Plan 11 types the bundle's `accruals` member as `AccrualPolicyRef` but says
the installed `persistra.accounting.us_equity_research@1` bundle resolves
`pre_flow_valuation` as its "accrual timing." The only policy with that token in the v3
contracts is Plan 15's `persistra.flow_timing.pre_flow_valuation@1`, which controls how
external cash flows split performance-return subperiods; it is not an accounting accrual
policy and does not define Plan-11 principal/rate/accrual-boundary behavior. Because Plan 11
also requires policy refs to resolve by exact kind, the documented default bundle is either
kind-invalid or depends on a second, unnamed policy that collides terminologically with the
Plan-15 policy.

**Proposed fix:** Give the Plan-11 accrual member its own qualified, registered accrual policy
and reserve `persistra.flow_timing.pre_flow_valuation@1` exclusively for Plan-12/13 return
sampling and Plan-15 interpretation.

---

## A18 — Plan 07's feature/label input refs do not match Plan 08's public IDs or lineage-root shape

**Severity:** major

**Files/sections:**
- `07-research-datasets-temporal-joins-sql-workspaces-safety.md` §6.2 "Ordered input
  contract" (`FeatureInputRef` and `LabelInputRef`)
- `08-features-labels-bounded-execution-temporal-conformance-provenance.md` §4.1 "Typed
  IDs"
- `08-features-labels-bounded-execution-temporal-conformance-provenance.md` §14.3
  "Completed materializations"
- `08-features-labels-bounded-execution-temporal-conformance-provenance.md` §14.4 "Output
  lineage"

**Description:** Plan 08 makes `FeatureMaterializationId` and `LabelMaterializationId`
distinct public types and explicitly says its repository chooses the typed ID at the public
boundary. Plan 07 collapses both fields to abstract `EntityId`, despite already separating
the two ref dataclasses. More importantly, each ref requires one
`relationship_root_content_id`, while Plan 08 persists
`relationship_root_manifest_content_id` per decision/instrument/output lineage row and
defines no materialization-level root with Plan 07's name or cardinality. Plan 07 says the
ref pins per-output relationship roots, so a Plan-08 handle cannot populate this scalar ref
without inventing an undocumented aggregate or discarding row-level distinctions.

**Proposed fix:** Use `FeatureMaterializationId`/`LabelMaterializationId` in their respective
refs and either define a Plan-08 aggregate `relationship_root_manifest_content_id` for the
selected outputs or make Plan 07 consume the exact per-row/output lineage-root manifest.

---

## A19 — Plan 15 still advertises shorthand result relation names that its exact mapping forbids

**Severity:** minor

**Files/sections:**
- `11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md` §§8–13
  (normalized accounting relation names)
- `12-vectorized-simulator.md` §13 "Metadata and physical schemas"
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.2 "Fixed result series"
- `15-results-analysis-metrics-attribution-comparison-export.md` §7.4 "Source mapping"

**Description:** Section 7.2 calls `result_data.targets`, `rebalances`, `settlements`,
`lots`, `borrow`, `margin`, and `corporate_actions` core fixed relations. Section 7.4 now
states there is no paired-source alias and instead declares the actual physical destinations
`run_targets`, `rebalance_decisions`, `settlement_obligations`,
`settlement_transitions`, `inventory_lots`, `lot_relief_applications`, `borrow_lots`,
`borrow_transitions`, `margin_evaluations`, `margin_components`,
`corporate_action_applications`, and `entitlements`, matching the Plan-11/12 source DDL.
The earlier names therefore read as tables that the normative mapping expressly does not
create, leaving query/report consumers with two vocabularies for the same result surface.

**Proposed fix:** Rewrite §7.2 with the exact §7.4 physical relation names, or explicitly
label the shorthand as logical kinds and provide their complete one-to-many physical mapping.

---

## Findings summary

| ID | Severity | File(s) | Summary |
| --- | --- | --- | --- |
| A16 | major | 15, 16 | `RunRef` root fields do not exist in the authoritative run registry |
| A17 | major | 11, 15 | Default accounting accrual slot points at the results-layer flow-timing policy |
| A18 | major | 07, 08 | Feature/label refs collapse typed IDs and assume a lineage-root shape Plan 08 does not expose |
| A19 | minor | 11, 12, 15 | Fixed-series prose names result tables that the exact no-alias mapping does not create |

No blockers were found.
