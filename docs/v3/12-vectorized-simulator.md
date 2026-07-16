# Focused specification 12: Vectorized simulator

**Status:** implementation plan
**Target:** Persistra 3.0
**Primary package:** `persistra.simulation.vectorized`

## 1. Purpose and relationship to the umbrella specification

This plan makes the umbrella's fast target-based simulator implementable. It defines exact
decision/execution timing, target acquisition, rebalance decisions, target-weight-to-
quantity conversion, aggregated synthetic fills, realized costs, Plan-11 accounting,
corporate actions, settlement, financing, checkpoints, safety, fidelity disclosure, and
normalized run evidence. It is an honest portfolio simulator, not an order-book or market-
replay engine.

Focused specifications 01 through 11 remain normative. This plan reuses their typed IDs,
time/decimal/event rules, project/lease/migration ownership, exact composite snapshots,
instrument/calendars/universes, raw prices/actions/status, rates, research safety/lineage,
features/labels structural separation, validation/causal releases, target construction,
and commodity-balanced accounting. In particular:

- direct labels, retrospective roots, and unreleased fits can never enter a run;
- precomputed targets retain exact input/current-path provenance, while state-dependent
  targets call plan 10's pure one-decision kernel with endogenous Plan-11 state;
- target weights/cash remain intent until this plan's rebalance adapter converts them;
- every economic transition uses Plan 11's pure kernel and journal schemas; and
- expected portfolio cost remains distinct from realized synthetic-fill cost.

Plan 13 owns granular orders, status/fill progress, latency, partial-fill persistence,
intrabar ambiguity, forced orders, and the event simulator. Plan 14 owns study/trial/fold/
scenario orchestration, general design/execution/attempt reuse, parallel workers, and
resume scheduling. Plan 15 owns final result merging, analysis, performance, attribution,
comparison, and export. This plan defines the vectorized occurrence and isolated artifact
they consume without preempting those owners.

## 2. Scope

### 2.1 In scope

- Scheduled vectorized simulation of exact target weights or one-decision construction
- Opening state/capital and exact causal `CurrentPortfolioView` at every decision
- Rebalance schedule, threshold, buffer, minimum trade, quantity rounding, and cash policy
- Default next-eligible-event and explicitly optimistic same-close timing
- Execution-time NAV/price conversion and deterministic implementation shortfall
- Aggregated per-instrument synthetic fills with explicit fees, spread, slippage, impact,
  volume/capacity approximation, borrow, and realized-cost components
- Plan-11 journal, lots, cash, settlement, accrual, corporate-action, valuation, margin,
  borrow, state, and reconciliation processing
- A bounded deterministic vectorized event grid and same-timestamp priorities
- Run/fidelity identity, safety/licensing, normalized evidence, checkpoints, interruption,
  exact retry, resources, schemas, APIs, and acceptance tests
- Restricted vectorized/event equivalence profile for Plan 13

### 2.2 Out of scope

- Explicit orders, order IDs/status transitions, queue position, acknowledgement, cancel/
  replace, IOC/FOK/GTC, order aging, or open-order interaction
- Partial-fill orders carried through later market events; unimplemented quantity is only
  visible shortfall and may be reconsidered at a later rebalance
- Tick/quote replay, order-book reconstruction, auction imbalance, or queue-priority claims
- Stateful strategy callbacks, event-dependent order management, or arbitrary strategy
  code invoked between vectorized grid points
- General study/search orchestration, compatible reuse, distributed execution, or final
  result/analysis schemas
- Live trading, broker reproduction, tax behavior, FX, derivatives, or non-USD books
- Silent target carry-forward, synthetic prices, unlimited staleness, guessed actions,
  implicit unlimited borrow, or accounting shortcuts

## 3. Normative decisions

1. One vectorized occurrence has one exact immutable execution content and one isolated
   run database. It reads pinned market snapshots and never writes attached market files.
2. The simulator operates on desired target risky weights plus cash. It does not reinterpret
   arbitrary signals/forecasts as weights or bypass Plan-10 construction semantics.
3. A state-dependent decision invokes the exact one-decision constructor after deriving a
   reconciled state immediately before that decision. A precomputed target is accepted only
   when its schedule, cutoff, state-path, safety, and execution compatibility verify.
4. Failed construction stops by default. Explicit `skip_decision` retains current economic
   state as a recorded rebalance outcome; it never fabricates a target or edits failure.
5. A target becomes visible no earlier than its effective attempt's logical availability.
   Execution eligibility is the maximum of decision/timing, target availability, and the
   configured submission/activation delay.
6. Default completed-bar timing is next eligible event. Same-close execution after using
   that close is an explicitly optimistic, prominently persisted fidelity assumption.
7. Target weights apply to execution-time pretrade NAV by default. Freezing decision-time
   notional is a distinct policy/identity; no moving convention is implicit.
8. Quantity conversion uses exact execution marks, multiplier one for initial equities/
   ETFs, Plan-01 decimal boundaries, and recorded fractional/whole-share rounding.
9. Rebalance thresholds/buffers/minimum trades act on economic target deviation before
   fills and persist every suppressed/resized asset reason.
10. The vectorized engine has no open orders. Each eligible rebalance produces at most one
    close leg and one opposite-direction open leg per instrument at one execution point;
    ordinary trades have one aggregated synthetic fill. Capacity/cash remainder becomes
    implementation shortfall, not a carried order.
11. Realized commission/regulatory fees are Plan-11 general-book costs. Spread, slippage,
    delay, and impact embedded in synthetic fill price are Plan-11 memorandum attribution
    and are never charged twice.
12. Fill price and capacity use exact point-in-time raw observations selected by registered
    policies. Missing/stale/halted/no-trade/partial/ambiguous data follows typed behavior;
    no price, volume, or halt is invented.
13. Cash feasibility uses settled available cash plus only the exact unsettled credit
    permitted by Plan 11. It reserves direct fees and buy payables before fills and never
    assumes future sale settlement unless the policy explicitly grants credit.
14. Borrow authorization is exact. Short increase without sufficient known authorization
    is clipped or fails as configured; only the explicit synthetic-unlimited model permits
    unlimited borrow and taints fidelity.
15. Every economic effect—fills, settlement, accrual, action, cash flow, margin, and borrow—
    passes through Plan 11. Vectorization may aggregate commands, not bypass the journal.
16. Margin breach produces a recorded intent/finding. This simulator may apply only a
    registered next-grid forced-rebalance approximation; granular forced orders belong to
    Plan 13 and the approximation is a material fidelity difference.
17. Corporate-action capture/effect/payment, settlement, and financing continue on grid
    instants even when no strategy decision occurs.
18. Event visibility and priority are deterministic. Strategy/constructor input never sees
    an observation, action correction, mark, fill, or state not yet visible.
19. Safety, information class, lineage completeness, licensing, custom-code trust, and
    fidelity limitations fold monotonically into the run. An override never relabels input.
20. Completed runs and normalized evidence are append-only. Exact retry verifies the
    isolated artifact; interruption resumes only from a verified matching checkpoint.
21. Every requested decision and grid event has a normalized outcome. Missing hard cases
    cannot disappear through row filtering or partitioning.
22. All work is bounded and deterministic for replay-eligible policies. Wall-time stops,
    opaque external paths, and unseeded custom behavior are visibly replay-ineligible.

## 4. Identity, enums, values, and limits

### 4.1 Typed IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `VectorizedSimulationId` | `vectorized_simulation` | One immutable standalone vectorized occurrence |
| `RunTargetId` | `run_target` | One run-owned per-decision target occurrence |
| `RebalanceDecisionId` | `rebalance_decision` | One comparison of current state and effective target |
| `SyntheticFillId` | `synthetic_fill` | One aggregated instrument fill at one execution point |
| `SimulationCheckpointId` | `simulation_checkpoint` | One verified resumable prefix cache |
| `FidelityProfileId` | `fidelity_profile` | One exact shared machine-readable simulator-fidelity profile |

The ID and common envelope live in `persistra.simulation.fidelity`; Plan 12 owns the
vectorized detail payload and Plan 13 owns the event detail payload. Plan 14 may associate
its general run/design/execution/attempt identities with `VectorizedSimulationId`; it does
not replace or alias this occurrence. Plan 13 defines its own order/fill identities.

### 4.2 Stable enums

| Enum | Initial values |
| --- | --- |
| `VectorizedRunState` | `planned`, `running`, `completed`, `failed`, `interrupted` |
| `TargetSourceKind` | `precomputed`, `endogenous_construction` |
| `ConstructionFailureAction` | `fail_run`, `skip_decision` |
| `ExecutionTimingKind` | `next_session_open`, `next_session_close`, `same_close_optimistic`, `fixed_eligible_instant` |
| `TargetNotionalBasis` | `execution_pretrade_nav`, `decision_nav` |
| `RebalancePolicyKind` | `always`, `threshold`, `buffered`, `calendar_and_threshold` |
| `QuantityPolicyKind` | `fractional`, `whole_share_down`, `whole_share_nearest` |
| `RebalanceState` | `scheduled`, `no_trade`, `partially_implemented`, `implemented`, `failed`, `skipped_failed_target` |
| `TradeIntentState` | `trade`, `below_threshold`, `inside_buffer`, `below_minimum`, `cash_scaled`, `capacity_scaled`, `borrow_scaled`, `price_unavailable`, `held`, `failed` |
| `SyntheticFillState` | `filled`, `not_filled`, `failed` |
| `MissingExecutionAction` | `fail_run`, `skip_asset`, `retain_current` |
| `CapacityAction` | `ignore_with_fidelity_warning`, `clip`, `fail` |
| `ForcedLiquidationApproximation` | `fail_run`, `next_grid_proportional`, `next_grid_policy_order` |
| `ReplayStatus` | `eligible`, `ineligible` |

Enum values are persisted exactly. `skip_asset` and `retain_current` remain asset-level
shortfall reasons; neither changes the target. `ignore_with_fidelity_warning` is never
described as infinite real liquidity.

### 4.3 Public request

```python no-run
@dataclass(frozen=True, slots=True)
class VectorizedSimulationRequest:
    market_context: CompositeAsOfContext
    universe: UniverseEvaluationRef
    schedule: DecisionScheduleRef
    opening: AccountingOpeningRef
    target_source: PrecomputedTargetRef | EndogenousConstructionRef
    rebalance_policy: RebalancePolicyRef
    execution_policy: VectorizedExecutionPolicyRef
    accounting_policy: AccountingPolicyBundleRef
    cash_flows: CashFlowScheduleRef | None
    fidelity: VectorizedFidelitySpec
    unsafe_override: UnsafeRunOverride | None
    seed: SeedSpec
    limits: VectorizedSimulationLimits
```

All friendly references resolve to exact IDs/versions/content before execution content is
frozen. The request contains no dataframe, callable, SQL, physical relation, mutable
estimator, or `latest` reference.

`AccountingPolicyBundleRef` (shared with plan 13) resolves one exact versioned plan-11
policy per accounting dimension: lot-relief method, settlement-cycle schedule,
cash-account or margin policy (with its marginability classification), borrow/financing
rate policy, accrual policy, valuation mark policy, corporate-action election policy, and
rounding/quantization policy. Every member is required; the bundle's resolved content ID
enters execution identity.

`UnsafeRunOverride` is the only mechanism admitting unsafe inputs to a run and is owned
here for every simulator and analysis surface:

```python no-run
@dataclass(frozen=True, slots=True)
class UnsafeAcknowledgement:
    input_content_id: str        # exact unsafe input the caller accepts
    finding_content_ids: tuple[str, ...]  # every acknowledged safety finding
    reason: str                  # caller-supplied justification, recorded verbatim

@dataclass(frozen=True, slots=True)
class UnsafeRunOverride:
    acknowledgements: tuple[UnsafeAcknowledgement, ...]
```

Acknowledgement is per input and per finding; there is no blanket override. Planning
rejects the request when any unsafe input or finding is not exactly acknowledged, when an
acknowledged content ID does not match a resolved input, or when a new unsafe finding
appears between planning and execution. An accepted override sets the run-level unsafe
flag, persists every acknowledgement in the run manifest and execution content, and
propagates the unsafe state into all derived results and analyses. Plan 13 reuses this
type unchanged; plan 15's `UnsafeAnalysisOverride` is the same structure applied to
analysis inputs.

```python no-run
@dataclass(frozen=True, slots=True)
class VectorizedSimulationLimits:
    max_decisions: int = 100_000
    max_grid_events: int = 10_000_000
    max_assets_per_decision: int = 1_000_000
    max_target_rows: int = 100_000_000
    max_synthetic_fills: int = 100_000_000
    max_journal_transactions: int = 10_000_000
    max_checkpoint_rows: int = 5_000_000
    max_frame_rows: int = 2_000_000
    partition_rows: int = 100_000
    timeout: Duration = Duration(7_200_000_000)
```

All values are positive. Effective project memory/temp/time ceilings may be lower. Limits
enter identity and never authorize sampling, event loss, asset truncation, or skipped
accounting/reconciliation.

The remaining request members are exact frozen values:

```python no-run
@dataclass(frozen=True, slots=True)
class DecisionScheduleRef:
    name: QualifiedName
    version: int
    schedule_content_id: ContentId

@dataclass(frozen=True, slots=True)
class PrecomputedTargetRef:
    construction_result_id: PortfolioConstructionResultId
    target_manifest_content_id: ContentId

@dataclass(frozen=True, slots=True)
class EndogenousConstructionRef:
    constructor: PortfolioConstructorRef
    inputs: DecisionInputBundleRef
    constraints: ConstraintSetRef
    expected_cost: ExpectedCostMaterializationRef | None
    fallback: FallbackSpec

@dataclass(frozen=True, slots=True)
class RebalancePolicyRef:
    name: QualifiedName
    version: int
    threshold: Rate | None
    threshold_boundary: Literal["inclusive", "exclusive"]
    buffer: Rate | None
    minimum_notional: Money | None
    minimum_quantity: Quantity | None
    quantity_rounding: Literal["down", "nearest"]
    nearest_tie: Literal["half_even", "half_up"]
    notional_basis: Literal["execution_pretrade_nav", "decision_nav"]
    insufficient_cash: Literal["pro_rata", "fail"]
    target_failure: ConstructionFailureAction
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class VectorizedExecutionPolicyRef:
    name: QualifiedName
    version: int
    timing: Literal["next_session_open", "next_session_close", "same_close_optimistic", "fixed_eligible_instant"]
    reference_field: Literal["open", "close", "trade", "quote_mid"]
    spread: QualifiedName
    slippage: QualifiedName
    delay: QualifiedName
    impact: QualifiedName
    fees: QualifiedName
    capacity: Literal["ignore_with_fidelity_warning", "clip", "fail"]
    participation_limit: Rate | None
    volume_source: Literal["lagged_volume", "adv", "current_session_retrospective"]
    missing_observation: Literal["defer", "skip", "fail"]
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class SimulationPolicyRef:
    name: QualifiedName
    version: int
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class VectorizedFidelitySpec:
    timing_assumption: SimulationPolicyRef
    capacity_assumption: SimulationPolicyRef
    level: Literal["vectorized"] = "vectorized"
    bar_resolution: Literal["session"] = "session"
    models_orders: bool = False
    models_queue: bool = False
    models_intrabar_path: bool = False
```

The installed defaults are `persistra.rebalance.threshold_buffer@1` and
`persistra.vectorized_execution.next_session_open@1`, whose fields match the section-7/8/9
defaults. Threshold/buffer/participation lie in `[0, 1]`, minimums are positive, a buffer
cannot exceed its threshold, fixed timing requires a schedule-supplied instant, current-
session volume is legal only at close and records the retrospective finding, and unused
variant fields are rejected. Target alternatives are exclusive. Registrations resolve every
named cost component to Plan-13's installed model catalog and store canonical content;
unknown versions/kinds or field violations raise `VectorizedSimulationRequestError` before
the run database is created.

## 5. Package, database, and lifecycle ownership

The implementation boundary is:

```text
src/persistra/simulation/vectorized/
├── __init__.py
├── requests.py
├── timing.py
├── grid.py
├── targets.py
├── rebalance.py
├── quantities.py
├── costs.py
├── fills.py
├── engine.py
├── checkpoints.py
├── fidelity.py
└── repositories.py
```

Planning/standalone execution requires `ProjectMode.RESEARCH_WRITE`, shared leases on every
exact market database, and exclusive ownership of one isolated disposable run database.
The project research database is not held writable during the simulation loop. The run
database uses Plan-11 `accounting`/`journal_data` plus migration-owned `simulation` for run,
grid, target, rebalance, fill, checkpoint, fidelity, finding, and manifest metadata and
`simulation_data` for controlled target/fill/state series.

Successful completion verifies schema, normalized rows, journal, state, counts, roots,
events, and final manifest, then marks the isolated occurrence completed atomically. Plan
15 owns transactional merge/export into final research results; Plan 14 owns worker
coordination. Until merged, the managed artifact path/manifest is returned through a typed
handle, not exposed as a raw DuckDB connection.

A normal modeled failure (failed target under fail policy, missing required execution,
blocked action, unrecovered margin, or resource outcome at a safe boundary) publishes a
bounded terminal failure manifest in the isolated artifact with exact last verified prefix,
reasons, findings, and event evidence. It publishes no completed output/artifact root and
remains available to Plan 14 failure accounting.

An infrastructure/invariant failure rolls back the current grid transaction and marks the
attempt failed only at a safe outer boundary. An interruption may leave a verified prior
checkpoint and `interrupted` metadata. No completed handle points at partial outputs.

## 6. Input eligibility and target acquisition

The simulator freezes exact composite/member snapshots, calendar schedules, universe
evaluation, decision keys/cutoffs, input materializations, target definitions/results,
Plan-11 policies, code/environment, safety/licensing, limits, and seed before running.
Structural direct-label/retrospective/unreleased-fit ancestry rejects regardless of unsafe
override. Unsafe causal or opaque inputs require the exact run override and remain unsafe.

For a precomputed target source, every decision key/asset manifest/outcome availability,
constructor/constraint/cost root, current-state path requirement, and failed decision
matches the run. A state-dependent result using another run's historical path remains an
external scenario; it is never rebound as endogenous.

For endogenous construction, each decision:

1. processes every earlier grid event;
2. creates a reconciled Plan-11 state over the construction asset manifest;
3. exposes only decision-safe input occurrences;
4. calls Plan 10's pure one-decision kernel;
5. persists complete attempts/constraints/target rows as `RunTargetId` in the same isolated
   grid transaction; and
6. schedules rebalance no earlier than the target's logical availability.

No second research writer or standalone Plan-10 result is created. Target failure follows
the frozen `ConstructionFailureAction`; `skip_decision` records current-state retention and
complete failure evidence.

## 7. Time, grid, visibility, and priority

### 7.1 Vectorized grid

The grid is the ordered union of opening/cash flows, selected action capture/effect/payment,
settlement boundaries/transitions, accrual boundaries, borrow/rate/recall changes, valuation
marks, decisions, target availability, execution eligibility, margin checks/forced actions,
and checkpoints. It is bounded before execution where possible and extended only by exact
new lifecycle effects already permitted by identity.

Every item has UTC instant, venue-local session when applicable, priority, and validated
stable source sequence. Duplicate semantic keys conflict; UUIDs and insertion/hash order
never define or break business ties.

### 7.2 Same-timestamp priority

The vectorized specialization maps onto Plan 13's total priority. Its ordered buckets are:

1. priority 10: session/calendar/status boundary;
2. priority 20: corporate-action capture/effect/payment and delisting state;
3. priority 30: settlement becoming effective;
4. priority 40: external cash flows and financing/interest/borrow accrual;
5. priority 50: exact execution observation becomes simulator-eligible;
6. priority 80: previously scheduled synthetic fills and Plan-11 accounting;
7. priority 100: valuation, reconciliation, margin, and state publication;
8. priority 110: scheduled decision and endogenous target construction, using only the
   committed visible prefix;
9. priority 120: target logical availability and rebalance scheduling; only the explicitly
   optimistic Plan-12 same-close policy may execute its newly scheduled synthetic fill in
   a later sub-ordinal of this bucket, followed by its valuation/state sub-ordinal; and
10. priority 130: checkpoint/result sampling.

Stable sub-ordinals are versioned wherever multiple vectorized operations share a Plan-13
priority. An item declared contractually after a boundary uses the next legal priority or
instant rather than moving backward. Plan 12's same-close exception remains a prominently
optimistic synthetic research assumption and is excluded from restricted equivalence;
ordinary Plan-13 callback orders can never use it. The restricted profile maps every
shared item explicitly.

### 7.3 Execution timing

`next_session_open` is the default after a completed daily/session bar decision. The exact
next eligible session comes from the pinned Plan-04 calendar and execution instrument
status; its open price may execute the synthetic fill without becoming strategy-visible
before that open. `next_session_close` and fixed instants are explicit alternatives.

Daily-bar open execution uses a typed execution-outcome projection: the exact later-
completed pinned raw bar supplies only its open field as the simulated outcome effective at
session open. The full bar remains publicly unavailable to strategy/constructor code until
its Plan-05 availability, and high/low/close/volume cannot leak through this capability.
The source revision must already belong to the frozen snapshot and satisfy the fixed
project cutoff when enabled. This execution-only reveal is persisted in fidelity/lineage;
it is not a general as-of market-data query or evidence that the provider published early.
The resulting synthetic fill's simulation logical availability is session open, when the
modeled outcome occurs; the canonical bar revision retains its later source availability
in lineage and cannot enter strategy-visible data at open.

Execution-time pretrade NAV uses Plan 11's `bar_open_execution_outcome` mark kind for the
same field-restricted projection across the exact holdings/construction asset manifest.
The valuation stores both canonical source availability and simulation reveal time. At and
after the ordered open event, the open mark may enter reconciled state; no other later bar
field does.

`same_close_optimistic` permits a target using a completed close to fill at that same close.
It records zero/optimistic latency, a prominent lookahead-like material fidelity limitation,
and a distinct identity. It does not relabel the source bar as having been publicly
available before close or change the separate data-safety axis.

Missing sessions, known halts, status-unavailable state, and target availability after the
configured event follow explicit defer/skip/fail behavior. A generic “delay N bars” is not
the primary contract.

## 8. Rebalance and quantity conversion

### 8.1 Rebalance kernel

At execution eligibility the engine obtains a fresh pretrade Plan-11 state and compares it
with the immutable target. Decision-time and execution-time state IDs are both retained.
The default notional basis is positive complete execution-time pretrade NAV:

```text
desired_notional_i = target_weight_i * execution_pretrade_NAV
desired_quantity_i = desired_notional_i / (execution_price_i * multiplier_i)
delta_i = rounded_desired_quantity_i - current_quantity_i
```

Initial multiplier is one. A nonpositive/incomplete NAV or missing required price makes
conversion unavailable. `decision_nav` freezes target notional at decision state and is a
separate visibly stale-drift policy.

Threshold compares absolute weight/notional deviation with registered inclusive/exclusive
boundary. A buffer trades to the named inner boundary rather than necessarily to target.
Minimum notional/quantity applies after rounding. Whole-share `down` rounds absolute trade
toward zero; `nearest` declares tie mode. Fractional mode still quantizes to Plan-01/
instrument precision. Residual cash and target deviation are explicit.

Held-ineligible `liquidate` targets seek zero; `retained_ineligible` and fallback-retained
weights remain explicit target values. Unknown current assets fail. Known-absent assets are
zero current quantity only through Plan-11 coverage evidence.

### 8.2 Batch feasibility

The proposed batch is solved deterministically before any fill:

- apply price/quantity/borrow/volume domains and required clipping;
- compute embedded/direct cost components and conservative cash reservations;
- credit only settled/unsettled proceeds permitted by the exact cash/margin policy;
- satisfy margin/borrow checks through the Plan-11 pretrade capability;
- if cash is insufficient, scale eligible buy/increase trades pro rata with largest
  remainder under exact quantity quanta, then re-evaluate costs/constraints; and
- repeat only for a bounded registered iteration count, otherwise fail.

Risk-reducing sells/covers and risk-increasing shorts/buys use a declared stable phase and
instrument order for journal application. Batch preflight proves every intermediate cash/
inventory policy remains valid. It does not assume an illegal temporary overdraft.

Turnover budget may proportionally scale or prioritize trades only under its registered
policy. Any scaling changes implementation, not target. Every original/rounded/scaled/
filled quantity and reason is stored.

## 9. Synthetic execution and realized costs

An execution policy selects exact raw bar/trade/quote observation and defines reference
price, spread, slippage, delay, impact, fee, volume, participation, missing/stale/status,
and randomization behavior. Bar close/open execution uses that field of the exact raw
completed bar; adjusted prices are forbidden.

Synthetic fill price is computed once in precision 80 and converted to positive Plan-01
`Price` under explicit quantum/rounding:

```text
fill_price = reference_price
           + signed_half_spread
           + signed_slippage
           + signed_delay_component
           + signed_impact
```

Each component retains model/input/availability/unit/root and favorable/adverse sign.
Direct commission/regulatory fees remain separate `Money`. Impact/capacity parameters are
scenario assumptions, not truth.

Volume participation may clip absolute quantity to a declared fraction of exact eligible
volume. At next-open execution, the default capacity source is causally available lagged
volume/ADV; the later-completed bar's full-session volume cannot constrain its own open.
Using current full-session volume is a separately named retrospective capacity assumption
with a prominent fidelity finding and no strategy visibility. At close, exact completed
session volume may be selected, still without a queue-access claim.
`ignore_with_fidelity_warning` records that no capacity limit was modeled; `clip` produces
visible remainder; `fail` stops. A zero observed volume is distinct from missing.

Each accepted execution leg becomes `SyntheticFillId` and Plan-11 `FillAccountingFacts`,
carrying the plan-13 four-value `FillSide` (`buy`, `sell`, `sell_short`, `buy_to_cover`).
Crossing from long to short or short to long creates deterministic close ordinal 1 and
opposite-direction open ordinal 2 so Plan-11 lot/borrow semantics are never inferred from
one ambiguous side. There is no order ID/status. A clipped/no-fill remainder expires at
that execution point and appears in implementation shortfall. Later rebalances start from
actual state, not hidden remainder.

## 10. Accounting, actions, financing, borrow, and margin

Opening, fills, settlement, cash flows, accruals, actions, borrow, valuation, margin, and
state use the exact Plan-11 kernel. The simulator persists returned normalized records in
its owning grid transaction and verifies journal/source idempotency before advancing.

Daily financing/borrow accrual occurs at configured exact boundaries even without a
rebalance. Corporate actions use exact selected revisions/legs and can create fractions,
receivables, obligations, successor lots, or blocked state. Missing/unresolved required
terms stop by default. Delisting never invents zero or proceeds.

Short increase consumes authorization. Recall/margin breach produces Plan-11 intent. The
default vectorized response is `fail_run`, because a granular forced liquidation requires
Plan 13. An optional next-grid approximation records candidate/selection root, assumed
eligibility/price/cost, delay, any inability to recover, and a material fidelity finding.

Every decision state is reconciled. Periodic valuation-only output may be incomplete under
the result policy, but a decision requiring weights cannot proceed from incomplete or
nonpositive NAV.

## 11. Fidelity profile and equivalence boundary

The immutable profile records every umbrella field. Order submission/activation, order
types/TIF, cancellation, queue, and bar-path ambiguity are `not_modeled_vectorized`, never
blank. It additionally records target notional basis, rebalance/rounding, batch sequencing,
synthetic fill aggregation, no-order remainder, capacity action, forced-liquidation
approximation, valuation sampling, and accounting aggregation.

Material limitations include at least:

- one execution point and at most one close plus one opposite-direction open fill per
  instrument/rebalance;
- no open-order or intrabar lifecycle;
- bar volume is capacity proxy, not queue evidence;
- synthetic spread/slippage/impact are scenario models;
- same-close timing when selected;
- synthetic-unlimited borrow when selected; and
- next-grid forced-liquidation approximation when selected.

Restricted vectorized/event equivalence requires: identical opening book/targets/grid;
fractional quantities; market execution at one deterministic observation; zero latency;
infinite modeled liquidity with no partials; identical observed price/direct fees; no
spread/slippage/impact unless identical constants; sufficient borrow/margin/cash; identical
settlement/actions/accruals; and no cancel/replace/forced order. Economic cash/positions/
NAV/cost/P&L at mapped checkpoints must agree exactly after allowed aggregation. Journal
IDs/row grouping need not be byte-identical.

## 12. Execution identity, checkpoints, retry, and completeness

Execution content includes resolved request, targets/construction recipe, snapshots,
universe/schedules/cutoffs, opening, policies, fidelity, all code/environment/dependency,
safety/licensing, seed, limits, output schemas, and event-grid definition. It excludes the
allocated occurrence ID and derived output roots.

A checkpoint binds exact occurrence/execution content, inclusive grid ordinal, prior
checkpoint, journal prefix, accounting snapshot, engine/rebalance state, scheduled future
items, RNG state, row/count roots, and checkpoint schema/content. It is a cache. Resume
verifies every field and replays from an earlier checkpoint/zero on mismatch; it never
mixes request or code identities.

An exact standalone request replay against an already completed occurrence verifies all
metadata, grid items, run targets, rebalances, fills,
costs, journal/accounting state, findings/events, counts, manifests, and artifact checksum.
Under Plan 14 this is an exact-reuse verification and edge, not a new attempt. An interrupted
same-attempt resume may continue only the same occurrence/isolated file under a verified
checkpoint and exclusive owner; a failed retry creates a new Plan-14 attempt, occurrence,
and isolated file.

Every scheduled decision has exactly one target/failure row and rebalance outcome. Every
trade-intent row maps to zero/one fill with reason. Every fill maps to one exact Plan-11
source application. Every sampled state maps to a reconciled prefix/valuation. Completed
counts and roots must close before publication.

## 13. Metadata and physical schemas

Both simulators populate the following shared, migration-owned publication relations in
their isolated run database. `simulation_run_id` is the owning
`VectorizedSimulationId`/`EventSimulationId`; Plan 15 replaces only that column with the
allocated `run_record_id`. Rows are written at the same committed sampling boundary as the
authoritative Plan-11 state, and completion verifies them against the cited state/journal/
fill/event roots.

```sql
CREATE TABLE simulation_data.published_equity (
    simulation_run_id UUID NOT NULL,
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
    PRIMARY KEY (simulation_run_id, sample_ordinal),
    UNIQUE (simulation_run_id, valued_at, journal_prefix_sequence),
    CHECK ((state = 'complete') = (nav_usd IS NOT NULL))
);

CREATE TABLE simulation_data.published_returns (
    simulation_run_id UUID NOT NULL,
    return_ordinal BIGINT NOT NULL CHECK (return_ordinal >= 1),
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    opening_nav_usd DECIMAL(38, 12),
    closing_nav_usd DECIMAL(38, 12),
    external_flow_usd DECIMAL(38, 12) NOT NULL,
    return_value DOUBLE,
    state VARCHAR NOT NULL CHECK (state IN ('computed', 'missing_opening', 'missing_closing', 'nonpositive_base', 'invalid_numeric')),
    flow_timing_policy_content_id VARCHAR NOT NULL,
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (simulation_run_id, return_ordinal),
    CHECK (interval_start < interval_end),
    CHECK ((state = 'computed') = (return_value IS NOT NULL))
);

CREATE TABLE simulation_data.published_positions (
    simulation_run_id UUID NOT NULL,
    position_ordinal BIGINT NOT NULL CHECK (position_ordinal >= 1),
    portfolio_state_id UUID NOT NULL,
    valued_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    present BOOLEAN NOT NULL,
    settled_quantity DECIMAL(38, 12) NOT NULL,
    unsettled_quantity DECIMAL(38, 12) NOT NULL,
    mark_price DECIMAL(38, 12) NOT NULL CHECK (mark_price > 0),
    market_value_usd DECIMAL(38, 12) NOT NULL,
    long_exposure_usd DECIMAL(38, 12) NOT NULL CHECK (long_exposure_usd >= 0),
    short_exposure_usd DECIMAL(38, 12) NOT NULL CHECK (short_exposure_usd >= 0),
    gross_exposure_usd DECIMAL(38, 12) NOT NULL CHECK (gross_exposure_usd >= 0),
    net_exposure_usd DECIMAL(38, 12) NOT NULL,
    mark_quality VARCHAR NOT NULL,
    lot_manifest_content_id VARCHAR,
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (simulation_run_id, position_ordinal),
    UNIQUE (simulation_run_id, portfolio_state_id, instrument_id)
);

CREATE TABLE simulation_data.published_cash (
    simulation_run_id UUID NOT NULL,
    cash_ordinal BIGINT NOT NULL CHECK (cash_ordinal >= 1),
    portfolio_state_id UUID NOT NULL,
    valued_at TIMESTAMPTZ NOT NULL,
    economic_cash_usd DECIMAL(38, 12) NOT NULL,
    settled_available_usd DECIMAL(38, 12) NOT NULL,
    settled_restricted_usd DECIMAL(38, 12) NOT NULL,
    receivable_usd DECIMAL(38, 12) NOT NULL,
    payable_usd DECIMAL(38, 12) NOT NULL,
    accrued_receivable_usd DECIMAL(38, 12) NOT NULL,
    accrued_payable_usd DECIMAL(38, 12) NOT NULL,
    source_content_id VARCHAR NOT NULL,
    PRIMARY KEY (simulation_run_id, cash_ordinal),
    UNIQUE (simulation_run_id, portfolio_state_id)
);

CREATE TABLE simulation_data.cost_components (
    simulation_run_id UUID NOT NULL,
    cost_ordinal BIGINT NOT NULL CHECK (cost_ordinal >= 1),
    source_kind VARCHAR NOT NULL CHECK (source_kind IN ('fill', 'synthetic_fill', 'accrual')),
    source_id UUID NOT NULL,
    component_kind VARCHAR NOT NULL CHECK (component_kind IN ('commission', 'regulatory_fee', 'spread', 'slippage', 'delay', 'impact', 'borrow', 'financing')),
    evidence_state VARCHAR NOT NULL CHECK (evidence_state IN ('observed', 'estimated', 'modeled', 'accounted_direct', 'unavailable')),
    amount_usd DECIMAL(38, 12),
    unit VARCHAR NOT NULL,
    component_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (simulation_run_id, cost_ordinal),
    CHECK ((evidence_state <> 'unavailable') = (amount_usd IS NOT NULL))
);

CREATE TABLE simulation_data.published_exposures (
    simulation_run_id UUID NOT NULL,
    exposure_ordinal BIGINT NOT NULL CHECK (exposure_ordinal >= 1),
    valued_at TIMESTAMPTZ NOT NULL,
    component_kind VARCHAR NOT NULL CHECK (component_kind IN ('taxonomy', 'factor', 'benchmark_relative', 'strategy')),
    component_content_id VARCHAR NOT NULL,
    unit VARCHAR NOT NULL,
    value DOUBLE,
    state VARCHAR NOT NULL CHECK (state IN ('computed', 'unavailable')),
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (simulation_run_id, exposure_ordinal),
    CHECK ((state = 'computed') = (value IS NOT NULL))
);

CREATE TABLE simulation_data.published_quality_findings (
    simulation_run_id UUID NOT NULL,
    finding_ordinal BIGINT NOT NULL CHECK (finding_ordinal >= 1),
    finding_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL CHECK (severity IN ('info', 'warning', 'unsafe')),
    subject_content_id VARCHAR NOT NULL,
    occurrence_count BIGINT NOT NULL CHECK (occurrence_count >= 1),
    evidence_content_id VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    PRIMARY KEY (simulation_run_id, finding_ordinal)
);

CREATE TABLE simulation_data.published_fidelity_findings (
    simulation_run_id UUID NOT NULL,
    finding_ordinal BIGINT NOT NULL CHECK (finding_ordinal >= 1),
    fidelity_field VARCHAR NOT NULL,
    assumption_content_id VARCHAR NOT NULL,
    occurrence_count BIGINT NOT NULL CHECK (occurrence_count >= 1),
    evidence_content_id VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    PRIMARY KEY (simulation_run_id, finding_ordinal)
);

CREATE TABLE simulation_data.published_lifecycle_events (
    simulation_run_id UUID NOT NULL,
    event_ordinal BIGINT NOT NULL CHECK (event_ordinal >= 1),
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type VARCHAR NOT NULL,
    event_schema_version INTEGER NOT NULL CHECK (event_schema_version >= 1),
    payload_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (simulation_run_id, event_ordinal)
);
```

```sql
CREATE TABLE simulation.fidelity_profiles (
    fidelity_profile_id UUID PRIMARY KEY,
    simulator_name VARCHAR NOT NULL,
    simulator_version VARCHAR NOT NULL,
    market_data_granularity VARCHAR NOT NULL,
    execution_timing VARCHAR NOT NULL,
    target_notional_basis VARCHAR NOT NULL,
    order_model VARCHAR NOT NULL CHECK (order_model = 'not_modeled_vectorized'),
    partial_fill_model VARCHAR NOT NULL CHECK (
        partial_fill_model = 'not_modeled_vectorized'
    ),
    capacity_action VARCHAR NOT NULL CHECK (
        capacity_action IN ('ignore_with_fidelity_warning', 'clip', 'fail')
    ),
    forced_liquidation_approximation VARCHAR NOT NULL CHECK (
        forced_liquidation_approximation IN (
            'fail_run', 'next_grid_proportional', 'next_grid_policy_order'
        )
    ),
    full_profile_json JSON NOT NULL,
    material_finding_manifest_content_id VARCHAR NOT NULL,
    fidelity_content_id VARCHAR NOT NULL UNIQUE
);

CREATE TABLE simulation.vectorized_runs (
    vectorized_simulation_id UUID PRIMARY KEY,
    run_state VARCHAR NOT NULL CHECK (
        run_state IN ('planned', 'running', 'completed', 'failed', 'interrupted')
    ),
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    opening_content_id VARCHAR NOT NULL,
    target_source_content_id VARCHAR NOT NULL,
    rebalance_policy_content_id VARCHAR NOT NULL,
    execution_policy_content_id VARCHAR NOT NULL,
    accounting_policy_content_id VARCHAR NOT NULL,
    fidelity_profile_id UUID NOT NULL,
    seed_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR,
    failure_manifest_content_id VARCHAR,
    artifact_content_id VARCHAR,
    replay_status VARCHAR NOT NULL CHECK (
        replay_status IN ('eligible', 'ineligible')
    ),
    nondeterminism_reason_code VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    terminal_at TIMESTAMPTZ,
    CHECK (
        (run_state = 'completed'
            AND output_manifest_content_id IS NOT NULL
            AND failure_manifest_content_id IS NULL
            AND artifact_content_id IS NOT NULL
            AND terminal_at IS NOT NULL)
        OR
        (run_state = 'failed'
            AND output_manifest_content_id IS NULL
            AND artifact_content_id IS NULL
            AND failure_manifest_content_id IS NOT NULL
            AND terminal_at IS NOT NULL)
        OR
        (run_state IN ('planned', 'running', 'interrupted')
            AND output_manifest_content_id IS NULL
            AND failure_manifest_content_id IS NULL
            AND artifact_content_id IS NULL
            AND terminal_at IS NULL)
    ),
    CHECK (
        (replay_status = 'eligible' AND nondeterminism_reason_code IS NULL)
        OR
        (replay_status = 'ineligible' AND nondeterminism_reason_code IS NOT NULL)
    )
);

CREATE TABLE simulation.run_transitions (
    vectorized_simulation_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    run_state VARCHAR NOT NULL CHECK (
        run_state IN ('planned', 'running', 'completed', 'failed', 'interrupted')
    ),
    transitioned_at TIMESTAMPTZ NOT NULL,
    reason_code VARCHAR,
    transition_content_id VARCHAR NOT NULL,
    PRIMARY KEY (vectorized_simulation_id, transition_sequence)
);

CREATE TABLE simulation.grid_events (
    vectorized_simulation_id UUID NOT NULL,
    grid_ordinal BIGINT NOT NULL CHECK (grid_ordinal >= 1),
    event_at TIMESTAMPTZ NOT NULL,
    priority INTEGER NOT NULL CHECK (priority >= 1),
    stable_source_sequence BIGINT NOT NULL CHECK (stable_source_sequence >= 0),
    event_kind VARCHAR NOT NULL,
    source_kind VARCHAR NOT NULL,
    source_id UUID,
    logical_available_at TIMESTAMPTZ NOT NULL,
    outcome VARCHAR NOT NULL CHECK (
        outcome IN ('processed', 'skipped', 'failed')
    ),
    reason_code VARCHAR,
    event_content_id VARCHAR NOT NULL,
    PRIMARY KEY (vectorized_simulation_id, grid_ordinal)
);

CREATE TABLE simulation.run_targets (
    run_target_id UUID PRIMARY KEY,
    vectorized_simulation_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    decision_sequence BIGINT NOT NULL CHECK (decision_sequence >= 1),
    source_kind VARCHAR NOT NULL CHECK (
        source_kind IN ('precomputed', 'endogenous_construction')
    ),
    source_target_id UUID,
    decision_portfolio_state_id UUID NOT NULL,
    source_current_state_id UUID,
    outcome_available_at TIMESTAMPTZ NOT NULL,
    construction_status VARCHAR NOT NULL CHECK (
        construction_status IN ('completed', 'completed_with_fallback', 'failed')
    ),
    target_manifest_content_id VARCHAR,
    attempt_manifest_content_id VARCHAR NOT NULL,
    constraint_manifest_content_id VARCHAR NOT NULL,
    run_target_content_id VARCHAR NOT NULL UNIQUE,
    UNIQUE (vectorized_simulation_id, decision_sequence),
    UNIQUE (vectorized_simulation_id, decision_at),
    CHECK (
        (source_kind = 'precomputed' AND source_target_id IS NOT NULL)
        OR
        (source_kind = 'endogenous_construction' AND source_target_id IS NULL)
    ),
    CHECK (
        (construction_status = 'failed' AND target_manifest_content_id IS NULL)
        OR
        (construction_status <> 'failed' AND target_manifest_content_id IS NOT NULL)
    )
);

CREATE TABLE simulation.rebalance_decisions (
    rebalance_decision_id UUID PRIMARY KEY,
    vectorized_simulation_id UUID NOT NULL,
    run_target_id UUID NOT NULL,
    decision_state_id UUID NOT NULL,
    execution_state_id UUID,
    decision_at TIMESTAMPTZ NOT NULL,
    eligible_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    rebalance_state VARCHAR NOT NULL CHECK (
        rebalance_state IN (
            'scheduled', 'no_trade', 'partially_implemented',
            'implemented', 'failed', 'skipped_failed_target'
        )
    ),
    target_notional_basis VARCHAR NOT NULL CHECK (
        target_notional_basis IN ('execution_pretrade_nav', 'decision_nav')
    ),
    original_intent_manifest_content_id VARCHAR NOT NULL,
    effective_intent_manifest_content_id VARCHAR NOT NULL,
    fill_manifest_content_id VARCHAR NOT NULL,
    implementation_shortfall_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    rebalance_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (executed_at IS NULL OR eligible_at IS NOT NULL),
    CHECK (executed_at IS NULL OR executed_at >= eligible_at)
);

CREATE TABLE simulation_data.trade_intents (
    rebalance_decision_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    intent_state VARCHAR NOT NULL CHECK (
        intent_state IN (
            'trade', 'below_threshold', 'inside_buffer', 'below_minimum',
            'cash_scaled', 'capacity_scaled', 'borrow_scaled',
            'price_unavailable', 'held', 'failed'
        )
    ),
    current_quantity DECIMAL(38, 12) NOT NULL,
    target_weight DECIMAL(38, 18),
    original_desired_quantity DECIMAL(38, 12),
    rounded_desired_quantity DECIMAL(38, 12),
    effective_delta_quantity DECIMAL(38, 12),
    filled_quantity DECIMAL(38, 12) NOT NULL DEFAULT 0,
    reference_price DECIMAL(38, 12),
    reason_code VARCHAR,
    intent_content_id VARCHAR NOT NULL,
    PRIMARY KEY (rebalance_decision_id, instrument_id),
    CHECK (filled_quantity >= 0)
);

CREATE TABLE simulation_data.synthetic_fills (
    synthetic_fill_id UUID PRIMARY KEY,
    vectorized_simulation_id UUID NOT NULL,
    rebalance_decision_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    fill_ordinal INTEGER NOT NULL CHECK (fill_ordinal IN (1, 2)),
    fill_state VARCHAR NOT NULL CHECK (
        fill_state IN ('filled', 'not_filled', 'failed')
    ),
    side VARCHAR CHECK (side IN ('buy', 'sell', 'sell_short', 'buy_to_cover')),
    quantity DECIMAL(38, 12),
    reference_price DECIMAL(38, 12),
    fill_price DECIMAL(38, 12),
    commission_amount DECIMAL(38, 12),
    regulatory_fee_amount DECIMAL(38, 12),
    executed_at TIMESTAMPTZ,
    source_observation_content_id VARCHAR,
    cost_component_content_id VARCHAR NOT NULL,
    accounting_source_application_content_id VARCHAR,
    reason_code VARCHAR,
    fill_content_id VARCHAR NOT NULL UNIQUE,
    UNIQUE (rebalance_decision_id, instrument_id, fill_ordinal),
    CHECK (
        (fill_state = 'filled'
            AND side IS NOT NULL
            AND quantity IS NOT NULL AND quantity > 0
            AND reference_price IS NOT NULL AND reference_price > 0
            AND fill_price IS NOT NULL AND fill_price > 0
            AND commission_amount IS NOT NULL AND commission_amount >= 0
            AND regulatory_fee_amount IS NOT NULL AND regulatory_fee_amount >= 0
            AND executed_at IS NOT NULL
            AND source_observation_content_id IS NOT NULL
            AND accounting_source_application_content_id IS NOT NULL)
        OR
        (fill_state <> 'filled'
            AND quantity IS NULL
            AND fill_price IS NULL
            AND executed_at IS NULL
            AND accounting_source_application_content_id IS NULL)
    )
);

CREATE TABLE simulation.simulation_checkpoints (
    simulation_checkpoint_id UUID PRIMARY KEY,
    vectorized_simulation_id UUID NOT NULL,
    checkpoint_sequence BIGINT NOT NULL CHECK (checkpoint_sequence >= 1),
    inclusive_grid_ordinal BIGINT NOT NULL CHECK (inclusive_grid_ordinal >= 0),
    prior_simulation_checkpoint_id UUID,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    accounting_snapshot_id UUID NOT NULL,
    engine_state_content_id VARCHAR NOT NULL,
    future_grid_content_id VARCHAR NOT NULL,
    rng_state_content_id VARCHAR NOT NULL,
    output_prefix_manifest_content_id VARCHAR NOT NULL,
    checkpoint_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (vectorized_simulation_id, checkpoint_sequence),
    UNIQUE (vectorized_simulation_id, inclusive_grid_ordinal)
);
```

Fixed `simulation_data` relations also store per-asset target/rebalance intent, realized
cost components, implementation shortfall, sampled state/equity, exact external-flow-split
return intervals carrying the plan-15 §7.3 return-state vocabulary, and fidelity findings.
Return intervals are simulator outputs derived at committed sampling boundaries from the
exact Plan-11 valuation/cash-flow prefix; Plan 15 maps them losslessly and never computes
hidden return facts during publication.
Their exact Plan-15 final-result mapping is plan 15 sections 7.3 (equity/returns/cost
components) and 7.4 (all remaining relations); generated names/untyped key-value rows are
not permitted. All row schemas/counts/roots are versioned now.

`run_state` lifecycle is normalized through immutable transitions in implementation; the
table above is the terminal occurrence summary published/updated only by the owning
isolated artifact transaction. A merged completed artifact is append-only.
Legal transitions are `planned -> running`, `running -> completed|failed|interrupted`, and
`interrupted -> running` only for verified same-attempt resume. Completed/failed are
terminal; Plan 14 retries as a new attempt/occurrence association rather than reopening.

## 14. Public API, events, failures, and reasons

```python no-run
plan = project.services.simulation.vectorized.plan(request)
run = project.services.simulation.vectorized.run(plan)
run = project.services.simulation.vectorized.resume(interrupted_handle)
run.targets(decisions=..., limit=...)
run.rebalances(decisions=..., limit=...)
run.synthetic_fills(decisions=..., instruments=..., limit=...)
run.accounting.current_state(...)
run.fidelity()
```

Handles expose bounded typed metadata/frames/iterators and progress callbacks. They expose
no raw database connection/path, physical relation, arbitrary SQL, journal writer, mutable
state, order API, or future decision rows.

Domain events include `persistra.simulation.vectorized_planned@1`,
`persistra.simulation.vectorized_started@1`,
`persistra.simulation.target_completed@1`,
`persistra.simulation.rebalance_completed@1`,
`persistra.simulation.synthetic_fill_completed@1`,
`persistra.simulation.checkpoint_completed@1`,
`persistra.simulation.vectorized_completed@1`,
`persistra.simulation.vectorized_failed@1`, and
`persistra.simulation.vectorized_interrupted@1`. Normalized tables remain authority;
events contain bounded IDs/counts/roots/reasons. Exact retry emits no duplicate.
Run lifecycle events use the vectorized occurrence aggregate and its gap-free transition
sequence. Target, rebalance, fill, and checkpoint completion use their own typed aggregate
at sequence one, correlate to the run workflow, and causally link the grid/source event.
One grid transaction captures one injected-clock `recorded_at` for all normalized rows and
event envelopes it commits.

Typed exceptions include `VectorizedSimulationError`, `SimulationInputError`,
`SimulationTimingError`, `TargetCompatibilityError`, `RebalanceError`,
`SyntheticExecutionError`, `SimulationAccountingError`, `CheckpointError`,
`SimulationResourceLimitError`, and `SimulationCorruptionError`.

Stable reasons include:

```text
simulation.input_incompatible
simulation.direct_label_forbidden
simulation.unsafe_override_required
simulation.target_unavailable
simulation.target_failed
simulation.target_available_after_execution
simulation.current_state_unavailable
simulation.nav_nonpositive
simulation.execution_price_missing
simulation.execution_price_stale
simulation.instrument_halted
simulation.execution_volume_missing
simulation.capacity_clipped
simulation.borrow_unavailable
simulation.cash_insufficient
simulation.margin_unavailable
simulation.margin_breach
simulation.forced_liquidation_approximated
simulation.rebalance_no_trade
simulation.minimum_trade_suppressed
simulation.quantity_rounded
simulation.fill_failed
simulation.action_blocked
simulation.accounting_reconciliation_failed
simulation.checkpoint_mismatch
simulation.incomplete_output
simulation.resource_limit
simulation.replay_ineligible
```

## 15. Edge cases, security, and migration

| Case | Required behavior |
| --- | --- |
| Target becomes available after next open | Execute next policy-eligible event; never backdate |
| Failed target | Fail by default or explicit skipped-failed-target outcome |
| Same-close selected | Prominent optimistic timing finding and distinct identity |
| Decision and cash flow tie | Priority contract determines exact predecision state |
| Missing nonheld target price | Wider construction state/conversion unavailable, not zero |
| Missing held price | Incomplete NAV; decision cannot proceed |
| Halt known | Defer/retain/fail by exact policy; never fill |
| Status feed absent | Missing/status-unavailable policy; never infer halt/trading |
| Zero volume | Zero capacity under clipping; distinct from missing volume |
| Cost makes cash insufficient | Deterministic rescale/recheck or fail |
| Whole-share rounding | Residual cash and weight shortfall persist |
| Short borrow partly available | Clip/fail; exact authorization consumed once |
| Settlement crosses decision | Decision state uses only priority-visible transition |
| Dividend/split without rebalance | Process through accounting grid anyway |
| Unresolved action | Block complete state/run under default policy |
| Margin breach | Fail by default or visible next-grid approximation, never hidden order |
| Capacity remainder | Expires as shortfall; no ghost open order |
| Later target | Recompute from actual state, not prior remainder/target |
| Interrupt after journal commit | Grid boundary/checkpoint proves whether event is complete |
| Corrupt checkpoint | Replay earlier/zero; never trust or patch it |
| Exact retry completed | Verify full artifact and return; do not rerun |

Custom timing, rebalance, cost, capacity, and execution policies use bounded plan-08-style
registration/conformance and return typed decisions only. They cannot read labels/future
rows, mutate accounting, emit orders, access connections, or hide fidelity findings.
Untrusted/opaque behavior taints replay/safety and is rejected by default.

All frames/ranges are bounded; sensitive/licensed target, price, borrow, and journal values
are access controlled and never dumped in logs/events. Resource failure rolls back the
current atomic boundary without partial completed state.

This is a greenfield v3 migration. Research/isolated-run migrations add `simulation` and
`simulation_data` plus Plan-11 schemas. V2 backtests are not imported as trusted runs.
Changed timing, target basis, rebalance/rounding, fill/cost/capacity, borrow/margin/action/
accounting, grid priority, safety, code/environment, seed, or schema changes execution
identity. Plan 14 compatibility reuse cannot masquerade as exact.

## 16. Implementation sequence

1. Add IDs/enums/requests, policies, fidelity schema, isolated run database migrations,
   bounded repositories, and exact planning identity.
2. Implement deterministic grid, timing/visibility/priority, target compatibility, safety/
   licensing, and precomputed target adapter.
3. Implement endogenous Plan-10 construction with Plan-11 decision state and atomic run
   target persistence.
4. Implement rebalance thresholds/buffers/minimums, execution-NAV quantity/rounding, cash/
   borrow/margin batch feasibility, and shortfall.
5. Implement raw-observation synthetic prices, realized costs, capacity clipping, fills,
   and Plan-11 accounting application.
6. Integrate cash flows, settlement, accrual, actions, valuation, margin intents, sampling,
   reconciliation, and optional forced approximation.
7. Implement normalized outputs/events/findings, checkpoints/resume, exact retry, fault/
   resource/determinism tests, and Plan-13 equivalence fixtures.
8. Complete docs, strict build, benchmark hooks, and cumulative plans 01–12 review.

## 17. Acceptance tests and exit criteria

### 17.1 Inputs, timing, targets, and safety

- IDs/request/policy/schema/content round-trip; moving names, wrong snapshot/universe/
  schedule/cutoff/asset path, missing rows, duplicate decisions, and incompatible target
  meaning reject.
- Direct label/retrospective/unreleased fit sentinels reject every adapter; unsafe/opaque
  causal inputs require override and remain tainted through run/accounting/result.
- Golden timing covers next open/close, target logical delay, same-close optimistic,
  weekends/holidays/early closes/halts, tied events, DST, and no future visibility; the
  execution-only next-open projection exposes no later bar field to decision code.
- Endogenous construction uses exact immediately-predecision state and persists all Plan-10
  attempts/constraints/failure; precomputed state-dependent paths remain external.

### 17.2 Rebalance, fills, and accounting

- Hand examples cover execution-NAV versus decision-NAV, threshold/buffer boundaries,
  minimum trade, fractional/whole rounding/ties, long/short cross-zero, held-ineligible,
  target cash, and exact shortfall.
- Cash solver covers fees, unsettled credit allowed/forbidden, proportional quantum
  scaling, iteration limit, deterministic phase order, and no intermediate invalid state.
- Borrow/margin fixtures cover missing/zero/partial/unlimited, authorization idempotency,
  pretrade failure, recall, breach, default fail, and visible forced approximation.
- Raw open/close/quote/trade synthetic fill fixtures cover spread/slippage/delay/impact,
  favorable/adverse signs, direct fees, causal lagged/ADV capacity at open, forbidden or
  prominently retrospective same-session volume, zero/missing volume, clipping, stale/
  halt/no-trade, cost roots, and no double charge.
- Every fill reconciles through Plan-11 lots/cash/payables/settlement/P&L/memorandum costs;
  no-fill/remainder has no accounting source application.
- No-decision periods still process deposits/withdrawals, T+ settlement, cash/borrow
  accrual, splits, dividends, fractions, delistings, and blocked actions.

### 17.3 Completeness, recovery, fidelity, and equivalence

- Every decision/asset/grid/fill/state count and manifest closes; partition/insertion/hash
  order does not change replay-eligible roots.
- Checkpoint at every boundary resumes to the same completed roots; request/code/seed/
  checkpoint corruption falls back or rejects without mixing.
- Fault injection at plan/target/rebalance/fill/journal/action/state/checkpoint/event/commit
  boundaries exposes no partial completed occurrence.
- Fidelity contains every umbrella field with explicit `not_modeled_vectorized`, all
  material approximations, safety, seeds, and comparison-relevant roots.
- Restricted Plan-13 configuration matches cash, quantities, NAV, costs, P&L, actions,
  settlement, and accounting at mapped checkpoints; an intentional fidelity difference
  produces a diagnosed difference rather than false equality.
- Every limit and licensing/access boundary fails explicitly without sampling, truncation,
  hidden values, partial journal, or unbounded frame.
- Docs snippets and the `persistra.benchmark.daily_equity_5000x20@1` integration hook pass.
  The hook uses Plan 18's exact monthly top-1,000 targets, next-open fractional execution,
  lagged-ADV capacity, cost, settlement/action/accounting, flow-split return, and lossless
  Plan-15 publication profile; it cannot substitute a smaller/sampled frame or private fast
  path. Strict MkDocs, optional/base import behavior, migrations/copies/reopen,
  `make lint type test`, and docs checks also pass.

### 17.4 End-to-end exit

A documented daily-bar workflow must run monthly long-only and long-short target strategies
from exact opening capital through next-open fractional synthetic execution, explicit
costs, settlement, financing, borrow, split/dividend, valuation, and reconciled final state;
demonstrate threshold/whole-share/capacity shortfall, one failed target, one missing mark,
same-close warning, checkpoint resume, and restricted Plan-13 equivalence fixture; and
produce a complete isolated artifact using only public APIs.

Plan 12 is complete only when all tests pass with the repository gates, docs checks,
strict build, benchmark hook, and cumulative review finds no contradiction with the
umbrella or plans 01–11.

## 18. Review checklist for dependent plans

Plans 13–15 and 18 must preserve:

- target logical availability and immediately-predecision endogenous accounting state;
- target intent versus rebalance/rounded/scaled/filled quantities and complete shortfall;
- default next-eligible-event timing and prominent same-close optimism;
- exact raw execution observations without strategy-visible future leakage;
- realized versus expected costs and Plan-11 general/memorandum separation;
- no order/open-remainder claim for vectorized synthetic fills;
- exact cash, borrow, margin, settlement, action, accrual, valuation, and reconciliation;
- explicit vectorized fidelity omissions/approximations and comparison roots;
- restricted equivalence only under the declared common profile;
- isolated artifact ownership, checkpoint verification, and no cross-file ACID claim;
- structural label prohibition and monotone safety/licensing/lineage propagation; and
- bounded deterministic normalized evidence, atomic completion, exact retry, and immutable
  completed occurrence.

Plan 13 must not retrofit order statuses onto synthetic fills. Plan 14 may schedule/reuse
attempts but cannot change this execution content or checkpoint meaning. Plan 15 may map
normalized outputs and analyze implementation shortfall/fidelity but cannot mutate runs or
report vectorized approximations as observed order behavior.

## 19. Consistency statement

This plan implements the umbrella vectorized simulator while retaining every completed
identity, cutoff, target, accounting, and reliability boundary. It makes the fast path
honest by using the same Plan-11 economics as the event path and by persisting what it does
not model. It gives Plan 10 endogenous state without predicting a state path, gives Plan 11
only validated accounting facts, and leaves granular orders to Plan 13 and general run/
result orchestration to Plans 14–15. No project-level direction is revised.

The cumulative plans 01–12 review records the new isolated-run schemas in plan 02, defines
the field-restricted session-open execution projection in plan 05, adds its simulation-only
valuation kind to plan 11, and links this plan from the umbrella. It also makes failed
occurrences terminally auditable without a false completed artifact root. Canonical bar
availability, strategy cutoffs, accounting reconciliation, and future Plan-13 order
ownership remain unchanged.

The cumulative Plan-13 review moves the common fidelity envelope to
`persistra.simulation.fidelity`, replaces UUID tie-breaking with validated stable source
sequence, and maps this specialized grid onto the Plan-13 total event priority. It retains
Plan 12's same-close mode only as its pre-existing synthetic optimistic exception; no
stateful callback order can backdate into a completed market bucket, and restricted
equivalence excludes that exception.
