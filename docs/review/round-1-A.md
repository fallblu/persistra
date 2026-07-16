# Round 1 — Reviewer A (consistency)

Scope: contradictions, terminology drift, and mismatched interfaces/assumptions across the
19 files in `docs/v3/` (`01-*.md` … `18-*.md` plus `v3-spec.md`). Every finding was
re-verified against both cited locations before inclusion. Missing detail, ambiguity, and
completeness are out of scope for this reviewer.

---

## A1 — Two incompatible project-service access patterns: `project.services.*` vs `project.<domain>.*`

**Severity:** major

**Files/sections:**
- `02-project-databases-leases-copies-migrations.md` §5 "Public API" (lines ~160–165)
- `03-…md` §5 (line 124), `04-…md` §8.4/§9/§10.4/§14.1, `05-…md` §8/§9.2/§15.2,
  `06-…md` §7.2/§11.2/§15, `07-…md` §6.3/§13.1/§17.1/§19.1, `08-…md` §13.1,
  `09-…md` §21.1 (lines 1917–1938) — all use `project.services.<namespace>`
- `10-…md` §18.1 (lines 2437–2458), `11-…md` §18 (lines 1973–1988),
  `12-…md` §14 (lines 788–797), `13-…md` §16 (lines 656–663),
  `14-…md` §15 (lines 654–659), `15-…md` §17 (lines 794–801),
  `16-…md` §12 (lines 447–449) — all use `project.<domain>.*` with no `services` segment

**Description:** Plan 02 defines the canonical service surface: "`Project.services` is a
frozen namespace populated only with capabilities valid for the open mode. It initially
exposes `databases`, `transactions`, and `diagnostics`; later plans add namespaced
services." Plans 03–09 follow this exactly (`project.services.ingestion.begin(...)`,
`project.services.reference.resolve_identifier(...)`, `project.services.market.bars.query(...)`,
`project.services.research.datasets.build(...)`, `project.services.research.alpha.register(...)`).
Plans 10–17 instead hang services directly off `Project`:
`project.portfolio.signals.register(definition)`, `project.accounting.books.create(request)`,
`project.simulation.vectorized.plan(request)`, `project.experiments.plan(request)`,
`project.results.get(run_record_id)`, `project.analysis.metrics.compute(...)`,
`project.reports.plan(request)`. Plan 10 even mixes both patterns inside one code block
(§18.1): `project.portfolio.forecasts.plan_fit(request)` on one line and
`project.services.research.validation.authorize_training(...)` two lines later. Plan 02's
capability/mode-gating contract (e.g., `CapabilityUnavailableError` for a write capability
in read-only mode) is specified for the `Project.services` namespace, so an implementer of
plans 10–17 building `project.portfolio` / `project.accounting` / etc. would place half of
the service surface outside the frozen namespace that plan 02 governs.

**Proposed fix:** Pick one convention (presumably `project.services.<domain>` per plan 02)
and rewrite the API snippets in plans 10–17 (and plan 10's mixed snippet) to match.

---

## A2 — `FillSide` interface mismatch: plan 11 requires a four-value fill side "owned by plan 13", but plan 13 defines and persists only `buy`/`sell`

**Severity:** major

**Files/sections:**
- `11-journal-accounting-….md` §4.3 "Public immutable values" (lines 269–273):
  "`FillSide` is a forward protocol whose exact order-side enum is owned by plan 13. The
  accounting adapter maps only validated `buy`, `sell`, `sell_short`, and `buy_to_cover`
  facts; it does not accept an arbitrary string or infer whether a sale opens a short."
  Also §22 edge case: "Sell more than long position | Reject or split exact close/open-short
  facts supplied by plan 13".
- `13-event-clock-….md` §4.2 (lines 124–125): "`OrderSide`: `buy`, `sell`" — the only
  side enum plan 13 defines; and §15 `simulation_data.fills` (line 621):
  `side VARCHAR NOT NULL CHECK (side IN ('buy', 'sell'))`.
- `12-vectorized-simulator.md` §9 (lines 431–435) and `simulation_data.synthetic_fills`
  (line 718): `side VARCHAR` with no vocabulary, while claiming "Plan-11 lot/borrow
  semantics are never inferred from one ambiguous side."

**Description:** Plan 11 explicitly delegates the fill-side enum to plan 13 and requires
the four values `buy`/`sell`/`sell_short`/`buy_to_cover`, forbidding the accounting layer
from inferring whether a sale opens a short. Plan 13's owned enum (`OrderSide`) and its
persisted fill rows carry only `buy`/`sell`; plan 13 never defines a fill-side type with
`sell_short`/`buy_to_cover`, and its cross-zero handling ("split by the engine into close
and open accounting legs") describes leg ordering, not side vocabulary. Plan 12's synthetic
fill schema likewise leaves `side` unconstrained. As specified, plan 13/12 cannot supply
the validated facts plan 11's adapter requires, and plan 11 is forbidden from deriving
them — the two components cannot interoperate without one side guessing.

**Proposed fix:** Define a four-value `FillSide` enum (`buy`, `sell`, `sell_short`,
`buy_to_cover`) in plan 13 (and reference it from plan 12's synthetic-fill schema), or
change plan 11 to accept `(OrderSide, leg-direction)` pairs and delete the four-value list.

---

## A3 — Public dataframe dtype contract: plan 10 mandates `datetime64[ns, UTC]` and nullable `Float64`; all other plans mandate `datetime64[us, UTC]` and finite `float64`

**Severity:** major

**Files/sections:**
- `01-domain-identity-….md` §6.1 (lines 259–264): "Public pandas dataframes use
  `datetime64[us, UTC]` where pandas and the installed backend support it"; §5.2:
  IDs expose "the typed wire form as pandas `string` dtype".
- `05-…md` §16 (line 1194), `07-…md` §16.2 (line 1179), `08-…md` §15.3 (line 1670),
  `09-…md` §21.3 (line 2051): all specify `datetime64[us, UTC]` and "finite `float64`".
- `10-signals-forecasts-….md` §19.1 (lines 2544–2550): "UUIDs use the project-wide
  canonical UUID dtype, UTC timestamps use `datetime64[ns, UTC]` where lossless … and
  numeric values use nullable `Float64` unless a domain type requires decimal/string
  representation."

**Description:** Plans 01, 05, 07, 08, and 09 uniformly fix the public frame contract at
microsecond-resolution UTC timestamps (`datetime64[us, UTC]`) and finite non-nullable
`float64` analytical values. Plan 10 alone specifies nanosecond timestamps
(`datetime64[ns, UTC]`) and pandas nullable `Float64` for the same kind of public frames
(signal/forecast/risk/target frames). This is not just naming: plan 01 fixes microsecond
precision as the project instant contract and its 0001–9999 year range cannot round-trip
through a nanosecond dtype (ns is limited to ~1677–2262), and downstream consumers (plans
15–18 frames) assume the plan-01 contract. Plan 10 also refers to an undefined
"project-wide canonical UUID dtype" where plan 01 defines the canonical representation as
typed-wire pandas `string`.

**Proposed fix:** Change plan 10 §19.1 to `datetime64[us, UTC]`, finite `float64` (or
explicitly justify the deviation in plan 01), and replace "canonical UUID dtype" with
plan 01's typed-wire `string` wording.

---

## A4 — Plan-01 event-type namespace registry omits the namespaces used by plans 08, 09, 10, and 12

**Severity:** minor

**Files/sections:**
- `01-domain-identity-….md` §8.2 "`EventType`" (lines 577–600): "Required initial
  namespaces are:" followed by 23 namespaces (`persistra.catalog.*` … `persistra.analysis.*`),
  including `persistra.research.*`, `persistra.portfolio.*`, `persistra.order.*`,
  `persistra.execution.*`, `persistra.accounting.*`, `persistra.experiment.*`.
- `08-…md` §19.1 (lines 2111–2117): `persistra.feature.*`, `persistra.label.*`,
  `persistra.component.*` events.
- `09-…md` §22.1 (lines 2124–2131): `persistra.alpha.*`, `persistra.validation.*` events.
- `10-…md` §21.1 (lines 2646–2661): `persistra.signal.*`, `persistra.forecast.*`,
  `persistra.risk_model.*`, `persistra.expected_cost.*`, `persistra.constraint_set.*`,
  `persistra.portfolio_constructor.*` events (only `persistra.portfolio.constructed@1`
  falls inside a listed namespace).
- `12-…md` §14 (lines 804–811): `persistra.simulation.*` events.

**Description:** Plans 02–07 define their events strictly inside plan 01's listed
namespaces, but plans 08–12 introduce fourteen event namespaces absent from the plan-01
registry (while plan 01's listed `persistra.order.*`/`persistra.execution.*` end up used by
no plan). Since plan 01 owns event-type registration and "names beginning with
`persistra.` are reserved for built-ins", an implementer seeding the registry from plan 01
would not cover the later plans' event types. Resolvable (the list is labeled "required
initial"), but the registry and the actual built-in event set have drifted apart.

**Proposed fix:** Extend the plan-01 §8.2 namespace list with the namespaces used in
plans 08, 09, 10, and 12 (or rename those events into the already-listed
`persistra.research.*`/`persistra.analysis.*`/`persistra.portfolio.*`/`persistra.simulation`-
equivalent namespaces) and drop or reassign the unused entries.

---

## A5 — Umbrella order-lifecycle diagram shows a `partially filled` status that both the umbrella's own text and plan 13 forbid

**Severity:** minor

**Files/sections:**
- `v3-spec.md` §21.3 "Lifecycle" (lines 1413–1425): diagram contains
  `active ─→ … └─→ partially filled ─→ filled / cancelled / expired / replaced`.
- `v3-spec.md` §21.3 (lines 1436–1441): "Status and execution progress are distinct. An
  order has one current or terminal status plus cumulative filled and remaining quantity …
  without inventing compound statuses."
- `13-event-clock-….md` §4.2 (lines 127–129): `OrderStatus`: `created`, `submitted`,
  `accepted`, `active`, `filled`, `cancelled`, `expired`, `replaced`, `rejected` — no
  partially-filled value; §7.1: "Partial fill never changes status away from `active`."

**Description:** The umbrella's transition diagram presents `partially filled` as an order
state, which directly contradicts the normative sentence three paragraphs below it (status
and fill progress are orthogonal; no compound statuses) and plan 13's closed `OrderStatus`
enum. An implementer reading only the diagram would add a `partially_filled` status that
plan 13's schema `CHECK` constraint rejects.

**Proposed fix:** Remove the `partially filled` node from the umbrella §21.3 diagram
(showing partial fills as `active` with cumulative progress instead).

---

## A6 — Plan 02: `experiments`/`results`/`analysis`/`annotations` schemas are both "reserved at database creation" and "added by plan 14/15 migrations"

**Severity:** minor

**Files/sections:**
- `02-project-databases-….md` §8.1 table (lines 349–355): "New databases reserve these
  schemas: … Research: `workspace`, `research`, `experiments`, `results`, `analysis`,
  `annotations`" (created by the bootstrap migration, which "creates all initial schemas",
  §8.2).
- `02-…md` §8.1 prose (lines 404–423): "Focused specification 14 **adds** migration-owned
  research-role schemas `experiments` … and `experiment_data`"; "Focused specification 15
  **adds** migration-owned research-role schemas `results` …, `analysis` …, and
  `annotations`" — yet the same section says plan 09 "keeps alpha/validation metadata …
  in the **existing** `analysis` schema."
- `15-results-….md` §5 (lines 155–157): "The research database owns migration-managed
  `results`, `result_data`, `analysis`, `analysis_data`, and `annotations`."

**Description:** Within one section, plan 02 states both that `experiments`, `results`,
`analysis`, and `annotations` exist from bootstrap (reserved-schema table; plan 09 calls
`analysis` "existing") and that plans 14/15 "add" those same schemas via later migrations
(a phrasing plan 15 repeats). An implementer cannot tell whether bootstrap migration 1
creates these schemas or whether the plan-14/15 migration streams do; creating them twice
or in the wrong stream are different behaviors.

**Proposed fix:** In plan 02 §8.1, distinguish schemas created at bootstrap from schemas
added by later migrations (e.g., keep `experiments`/`results`/`analysis`/`annotations` in
the bootstrap table and reword plans 14/15 as "adds tables to the reserved … schema and
adds new schema `experiment_data`/`result_data`/`analysis_data`").

---

## A7 — Plan 02 CLI flag drift: `persistra db create --role research` vs `persistra db create --database research`

**Severity:** minor

**Files/sections:**
- `02-project-databases-….md` §7 "Initialization and workspace layout" (lines 336–339):
  "ordinary `Project.open()` then raises `DatabaseNotFoundError` until
  `persistra db create --role research` succeeds."
- `02-…md` §15.2 "CLI surface" (lines 921–923): `persistra db create --database research`
  and `persistra db create --database market:NAME`.

**Description:** The same command is specified with two different flag spellings inside
one document. The §15.2 surface is the contract-tested one, so `--role` in §7 is stale.

**Proposed fix:** Change §7 to `persistra db create --database research`.

---

## A8 — `data doctor` (plan 03) vs `persistra doctor` (plan 02 / umbrella): unregistered command name

**Severity:** nit

**Files/sections:**
- `03-catalog-ingestion-….md` §9.2 (line 599): "Process death may leave `staging`;
  `data doctor` reports it"; §22 edge table (line 1095) says "doctor reports it".
- `02-…md` §15.2 (line 929) and `v3-spec.md` §28 (line 1918): the command is
  `persistra doctor`; plan 03's own CLI section (§25.7, lines 1225–1226) registers only
  `persistra data validate`, `persistra data quarantine`, `persistra data snapshot`.

**Description:** Plan 03 names a `data doctor` command that no CLI surface (including its
own) defines; the diagnostic command everywhere else is `persistra doctor`.

**Proposed fix:** Replace "`data doctor`" in plan 03 §9.2 with "`persistra doctor`" (or add
`persistra data doctor` to a CLI surface if a separate command is intended).

---

## A9 — Plan 05 dangling internal cross-reference to "section 7.5"

**Severity:** nit

**Files/sections:**
- `05-market-bars-….md` §9.2 (lines 570–573): "The Plan-12/13 daily-bar open capability
  remains field-restricted as specified in **section 7.5**; neither simulator changes
  canonical revision availability."
- `05-…md` §7 has only subsections 7.1 "Versioned `BarSpec`", 7.2 "Canonical bars", and
  7.3 "Interval and session rules"; the execution-outcome projection is specified in the
  closing paragraphs of §7.3 (lines 418–432). Plan 23.1 (line 1464) also references the
  projection without a numbered anchor.

**Description:** There is no section 7.5 (or 7.4) in the file; the referenced contract
lives in §7.3. Cosmetic, but a broken normative cross-reference.

**Proposed fix:** Change "section 7.5" to "section 7.3" (or number the projection as its
own subsection).

---

## A10 — Fold-ordinal column type drift: `INTEGER` (plans 09, 10) vs `BIGINT` (plan 14)

**Severity:** nit

**Files/sections:**
- `09-alpha-diagnostics-….md` §20.4 `analysis.validation_folds.fold_ordinal INTEGER`
  (line 1596) and §20.1 `alpha_analysis_results.validation_fold_ordinal INTEGER`
  (line 1019).
- `10-…md` §17.2 `portfolio.forecast_fits.validation_fold_ordinal INTEGER` (line 1614)
  and `risk_model_fits.validation_fold_ordinal INTEGER`.
- `14-…md` §14 `experiments.experiment_folds.fold_ordinal BIGINT` /
  `validation_fold_ordinal BIGINT` (lines 530–532).

**Description:** The same logical field — a plan-09 fold ordinal — is declared `INTEGER`
in plans 09 and 10 but `BIGINT` in plan 14's binding table (which stores the exact tuple
`(ValidationPlanId, fold_ordinal, …)` from plan 09). Cosmetic width mismatch for one
shared identity component.

**Proposed fix:** Use one type (`INTEGER`, matching the owning plan-09 schema) for
fold/validation-fold ordinals in plan 14.

---

## Findings summary

| ID | Severity | File(s) | Summary |
| --- | --- | --- | --- |
| A1 | major | 02 vs 10–17 (03–09 for contrast) | Service surface split between `project.services.*` and `project.<domain>.*`; plan 10 mixes both |
| A2 | major | 11 vs 12, 13 | Plan 11 requires four-value `FillSide` owned by plan 13; plans 12/13 define/persist only `buy`/`sell` |
| A3 | major | 10 vs 01, 05, 07, 08, 09 | Plan-10 frames use `datetime64[ns, UTC]`/nullable `Float64` against the project-wide `datetime64[us, UTC]`/finite `float64` contract |
| A4 | minor | 01 vs 08, 09, 10, 12 | Plan-01 event-namespace registry omits ~14 namespaces used by later plans' events |
| A5 | minor | v3-spec vs 13 | Umbrella lifecycle diagram shows `partially filled` status forbidden by its own text and plan-13 `OrderStatus` |
| A6 | minor | 02 (internal), 15 | `experiments`/`results`/`analysis`/`annotations` both bootstrap-reserved and "added" by plan 14/15 migrations |
| A7 | minor | 02 (internal) | `db create --role research` (§7) vs `db create --database research` (§15.2) |
| A8 | nit | 03 vs 02, v3-spec | `data doctor` command name vs `persistra doctor`; not in any registered CLI surface |
| A9 | nit | 05 (internal) | Reference to nonexistent "section 7.5"; content is in §7.3 |
| A10 | nit | 09, 10 vs 14 | Fold ordinal `INTEGER` vs `BIGINT` across schemas binding the same value |

No other cross-cutting inconsistencies met the verification bar. Items deliberately not
reported after re-reading both sides: plan 03's richer batch state machine vs the umbrella
diagram (plan 03 declares itself a refinement "without changing outcomes"), package-tree
naming differences vs umbrella §11 (explicitly disclaimed as "a boundary map, not a
promise"), plan 12's `vectorized/fidelity.py` vs the shared `persistra.simulation.fidelity`
module (reconcilable as the vectorized detail payload), and
`OptimizationReplayStatus.wall_time_limited` vs plan-12 `ReplayStatus.ineligible`
(different enums for domains of different breadth).
