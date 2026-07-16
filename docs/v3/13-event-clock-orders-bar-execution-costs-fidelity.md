# Focused specification 13: event clock, orders, bar execution, costs, and fidelity

**Status:** Implementation-ready draft  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Primary package:** `persistra.simulation.event`  
**Required before:** focused specifications 14–18  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines the stateful order simulator promised by sections 19–22 of the
umbrella specification. It fixes the event clock, callback visibility, order state and fill
progress, cancellation and replacement, bar-based execution, capacity, latency, realized
costs, forced orders, fidelity disclosure, persistence, and recovery contracts.

Plans 01–10 supply identities, point-in-time observations, safe strategy inputs, forecasts,
and target construction. Plan 11 is the sole accounting authority. Plan 12 owns aggregated
target simulation and its deliberately order-free synthetic fills. This plan consumes those
contracts without changing canonical market availability or inventing exchange microstructure
that bars cannot reveal.

## 2. Scope

### 2.1 In scope

- A deterministic event clock and total order for simultaneous occurrences
- Strictly point-in-time strategy callbacks and commands
- Market, limit, stop, stop-limit, MOO, and MOC orders
- Day, GTC, IOC, and FOK time in force
- Immutable status transitions distinct from cumulative fill progress
- Cancellation, replacement, rejection, expiration, partial fills, and forced orders
- Bar/quote/trade observation selection and named OHLC ambiguity policies
- Eligibility timestamps, submission/activation/cancellation latency, and seeded randomness
- Capacity, participation, quantity quanta, spread, slippage, delay, impact, and direct fees
- Borrow/margin gates, recalls, and deterministic liquidation order ownership
- Plan-11 fill accounting, settlement, actions, accrual, valuation, and reconciliation
- Isolated run persistence, checkpoints, exact retry, terminal failures, and fidelity profiles
- The restricted equivalence boundary with Plan 12

### 2.2 Out of scope

- Tick reconstruction, exchange matching, queue position, hidden/iceberg liquidity, auctions,
  NBBO routing, venue rebates, maker/taker status, or broker-specific locate workflows
- Limit-on-open, limit-on-close, trailing, peg, bracket, conditional, or multi-leg orders
- Quote/trade replay presented as market replay; 3.0 remains an observation-driven simulator
- Fractional listed-equity orders under the default broker policy
- Portfolio optimization, journal rules, experiment scheduling, final result merge, metrics,
  plots, reports, or dashboard behavior
- Live trading, external messages, wall-clock scheduling, or distributed execution

## 3. Normative decisions

1. Engine state advances through immutable event occurrences ordered by
   `(effective_at, priority, stable_sequence)`. UUIDs, insertion order, hash order, and worker
   timing never break ties.
2. An event can affect engine state at `effective_at` while its payload becomes strategy
   visible only at its declared availability. Callback contexts expose only the closed
   visible prefix.
3. Strategy commands are accepted only from the callback occurrence that created them.
   They cannot be backdated. The engine records callback input and command roots.
4. Status and fill progress are orthogonal. Status is one value; cumulative filled and
   remaining quantity derive from immutable fills and never appear as compound statuses.
5. Every accepted order has one immutable original quantity, side, type, TIF, owner, and
   instrument. Amendments are replacements, never in-place mutation.
6. A replacement terminalizes its parent as `replaced` and creates a linked child for the
   requested new total quantity. The child quantity is not automatically parent remainder;
   the request must state it. Parent fills remain parent history.
7. FOK either fills its complete eligible remaining quantity in one eligibility cycle or
   cancels with no fill. IOC may partially fill and cancels the remainder in that same cycle.
8. Bar data proves a price range and total volume, not path, touch order, accessible queue,
   or auction participation. Every inferred outcome records the exact ambiguity/capacity
   policy and limitations.
9. Conservative ambiguity is the default. Optimistic and retrospective assumptions require
   explicit configuration and persistent material findings.
10. Eligibility plus a duration/seeded latency realization is the time abstraction. There
    is no primary `delay_bars` setting.
11. Capacity is shared deterministically among this engine's eligible orders by registered
    allocation policy. It never asserts real queue priority.
12. Execution price is formed once from a raw observed reference plus signed modeled spread,
    slippage, delay, and impact. Direct fees remain separate; Plan 11 prevents double posting.
13. A fill crossing through zero is split by the engine into close and open accounting legs
    with stable ordinals. Plan 11 never infers position effect from a net side.
14. Borrow and initial-margin checks occur before risk-increasing activation/fill. Maintenance
    breaches and recalls create engine-owned forced orders; strategy code cannot cancel,
    replace, or subordinate them.
15. Corporate actions, settlement, accrual, and cash flows advance without callbacks or
    orders. Their priority is explicit and their accounting is exclusively Plan 11.
16. A callback exception, invalid command, or modeled rejection is not silently dropped.
    Policy decides command rejection, callback disablement, or terminal failure and records it.
17. The event engine uses the same field-restricted next-open execution-outcome capability as
    Plan 12. It never makes later bar high/low/close/session volume visible at the open.
18. The isolated database is the occurrence boundary. A completed occurrence is immutable;
    interruption resumes only from a verified checkpoint and a retry is a new occurrence.
19. Safety, licensing, trust, conformance, fidelity, and lineage findings propagate
    monotonically. Overrides do not erase their cause.
20. Replay eligibility requires bounded deterministic components, exact seeds, immutable
    inputs, and resolvable code/environment identity. Wall-time or opaque external policies
    are allowed only as visibly replay-ineligible custom execution.

## 4. Identity, values, and public request

### 4.1 Typed IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `EventSimulationId` | `event_simulation` | One immutable standalone event occurrence |
| `SimulationEventOccurrenceId` | `simulation_event` | One clock occurrence |
| `StrategyCallbackId` | `strategy_callback` | One callback invocation and command batch |
| `OrderId` | `order` | One immutable order generation |
| `OrderTransitionId` | `order_transition` | One status transition |
| `FillId` | `fill` | One economic execution before accounting-leg split |
| `LatencyRealizationId` | `latency_realization` | One resolved policy delay |
| `ExecutionCheckpointId` | `execution_checkpoint` | One verified resumable prefix cache |
| `StatefulStrategyDefinitionId` | `stateful_strategy_definition` | Stable registered event-strategy lineage |

This plan reuses Plan-12 `FidelityProfileId` and fixes its shared home as
`persistra.simulation.fidelity`. Event and vectorized profiles use one envelope and distinct
versioned simulator-detail payloads. Plan 14 may associate general run identities with an
`EventSimulationId`; it may not alias or replace the occurrence.

### 4.2 Stable enums

Persisted values include:

- `OrderSide`: `buy`, `sell`
- `FillSide`: `buy`, `sell`, `sell_short`, `buy_to_cover` — the accounting-facing side of
  one fill leg. The engine derives it deterministically from `OrderSide` and reconciled
  position state: a `sell` beyond the owned long quantity splits into a `sell` close leg
  and a `sell_short` open leg, and a `buy` against an open short splits into a
  `buy_to_cover` close leg and a `buy` open leg. Plan 11 consumes only validated
  `FillSide` facts and never infers short semantics itself.
- `OrderType`: `market`, `limit`, `stop`, `stop_limit`, `market_on_open`, `market_on_close`
- `TimeInForce`: `day`, `gtc`, `ioc`, `fok`
- `OrderStatus`: `created`, `submitted`, `accepted`, `active`, `filled`, `cancelled`,
  `expired`, `replaced`, `rejected`
- `OrderOwner`: `strategy`, `rebalance`, `borrow_recall`, `margin_liquidation`, `system_action`
- `CommandKind`: `submit`, `cancel`, `replace`
- `AmbiguityPolicy`: `conservative`, `optimistic`, `seeded_randomized`, `reject_ambiguous`,
  `registered_custom`
- `CapacityPolicy`: `none_with_warning`, `pro_rata`, `price_time_simulated`, `priority_then_pro_rata`
- `SpreadSource`: `observed_quote`, `bar_estimator`, `constant`, `none`
- `EventRunStatus`: `planned`, `running`, `interrupted`, `completed`, `failed`

`price_time_simulated` orders by engine activation time and stable sequence only; its name
does not claim exchange queue position. Persisted enums are closed per schema version.

### 4.3 Orders and commands

```python no-run
@dataclass(frozen=True, slots=True)
class OrderSpec:
    instrument_id: InstrumentId
    side: OrderSide
    quantity: Quantity
    order_type: OrderType
    time_in_force: TimeInForce
    eligibility_at: datetime
    limit_price: Price | None = None
    stop_price: Price | None = None
    expire_at: datetime | None = None
    client_key: str | None = None

@dataclass(frozen=True, slots=True)
class ReplaceOrder:
    parent_order_id: OrderId
    new_spec: OrderSpec
    reason: str

@dataclass(frozen=True, slots=True)
class EventSimulationRequest:
    market_context: CompositeAsOfContext
    universe: UniverseEvaluationRef
    opening: AccountingOpeningRef
    strategy: StatefulStrategyRef
    schedule: EventScheduleRef
    execution: ExecutionPolicyRef
    accounting_policy: AccountingPolicyBundleRef
    cash_flows: CashFlowScheduleRef | None
    fidelity: EventFidelitySpec
    unsafe_override: UnsafeRunOverride | None
    seed: SeedSpec
    limits: EventSimulationLimits
```

Validation requires positive quantity and exact Plan-01 price/quantity quanta. Limit is
required only for limit/stop-limit; stop only for stop/stop-limit. MOO/MOC reject IOC/FOK in
3.0 because bar auction data cannot support the promised immediate atomic test. GTC may
carry an explicit finite `expire_at`; engine horizon still expires every surviving order.

Friendly references resolve before execution content is frozen. Requests contain no raw
dataframes, unregistered callables, mutable estimators, physical relation names, or `latest`.
`UnsafeRunOverride` is the plan-12 type with identical per-input, per-finding
acknowledgement and rejection semantics.

### 4.4 Limits

Limits cover events, callbacks, commands per callback, total orders, active orders, fills,
transitions, journal transactions, checkpoints, rows per materialization, bytes of strategy
state, custom-policy CPU time, and total deterministic work units. A limit outcome occurs at
a safe event boundary and never samples, truncates, or omits an order or accounting effect.
`max_custom_policy_cpu` is cumulative over all registered custom-policy calls in one event
occurrence, measured with the monotonic process CPU clock (`time.process_time_ns`) around each
call. The engine charges the nonnegative before/after delta and checks immediately after the
call; exceeding the limit stops at that call's safe event boundary. Because this boundary is
machine-dependent, the run becomes replay-ineligible with reason
`simulation.resource.custom_policy_cpu` and cannot claim exact replay roots.

```python no-run
@dataclass(frozen=True, slots=True)
class EventScheduleRef:
    name: QualifiedName
    version: int
    start: datetime
    end: datetime
    callback_kinds: tuple[Literal["session_open", "session_close", "bar", "scheduled"], ...]
    schedule_content_id: ContentId

@dataclass(frozen=True, slots=True)
class ExecutionPolicyRef:
    name: QualifiedName
    version: int
    activation: Literal["after_latency"]
    latency_model: QualifiedName
    observation_source: Literal["bar", "trade", "quote"]
    ambiguity: AmbiguityPolicy
    spread_model: QualifiedName
    slippage_model: QualifiedName
    impact_model: QualifiedName
    fee_model: QualifiedName
    capacity: CapacityPolicy
    participation_limit: Rate | None
    price_improvement: bool
    stale_after: Duration | None
    missing_observation: Literal["wait", "expire", "reject"]
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class EventFidelitySpec:
    level: Literal["event"] = "event"
    observation_resolution: Literal["bar", "trade", "quote"] = "bar"
    queue_claim: Literal["none", "synthetic_price_time"] = "none"
    intrabar_path: Literal["unknown_policy_resolved"] = "unknown_policy_resolved"
    partial_fills: bool = True
    latency_modeled: bool = True

@dataclass(frozen=True, slots=True)
class EventSimulationLimits:
    max_events: int = 100_000_000
    max_callbacks: int = 10_000_000
    max_commands_per_callback: int = 100_000
    max_orders: int = 100_000_000
    max_active_orders: int = 10_000_000
    max_fills: int = 100_000_000
    max_transitions: int = 500_000_000
    max_journal_transactions: int = 100_000_000
    max_checkpoints: int = 1_000_000
    max_rows_per_materialization: int = 100_000_000
    max_strategy_state_bytes: int = 100_000_000
    max_custom_policy_cpu: Duration = Duration(60_000_000)
    max_work_units: int = 1_000_000_000
    timeout: Duration = Duration(7_200_000_000)
```

`persistra.execution.daily_bar@1` is installed with constant-zero latency, bar observations,
conservative ambiguity, the section-11 zero spread/slippage/impact/fee models, pro-rata
capacity, no price improvement, and wait-on-missing. Every named model resolves to the
section-11 registry before identity freezes. Schedules are nonempty half-open intervals with
unique callback kinds; limits are positive; participation is in `(0, 1]`; stale duration is
positive; `price_time_simulated` requires `synthetic_price_time`; and unused/incompatible
fields are rejected with `EventSimulationRequestError` before execution.

## 5. Package and storage ownership

```text
src/persistra/simulation/
├── fidelity.py
├── event/
│   ├── requests.py
│   ├── clock.py
│   ├── context.py
│   ├── strategy.py
│   ├── engine.py
│   ├── checkpoints.py
│   └── repositories.py
├── orders/
│   ├── models.py
│   ├── state.py
│   ├── commands.py
│   └── repository.py
└── execution/
    ├── observations.py
    ├── bars.py
    ├── capacity.py
    ├── latency.py
    ├── costs.py
    └── policies.py
```

An occurrence requires `ProjectMode.RESEARCH_WRITE`, shared leases on exact market members,
and exclusive ownership of one disposable run database. It reuses migration-owned
`simulation`, `simulation_data`, `accounting`, and `journal_data` schemas. Final merge/export
belongs to Plan 15 and orchestration to Plan 14. There is no cross-file transaction claim.

## 6. Event clock, visibility, and callbacks

### 6.1 Clock key and occurrence

The engine preplans fixed calendar/decision/cash-flow boundaries and incrementally inserts
orders, latency completions, fills, recalls, margin actions, and checkpoints. Every event has:

- exact UTC `effective_at` and venue-local session identity where applicable;
- priority from the table below;
- a source-local stable key resolved into gap-free `stable_sequence` before dispatch;
- event kind/version, payload root, availability, safety/lineage/licensing roots; and
- predecessor/cause IDs sufficient to audit why it exists.

No same-key collision is resolved through UUID ordering. Duplicate semantic source keys with
different payloads fail planning or the enclosing event transaction.

### 6.2 Same-timestamp priority

The total priority, lowest number first, is:

| Priority | Occurrence |
| ---: | --- |
| 10 | session/calendar/status boundary effective at the instant |
| 20 | corporate-action capture/effect/payment and delisting state |
| 30 | settlement obligations becoming settled |
| 40 | external cash flows and scheduled financing/borrow accrual |
| 50 | raw market observation becomes engine-eligible |
| 60 | previously scheduled cancel/replace commands become effective |
| 70 | submitted orders are accepted/rejected; accepted orders activate when latency permits |
| 80 | triggers, capacity allocation, executions, fills, and Plan-11 fill accounting |
| 90 | expirations and IOC remainder cancellation after the eligibility cycle |
| 100 | valuation, reconciliation, maintenance margin, recall evaluation, forced-order creation |
| 110 | strategy callback with the fully committed visible prefix |
| 120 | callback command validation/submission; no command can execute earlier than this point |
| 130 | checkpoint/result sampling and progress event |

An event created during a priority bucket cannot retroactively enter an earlier bucket at
the same timestamp. It receives the earliest legal later priority or a later instant. Thus a
callback sees fills and margin state at its timestamp, but its orders cannot consume the
market occurrence that preceded it. A deposit at that timestamp is included in callback
state. Corporate-action date mapping remains Plan 05/11 authority.

### 6.3 Observation visibility

Canonical observation availability remains Plan 03–06 authority. The engine can consume an
exact execution-only outcome when its policy is eligible, but the strategy context exposes
only observations whose canonical availability is at or before callback cutoff. At daily
next-open, only the exact open projection is execution-eligible; current-session high, low,
close, full volume, and revised values remain inaccessible.

Sentinel fields injected after each cutoff must be unreachable through context, strategy
state, custom execution policy, logs, errors, and command validation. Custom policies receive
capability-scoped immutable facts, not project/database access.

### 6.4 Stateful strategy boundary

```python no-run
@dataclass(frozen=True, slots=True)
class StrategyStateTypeSpec:
    kind: Literal["id", "instant", "date", "duration", "decimal", "money", "price", "quantity", "enum", "bool", "string", "tuple", "mapping"]
    nullable: bool = False
    item_type: "StrategyStateTypeSpec | None" = None
    key_type: "StrategyStateTypeSpec | None" = None
    value_type: "StrategyStateTypeSpec | None" = None
    enum_name: QualifiedName | None = None

@dataclass(frozen=True, slots=True)
class StrategyStateFieldSpec:
    name: str
    type_spec: StrategyStateTypeSpec

@dataclass(frozen=True, slots=True)
class StatefulStrategyDefinition:
    name: QualifiedName
    version: ResearchComponentVersion
    parameter_schema_content_id: ContentId
    default_parameters: ParameterValues
    default_parameters_content_id: ContentId
    state_fields: tuple[StrategyStateFieldSpec, ...]
    implementation_content_id: ContentId
    conformance_content_id: ContentId
    callback_limit: int
    state_schema_version: SchemaVersion

@dataclass(frozen=True, slots=True)
class StatefulStrategyRef:
    strategy_definition_id: StatefulStrategyDefinitionId
    version: ResearchComponentVersion
    definition_content_id: ContentId
    parameters: ParameterValues
    parameters_content_id: ContentId
    initial_state_content_id: ContentId
    implementation_content_id: ContentId
    conformance_content_id: ContentId
```

`simulation.event.strategies.register(definition, implementation)` uses Plan-08 code capture,
persists the closed definition, and returns a resolver. `.resolve(name, version, parameters,
initial_state)` validates defaults/overrides and the initial state, canonicalizes both, and
returns `StatefulStrategyRef`. The default-parameter content ID must byte-match the canonical
defaults and every override is merged only through the registered parameter schema. Field
names are unique; tuple/mapping type specs embed their required nested type specs and forbid
unused fields; mapping keys are scalar/string/enum;
callback limits are positive. Unknown versions, schema/state/parameter mismatch, opaque code,
or conformance failure map to `StrategyRegistrationError`/`StrategyStateError`; opaque code
may proceed only under the explicit unsafe/replay-ineligible path.

`StatefulStrategy.on_event(context) -> tuple[OrderCommand, ...]` is synchronous and bounded.
Context contains event envelope, exact cutoff, reconciled Plan-11 portfolio view, strategy-
owned prior state, active/order-history projections, and registered point-in-time research
capabilities. It contains no writable repository or future schedule payload.

Strategy state changes and its commands commit atomically with callback evidence. Re-running
a callback from its verified predecessor yields the same state/command roots when replay
eligible. Direct labels, retrospective roots, unreleased fits, unsafe inputs without explicit
override, and untrusted opaque code follow Plans 07–10.

`StatefulStrategyRef` resolves a strategy registered exactly like a plan-08 component: a
qualified name, semantic version, declared frozen parameters, and plan-08 implementation
capture (code identity for trusted registration; unregistered or opaque callables make the
run replay-ineligible and unsafe by default). Registration also declares the strategy's
state schema: a named, versioned, closed set of fields limited to plan-01 value types
(IDs, instants, dates, `Duration`, fixed-precision numbers/`Money`/`Price`/`Quantity`,
enums, booleans, strings), homogeneous tuples/mappings of those, and `None`. State is
canonically serialized under plan-01 section 10 — this serialization is what checkpoints
hash and what the `bytes of strategy state` limit measures. A callback returning state
outside the declared schema fails the run at that safe boundary; arbitrary Python objects,
floats in identity material without a declared normalization, and hidden mutable captures
are rejected. A state-schema change is a new strategy version.

## 7. Order lifecycle and fill progress

### 7.1 Legal transitions

| From | To | Required cause |
| --- | --- | --- |
| none | `created` | validated command allocated an order ID |
| `created` | `submitted` | command batch committed |
| `submitted` | `accepted` | venue/policy validation succeeds |
| `submitted` | `rejected` | static, policy, eligibility, locate, or margin validation fails |
| `submitted` | `cancelled` | permitted cancel becomes effective before acceptance |
| `submitted` | `replaced` | permitted replace becomes effective before acceptance |
| `accepted` | `active` | activation instant reached and instrument eligible |
| `accepted` | `cancelled`/`replaced` | permitted preactivation command becomes effective |
| `accepted` | `rejected` | only a recorded late external gate invalidates acceptance before activation |
| `active` | `filled` | cumulative fill equals original quantity |
| `active` | `cancelled` | user/system cancel or IOC/FOK remainder outcome |
| `active` | `expired` | day/session/explicit/horizon expiry |
| `active` | `replaced` | replacement becomes effective |

Terminal states have no outgoing transition. `rejected` from accepted is narrowly limited to
an exact activation-time venue/status/borrow gate; ordinary later unavailability leaves an
active order unfilled or cancels it under policy. Partial fill never changes status away from
`active`. Each transition stores prior status, new status, owner, cause, reason, event key,
cumulative filled, remaining, and content root.

Cancel/replace requests rejected because the order is terminal or the fill won the exact
event ordering create command outcomes but no false order transition. Duplicate command
client keys with identical content return the original outcome; conflicting reuse rejects.

### 7.2 Fill progress

For every order:

```text
cumulative_filled = exact sum(fill.quantity)
remaining = original_quantity - cumulative_filled
0 <= cumulative_filled <= original_quantity
```

Fills are positive absolute quantities; order side supplies sign. A fill references the
active transition, observation, capacity allocation, latency realization, price/cost roots,
and event. Fill ordinals are gap-free. Filled quantity never exceeds the remaining quantity
at the start of its eligibility cycle.

### 7.3 Replacement and forced ownership

A replacement child records parent, root order, generation, command, and reason. It undergoes
normal validation/latency and can be rejected without altering the already-replaced parent.
The strategy must choose a child quantity accounting for known parent fills.

Forced orders are otherwise ordinary auditable orders but have system owner, source intent,
highest order-allocation priority, and non-cancellable/non-replaceable policy. They still
obey market eligibility and cannot invent liquidity or prices. Failure to recover a breach
is a visible state and may terminally fail under policy.

## 8. Activation, expiration, and order-type semantics

Submission latency starts at command commit. Acceptance validates instrument/listing/session,
quantity quantum, price fields, TIF/type compatibility, short locate, initial margin, cash
policy, and bounded policy availability. Activation occurs at the first exact eligible event
at or after `max(order.eligibility_at, acceptance_at + activation_latency)`.

- `market`: fills at the next eligible execution observation, subject to capacity.
- `limit`: buy is eligible at prices at or below limit; sell at or above limit.
- `stop`: triggers at or beyond the stop and then behaves as a market order from the trigger
  point; it cannot fill before the trigger.
- `stop_limit`: triggers like stop and thereafter behaves as a limit order. Trigger state is
  immutable auxiliary progress, not an order status.
- `market_on_open`: eligible only for the next permitted session open outcome.
- `market_on_close`: eligible only for the next permitted session close outcome.

`day` expires after the owning venue's eligible session execution cycle; an order activated
outside any session belongs to the next eligible session and expires at the end of that
session's cycle. `gtc` survives
sessions until explicit expiry/horizon. IOC/FOK receive exactly one eligibility cycle. A halt
or missing required observation yields no cycle until policy says the venue opportunity has
passed; auction orders expire if their named auction proxy is unavailable.

## 9. Bar execution and ambiguity

### 9.1 Observation selection

Policies bind exact raw canonical bar, trade, or quote revisions and their snapshot/cutoff.
Adjusted prices are forbidden. Quotes can supply observed bid/ask/mid and size only when exact
and eligible. Trades provide observed price/size but no universal accessible capacity. Bars
provide open/high/low/close/volume and status under Plan 05 limitations.

MOO uses the raw open as an auction proxy and MOC the raw close as a closing-auction proxy;
both record `auction_not_observed`. Exact auction data can be introduced only by a versioned
policy after canonical schema support.

### 9.2 OHLC reachability

For a bar after activation:

- buy limit is touched when `low <= limit`; sell limit when `high >= limit`;
- buy stop triggers when `high >= stop`; sell stop when `low <= stop`;
- a market order uses the policy's exact open/close/reference point;
- a favorable opening gap executes a limit at the open under the configured price-improvement
  rule, never worse than its limit before modeled costs;
- a stop gapping through its level uses the open/reference and can be worse than stop; and
- stop-limit needs both a trigger and a later/equal limit-eligible point under the chosen path.

Absent a gap, an intrabar touch pins `observed_reference` (section 11) to the order's own
level: a touched limit fills at its limit price, and a triggered stop converts at its stop
price. Gap cases use the open/reference as above; market orders always use the policy's
declared open/close/reference point. The pre-cost reference never violates the order's
limit; modeled cost components applied on top of it may make the all-in `fill_price`
worse than the limit, consistent with "never worse than its limit before modeled costs"
above and the unconditional section-11.1 formulas.

When OHLC cannot establish trigger/touch order, capacity ordering, or whether stop-limit
filled after trigger, the result is ambiguous. `conservative` chooses the least favorable
valid outcome for the order/portfolio without violating OHLC; `optimistic` the most favorable;
`seeded_randomized` samples a registered finite valid-path family with stored seed/draw;
`reject_ambiguous` produces no fill and a finding. A custom path returns explicit steps and
proof; opaque/unbounded code is replay-ineligible.

Conservative is evaluated per jointly competing order set, not independently in a way that
allocates the same capacity twice. No policy claims the selected path actually occurred.

### 9.3 Same-close research mode

Orders created from a callback after a completed close cannot fill that close. An explicitly
optimistic same-close workflow must schedule the decision before the execution outcome while
restricting its information cutoff, or use Plan 12's synthetic same-close mode. Backdating a
callback-created order is always rejected.

## 10. Capacity and partial fills

Eligible capacity derives from one exact source and records observed/estimated/ignored state.
Participation applies a nonnegative rate to eligible volume, subtracts earlier allocations,
rounds down to quantity quantum, and honors minimum fill size. At session open the default is
causally available lagged volume/ADV. Same-session total volume is a retrospective fidelity
assumption and is never strategy-visible. Zero volume differs from missing volume.

Capacity allocation first places forced orders (`borrow_recall` and `margin_liquidation`
owners), then the remaining owner groups in fixed order `rebalance`, `strategy`,
`system_action`, then stable activation/order sequence within each group. Pro-rata allocation uses deterministic largest remainder. Self-crossing
orders do not fabricate fills; a registered internal-cross scenario would require separate
accounting and is deferred.

Partial fills are permitted for market/limit/stop/stop-limit/day/GTC/IOC. FOK preflights
complete quantity, price, capacity, borrow, margin, cash, and accounting before any fill.
IOC allocates once and cancels a remainder at priority 90. A day/GTC remainder stays active
only when its TIF permits.

## 11. Price and realized costs

Precision-80 calculation forms a positive Plan-01 price:

```text
fill_price = observed_reference
           + signed_half_spread
           + signed_slippage
           + signed_delay_cost
           + signed_market_impact
```

Every component records amount per unit, sign, units, observed/estimated/model state,
component/version, parameters/calibration root, applicability regime, input observation,
availability, and seed draw. Price improvement may make a component favorable. Direct
commission and regulatory fees are positive USD amounts attached separately.

An observed quote spread cannot also be charged through an estimator. Slippage/impact models
declare whether spread is included; overlapping configurations fail by default or require a
named warning policy. Delay compares exact arrival/reference and execution observations when
both exist; otherwise it is a marked model, never relabeled observed. Impact is always a
scenario model.

Each economic `FillId` becomes one or two Plan-11 `FillAccountingFacts` applications. Direct
fees post to the general book; spread/slippage/delay/impact use the memorandum book because
they are embedded in fill price. Source IDs/ordinals make retry idempotent.

### 11.1 Built-in model catalog

The initial registry, shared with plan 12, contains exactly these versioned built-ins;
anything else registers as a custom policy under section 18:

- **Latency** — `persistra.latency.zero@1` (submission and activation delays are zero;
  activation at eligibility) and `persistra.latency.constant@1` (parameters
  `submission: Duration`, `activation: Duration`; fixed deterministic delays, no seed
  draw). Seeded latency requires a registered custom policy.
- **Spread** — for `SpreadSource.constant`, `persistra.spread.constant_bps@1` with
  nonnegative parameter `half_spread_bps`:
  `signed_half_spread = direction * (half_spread_bps / 10_000) * observed_reference`,
  where `direction` is `+1` for buy-side legs and `-1` for sell-side legs. For
  `SpreadSource.bar_estimator`, `persistra.spread.corwin_schultz@1`: the Corwin–Schultz
  high–low estimator over the fill bar and its immediately preceding complete raw bar
  (`beta = ln(H1/L1)^2 + ln(H2/L2)^2`, `gamma = ln(max(H1,H2)/min(L1,L2))^2`,
  `alpha = (sqrt(2*beta) - sqrt(beta))/(3 - 2*sqrt(2)) - sqrt(gamma/(3 - 2*sqrt(2)))`,
  `spread = max(0, 2*(exp(alpha) - 1)/(1 + exp(alpha)))`, half-spread applied as above);
  a missing or partial predecessor bar makes the component unavailable and the fill
  follows the policy's declared unavailable action (fail, or fall back to a declared
  constant) — never a silent zero.
- **Slippage** — `persistra.slippage.zero@1` and `persistra.slippage.constant_bps@1` with
  nonnegative one-way parameter `bps`:
  `signed_slippage = direction * (bps / 10_000) * observed_reference`. Both declare that
  spread is not included.
- **Delay cost** — observed when exact arrival/reference and execution observations both
  exist (section 11); the only built-in model otherwise is `persistra.delay.none@1`,
  which records a zero component in model state.
- **Market impact** — no built-in realized-impact model exists in 3.0;
  `signed_market_impact` is zero unless a registered scenario model is configured
  (plan 10's expected-cost impact formulas are estimates and are never reused as realized
  components).
- **Fees** — `persistra.fees.zero@1` and `persistra.fees.per_share@1` with parameters
  `usd_per_share`, `minimum_usd`:
  `commission = max(minimum_usd, usd_per_share * quantity)` quantized half-even to USD
  0.01; regulatory fees, when configured, are a separate registered schedule, never
  folded into commission.

The plan-18 benchmark's "constant 5 bps one-way slippage" and "USD 0.005/share, USD 1
minimum commission" bind `persistra.slippage.constant_bps@1(bps=5)` and
`persistra.fees.per_share@1(usd_per_share=0.005, minimum_usd=1)`.

## 12. Borrow, margin, settlement, and corporate actions

Risk-increasing short activation consumes an exact Plan-11 authorization/locate. Partial
fills consume only filled quantity. Expired/cancelled/replaced/rejected remainder releases
reservation. Long sales require owned/unrestricted quantity unless a child short-open leg is
separately authorized.

Initial-margin/cash checks preflight fills; maintenance margin is evaluated after committed
fills/actions/accrual/valuation. Plan-11 liquidation intents are transformed deterministically
into forced market orders using the intent candidate/selection root. A newly created forced
order cannot fill in an earlier same-timestamp bucket. Recall intents follow the same rule.

Fill accounting creates exact trade-date lots/payables/receivables and Plan-11 settlement
obligations. Settlement, financing, borrow charges, distributions, splits, mergers,
delistings, fractions, and corrections use Plan 11 unchanged. An action that changes an active
order's instrument/quantity follows an explicit cancel policy in 3.0; the engine does not
silently adjust orders. The cancellation reason names the action.

## 13. Fidelity profile and Plan-12 equivalence

The shared profile envelope records every umbrella field: simulator/version, granularity,
decision cutoff/schedule, knowledge mode/availability quality, submission/activation,
latency, ambiguity, spread, fee/slippage/impact, participation, borrow, margin, settlement,
actions, stale/missing marks, precision/rounding, unsafe flags, custom trust/conformance, and
seeds. Event detail also records order types/TIF, callback policy, cancellation/replacement,
capacity allocation, quote/bar/auction limitations, forced priority, checkpoint/replay, and
every retrospective assumption.

Comparisons classify field differences under a versioned Plan-15 policy. A missing fidelity
field is incompatible, not equal-by-default.

Restricted Plan-12 equivalence requires identical opening/targets/grid; a deterministic
target-to-market-order adapter; fractional quantities; zero latency; one exact observation;
infinite modeled liquidity; no partial/cancel/replace/forced order; identical observed price
and direct fees; identical constant modeled costs or none; sufficient cash/borrow/margin;
and identical accounting/action/settlement/accrual policy. Economic cash, quantities, NAV,
cost, and P&L agree at mapped checkpoints. Order/transition/fill IDs and journal row grouping
need not match. Plan-12 synthetic fills never receive retrofitted order status.

## 14. Execution identity, checkpoints, and completion

Execution content includes resolved request, immutable snapshots, universe/schedule/cutoffs,
opening, strategy/version/state schema, all policies and fidelity, code/dependency/platform,
safety/licensing/trust, seed plan and realized RNG streams, limits, event-priority version,
schemas, and output contract. It excludes allocated occurrence IDs and derived roots.

A checkpoint binds the occurrence execution content, inclusive event sequence, prior
checkpoint, event/order/transition/fill/journal prefixes, accounting snapshot, strategy
state, pending-event heap, active orders, reservations, trigger progress, RNG states,
normalized count/roots, schema, and checkpoint bytes. Resume verifies all fields and replays
from an earlier verified checkpoint or zero on mismatch. It never repairs authority from a
cache or mixes occurrence IDs.

Completion requires terminal/explicitly-horizon-expired orders, complete callbacks/events,
gap-free sequences, reconciled journal/state, exact count and Merkle roots, fidelity/safety/
lineage/licensing manifests, no pending transaction, and atomic completed manifest. A modeled
failure writes a bounded terminal failure manifest but no completed artifact root. A retry is
a new `EventSimulationId` and isolated file under a new Plan-14 attempt identity. Only an
`interrupted` occurrence with a verified checkpoint may resume within the same attempt.

Result sampling also emits exact external-flow-split return intervals from committed
Plan-11 valuation and cash-flow prefixes, including structured unavailable intervals. These
are occurrence outputs covered by completion roots. Plan 15 maps them without recalculating
simulator history; alternative performance-return policies remain immutable analyses.

## 15. Physical schema

Plan 15 may copy these normalized relations into final result storage without changing their
semantics. Payload/parameter manifests are canonical bounded objects, not arbitrary pickle.
Event runs insert `profile_kind='event'` into Plan-12 §13's simulator-discriminated
`simulation.fidelity_profiles` table, with the resolved latency model, ambiguity policy,
event capacity action, and `event_forced_orders`; they never use the vectorized-only branch.
Every event run also creates and populates the shared
`simulation_data.published_equity`, `published_returns`, `published_positions`,
`published_cash`, `cost_components`, `published_exposures`,
`published_quality_findings`, `published_fidelity_findings`, and
`published_lifecycle_events` relations with the exact DDL and verification rules in Plan-12
§13. Its `simulation_run_id` is the `event_simulation_id`. Per-component rows reference the
owning fill and retain the model/version, inputs, availability, sign, and evidence through
`component_content_id`; `fills.cost_component_content_id` is their ordered manifest root,
not a substitute for the normalized rows.

```sql
CREATE TABLE simulation.event_runs (
    event_simulation_id UUID PRIMARY KEY,
    status VARCHAR NOT NULL CHECK (
        status IN ('planned', 'running', 'interrupted', 'completed', 'failed')
    ),
    execution_content_id VARCHAR NOT NULL,
    fidelity_profile_id UUID NOT NULL,
    strategy_content_id VARCHAR NOT NULL,
    event_priority_version VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    seed_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    completed_manifest_content_id VARCHAR,
    failure_manifest_content_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CHECK ((status = 'completed') = (completed_manifest_content_id IS NOT NULL)),
    CHECK (NOT (completed_manifest_content_id IS NOT NULL AND failure_manifest_content_id IS NOT NULL))
);

CREATE TABLE simulation.event_occurrences (
    simulation_event_occurrence_id UUID PRIMARY KEY,
    event_simulation_id UUID NOT NULL,
    event_sequence BIGINT NOT NULL CHECK (event_sequence >= 1),
    effective_at TIMESTAMPTZ NOT NULL,
    priority SMALLINT NOT NULL CHECK (priority > 0),
    stable_sequence BIGINT NOT NULL CHECK (stable_sequence >= 1),
    event_kind VARCHAR NOT NULL,
    event_version INTEGER NOT NULL CHECK (event_version >= 1),
    cause_event_id UUID,
    session_id UUID,
    payload_content_id VARCHAR NOT NULL,
    availability_content_id VARCHAR NOT NULL,
    outcome_content_id VARCHAR NOT NULL,
    UNIQUE (event_simulation_id, event_sequence),
    UNIQUE (event_simulation_id, effective_at, priority, stable_sequence)
);
```

```sql
CREATE TABLE simulation.orders (
    order_id UUID PRIMARY KEY,
    event_simulation_id UUID NOT NULL,
    root_order_id UUID NOT NULL,
    parent_order_id UUID,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    instrument_id UUID NOT NULL,
    side VARCHAR NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type VARCHAR NOT NULL CHECK (
        order_type IN ('market', 'limit', 'stop', 'stop_limit', 'market_on_open', 'market_on_close')
    ),
    time_in_force VARCHAR NOT NULL CHECK (time_in_force IN ('day', 'gtc', 'ioc', 'fok')),
    owner VARCHAR NOT NULL CHECK (
        owner IN ('strategy', 'rebalance', 'borrow_recall', 'margin_liquidation', 'system_action')
    ),
    original_quantity DECIMAL(38, 12) NOT NULL CHECK (original_quantity > 0),
    limit_price DECIMAL(38, 12),
    stop_price DECIMAL(38, 12),
    eligibility_at TIMESTAMPTZ NOT NULL,
    expire_at TIMESTAMPTZ,
    created_event_id UUID NOT NULL,
    order_content_id VARCHAR NOT NULL UNIQUE,
    CHECK ((order_type IN ('limit', 'stop_limit')) = (limit_price IS NOT NULL)),
    CHECK ((order_type IN ('stop', 'stop_limit')) = (stop_price IS NOT NULL))
);

CREATE TABLE simulation.order_transitions (
    order_transition_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    transition_ordinal INTEGER NOT NULL CHECK (transition_ordinal >= 1),
    event_id UUID NOT NULL,
    prior_status VARCHAR,
    new_status VARCHAR NOT NULL CHECK (
        new_status IN ('created', 'submitted', 'accepted', 'active', 'filled', 'cancelled', 'expired', 'replaced', 'rejected')
    ),
    cumulative_filled DECIMAL(38, 12) NOT NULL CHECK (cumulative_filled >= 0),
    remaining_quantity DECIMAL(38, 12) NOT NULL CHECK (remaining_quantity >= 0),
    reason_code VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    transition_content_id VARCHAR NOT NULL UNIQUE,
    UNIQUE (order_id, transition_ordinal)
);
```

```sql
CREATE TABLE simulation_data.fills (
    fill_id UUID PRIMARY KEY,
    event_simulation_id UUID NOT NULL,
    order_id UUID NOT NULL,
    fill_ordinal INTEGER NOT NULL CHECK (fill_ordinal >= 1),
    event_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    side VARCHAR NOT NULL CHECK (side IN ('buy', 'sell', 'sell_short', 'buy_to_cover')),
    quantity DECIMAL(38, 12) NOT NULL CHECK (quantity > 0),
    observed_reference_price DECIMAL(38, 12) NOT NULL CHECK (observed_reference_price > 0),
    fill_price DECIMAL(38, 12) NOT NULL CHECK (fill_price > 0),
    direct_fee_usd DECIMAL(38, 12) NOT NULL CHECK (direct_fee_usd >= 0),
    observation_content_id VARCHAR NOT NULL,
    ambiguity_content_id VARCHAR NOT NULL,
    capacity_content_id VARCHAR NOT NULL,
    cost_component_content_id VARCHAR NOT NULL,
    accounting_source_content_id VARCHAR NOT NULL,
    fill_content_id VARCHAR NOT NULL UNIQUE,
    UNIQUE (order_id, fill_ordinal)
);

CREATE TABLE simulation.execution_checkpoints (
    execution_checkpoint_id UUID PRIMARY KEY,
    event_simulation_id UUID NOT NULL,
    checkpoint_sequence BIGINT NOT NULL CHECK (checkpoint_sequence >= 1),
    inclusive_event_sequence BIGINT NOT NULL CHECK (inclusive_event_sequence >= 0),
    prior_execution_checkpoint_id UUID,
    execution_content_id VARCHAR NOT NULL,
    prefix_manifest_content_id VARCHAR NOT NULL,
    engine_state_content_id VARCHAR NOT NULL,
    checkpoint_content_id VARCHAR NOT NULL UNIQUE,
    UNIQUE (event_simulation_id, checkpoint_sequence)
);
```

Application validation supplies cross-table foreign keys, status-transition legality,
parent/root/generation consistency, exact quantity sums, and completion closure where DuckDB
`CHECK` constraints cannot express them. Migrations may add physical foreign keys only after
copy/merge ordering and performance are proven.

## 16. Public API, events, and failures

```python no-run
plan = project.services.simulation.event.plan(request)
run = project.services.simulation.event.run(plan)
run = project.services.simulation.event.resume(interrupted_handle)
orders = run.orders(limit=1_000)
fills = run.fills(limit=1_000)
events = run.events(limit=1_000)
```

Handles expose bounded typed projections and explicit pandas materialization. They do not
expose mutable connections. Domain events cover planned, started, callback completed,
command outcome, order transition, fill completed, checkpoint, completed, interrupted, and
failed occurrences. Tables remain authority; event delivery is post-commit and at-least-once.

Public exceptions include `EventPlanningError`, `StrategyCallbackError`, `OrderCommandError`,
`ExecutionPolicyError`, `EventInvariantError`, `EventResourceLimitError`, and
`EventResumeError`. Stable reasons include invalid order fields/TIF, late command, duplicate
client-key conflict, venue closed/halted, locate/margin/cash unavailable, ambiguous bar,
missing/stale observation, capacity unavailable/clipped, auction proxy unavailable, cancel/
replace too late, callback unsafe/resource failure, accounting rejection/reconciliation,
checkpoint mismatch, incomplete output, and replay ineligible.

## 17. Edge cases and failure behavior

| Case | Required outcome |
| --- | --- |
| Limit touched with no path order | Apply named ambiguity policy and persist proof/finding |
| Stop and limit both inside bar | Conservative default cannot assume favorable ordering |
| Multiple orders exceed capacity | One deterministic shared allocation; never duplicate volume |
| FOK capacity sufficient but cash fails | No fill, cancel/reject reason, no journal side effect |
| IOC partial | Fill once, cancel remainder in same cycle |
| Cancel ties with fill | Priority table decides; losing command has explicit outcome |
| Replace after partial | Parent retains fills; child uses explicitly requested new quantity |
| Split with active order | Cancel under named action policy; never silently resize |
| Recall during halt | Forced cover stays active/unfilled and breach remains visible |
| Missing open | MOO expires or fails by policy; no close substitution |
| Open execution on daily bar | Only open projection available; session high/low/close/volume hidden |
| Delisting without proceeds | Block accounting/order path; never assume zero |
| Strategy callback exception | Apply declared fail/disable policy with immutable evidence |
| Interrupt after fill journal commit | Event transaction/checkpoint proves complete prefix; no duplicate fill |
| Corrupt checkpoint | Ignore and replay earlier/zero; never patch it |
| Engine horizon with GTC | Expire explicitly and close lifecycle before completion |

Secrets, credentials, raw unrestricted SQL, filesystem handles, and mutable project services
never reach strategy/custom policy contexts or structured logs. Error strings are bounded and
redacted. Seeded random streams are partitioned by qualified component/event key so unrelated
event insertion does not perturb prior draws.

## 18. Migration and extension policy

There is no trusted v2 order/run import. V2 artifacts may be external opaque evidence only.
Schemas are migration-owned under Plan 02, changed by verified copy migration, and versioned
in execution identity. A completed occurrence is never migrated in place as if byte-identical;
Plan 15 owns compatible export upgrades.

Custom latency, path, capacity, cost, fee, borrow, margin, action-order, and liquidation
policies register qualified name, semantic/schema version, canonical configuration, code/
dependency identity, determinism/resource declaration, required facts, fidelity fields, and
conformance suite. They receive bounded capability objects. Unknown identity or unseeded/
wall-time behavior makes replay/exact reuse ineligible and cannot be hidden by override.

## 19. Implementation sequence

1. Add shared fidelity envelope, IDs/enums/requests, schemas, repositories, and limits.
2. Implement event planning, total priority, visibility sentinels, callback/state boundary,
   event transactions, and deterministic seed streams.
3. Implement order validation, legal transitions, fill progress, client idempotency,
   cancellation, replacement, TIF, and expiration.
4. Implement raw observation selection, market/auction proxies, OHLC reachability, ambiguity,
   latency, and activation.
5. Implement shared capacity, partial/IOC/FOK allocation, price formation, cost components,
   and accounting-leg split.
6. Integrate Plan-11 settlement/actions/accrual/borrow/margin/forced orders/reconciliation.
7. Add fidelity, normalized evidence, checkpoints/resume, failure manifests, resource/fault/
   determinism tests, and restricted Plan-12 equivalence.
8. Complete public docs, strict build, benchmark hooks, and cumulative plans 01–13 review.

## 20. Acceptance tests and exit criteria

### 20.1 Clock and visibility

- Golden schedules cover tied priorities, callbacks, deposits, actions, settlement, accrual,
  market events, fills, margin, DST, holidays, early close, halt, and horizon expiration.
- Insertion/partition/hash order cannot change sequences or roots. Duplicate semantic keys
  conflict. Created same-timestamp events never move backward in priority.
- Future/revised/sentinel fields never reach strategy or custom code. Daily next-open exposes
  only exact open to execution and no later bar field to decision context.
- Callback state/commands are atomic, bounded, deterministic, causal, and reject structural
  label or unreleased-fit paths under every override.

### 20.2 Orders and execution

- Table-driven tests cover every legal/illegal transition, preactivation cancel/replace,
  terminal command races, client-key idempotency, partial-terminal history, and child quantity.
- Every order type/TIF covers gaps, touches, trigger ordering, missing auction proxy, halt,
  day/GTC/IOC/FOK, fractional policy, quantity quantum, and minimum fill.
- Conservative/optimistic/random/reject policies cover every valid OHLC path family; seeded
  replay is exact and limitations persist.
- Competing-order capacity never double allocates; forced priority, pro-rata remainder, zero/
  missing volume, lagged open capacity, and retrospective current volume are explicit.
- Fill price/cost signs, observed/estimated classification, overlap rejection, direct fees,
  favorable components, arrival delay, impact scenario, and no double accounting are golden.

### 20.3 Accounting, recovery, and fidelity

- Long/short/cross-zero/partial fills reconcile through Plan-11 lots, cash, fees, memorandum
  costs, settlement, borrow, margin, actions, accruals, valuation, and state.
- FOK preflight and failed/cancelled/no-fill paths leave no accounting source. Retry cannot
  duplicate fill or journal application.
- Locate reservations release exactly; recall/margin intents generate non-cancellable forced
  orders and unresolved halt/liquidity cases remain breaches.
- Fault injection at every event/callback/transition/fill/journal/checkpoint/completion boundary
  exposes only a verified prefix. Resume equals uninterrupted roots.
- Fidelity contains every umbrella/event detail; material differences warn/incompatibly
  compare. Restricted Plan-12 fixture agrees economically without synthetic order statuses.
- Schemas, bounded APIs, migration/copy/reopen, docs snippets, strict MkDocs, optional/base
  imports, `make lint type test`, and docs checks pass.

### 20.4 End-to-end exit

A documented daily-bar stateful long/short workflow must process exact opening capital,
next-open market and limit/stop orders, partial/IOC/FOK outcomes, cancellation/replacement,
explicit costs, borrow, recall, margin liquidation, settlement, financing, split/dividend,
valuation, reconciliation, checkpoint resume, ambiguity comparison, and final immutable
isolated artifact using public APIs only. It must also run the restricted Plan-12 equivalence
fixture and diagnose one deliberate fidelity difference.

Plan 13 is complete only when all tests pass with repository gates, docs checks, strict build,
benchmark hooks, and cumulative review finds no contradiction with the umbrella or Plans
01–12.

## 21. Review checklist for dependent plans

Plans 14–18 must preserve:

- the immutable occurrence, event priority, closed visibility prefix, and callback command
  boundary;
- status separate from fill progress, complete transition history, and explicit replacement
  child quantity;
- atomic FOK, same-cycle IOC, partial terminal history, deterministic capacity, and no queue
  realism claim;
- raw observation identity, field-restricted open execution, ambiguity evidence, and exact
  realized cost classification;
- Plan-11 accounting ownership and order-to-fill-to-accounting source traceability;
- non-cancellable forced ownership without invented liquidity;
- shared complete fidelity, monotone safety/licensing/lineage, and equivalence restrictions;
- verified isolated checkpoints, exact retry, bounded normalized evidence, and atomic
  completion; and
- Plan-12 synthetic fills remaining order-free.

Plan 14 schedules/reuses attempts but cannot reorder their events or alter checkpoints.
Plan 15 copies and analyzes immutable normalized outputs but cannot mutate occurrences or
replace missing observations with unmarked estimates. Plans 16–17 render public result APIs,
not private calculations. Plan 18 tests these contracts and cannot weaken them to meet a
benchmark.

## 22. Consistency statement

This plan implements the umbrella stateful order simulator while retaining all completed
identity, point-in-time, construction, and accounting boundaries. It names precisely what
bar data can prove, makes every modeled path and cost inspectable, and leaves market replay
out of scope. It shares fidelity and economic accounting with Plan 12 without pretending
synthetic fills have order history. No project-level direction is revised.
