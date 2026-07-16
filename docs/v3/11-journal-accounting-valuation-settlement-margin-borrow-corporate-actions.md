# Focused specification 11: Journal accounting, valuation, settlement, margin, borrow, and corporate actions

**Status:** implementation plan
**Target:** Persistra 3.0
**Primary package:** `persistra.accounting`

## 1. Purpose and relationship to the umbrella specification

This plan makes the accounting direction in the
[v3 umbrella specification](v3-spec.md) implementable. It defines the immutable
double-entry journal, position lots, settlement obligations, cash flows and accruals,
short borrow, margin, corporate-action entitlements, valuation, materialized projections,
reconciliation, and the exact `CurrentPortfolioView` consumed by plan 10. Accounting is
the economic state authority; it does not decide portfolio targets, invent fills, or
select an execution path.

Focused specifications 01 through 10 remain normative. This plan reuses:

- plan-01 typed IDs, fixed-precision values, explicit rounding, canonical content IDs,
  UTC instants, deterministic ordering, clocks, events, and stable failures;
- plan-02 research-database ownership, modes, leases, transactions, migrations, verified
  copies, event storage, recovery, and prohibition on raw connection access;
- plan-03 exact composite snapshots, source revisions, dual availability evidence,
  provenance, licensing, and immutable source selection;
- plan-04 security/instrument/listing identity, effective terms, venue calendars, session
  identity, and the rule that ticker is never accounting identity;
- plan-05 raw prices, quotes, status, exact selected corporate-action revisions and legs,
  action timing, and the prohibition on inferred missing entitlements or terminal prices;
- plan-06 exact risk-free curves, compounding, day-count conventions, and point-in-time
  rate selection;
- plan-07 dual cutoffs, safety, lineage, bounded managed execution, and opaque custom-input
  behavior; and
- plan-10 desired target weights, current-state capability, point-in-time margin/borrow
  requirements, expected-versus-realized cost separation, and the pure one-decision
  construction boundary.

Plans 12 and 13 own simulation sequencing, target-to-order conversion, orders, fills,
execution costs, and forced-order execution. They invoke the pure accounting transition
kernel defined here and persist its normalized effects in their isolated run transaction.
Plan 14 owns trial orchestration and worker merge. Plan 15 owns immutable result analysis,
performance, attribution, comparison, and export; it cannot revise a journal or mark root.

## 2. Scope

### 2.1 In scope

- One USD accounting book per independent economic portfolio or simulation run
- Immutable, balanced general and memorandum journal postings
- Deterministic source idempotency, reversals, corrections, and replay
- Settled, restricted, receivable, payable, collateral, and accrued cash classifications
- Long and short inventory, FIFO lots, cost basis, realized gain/loss, and position views
- Trade-date fill accounting and effective-dated cash/security settlement
- Initial capital, deposits, withdrawals, interest, financing, fees, and residual handling
- Point-in-time borrow availability/rate capabilities, borrow lots, recalls, and accruals
- Generic margin interface plus a documented simplified US-equity research default
- Margin excess, buying power, breach decisions, and forced-liquidation intents
- Split, stock-dividend, cash-distribution, cash-merger/liquidation, resolved security-
  exchange, spinoff, fractional, short-obligation, and unresolved-action behavior
- Point-in-time mark selection, stale/halted/missing states, NAV, exposure, and valuation
  quality
- Exact `CurrentPortfolioView`, point-in-time `MarginView`, and `BorrowView` adapters
- Rebuildable position, cash, lot, settlement, entitlement, accrual, and valuation snapshots
- Reconciliation, fault recovery, schemas, APIs, events, resources, and acceptance tests

### 2.2 Out of scope

- Tax accounting, tax-lot election, wash sales, jurisdiction-specific reporting, or tax-
  optimized disposal
- Multiple currencies, FX translation, currency hedging, or non-USD managed books
- Options, futures, swaps, fixed-income accrual conventions, derivatives collateral, or
  portfolio margin
- Live brokerage custody, prime-broker reconciliation, regulatory books and records, or
  legal/compliance claims
- Arbitrary manual journal posting through the public API
- Order generation, order lifecycle, fill modeling, queue priority, or execution venue
  behavior
- Broker-specific locate messaging, securities-lending contract negotiation, or recall
  execution
- Automatic action-term inference, appraisal rights, elections, withholding tax, or
  unsupported contingent consideration
- Guaranteed market value when a usable point-in-time mark does not exist
- Performance metric definitions beyond preserving external cash-flow and valuation inputs
- Mutable snapshots as authority or repair by editing prior journal rows

## 3. Normative decisions

1. One `AccountingBook` is an independent USD economic portfolio. It belongs to exactly
   one project and, when simulation-owned, exactly one run identity.
2. The immutable journal is authoritative. Mutable balance, position, lot, settlement,
   accrual, entitlement, and valuation tables are prohibited as independent truth.
3. Every atomic journal transaction balances separately for each posting book and
   commodity: USD debits equal USD credits, and instrument-quantity debits equal credits
   per instrument. Quantity control accounts make external acquisition/disposal explicit.
4. General-book postings affect economic state. Memorandum postings provide balanced cost
   attribution or diagnostics and never affect NAV, cash, inventory, or margin.
5. Journal postings contain nonnegative magnitudes plus explicit debit/credit side. Signed
   quantities are projection outputs, never ambiguous posting inputs.
6. Source application is exactly once by immutable source identity and content. An exact
   retry returns the original result; changed content under the same source key conflicts.
7. Posted history is never updated or deleted. A correction directly reverses/replaces a
   prior transaction only when no later dependency consumed it; otherwise a validated
   dependency-aware correction cascade appends exact compensating transactions or blocks.
8. Trade economics are recognized at fill time. Settlement later reclassifies exact
   receivables/payables and inventory settlement state; it does not recognize the trade a
   second time.
9. Long inventory uses FIFO lot relief in 3.0. Callers cannot elect tax lots. Short lots
   are separately FIFO and never net silently against long lots across books or sleeves.
10. Commission and regulatory charges are general-book expenses. Spread, slippage, delay,
    and impact embedded in the fill price are balanced memorandum attribution only; they
    are never charged to NAV twice.
11. Accounting arithmetic uses plan-01 decimals and explicit quantization. Float values
    cross the boundary only through a recorded conversion policy. A transaction never
    uses a tolerance to claim balance.
12. Cash settlement and external cash movement use the resolved currency quantum and
    rounding mode. Higher-precision accruals remain at the amount profile until payment;
    deterministic residual postings explain the final currency-quantum difference.
13. Settlement uses an effective-dated convention and a pinned settlement-calendar
    policy. Adding calendar days or using the host weekday calendar is forbidden.
14. Use of unsettled proceeds is a separate account-policy capability. It may affect
    buying power but never relabel an unsettled balance as settled.
15. Borrow availability, rate, locate/reservation, open borrow, recall, and return are
    distinct states. A short fill requires the exact borrow authorization selected by the
    execution owner unless an explicitly synthetic unlimited-borrow model is recorded.
16. Margin is a deterministic policy evaluation over exact positions, cash classifications,
    marks, and effective rules. It is not a broker guarantee or a legal compliance engine.
17. A margin breach emits a liquidation intent. Only plan 13 may turn that intent into
    orders/fills; accounting never fabricates a fill or directly deletes a position.
18. Corporate actions apply only an exact plan-05 selected revision/leg set that was
    available under the simulation's information policy. Missing, ambiguous, cancelled,
    unsafe, or unresolved terms cannot be guessed.
19. Entitlement capture, effective transformation, and payment are separate journal or
    lifecycle instants. Record, ex, effective, and payment dates are not collapsed.
20. Position accounting may retain fractional quantities created by exact actions even
    when an execution policy allows only whole shares. Cash in lieu requires explicit
    terms or a later exact payment observation.
21. Valuation is a point-in-time projection from journal state plus exact marks. Missing
    prices never become zero; unlimited forward-fill is forbidden; a halt is known only
    from selected status data.
22. NAV includes every economic cash classification, receivable/payable, accrual, and
    signed security market value exactly once. Restricted cash and short-sale collateral
    are classifications, not extra assets.
23. Materialized accounting and valuation snapshots are immutable caches identified by
    journal prefix and input roots. Rebuild must reproduce their content exactly at the
    stored precision.
24. A `CurrentPortfolioView` is emitted only from a reconciled state and exact valuation.
    It distinguishes absent from unknown instruments and retains unsettled, restricted,
    margin, borrow, mark-quality, logical-availability, and lineage evidence.
25. Standalone accounting writes use one research-database transaction. Simulation-time
    accounting is a pure transition kernel whose owning run transaction persists journal,
    target, order/fill, and result effects atomically without a second research writer.
26. Custom policies emit validated typed decisions. They never receive a journal writer,
    mutable projection, raw database connection, or permission to alter balances.
27. Completed transactions, source applications, snapshots, reconciliations, views, and
    findings are append-only and bounded. Exact retry verifies normalized rows and roots.
28. Accounting accepts research-derived intent only through plan-10 target and plan-12/13
    order/fill adapters. Direct labels, retrospective roots, unreleased fits, opaque SQL/
    workspace values, or arbitrary strategy numerics cannot become journal sources. Run
    safety/lineage is folded into every resulting state and cannot be cleansed by posting.

## 4. Identity, enums, public values, and limits

### 4.1 Typed IDs

This plan adds these plan-01 typed UUID identities:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `AccountingBookId` | `accounting_book` | One independent USD economic portfolio |
| `JournalAccountId` | `journal_account` | One immutable chart account/dimension tuple |
| `JournalTransactionId` | `journal_transaction` | One atomic balanced journal transaction |
| `InventoryLotId` | `inventory_lot` | One acquired long or opened short inventory lot |
| `SettlementObligationId` | `settlement_obligation` | One cash/security settlement obligation |
| `CashFlowId` | `cash_flow` | One external capital contribution or withdrawal |
| `AccrualId` | `accrual` | One interest, financing, borrow, or registered time accrual |
| `BorrowAuthorizationId` | `borrow_authorization` | One exact locate/synthetic authorization |
| `BorrowLotId` | `borrow_lot` | One opened and subsequently reduced borrow lot |
| `CorporateActionApplicationId` | `corporate_action_application` | One selected action revision applied to one book |
| `EntitlementId` | `entitlement` | One book/action/lot economic entitlement or obligation |
| `ValuationId` | `valuation` | One exact mark-to-market occurrence |
| `PortfolioStateId` | `portfolio_state` | One reconciled journal-prefix state and valuation |
| `AccountingSnapshotId` | `accounting_snapshot` | One immutable cached journal projection prefix |
| `ReconciliationId` | `reconciliation` | One immutable rebuild/reconciliation occurrence |
| `MarginEvaluationId` | `margin_evaluation` | One point-in-time margin calculation |
| `LiquidationIntentId` | `liquidation_intent` | One deterministic response to a margin/borrow breach |

IDs identify entities or occurrences, not content. Each immutable definition, request,
journal transaction, projection, mark set, state, and output also carries a plan-01
`ContentId`. A state identity never derives from a ticker, mutable book name, row number,
or current wall clock.

Chart, lot, settlement, cash-use, accrual, borrow, margin, liquidation, corporate-action,
valuation, and precision policies use an exact qualified name, semantic version, and
definition `ContentId`; they do not allocate an entity ID merely to wrap configuration.
Every `*PolicyRef` resolves that triple before execution, and persisted occurrences retain
the content ID rather than a moving name/version lookup.

### 4.2 Stable enums

| Enum | Initial values |
| --- | --- |
| `PostingBook` | `general`, `memorandum` |
| `PostingDimension` | `money`, `quantity` |
| `PostingSide` | `debit`, `credit` |
| `AccountNormalSide` | `debit`, `credit` |
| `AccountKind` | `settled_cash`, `restricted_cash`, `cash_receivable`, `cash_payable`, `accrued_receivable`, `accrued_payable`, `long_cost`, `short_liability`, `long_quantity_unsettled`, `long_quantity_settled`, `short_quantity_unsettled`, `short_quantity_settled`, `quantity_control`, `action_quantity_control`, `realized_gain`, `realized_loss`, `dividend_income`, `manufactured_dividend_expense`, `commission_expense`, `regulatory_fee_expense`, `borrow_expense`, `financing_expense`, `interest_income`, `rounding_gain`, `rounding_loss`, `capital_contribution`, `capital_withdrawal`, `corporate_action_equity`, `memorandum_cost`, `memorandum_offset` |
| `LotDirection` | `long`, `short` |
| `LotState` | `open`, `closed` |
| `SettlementAssetKind` | `cash`, `security` |
| `SettlementState` | `scheduled`, `settled`, `failed`, `cancelled` |
| `CashAvailability` | `settled_available`, `settled_restricted`, `receivable`, `payable`, `accrued` |
| `AccrualKind` | `positive_cash_interest`, `negative_cash_financing`, `borrow_fee`, `other_registered` |
| `BorrowAuthorizationKind` | `located`, `synthetic_unlimited`, `preborrowed` |
| `BorrowState` | `authorized`, `partially_used`, `used`, `expired`, `cancelled`, `recalled`, `returned` |
| `MarginAccountKind` | `cash`, `simplified_us_reg_t`, `custom_registered` |
| `MarginState` | `sufficient`, `initial_deficit`, `maintenance_deficit`, `mark_unavailable`, `rule_unavailable` |
| `MarkKind` | `quote_mid`, `quote_side`, `trade`, `bar_open_execution_outcome`, `bar_close`, `action_cash_value`, `manual_fixture` |
| `MarkState` | `selected`, `stale_allowed`, `missing`, `stale_rejected`, `halted_with_mark`, `halted_without_mark`, `invalid`, `unsupported` |
| `ValuationState` | `complete`, `complete_with_stale_marks`, `incomplete` |
| `EntitlementState` | `pending`, `effective`, `payable`, `paid`, `resolved`, `cancelled`, `blocked_unresolved` |
| `ActionApplicationState` | `applied`, `no_position`, `cancelled`, `blocked`, `reversed` |
| `ReconciliationState` | `matched`, `mismatched`, `blocked` |

Enum strings are persisted exactly. Adding a value requires a migration and compatibility
review. Provider/broker strings do not become enum values automatically.

### 4.3 Public immutable values

Normative value contracts include:

```python no-run
@dataclass(frozen=True, slots=True)
class AccountingSourceRef:
    source_kind: QualifiedName
    source_id: EntityId
    source_version: int
    source_content_id: ContentId
    event_at: datetime
    logical_available_at: datetime


@dataclass(frozen=True, slots=True)
class FillAccountingFacts:
    source: AccountingSourceRef
    instrument_id: InstrumentId
    side: FillSide
    quantity: NonNegativeQuantity
    price: Price
    commission: Money
    regulatory_fees: Money
    trade_session: SessionKey
    settlement_policy: SettlementPolicyRef
    borrow_authorization: BorrowAuthorizationRef | None
    execution_attribution: ExecutionAttribution | None


@dataclass(frozen=True, slots=True)
class JournalTransaction:
    transaction_id: JournalTransactionId
    book_id: AccountingBookId
    book_sequence: int
    source: AccountingSourceRef
    source_transaction_ordinal: int
    effective_at: datetime
    recorded_at: datetime
    postings: tuple[JournalPosting, ...]
    reversal_of: JournalTransactionId | None
    content_id: ContentId
```

The public policy, opening, schedule, and write-request graph is:

```python no-run
@dataclass(frozen=True, slots=True)
class AccountingPolicyRef:
    name: QualifiedName
    version: int
    definition_content_id: ContentId

SettlementPolicyRef = AccountingPolicyRef
LotReliefPolicyRef = AccountingPolicyRef
MarkPolicyRef = AccountingPolicyRef
AccrualPolicyRef = AccountingPolicyRef
FinancingPolicyRef = AccountingPolicyRef
MarginPolicyRef = AccountingPolicyRef
CorporateActionElectionPolicyRef = AccountingPolicyRef
RoundingPolicyRef = AccountingPolicyRef
ValuationPolicyRef = MarkPolicyRef

@dataclass(frozen=True, slots=True)
class BorrowAuthorizationRef:
    borrow_authorization_id: BorrowAuthorizationId
    authorization_content_id: ContentId
    available_quantity: Quantity
    logical_available_at: datetime

@dataclass(frozen=True, slots=True)
class SettlementPolicyDefinition:
    name: QualifiedName
    version: int
    cycle_sessions: int
    calendar_policy: QualifiedName
    failed_settlement: Literal["retain_failed", "retry_on_named_session"]

@dataclass(frozen=True, slots=True)
class LotReliefPolicyDefinition:
    name: QualifiedName
    version: int
    method: Literal["fifo", "lifo", "specific_id"]

@dataclass(frozen=True, slots=True)
class MarkPolicyDefinition:
    name: QualifiedName
    version: int
    source_order: tuple[Literal["quote_mid", "trade", "bar_close", "bar_open_execution_outcome"], ...]
    stale_after: Duration
    missing: Literal["unavailable", "fail"]

@dataclass(frozen=True, slots=True)
class AccrualPolicyDefinition:
    name: QualifiedName
    version: int
    day_count: DayCountKind
    boundary_policy: Literal["rate_principal_and_period"]
    rounding: RoundingPolicyRef

@dataclass(frozen=True, slots=True)
class RegisteredRateSourceRef:
    name: QualifiedName
    version: int
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class FinancingPolicyDefinition:
    name: QualifiedName
    version: int
    rate_source: RiskFreeCurveRef | RegisteredRateSourceRef
    spread_bps: Decimal
    collateral_policy: QualifiedName

@dataclass(frozen=True, slots=True)
class MarginPolicyDefinition:
    name: QualifiedName
    version: int
    account_kind: Literal["cash", "simplified_us_reg_t", "custom_registered"]
    marginability_policy: QualifiedName
    rule_content_id: ContentId

@dataclass(frozen=True, slots=True)
class CorporateActionElectionPolicyDefinition:
    name: QualifiedName
    version: int
    default_election: Literal["cash", "security", "issuer_default", "block_unresolved"]

@dataclass(frozen=True, slots=True)
class RoundingPolicyDefinition:
    name: QualifiedName
    version: int
    money_mode: Literal["half_even", "half_up"]
    quantity_mode: Literal["down", "nearest_half_even"]

AccountingPolicyDefinition = (
    SettlementPolicyDefinition | LotReliefPolicyDefinition | MarkPolicyDefinition
    | AccrualPolicyDefinition | FinancingPolicyDefinition | MarginPolicyDefinition
    | CorporateActionElectionPolicyDefinition | RoundingPolicyDefinition
)

@dataclass(frozen=True, slots=True)
class AccountingPolicyBundleRef:
    lot_relief: LotReliefPolicyRef
    settlement: SettlementPolicyRef
    marks: MarkPolicyRef
    accruals: AccrualPolicyRef
    financing_and_borrow: FinancingPolicyRef
    margin: MarginPolicyRef
    corporate_action_elections: CorporateActionElectionPolicyRef
    rounding: RoundingPolicyRef

@dataclass(frozen=True, slots=True)
class OpeningPosition:
    instrument_id: InstrumentId
    quantity: Quantity
    unit_cost: Price
    acquired_at: datetime
    settled: bool

@dataclass(frozen=True, slots=True)
class AccountingOpeningRef:
    effective_at: datetime
    base_currency: Currency
    cash: Money
    positions: tuple[OpeningPosition, ...]
    source_content_id: ContentId

@dataclass(frozen=True, slots=True)
class ScheduledCashFlow:
    ordinal: int
    effective_at: datetime
    amount: Money
    kind: Literal["deposit", "withdrawal"]
    source_content_id: ContentId

@dataclass(frozen=True, slots=True)
class CashFlowScheduleRef:
    flows: tuple[ScheduledCashFlow, ...]
    schedule_content_id: ContentId

@dataclass(frozen=True, slots=True)
class BookCreateRequest:
    owner_run_id: EntityId | None
    owner_strategy_id: EntityId | None
    account_kind: Literal["cash", "simplified_us_reg_t", "custom_registered"]
    fixture_kind: Literal["endogenous", "opening_fixture", "external_path"]
    opening: AccountingOpeningRef
    policies: AccountingPolicyBundleRef
    limits: AccountingLimits

@dataclass(frozen=True, slots=True)
class CashFlowApplyRequest:
    source: AccountingSourceRef
    amount: Money
    kind: Literal["deposit", "withdrawal"]

@dataclass(frozen=True, slots=True)
class AccrualApplyRequest:
    source: AccountingSourceRef
    policy: AccrualPolicyRef
    interval: TimeInterval
    basis_content_id: ContentId

@dataclass(frozen=True, slots=True)
class CorporateActionApplyRequest:
    source: AccountingSourceRef
    action_revision_id: CorporateActionRevisionId
    election: CorporateActionElectionPolicyRef
    effective_at: datetime

@dataclass(frozen=True, slots=True)
class ValuationRequest:
    book_id: AccountingBookId
    valued_at: datetime
    marks: MarkPolicyRef
    instrument_ids: tuple[InstrumentId, ...]
    market_context: CompositeAsOfContext

@dataclass(frozen=True, slots=True)
class ReconciliationRequest:
    book_id: AccountingBookId
    inclusive_book_sequence: int
    checks: tuple[QualifiedName, ...]
    tolerance: Money

@dataclass(frozen=True, slots=True)
class SettlementTransitionRequest:
    settlement_obligation_id: SettlementObligationId
    transition: Literal["settled", "failed", "cancelled"]
    effective_at: datetime
    logical_available_at: datetime
    source: AccountingSourceRef
    reason_code: str

@dataclass(frozen=True, slots=True)
class StateCreateRequest:
    book_id: AccountingBookId
    valuation_id: ValuationId
    decision_at: datetime
    asset_manifest_content_id: ContentId
    margin_evaluation_id: MarginEvaluationId
    borrow_manifest_content_id: ContentId | None
```

The built-in bundle `persistra.accounting.us_equity_research@1` resolves FIFO lot relief,
the Plan-04 instrument settlement schedule,
`persistra.accrual.actual_elapsed_boundaries@1` accrual timing, the
Plan-11 causal mark policy, `simplified_us_reg_t_v1` margin, explicit borrow/financing
rates, default corporate-action elections, and Plan-01 half-even quantization. Each member
also registers independently under `(name, version, kind)` with canonical definition bytes;
kind mismatch, unknown version, or unequal duplicate content raises
`AccountingPolicyRegistrationError`.
`accounting.policies.register(AccountingPolicyDefinition)` returns the matching typed ref;
`.resolve(ref)` checks kind/version/content. `apply_settlement` accepts only
`SettlementTransitionRequest`, and `states.create` accepts only `StateCreateRequest` after
verifying valuation/book/prefix/time/asset/margin/borrow compatibility. Invalid variants,
nonpositive cycles/durations, unavailable source refs, illegal transitions, and state-prefix
mismatches map to `AccountingPolicyRegistrationError`, `AccountingRequestError`,
`SettlementTransitionError`, or `PortfolioStateError` before persistence.

`persistra.accrual.actual_elapsed_boundaries@1` partitions at registered rate, principal,
and accrual boundaries, uses exact elapsed UTC time and the declared §10.2 day-count rule,
and posts only through the pure accrual kernel. It is unrelated to Plan-15
`persistra.flow_timing.pre_flow_valuation@1`, which partitions performance returns around
external flows.

Openings require USD, nonnegative cash, unique instruments, nonzero representable quantities,
positive representable costs, and `acquired_at <= effective_at`. Flow ordinals are gap-free,
instants nondecreasing, currencies USD, and flow amounts are strictly positive magnitudes;
`kind` supplies the posting sign (deposit debit-cash, withdrawal credit-cash), matching the
positive `accounting.cash_flows.amount` storage contract. Endogenous fixtures require a run
owner; external paths forbid one; a strategy owner, when present, requires a run owner.
Request IDs/refs resolve exactly; intervals are nonempty; instrument
lists/checks are unique and bounded. Field/variant errors raise `AccountingRequestError`,
missing policy/input facts return the specified structured unavailable state, and invariant
or posting failures raise `AccountingInvariantError`. No request accepts raw postings,
callbacks, arbitrary mappings, or physical names.

`FillSide` is a forward protocol whose exact order-side enum is owned by plan 13. The
accounting adapter maps only validated `buy`, `sell`, `sell_short`, and `buy_to_cover`
facts; it does not accept an arbitrary string or infer whether a sale opens a short.

Definitions are frozen, slotted, canonically serialized dataclasses. Typed references
resolve before execution and become exact IDs/versions/content roots. No public model
contains a physical relation name, mutable mapping, callback object, or unbounded payload.

### 4.4 Resource limits

```python no-run
@dataclass(frozen=True, slots=True)
class AccountingLimits:
    max_books_per_operation: int = 1
    max_transactions: int = 10_000_000
    max_postings_per_transaction: int = 1_000
    max_dependency_edges: int = 20_000_000
    max_open_lots: int = 2_000_000
    max_open_settlements: int = 2_000_000
    max_entitlements_per_action: int = 2_000_000
    max_positions_per_state: int = 1_000_000
    max_marks_per_valuation: int = 1_000_000
    max_rebuild_transactions: int = 10_000_000
    max_frame_rows: int = 2_000_000
    partition_rows: int = 100_000
    timeout: Duration = Duration(1_800_000_000)
```

Values are positive. Project memory, temporary-storage, and wall-time ceilings may be
lower. Limits enter operation identity. Breach fails before publication; it never drops
postings, positions, lots, marks, or reconciliation checks.

## 5. Package, project, database, and lifecycle ownership

The implementation boundary is:

```text
src/persistra/accounting/
├── __init__.py
├── books.py
├── accounts.py
├── journal.py
├── postings.py
├── lots.py
├── settlement.py
├── cash.py
├── accruals.py
├── borrow.py
├── margin.py
├── actions.py
├── valuation.py
├── state.py
├── reconciliation.py
├── policies.py
├── repositories.py
└── kernel.py
```

Standalone book creation, source application, snapshot materialization, and reconciliation
require `ProjectMode.RESEARCH_WRITE`. They write only the exclusively leased research
database while holding shared leases on exact market databases required by marks, actions,
calendars, or rates. Read-only repositories expose bounded immutable handles.

Research-role migrations add `accounting` for definitions, books, transactions, lifecycle
metadata, snapshots, and findings, and `journal_data` for controlled postings, lot links,
state rows, marks, and projection rows. Shared lineage/safety evidence remains in plan-07
relations. Lifecycle envelopes remain in `_persistra.domain_events`. Neither schema is a
user workspace, and physical controlled names never enter public APIs.

Plans 12 and 13 may create the same migration-owned schema in an isolated run database.
Their simulation transaction owns accounting persistence together with run target/order/
fill evidence. It calls an in-memory pure kernel and does not open the project's research
database for each event. Plan 14 later validates and transactionally merges complete run
files; plan 15 defines final result ownership. This plan does not claim cross-file ACID.

Book state is append-only. A transaction publishes normalized transaction, postings,
source application, lot/settlement/action lifecycle records, content roots, and domain
events in one transaction. Infrastructure or invariant failure publishes nothing. A
business outcome such as blocked action, missing mark, or margin deficit may publish an
immutable diagnostic occurrence when its contract says the outcome itself is evidence.
Each state-changing command captures one `recorded_at` from the injected plan-01 clock;
all rows and events in that command share it while retaining their distinct effective and
logical-availability instants.

## 6. Journal model and accounting convention

### 6.1 Books and chart of accounts

An `AccountingBook` pins:

- project and optional run/strategy owner;
- `currency='USD'` and account kind;
- chart, lot-relief, settlement, cash-use, precision, valuation, margin, borrow, corporate-
  action, and accrual policy roots;
- opening source/snapshot/cutoff and logical availability;
- code/environment/schema identity and limits; and
- whether it is a safe endogenous book, a one-decision opening fixture, or an opaque
  external path fixture.

One book has exactly one immutable chart version. Accounts are deterministically selected
from registered account kind plus dimensions such as instrument, lot, settlement date,
or accrual kind. Account IDs are allocated once; account key/content prevents two IDs for
the same tuple. Friendly labels are display-only.

Debit-normal general accounts are assets and expenses. Credit-normal accounts are
liabilities, income, and contributed capital/equity. A projected account balance is:

```text
debit-normal balance  = sum(debits) - sum(credits)
credit-normal balance = sum(credits) - sum(debits)
```

Balances may become negative only when the account policy explicitly permits it. A
negative settled-cash balance is permitted only for a margin/financing book and is shown
as borrowing; a cash account rejects it before commit.

### 6.2 Commodity-balanced postings

Each posting has one and only one dimension:

- a money posting has USD `amount`, null quantity/instrument commodity; or
- a quantity posting has positive `quantity`, exact `instrument_id`, and null amount/
  currency commodity.

For every transaction and posting book:

```text
sum(USD debit amounts) = sum(USD credit amounts)

for each instrument:
    sum(quantity debits) = sum(quantity credits)
```

Both are exact decimal equalities after explicit boundary quantization. A transaction may
contain only money, only quantity, or both. Each nonempty `(posting_book, dimension,
commodity)` group has at least one debit and one credit. Zero postings are forbidden.

`quantity_control` is the explicit contra account for inventory entering or leaving the
book through fills/opening fixtures. `action_quantity_control` is the corresponding
corporate-action contra. Both are excluded from owned-position projections but retained in
reconciliation; quantity never appears from an unbalanced mutation.

General and memorandum groups balance independently. Memorandum values use the same fixed
precision and source roots but are excluded from the general trial balance and every
economic projection.

### 6.3 Corrections and reversals

A reversal contains the same posting book, dimensions, commodities, accounts, and exact
magnitudes as its target with every side inverted. It links `reversal_of`, uses a new
source application, and becomes effective at the correction's permitted effective time;
it never backdates knowledge. A replacement is a separate transaction linked by the same
correlation ID.

One correction command validates that the target has not already been fully reversed,
posts reversal and replacement with consecutive book sequences, and emits their events in
one database transaction. Partial ad hoc reversal is not supported. Legitimate lifecycle
reductions such as a partial lot close or settlement are new business transactions, not
corrections.

Direct reversal is legal only when no later lot relief, settlement, borrow use/return,
accrual principal, entitlement, action transformation, or other source application depends
on the target and replay proves every account/balance policy remains valid (including
fungible cash). The journal maintains a complete application-dependency manifest for this
check. Valuations, states, and snapshots are immutable derived dependents: they are not
reversed, but their old roots remain historical and any new state uses the corrected
prefix.

When economic dependents exist, a registered correction planner replays the affected
dependency subgraph without changing its business-event order and emits an atomic cascade:

- a price/fee correction adjusts remaining carrying basis, each already relieved basis,
  realized gain/loss, receivable/payable, and settled-cash difference exactly;
- a quantity correction reallocates FIFO relief, settlement, borrow, and action effects
  only when the corrected quantity can satisfy every later disposal/obligation; and
- an effective-time/instrument/side correction requires a separately supported full
  restatement capability and otherwise blocks.

Every compensating transaction names the corrected source, affected application, prior and
replacement calculation roots, and source transaction ordinal. The cascade balances and
reconciles as a whole at the correction's logical-availability instant. It never backdates
the revised knowledge, erases the original source, silently changes an old state, or posts
an unexplained net plug. If dependency closure is incomplete or the corrected economics
cannot represent the observed later events, the correction publishes no journal change and
returns `accounting.correction_dependency_blocked`.

## 7. Core journal schema

```sql
CREATE TABLE accounting.books (
    accounting_book_id UUID PRIMARY KEY,
    owner_project_id UUID NOT NULL,
    owner_run_id UUID,
    owner_strategy_id UUID,
    currency VARCHAR NOT NULL CHECK (currency = 'USD'),
    account_kind VARCHAR NOT NULL CHECK (
        account_kind IN ('cash', 'simplified_us_reg_t', 'custom_registered')
    ),
    opening_source_content_id VARCHAR NOT NULL,
    chart_content_id VARCHAR NOT NULL,
    policy_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    fixture_kind VARCHAR NOT NULL CHECK (
        fixture_kind IN ('endogenous', 'opening_fixture', 'external_path')
    ),
    logical_available_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    book_content_id VARCHAR NOT NULL UNIQUE
);

CREATE TABLE accounting.journal_accounts (
    journal_account_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    account_kind VARCHAR NOT NULL,
    normal_side VARCHAR NOT NULL CHECK (normal_side IN ('debit', 'credit')),
    posting_dimension VARCHAR NOT NULL CHECK (
        posting_dimension IN ('money', 'quantity')
    ),
    currency VARCHAR,
    instrument_id UUID,
    inventory_lot_id UUID,
    dimension_content_id VARCHAR NOT NULL,
    account_content_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (accounting_book_id, account_content_id),
    CHECK (
        (posting_dimension = 'money' AND currency = 'USD')
        OR
        (posting_dimension = 'quantity'
            AND currency IS NULL
            AND instrument_id IS NOT NULL)
    ),
    CHECK (inventory_lot_id IS NULL OR instrument_id IS NOT NULL)
);

CREATE TABLE accounting.journal_transactions (
    journal_transaction_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    book_sequence BIGINT NOT NULL CHECK (book_sequence >= 1),
    source_kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    source_transaction_ordinal INTEGER NOT NULL CHECK (
        source_transaction_ordinal >= 1
    ),
    source_content_id VARCHAR NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    reversal_of_journal_transaction_id UUID,
    correlation_id UUID,
    policy_manifest_content_id VARCHAR NOT NULL,
    posting_manifest_content_id VARCHAR NOT NULL,
    transaction_content_id VARCHAR NOT NULL,
    UNIQUE (accounting_book_id, book_sequence),
    UNIQUE (
        accounting_book_id, source_kind, source_id, source_version,
        source_transaction_ordinal
    ),
    UNIQUE (accounting_book_id, transaction_content_id)
);

CREATE TABLE journal_data.journal_postings (
    journal_transaction_id UUID NOT NULL,
    posting_ordinal INTEGER NOT NULL CHECK (posting_ordinal >= 1),
    posting_book VARCHAR NOT NULL CHECK (
        posting_book IN ('general', 'memorandum')
    ),
    journal_account_id UUID NOT NULL,
    posting_dimension VARCHAR NOT NULL CHECK (
        posting_dimension IN ('money', 'quantity')
    ),
    side VARCHAR NOT NULL CHECK (side IN ('debit', 'credit')),
    amount DECIMAL(38, 12),
    currency VARCHAR,
    quantity DECIMAL(38, 12),
    instrument_id UUID,
    component_kind VARCHAR NOT NULL,
    posting_content_id VARCHAR NOT NULL,
    PRIMARY KEY (journal_transaction_id, posting_ordinal),
    CHECK (
        (posting_dimension = 'money'
            AND amount IS NOT NULL
            AND amount > 0
            AND currency = 'USD'
            AND quantity IS NULL
            AND instrument_id IS NULL)
        OR
        (posting_dimension = 'quantity'
            AND quantity IS NOT NULL
            AND quantity > 0
            AND instrument_id IS NOT NULL
            AND amount IS NULL
            AND currency IS NULL)
    )
);

CREATE TABLE accounting.source_applications (
    accounting_book_id UUID NOT NULL,
    source_kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    source_content_id VARCHAR NOT NULL,
    first_book_sequence BIGINT NOT NULL CHECK (first_book_sequence >= 1),
    last_book_sequence BIGINT NOT NULL CHECK (last_book_sequence >= first_book_sequence),
    dependency_manifest_content_id VARCHAR NOT NULL,
    result_content_id VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (accounting_book_id, source_kind, source_id, source_version)
);

CREATE TABLE accounting.application_dependencies (
    accounting_book_id UUID NOT NULL,
    source_kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    dependency_ordinal INTEGER NOT NULL CHECK (dependency_ordinal >= 1),
    depends_on_source_kind VARCHAR NOT NULL,
    depends_on_source_id UUID NOT NULL,
    depends_on_source_version INTEGER NOT NULL CHECK (
        depends_on_source_version >= 1
    ),
    relation_kind VARCHAR NOT NULL CHECK (
        relation_kind IN (
            'cash_balance', 'lot_relief', 'settlement', 'borrow', 'accrual_principal',
            'corporate_action', 'entitlement', 'correction'
        )
    ),
    dependency_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        accounting_book_id, source_kind, source_id, source_version,
        dependency_ordinal
    )
);
```

The writer validates account kind, normal side, dimensions, posting-account match,
minimum cardinality, exact commodity balance, contiguous posting and per-source transaction
ordinals, consecutive book sequences, source-application uniqueness, reversal legality,
and every manifest before insertion.
Database checks alone are not claimed to enforce cross-row balance.

`source_kind` is a registered qualified name, not arbitrary user text. `source_id` may be
a plan-11 ID or a forward plan-12/13 run/fill/event ID. The registered source codec proves
its typed kind and content before accounting can apply it.

## 8. Lots, positions, and realized P&L

### 8.1 Lot authority

A long acquisition or short opening creates one immutable lot master per fill allocation.
The lot records opening instrument, direction, source fill, trade/settlement dates, opened
quantity, monetary carrying basis, per-unit execution price, direct capitalized amount,
borrow link for shorts, and roots for instrument terms and precision. Quantity and carrying
basis remain authoritative in journal postings; the master supplies immutable dimensions.

FIFO means ascending `(opened_at, source sequence, InventoryLotId)` among eligible open
lots. UUID is only the final deterministic tie-breaker. A close cannot choose a different
lot. Corporate-action descendants retain ancestry to the source lot and preserve order by
the original opening key.

```sql
CREATE TABLE accounting.inventory_lots (
    inventory_lot_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    direction VARCHAR NOT NULL CHECK (direction IN ('long', 'short')),
    opening_journal_transaction_id UUID NOT NULL,
    source_fill_kind VARCHAR NOT NULL,
    source_fill_id UUID NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    trade_session_date DATE NOT NULL,
    contractual_settlement_date DATE NOT NULL,
    opened_quantity DECIMAL(38, 12) NOT NULL CHECK (opened_quantity > 0),
    opened_carrying_amount DECIMAL(38, 12) NOT NULL CHECK (
        opened_carrying_amount > 0
    ),
    execution_price DECIMAL(38, 12) NOT NULL CHECK (execution_price > 0),
    borrow_lot_id UUID,
    parent_inventory_lot_id UUID,
    terms_content_id VARCHAR NOT NULL,
    lot_content_id VARCHAR NOT NULL UNIQUE,
    CHECK ((direction = 'short') = (borrow_lot_id IS NOT NULL))
);

CREATE TABLE accounting.lot_relief_applications (
    closing_journal_transaction_id UUID NOT NULL,
    relief_ordinal INTEGER NOT NULL CHECK (relief_ordinal >= 1),
    inventory_lot_id UUID NOT NULL,
    relieved_quantity DECIMAL(38, 12) NOT NULL CHECK (relieved_quantity > 0),
    relieved_carrying_amount DECIMAL(38, 12) NOT NULL CHECK (
        relieved_carrying_amount > 0
    ),
    proceeds_or_cover_amount DECIMAL(38, 12) NOT NULL CHECK (
        proceeds_or_cover_amount > 0
    ),
    realized_gain_amount DECIMAL(38, 12) NOT NULL DEFAULT 0,
    realized_loss_amount DECIMAL(38, 12) NOT NULL DEFAULT 0,
    relief_content_id VARCHAR NOT NULL,
    PRIMARY KEY (closing_journal_transaction_id, relief_ordinal),
    CHECK (
        (realized_gain_amount = 0 OR realized_loss_amount = 0)
        AND realized_gain_amount >= 0
        AND realized_loss_amount >= 0
    )
);
```

Open quantity and remaining carrying basis are exact journal projections through a book
sequence. `LotState` is derived: remaining quantity zero is closed. There is no mutable
status column. A lot cannot cross through zero; a fill that closes a long and opens a
short is split into deterministic close and open transactions/allocations by plan 13.

### 8.2 Position projection

For instrument `i` at journal prefix `s`:

```text
long_quantity_i  = sum(debits - credits across settled/unsettled long accounts)
short_quantity_i = sum(credits - debits across settled/unsettled short accounts)
net_quantity_i   = long_quantity_i - short_quantity_i

long_cost_i      = debits(long_cost_i) - credits(long_cost_i)
short_liability_i = credits(short_liability_i) - debits(short_liability_i)
```

Long and short quantity must each be nonnegative. Ordinary books cannot hold both for the
same instrument after one atomic event; an explicitly registered sleeve/subledger model
would require a new dimension. Position rows include zero only when an audit request asks
for closed history; current views omit known-zero positions and distinguish them from
unknown instruments through their complete asset manifest.

### 8.3 Fill posting templates

Let `N` be fill price times quantity at the execution quantum, `B` the FIFO relieved basis,
`F` commission plus regulatory fees, and all values be USD.

**Open/increase long:** debit long cost `N`; credit trade cash payable `N`; debit long
unsettled quantity and credit quantity control for filled shares. Commission/regulatory fees debit
their expense accounts and credit the same payable. A configured capitalized-fee policy is
not in the initial surface.

**Close/reduce long:** debit trade cash receivable `N`; credit long cost `B`; credit
realized gain `N-B` when positive or debit realized loss `B-N` when negative. Credit long
settled/unsettled quantity according to the delivered lots and debit quantity control. Fees debit expense and credit receivable, reducing
the net receivable while remaining separately auditable.

**Open/increase short:** debit trade cash receivable `N`; credit short liability `N`;
debit quantity control and credit short unsettled quantity. The settlement/collateral policy later
reclassifies received proceeds to restricted cash. Fees debit expense and credit
receivable. The exact borrow authorization is consumed atomically.

**Close/reduce short:** debit short liability for relieved carrying amount `B`; debit
realized loss `N-B` when positive or credit realized gain `B-N` when positive; credit trade
cash payable `N`. Debit short settled/unsettled quantity according to the delivered lots
and credit quantity control. Fees debit expense and
credit payable.

Every template expands to explicit postings; formulas do not authorize net journal rows.
Receivable/payable signs are validated so a fee greater than gross proceeds either creates
a separate payable or rejects under the registered netting policy—it cannot create a
negative posting.

Execution attribution embedded in fill price uses the memorandum book:

- debit `memorandum_cost` and credit `memorandum_offset` for adverse spread, slippage,
  delay, or impact;
- reverse sides for favorable attribution where the registered model permits it; and
- exact component/model/reference-price roots from plan 13.

Memorandum totals reconcile to execution diagnostics but never enter realized P&L or NAV.

### 8.4 Opening fixtures

An opening fixture is converted once into balanced opening transactions; it is never a
mutable seed balance. Cash debits settled/restricted cash and credits capital contribution.
A long position debits long cost, credits opening capital, debits settled long quantity,
and credits quantity control. A short position debits restricted cash for the carried
short-sale proceeds, credits short liability, debits quantity control, and credits settled
short quantity; it additionally requires a synthetic/open borrow fixture. Any separate
margin collateral is contributed cash and then reclassified explicitly. Opening capital
is the balancing historical-equity account for long basis, not an external cash flow unless
cash actually entered at the opening instant.

Every position requires exact instrument, signed quantity, carrying basis, acquisition
instant/order, settled state, and—when short—borrow/collateral policy. If only current
market value is known, the fixture may use a declared mark-to-basis approximation but is
opaque and cannot claim realized-P&L history. Missing basis, instrument, settlement, or
borrow facts reject. The opening manifest, conversion policy, and all generated lots/
postings are exact identity.

## 9. Settlement

### 9.1 Effective-dated convention

A `SettlementPolicy` declares instrument scope, trade-date resolver, number of settlement
business days, exact plan-04 settlement-calendar profile/version, holiday treatment,
contractual boundary instant, cash/security legs, fail handling, unsettled-proceeds usage,
source basis, version, and effective interval. The built-in uses
`persistra.calendar.us_equity_settlement`; that profile already materializes the reviewed
securities/payment-system eligible-day intersection, so runtime code never intersects a
venue calendar with host/federal weekdays. The policy selected by trade instant and exact
instrument terms is stored on the obligation.

The built-in US-listed-equity research schedule begins at the first covered T+3 fixture:

| Trade-date interval | Standard cycle |
| --- | --- |
| 1995-06-07 through 2017-09-04 | T+3 |
| 2017-09-05 through 2024-05-27 | T+2 |
| from 2024-05-28 | T+1 |

The T+3 start is grounded in the
[SEC May 1995 implementation notice](https://www.sec.gov/news/digest/1995/dig051295.pdf),
the T+2 boundary in the
[SEC 2017 settlement-cycle rule](https://www.sec.gov/rules-regulations/2017/03/securities-transaction-settlement-cycle),
and the T+1 compliance date in the
[SEC T+1 guidance](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq). Dates before
1995-06-07 are unavailable under this built-in rather than incorrectly labeled T+3; a
reviewed explicit historical policy may cover them. The schedule remains a versioned
research default, not a claim that every transaction or instrument followed the standard.
Exceptions require an explicit policy. A settlement date is found by advancing eligible
dates on the pinned settlement-calendar schedule; the trade date is day zero.

### 9.2 Obligations and transitions

Each fill creates cash and security obligations sharing one settlement group. Cash amount
is the exact receivable/payable after direct cash charges under the configured netting
policy. Security quantity links exact lots and remains economically owned/owed from trade
date while its settled/unsettled classification is projected separately.

```sql
CREATE TABLE accounting.settlement_obligations (
    settlement_obligation_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    source_journal_transaction_id UUID NOT NULL,
    settlement_group_content_id VARCHAR NOT NULL,
    asset_kind VARCHAR NOT NULL CHECK (asset_kind IN ('cash', 'security')),
    direction VARCHAR NOT NULL CHECK (direction IN ('receive', 'deliver')),
    currency VARCHAR,
    instrument_id UUID,
    amount DECIMAL(38, 12),
    quantity DECIMAL(38, 12),
    trade_session_date DATE NOT NULL,
    contractual_settlement_date DATE NOT NULL,
    settlement_at TIMESTAMPTZ NOT NULL,
    settlement_policy_content_id VARCHAR NOT NULL,
    calendar_schedule_content_id VARCHAR NOT NULL,
    obligation_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (
        (asset_kind = 'cash'
            AND currency = 'USD'
            AND amount IS NOT NULL
            AND amount > 0
            AND instrument_id IS NULL
            AND quantity IS NULL)
        OR
        (asset_kind = 'security'
            AND currency IS NULL
            AND amount IS NULL
            AND instrument_id IS NOT NULL
            AND quantity IS NOT NULL
            AND quantity > 0)
    )
);

CREATE TABLE accounting.settlement_transitions (
    settlement_obligation_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    state VARCHAR NOT NULL CHECK (
        state IN ('scheduled', 'settled', 'failed', 'cancelled')
    ),
    effective_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    source_kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    reason_code VARCHAR,
    transition_content_id VARCHAR NOT NULL,
    PRIMARY KEY (settlement_obligation_id, transition_sequence)
);
```

Legal transitions are `scheduled -> settled`, `scheduled -> failed`, `failed -> settled`,
and `scheduled -> cancelled` only as part of a complete source correction/reversal.
Repeated `failed` observations require distinct evidenced attempts and remain transitions;
they do not change quantity/cash twice.

On cash settlement, receivable is credited and settled cash debited, or payable is debited
and settled cash credited. On short-sale cash receipt, settled cash is immediately
reclassified to restricted cash under the book's collateral policy. Security settlement
debits settled/credits unsettled for a long receipt and debits unsettled/credits settled
for a long delivery, with the directionally corresponding short-account transfer. Each
transfer balances within the instrument; it does not change net economic quantity or cost
basis.

Settlement cannot occur before the contractual boundary. A late event uses actual
`effective_at` and records lateness. Missing expected settlement leaves an overdue
obligation and diagnostic; it does not auto-settle because time passed. A source correction
to a fill reverses or adjusts its obligations through linked transactions and transitions.

### 9.3 Available cash and unsettled proceeds

The state projection reports at least:

```text
settled_available_cash
settled_restricted_cash
cash_receivable
cash_payable
accrued_receivable
accrued_payable
net_economic_cash
```

`net_economic_cash` is their signed economic sum and is not synonymous with buying power.
A cash account may spend only settled available cash. A margin policy may give a declared
fraction of eligible unsettled sale proceeds buying-power credit, subject to settlement
and restriction state. That computed credit is a margin view, not a journal reclassification.

## 10. Cash flows, fees, interest, financing, and accruals

### 10.1 External capital

An opening contribution or later deposit debits settled cash and credits capital
contribution. A withdrawal debits capital withdrawal and credits settled cash. External
flows require exact source, effective/logical-availability instants, USD amount, currency
quantum, funding state, and purpose. Pending deposits/withdrawals use receivable/payable
only when an explicit funding lifecycle is supplied; otherwise a flow posts when effective.

`CashFlowId` and the journal source make exact retry deterministic. A reversal preserves
the original flow for performance analysis. Transfers between cash classifications are
internal and never external performance flows.

### 10.2 Accrual calculation

An accrual policy pins rate source, selected revision, compounding, day count, start/end
instants, accrual boundary, eligible principal, calendar, quantization, payment policy,
and missing-rate behavior. The default is no interpolation or extrapolation beyond plan-06
capabilities.

For simple annualized rate `r`, signed principal `P`, and day-count fraction `d`:

```text
raw accrual = abs(P) * r * d
```

The exact formula changes with the registered quote/compounding convention and is stored
in the policy root. Positive available cash may earn interest; restricted cash earns only
when the policy explicitly says so. Negative settled cash accrues financing expense.
Receivables/payables do not earn or cost interest unless separately declared.

Each accrual interval is half-open `(prior_boundary, boundary]`, with no overlap or gap for
the same principal/rate component. Principal changes partition the interval. Rate changes
use the exact effective/availability rule and cannot revise an earlier simulated accrual
with later knowledge.

Accruals post at `DECIMAL(38,12)` to accrued receivable/payable against income/expense.
Payment reclassifies the exact accrued balance to cash. Currency-quantum settlement uses
half-even by default and posts the difference to `rounding_gain` or `rounding_loss`; the
unrounded computation and residual root remain auditable. No residual is silently dropped.

```sql
CREATE TABLE accounting.cash_flows (
    cash_flow_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    journal_transaction_id UUID NOT NULL,
    flow_kind VARCHAR NOT NULL CHECK (
        flow_kind IN ('opening_capital', 'deposit', 'withdrawal')
    ),
    amount DECIMAL(38, 12) NOT NULL CHECK (amount > 0),
    currency VARCHAR NOT NULL CHECK (currency = 'USD'),
    effective_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    source_content_id VARCHAR NOT NULL,
    flow_content_id VARCHAR NOT NULL UNIQUE
);

CREATE TABLE accounting.accruals (
    accrual_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    accrual_kind VARCHAR NOT NULL CHECK (
        accrual_kind IN (
            'positive_cash_interest', 'negative_cash_financing', 'borrow_fee',
            'other_registered'
        )
    ),
    subject_content_id VARCHAR NOT NULL,
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    principal_amount DECIMAL(38, 12) NOT NULL,
    rate DECIMAL(38, 18) NOT NULL,
    day_count_fraction DECIMAL(38, 18) NOT NULL CHECK (day_count_fraction >= 0),
    economic_direction VARCHAR NOT NULL CHECK (
        economic_direction IN ('income', 'expense')
    ),
    accrued_amount DECIMAL(38, 12) NOT NULL CHECK (accrued_amount >= 0),
    journal_transaction_id UUID,
    rate_source_content_id VARCHAR NOT NULL,
    policy_content_id VARCHAR NOT NULL,
    calculation_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    accrual_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (interval_end > interval_start),
    CHECK ((accrued_amount = 0) = (journal_transaction_id IS NULL))
);

CREATE TABLE accounting.accrual_payments (
    accrual_id UUID NOT NULL,
    payment_sequence INTEGER NOT NULL CHECK (payment_sequence >= 1),
    journal_transaction_id UUID NOT NULL,
    paid_amount DECIMAL(38, 12) NOT NULL CHECK (paid_amount > 0),
    residual_amount DECIMAL(38, 12) NOT NULL DEFAULT 0,
    effective_at TIMESTAMPTZ NOT NULL,
    payment_content_id VARCHAR NOT NULL,
    PRIMARY KEY (accrual_id, payment_sequence)
);
```

`principal_amount` retains its economic sign for audit; the registered formula declares
whether the absolute value or sign participates. `accrued_amount` is a nonnegative posting
magnitude and `economic_direction` selects receivable/income or expense/payable sides. A
zero/negative rate can produce zero or opposite-direction economics only when that accrual
kind/policy supports it. Zero computed accruals are recorded in calculation evidence but
do not create forbidden zero postings. Payment totals cannot exceed the projected payable/
receivable plus the exact residual.

### 10.3 Fee classification

Commission and regulatory fees supplied by the fill owner are realized general-book
expenses. Borrow and financing are accrual expenses. Manufactured dividends are distinct
from borrow fees. Exchange rebates may be negative economic fees only through an explicit
rebate income component; posting magnitudes remain positive. Spread, slippage, delay, and
impact remain memorandum components because they are already embedded in execution price.

## 11. Borrow and short inventory

### 11.1 Point-in-time borrow capability

`BorrowAvailabilityView` is an immutable point-in-time capability containing exact
instrument, available quantity, annualized rate and convention, availability/expiry,
source or synthetic-model identity, restricted/recall state, logical availability,
lineage, safety, licensing, and content root. Absence, unknown, unavailable, zero, and
unlimited synthetic capacity are distinct.

In 3.0 a managed borrow view may come from:

- an immutable causal custom dataset satisfying plan 07;
- a run/scenario-owned effective-dated schedule; or
- the explicit `synthetic_unlimited` model, which is visibly optimistic and enters the
  fidelity profile.

A hand-authored future borrow schedule is opaque unless managed temporal evidence proves
it causal. Plan 10 may use the view for pretrade constraints; plan 13 consumes it for
locate/short-order decisions. Accounting owns authorization consumption, open borrow lots,
returns, recalls, and fee accrual after a short fill.

### 11.2 Authorization and lot lifecycle

A borrow authorization reserves positive quantity for one instrument, book, strategy/run,
availability view, and expiry. It transitions monotonically through authorized/partially
used/used/expired/cancelled. A short fill consumes no more than remaining authorized
quantity. Exact retry does not consume twice.

An open short creates a `BorrowLot` linked one-to-one or many-to-one with short inventory
lots according to the policy. Reductions return quantity FIFO against borrow lots unless
the authorization requires an exact mapping. Returned quantity cannot be reused without a
new authorization.

```sql
CREATE TABLE accounting.borrow_lots (
    borrow_lot_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    borrow_authorization_id UUID NOT NULL,
    opened_by_journal_transaction_id UUID NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    opened_quantity DECIMAL(38, 12) NOT NULL CHECK (opened_quantity > 0),
    rate_policy_content_id VARCHAR NOT NULL,
    collateral_policy_content_id VARCHAR NOT NULL,
    source_view_content_id VARCHAR NOT NULL,
    borrow_lot_content_id VARCHAR NOT NULL UNIQUE
);

CREATE TABLE accounting.borrow_authorizations (
    borrow_authorization_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    authorization_kind VARCHAR NOT NULL CHECK (
        authorization_kind IN ('located', 'synthetic_unlimited', 'preborrowed')
    ),
    authorized_quantity DECIMAL(38, 12),
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    source_view_content_id VARCHAR NOT NULL,
    policy_content_id VARCHAR NOT NULL,
    authorization_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (
        (authorization_kind = 'synthetic_unlimited'
            AND authorized_quantity IS NULL)
        OR
        (authorization_kind <> 'synthetic_unlimited'
            AND authorized_quantity IS NOT NULL
            AND authorized_quantity > 0)
    ),
    CHECK (expires_at IS NULL OR expires_at > available_at)
);

CREATE TABLE accounting.borrow_authorization_uses (
    borrow_authorization_id UUID NOT NULL,
    use_sequence INTEGER NOT NULL CHECK (use_sequence >= 1),
    source_fill_id UUID NOT NULL,
    used_quantity DECIMAL(38, 12) NOT NULL CHECK (used_quantity > 0),
    used_at TIMESTAMPTZ NOT NULL,
    use_content_id VARCHAR NOT NULL,
    PRIMARY KEY (borrow_authorization_id, use_sequence),
    UNIQUE (borrow_authorization_id, source_fill_id)
);

CREATE TABLE accounting.borrow_transitions (
    borrow_lot_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    transition_kind VARCHAR NOT NULL CHECK (
        transition_kind IN ('opened', 'returned', 'recalled', 'rate_changed', 'closed')
    ),
    effective_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    quantity DECIMAL(38, 12),
    source_view_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    transition_content_id VARCHAR NOT NULL,
    PRIMARY KEY (borrow_lot_id, transition_sequence),
    CHECK (quantity IS NULL OR quantity > 0)
);
```

A recall creates a required-cover decision for the recalled remaining quantity and
deadline. Accounting records the recall and exposes the constraint; plan 13 chooses and
executes forced orders. If execution cannot cover, the borrow remains open/recalled and
fees continue under policy. It is never removed by administrative fiat.

### 11.3 Borrow fee

Borrow fee principal is the exact short market value at each registered accrual boundary,
using the borrow policy's mark source. Rate and principal changes partition the interval.
The annual rate/day count are explicit. A missing required mark or rate blocks accrual and
book completion under fail policy, or creates a typed estimated/opaque accrual only when a
registered fallback explicitly permits it. A zero rate is valid evidence, not missing.

## 12. Margin and liquidation intent

### 12.1 Generic contract

A `MarginPolicy` maps exact state and proposed trade effects to:

- equity and eligible collateral;
- initial and maintenance requirement by position and aggregate;
- settled/unsettled buying-power credit;
- concentration, nonmarginable, short, and house overlays;
- initial excess, maintenance excess, and buying power;
- selected effective rule/version/source; and
- state/reasons/findings with logical availability.

The pretrade method evaluates the hypothetical posttrade state without journaling it. The
maintenance method evaluates the actual reconciled state. Unknown marks, instrument
marginability, or rules return unavailable rather than assuming zero requirement.

For plan-10 target feasibility, the pretrade capability evaluates ideal signed target
notionals `weight * NAV` under exact marks/multipliers and the selected rules. It applies no
share rounding, minimum trade, open-order reservation, settlement forecast, or assumed
fill and therefore cannot claim broker acceptance.

Plan 11 also owns the registry of named pretrade leverage measures that plan-10 `leverage`
constraints reference. The initial registry contains exactly
`persistra.leverage.gross_market_value_over_equity@1`: the sum of absolute position market
values under exact marks and contract multipliers, divided by plan-11 equity (NAV,
including restricted short-proceeds collateral already classified in NAV); an unavailable
mark or equity makes the measure unavailable. Additional measures register as versioned
qualified names with exact formulas; a constraint never references an unregistered
measure. For plan-13 order preflight, a separate
call evaluates exact proposed quantities, cash reservations, unsettled-use rules, and open
orders. Both retain the same rule/component schema and distinct request content roots.

### 12.2 Simplified US-equity research default

`simplified_us_reg_t_v1` is a transparent research approximation. Marginability is an
explicit input: each instrument's margin-eligible/nonmarginable classification comes from
the margin policy's effective-dated instrument classification table, registered with the
policy (defaulting, for this simplified policy, to margin-eligible for US-listed common
equity and ETFs and nonmarginable otherwise); an instrument with no classification at the
evaluation instant makes the result unavailable, never silently eligible. The rules are:

- margin-eligible long and short positions require 50% initial equity;
- long maintenance is 25% of long market value;
- short maintenance is 30% of short market value;
- nonmarginable long and short positions require 100%;
- short-sale proceeds are fully restricted collateral and are not counted twice; and
- no portfolio-margin offsets, day-trading buying power, broker house rules, or special
  low-price/concentration schedule is implied.

The broad 50% initial and 25%/30% maintenance baselines are documented by
[FINRA's margin guidance](https://www.finra.org/rules-guidance/notices/21-12), but this
policy is deliberately labeled simplified and unsuitable for regulatory or broker
reproduction. Every run using it carries that fidelity limitation. A project needing a
broker schedule registers a typed effective-dated custom policy and conformance fixtures.

For signed market values `L >= 0` and absolute short values `S >= 0`, absent overlays:

```text
equity = NAV
initial_requirement = 0.50 * eligible_L + 0.50 * eligible_S
                    + 1.00 * nonmarginable_L + 1.00 * nonmarginable_S
maintenance_requirement = 0.25 * eligible_L + 0.30 * eligible_S
                         + 1.00 * nonmarginable_L + 1.00 * nonmarginable_S
initial_excess = equity - initial_requirement
maintenance_excess = equity - maintenance_requirement
```

Requirement components use exact amounts, then the policy's conservative quantization.
Gross short proceeds restricted as collateral remain an asset classification already in
NAV; they are not added again to equity.

### 12.3 Breach and liquidation

Maintenance evaluation occurs after every state-changing event and at configured mark
boundaries. A negative maintenance excess creates one deterministic breach occurrence.
The registered liquidation policy returns a `LiquidationIntent` with required recovery
amount, candidate positions, ordered selection rationale, protected/restricted assets,
deadline, priority, and source margin root.

Built-in selection is deterministic: remove nonmarginable/most requirement-intensive
positions first, then descending maintenance relief per estimated liquidation dollar,
then instrument order from the state manifest. Short recalls may impose higher priority.
The policy may prefer liquidity or proportional reduction only when explicitly registered.

An intent is not an order and provides no fill guarantee. Plan 13 records any order,
rejection, partial fill, repeated evaluation, and residual breach. A new state/root creates
a new evaluation; exact retry of the same state returns the same intent. A recovered
account retains prior breach/intent history.

```sql
CREATE TABLE accounting.margin_evaluations (
    margin_evaluation_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    state_basis_content_id VARCHAR NOT NULL,
    evaluation_kind VARCHAR NOT NULL CHECK (
        evaluation_kind IN ('pretrade', 'maintenance')
    ),
    evaluated_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    margin_state VARCHAR NOT NULL CHECK (
        margin_state IN (
            'sufficient', 'initial_deficit', 'maintenance_deficit',
            'mark_unavailable', 'rule_unavailable'
        )
    ),
    equity_amount DECIMAL(38, 12),
    initial_requirement_amount DECIMAL(38, 12),
    maintenance_requirement_amount DECIMAL(38, 12),
    initial_excess_amount DECIMAL(38, 12),
    maintenance_excess_amount DECIMAL(38, 12),
    buying_power_amount DECIMAL(38, 12),
    rule_content_id VARCHAR NOT NULL,
    mark_manifest_content_id VARCHAR NOT NULL,
    component_manifest_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    evaluation_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (
        (evaluation_kind = 'pretrade'
            AND margin_state IN (
                'sufficient', 'initial_deficit',
                'mark_unavailable', 'rule_unavailable'
            ))
        OR
        (evaluation_kind = 'maintenance'
            AND margin_state IN (
                'sufficient', 'maintenance_deficit',
                'mark_unavailable', 'rule_unavailable'
            ))
    ),
    CHECK (
        (margin_state IN ('mark_unavailable', 'rule_unavailable')
            AND equity_amount IS NULL
            AND initial_requirement_amount IS NULL
            AND maintenance_requirement_amount IS NULL
            AND initial_excess_amount IS NULL
            AND maintenance_excess_amount IS NULL
            AND buying_power_amount IS NULL)
        OR
        (margin_state NOT IN ('mark_unavailable', 'rule_unavailable')
            AND equity_amount IS NOT NULL
            AND initial_requirement_amount IS NOT NULL
            AND maintenance_requirement_amount IS NOT NULL
            AND initial_excess_amount IS NOT NULL
            AND maintenance_excess_amount IS NOT NULL)
    )
);

CREATE TABLE journal_data.margin_components (
    margin_evaluation_id UUID NOT NULL,
    component_ordinal INTEGER NOT NULL CHECK (component_ordinal >= 1),
    instrument_id UUID,
    component_kind VARCHAR NOT NULL,
    basis_amount DECIMAL(38, 12) NOT NULL CHECK (basis_amount >= 0),
    requirement_rate DECIMAL(38, 18) NOT NULL CHECK (requirement_rate >= 0),
    requirement_amount DECIMAL(38, 12) NOT NULL CHECK (requirement_amount >= 0),
    rule_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    component_content_id VARCHAR NOT NULL,
    PRIMARY KEY (margin_evaluation_id, component_ordinal)
);

CREATE TABLE accounting.liquidation_intents (
    liquidation_intent_id UUID PRIMARY KEY,
    margin_evaluation_id UUID NOT NULL,
    accounting_book_id UUID NOT NULL,
    required_recovery_amount DECIMAL(38, 12) NOT NULL CHECK (
        required_recovery_amount > 0
    ),
    deadline_at TIMESTAMPTZ NOT NULL,
    priority INTEGER NOT NULL CHECK (priority >= 1),
    candidate_manifest_content_id VARCHAR NOT NULL,
    selection_policy_content_id VARCHAR NOT NULL,
    intent_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);
```

`state_basis_content_id` is the noncircular root of exact journal prefix, valuation,
cash/position/settlement/borrow projections, and proposed trade effects when applicable;
it deliberately excludes both the margin evaluation and final `PortfolioStateId`.
Pretrade evaluations bind a hypothetical basis; maintenance evaluations bind the actual
reconciled basis. The final portfolio state may then bind the completed margin evaluation.
Component sums must reproduce requirements exactly. `buying_power_amount` is nullable
when the policy does not define it or inputs are unavailable; it is never inferred from
margin excess by an unregistered multiplier.

## 13. Corporate-action accounting

### 13.1 Selection and application identity

An application binds exact `CorporateActionId`, selected plan-05
`CanonicalRevisionId`, ordered leg manifest, action status, subject/instrument expansion,
snapshot, public/project cutoffs, calendar/date policy, affected journal prefix/lots,
corporate-action policy, precision, implementation, and source availability. Similar
fingerprints or ticker matches never substitute.

Action processing distinguishes:

1. **capture** — determine eligible quantity/lots and create pending entitlement or
   obligation;
2. **effective transformation** — change instrument/quantity/cost-basis state when terms
   become effective; and
3. **payment/resolution** — exchange cash/security or resolve fractional/unsettled claims.

The exact plan-05 date policy maps civil dates to instants and plan-13 event priority.
Applying a correction learned later reverses affected transactions/entitlements and posts
replacement effects no earlier than correction availability. A completed run never
silently backfills the corrected outcome.

### 13.2 Entitlements

```sql
CREATE TABLE accounting.corporate_action_applications (
    corporate_action_application_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    corporate_action_id UUID NOT NULL,
    selected_canonical_revision_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    application_state VARCHAR NOT NULL CHECK (
        application_state IN ('applied', 'no_position', 'cancelled', 'blocked', 'reversed')
    ),
    capture_journal_prefix BIGINT NOT NULL CHECK (capture_journal_prefix >= 0),
    affected_lot_manifest_content_id VARCHAR NOT NULL,
    leg_manifest_content_id VARCHAR NOT NULL,
    timing_content_id VARCHAR NOT NULL,
    policy_content_id VARCHAR NOT NULL,
    source_availability_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    result_manifest_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    application_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE accounting.entitlements (
    entitlement_id UUID PRIMARY KEY,
    corporate_action_application_id UUID NOT NULL,
    inventory_lot_id UUID,
    leg_ordinal INTEGER NOT NULL CHECK (leg_ordinal >= 1),
    entitlement_kind VARCHAR NOT NULL CHECK (
        entitlement_kind IN (
            'cash_receivable', 'cash_payable', 'security_receivable',
            'security_deliverable', 'fractional_claim', 'unresolved'
        )
    ),
    state VARCHAR NOT NULL CHECK (
        state IN (
            'pending', 'effective', 'payable', 'paid', 'resolved',
            'cancelled', 'blocked_unresolved'
        )
    ),
    currency VARCHAR,
    target_instrument_id UUID,
    amount DECIMAL(38, 12),
    quantity DECIMAL(38, 12),
    exact_unquantized_quantity DECIMAL(38, 18),
    capture_at TIMESTAMPTZ NOT NULL,
    effective_at TIMESTAMPTZ,
    payment_at TIMESTAMPTZ,
    terms_content_id VARCHAR NOT NULL,
    entitlement_content_id VARCHAR NOT NULL UNIQUE,
    CHECK (
        (entitlement_kind IN ('cash_receivable', 'cash_payable')
            AND currency = 'USD'
            AND amount IS NOT NULL
            AND amount > 0
            AND target_instrument_id IS NULL
            AND quantity IS NULL
            AND exact_unquantized_quantity IS NULL)
        OR
        (entitlement_kind IN ('security_receivable', 'security_deliverable')
            AND currency IS NULL
            AND target_instrument_id IS NOT NULL
            AND quantity IS NOT NULL
            AND quantity > 0
            AND amount IS NULL
            AND exact_unquantized_quantity IS NULL)
        OR
        (entitlement_kind = 'fractional_claim'
            AND currency IS NULL
            AND target_instrument_id IS NOT NULL
            AND exact_unquantized_quantity IS NOT NULL
            AND exact_unquantized_quantity > 0
            AND amount IS NULL
            AND quantity IS NULL)
        OR
        (entitlement_kind = 'unresolved'
            AND currency IS NULL
            AND amount IS NULL
            AND quantity IS NULL
            AND exact_unquantized_quantity IS NULL
            AND target_instrument_id IS NULL)
    )
);

CREATE TABLE accounting.entitlement_transitions (
    entitlement_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    state VARCHAR NOT NULL CHECK (
        state IN (
            'pending', 'effective', 'payable', 'paid', 'resolved',
            'cancelled', 'blocked_unresolved'
        )
    ),
    effective_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    journal_transaction_id UUID,
    source_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    transition_content_id VARCHAR NOT NULL,
    PRIMARY KEY (entitlement_id, transition_sequence)
);
```

The `state` on the entitlement master is its immutable initial state. Current state comes
from the last legal immutable transition, never an update to the master. A transition that
changes economics links the balanced journal transaction; a diagnostic blocked/cancelled
transition may have no journal transaction.

### 13.3 Supported action templates

**Cash dividend/distribution:** at capture, long eligible quantity debits dividend
receivable and credits dividend income. A short position debits manufactured-dividend
expense and credits accrued payable. Payment debits settled cash/credits receivable for
longs, or debits payable/credits settled cash for shorts. Withholding is unsupported; it
cannot be silently netted. Quantity times cash-per-unit is calculated at precision 80,
quantized to the amount profile under the action policy, and allocated across lots with
the deterministic residual rule; currency-quantum payment retains any rounding posting.

**Split/reverse split:** at effective time, each affected lot keeps total carrying basis
and transforms quantity by the selected `share_ratio`/terms basis. The precision-80 product
is quantized to the 18-place entitlement profile under the recorded action policy before
the 12-place posted-quantity split; the prequantized canonical product and rounding residual
remain in calculation content, and discarded digits are never accepted implicitly.
Balanced quantity postings move the net created/cancelled units through action control.
Per-unit basis is derived, never separately posted. Representable quantity posts at 12
places and any remainder becomes a fractional claim.

**Stock dividend:** resolved same-instrument additions behave as a split when plan-05
terms declare that meaning. A different target instrument creates a security entitlement
and descendant lot at receipt. Total source basis allocation requires a registered policy;
without one, the entitlement remains blocked rather than assigning zero basis.

**Symbol change:** no economic posting. The existing stable instrument continues; exact
reference lineage is recorded. A listing change that creates a new instrument is not
stitched without explicit exchange terms.

**Cash merger, acquisition, liquidation, or cash-out:** resolved cash consideration closes
the subject lots at effective/payment policy, recognizes realized gain/loss against FIFO
basis, creates receivable, and settles when paid. It may use a zero market mark only after
the position is economically extinguished by those exact terms; absent consideration does
not imply zero.

**Resolved security exchange:** close subject quantity/cost accounts and create descendant
target lots using exact security-leg ratios. Basis follows a registered allocation rooted
in source terms. Boot/cash legs are handled separately. Missing allocation, target
instrument, or precision policy blocks application.

**Spinoff:** create a target security entitlement and descendant lot. Basis allocation
requires exact source percentages or a registered point-in-time fair-value allocation with
exact marks. A later retrospective allocation is unavailable to an earlier simulation.

**Delisting:** a delisting without resolved liquidation or successor terms changes
tradability/mark state but does not remove quantity, invent proceeds, or realize a total
loss. The state remains incomplete/unresolved until a supported resolution.

**Cancelled/unresolved action:** cancellation before application has no economic posting
and retains audit. An unresolved leg creates `blocked_unresolved`; the book cannot claim a
complete valuation/state across required effects. A policy may stop the simulation, but
cannot ignore the action and call the result complete.

### 13.4 Fractional shares and cash in lieu

Accounting supports fractional quantities created by actions independent of order
fractionality. When terms require whole-share delivery, the deliverable whole quantity
uses the declared direction-aware rounding rule and the remainder stays as an exact
fractional entitlement. Cash in lieu is journaled only from explicit cash-per-fraction
terms or an exact later payment/price policy. No current or next bar price is substituted
without that registered policy and availability proof.

## 14. Valuation and NAV

### 14.1 Mark policy

A `ValuationPolicy` declares:

- valuation instant/session and exact composite snapshot/cutoffs;
- the exact bounded asset-coverage manifest, always including open positions and optionally
  including nonheld construction assets, plus contract multipliers;
- ordered mark sources (`quote_mid`, side-specific liquidation quote, trade, completed raw
  bar close, plan-05 execution-only bar open, action cash value, or fixture);
- source precedence, observation state, maximum age, session/calendar treatment, and
  fallback behavior;
- halted, suspended, delisted, partial/no-trade, crossed/locked quote, and missing rules;
- long/short side convention and whether conservative bid/ask marking applies;
- precision/rounding, completeness requirement, and policy/version/content identity.

The default daily research policy selects the latest completed unadjusted session close
available by the valuation cutoff for the exact instrument, subject to a finite maximum
session age. It does not use adjusted prices, current vendor data, ticker stitching, or an
unbounded stale close. An intraday policy must explicitly select quote/trade/bar sources.

`bar_open_execution_outcome` is installed only inside plans 12–13. It uses plan 05's exact
field-restricted projection, becomes simulation-visible at session open, preserves the
complete bar's later canonical source availability, and cannot make any other bar field or
future volume strategy-visible. A standalone/research valuation cannot select it. The mark
and state retain both instants and the execution-projection/fidelity root.

Every open position requires a usable mark for complete NAV. A state requested for plan-10
construction also requires a usable mark for each known nonheld asset in its exact coverage
manifest so target notionals/costs can be converted; those marks do not contribute value
while quantity is zero. Missing a nonheld construction mark may leave a holdings-only
valuation complete but makes that wider state/view unavailable rather than unknown or zero.

Mark selection stores source observation/revision, observation/event/availability times,
status observation when present, age, state, fallback ordinal, price, currency, multiplier,
safety/lineage, and root. A selected zero price is valid only for an exact supported
economic extinguishment/action policy; ordinary equity marks must be positive.

For ordinary marks, `simulation_revealed_at` is null and state logical availability folds
canonical `available_at`. For `bar_open_execution_outcome`, `observed_at` and
`simulation_revealed_at` equal the session open while canonical `available_at` remains at/
after bar end; simulation state folds the reveal instant and separately retains the later
source availability/project-cutoff proof. The writer validates this kind-dependent rule and
forbids the execution mark outside a simulation-owned book.

### 14.2 Valuation schema

```sql
CREATE TABLE accounting.valuations (
    valuation_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    valued_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    valuation_policy_content_id VARCHAR NOT NULL,
    position_manifest_content_id VARCHAR NOT NULL,
    mark_manifest_content_id VARCHAR NOT NULL,
    component_manifest_content_id VARCHAR NOT NULL,
    valuation_state VARCHAR NOT NULL CHECK (
        valuation_state IN ('complete', 'complete_with_stale_marks', 'incomplete')
    ),
    nav_amount DECIMAL(38, 12),
    gross_exposure_amount DECIMAL(38, 12),
    net_exposure_amount DECIMAL(38, 12),
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    valuation_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (valuation_state = 'incomplete'
            AND nav_amount IS NULL
            AND gross_exposure_amount IS NULL
            AND net_exposure_amount IS NULL)
        OR
        (valuation_state <> 'incomplete'
            AND nav_amount IS NOT NULL
            AND gross_exposure_amount IS NOT NULL
            AND gross_exposure_amount >= 0
            AND net_exposure_amount IS NOT NULL)
    )
);

CREATE TABLE journal_data.valuation_marks (
    valuation_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    mark_state VARCHAR NOT NULL CHECK (
        mark_state IN (
            'selected', 'stale_allowed', 'missing', 'stale_rejected',
            'halted_with_mark', 'halted_without_mark', 'invalid', 'unsupported'
        )
    ),
    mark_kind VARCHAR,
    price DECIMAL(38, 12),
    currency VARCHAR,
    contract_multiplier DECIMAL(38, 12),
    observed_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    simulation_revealed_at TIMESTAMPTZ,
    source_revision_id UUID,
    source_content_id VARCHAR,
    status_revision_id UUID,
    age_us BIGINT CHECK (age_us IS NULL OR age_us >= 0),
    fallback_ordinal INTEGER CHECK (fallback_ordinal IS NULL OR fallback_ordinal >= 1),
    reason_code VARCHAR,
    mark_content_id VARCHAR NOT NULL,
    PRIMARY KEY (valuation_id, instrument_id),
    CHECK (
        (mark_state IN ('selected', 'stale_allowed', 'halted_with_mark')
            AND mark_kind IS NOT NULL
            AND price IS NOT NULL
            AND price >= 0
            AND currency = 'USD'
            AND contract_multiplier IS NOT NULL
            AND contract_multiplier > 0)
        OR
        (mark_state NOT IN ('selected', 'stale_allowed', 'halted_with_mark')
            AND price IS NULL)
    ),
    CHECK (
        (mark_kind = 'bar_open_execution_outcome'
            AND simulation_revealed_at IS NOT NULL
            AND observed_at = simulation_revealed_at
            AND available_at >= simulation_revealed_at)
        OR
        (mark_kind IS DISTINCT FROM 'bar_open_execution_outcome'
            AND simulation_revealed_at IS NULL)
    )
);
```

### 14.3 Valuation identity

For each position `i`, signed market value is:

```text
MV_i = net_quantity_i * mark_price_i * contract_multiplier_i
```

For the initial USD-listed equity/ETF scope, contract multiplier is exactly one and that
constant/policy enters the mark and state roots. A different multiplier requires a future
typed plan-04 instrument-term and accounting capability; it cannot arrive through opaque
metadata. Define:

```text
economic_cash = settled_available_cash
              + settled_restricted_cash
              + cash_receivable
              - cash_payable
              + accrued_receivable
              - accrued_payable

NAV = economic_cash + sum(MV_i)
gross_exposure = sum(abs(MV_i))
net_exposure = sum(MV_i)
```

Every general account maps to exactly one valuation component or an equity/income/expense
reconciliation class. Journal net assets at carrying basis plus the explicit long/short
fair-value adjustment must equal component NAV and valuation equity exactly at stored
precision. Trial-balance contributed capital plus cumulative income/expense must equal
journal net assets before that fair-value adjustment. Restricted cash and collateral occur
once in `economic_cash`; memorandum accounts occur zero times. An incomplete required mark
makes NAV/exposure null; a partial numeric NAV is not published as complete.

Unrealized P&L per open lot is signed market value minus remaining carrying amount for a
long, or remaining short liability minus absolute market value for a short. It is a
valuation projection rooted in journal plus marks, not a fabricated cash posting.

## 15. Reconciled portfolio state and Plan 10 handoff

### 15.1 State identity and timing

A `PortfolioStateId` binds one book, exact journal prefix, valuation, cash/position/lot/
settlement/accrual/entitlement/borrow projections, margin evaluation, optional borrow
view, policy roots, safety/lineage, logical availability, schema, and complete output
manifest. It is created only after all reconciliation checks pass.

State construction is acyclic. First, journal/projection and valuation checks produce an
internal `state_basis_content_id` over everything except margin and final state identity.
Second, margin evaluates that exact basis. Third, final reconciliation proves the margin
components refer to the same basis and publishes `PortfolioStateId`. The basis is an
internal content root, not a separately mutable state or public entity.

The state immediately before decision `d` includes exactly events ordered before `d` by
plan 12/13. It excludes the target construction, orders, fills, settlements, actions,
marks, or financing events at or after `d` unless the event-priority contract makes them
visible first. Its `logical_available_at` is the maximum of all required state, valuation,
margin, borrow, and governing evidence and must be no later than the decision cutoff.

An endogenous state retains run/strategy/book identity. A completed state path cannot
masquerade as endogenous state for another counterfactual. An opening fixture is safe only
at its declared opening decision. A hand-authored future path remains opaque as required
by plan 10.

```sql
CREATE TABLE accounting.portfolio_states (
    portfolio_state_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    owner_run_id UUID,
    owner_strategy_id UUID,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    state_at TIMESTAMPTZ NOT NULL,
    logical_available_at TIMESTAMPTZ NOT NULL,
    state_basis_content_id VARCHAR NOT NULL,
    valuation_id UUID NOT NULL,
    margin_evaluation_id UUID NOT NULL,
    borrow_view_content_id VARCHAR,
    account_manifest_content_id VARCHAR NOT NULL,
    position_manifest_content_id VARCHAR NOT NULL,
    lot_manifest_content_id VARCHAR NOT NULL,
    settlement_manifest_content_id VARCHAR NOT NULL,
    accrual_manifest_content_id VARCHAR NOT NULL,
    entitlement_manifest_content_id VARCHAR NOT NULL,
    borrow_manifest_content_id VARCHAR NOT NULL,
    asset_manifest_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    state_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (accounting_book_id, journal_prefix_sequence, valuation_id)
);

CREATE TABLE journal_data.portfolio_state_positions (
    portfolio_state_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    present BOOLEAN NOT NULL,
    net_quantity DECIMAL(38, 12),
    market_value_amount DECIMAL(38, 12),
    risky_weight DECIMAL(38, 18),
    settled_quantity DECIMAL(38, 12),
    unsettled_quantity DECIMAL(38, 12),
    mark_content_id VARCHAR,
    lot_manifest_content_id VARCHAR,
    borrow_state_content_id VARCHAR,
    reason_code VARCHAR,
    row_content_id VARCHAR NOT NULL,
    PRIMARY KEY (portfolio_state_id, instrument_id),
    CHECK (
        (present
            AND net_quantity IS NOT NULL
            AND net_quantity <> 0
            AND market_value_amount IS NOT NULL
            AND risky_weight IS NOT NULL
            AND settled_quantity IS NOT NULL
            AND unsettled_quantity IS NOT NULL
            AND mark_content_id IS NOT NULL
            AND lot_manifest_content_id IS NOT NULL)
        OR
        (NOT present
            AND net_quantity = 0
            AND market_value_amount = 0
            AND risky_weight = 0
            AND settled_quantity = 0
            AND unsettled_quantity = 0
            AND mark_content_id IS NOT NULL
            AND lot_manifest_content_id IS NULL)
    )
);

CREATE TABLE journal_data.portfolio_state_cash (
    portfolio_state_id UUID PRIMARY KEY,
    nav_amount DECIMAL(38, 12) NOT NULL CHECK (nav_amount > 0),
    economic_cash_amount DECIMAL(38, 12) NOT NULL,
    cash_weight DECIMAL(38, 18) NOT NULL,
    settled_available_cash_amount DECIMAL(38, 12) NOT NULL,
    settled_restricted_cash_amount DECIMAL(38, 12) NOT NULL,
    cash_receivable_amount DECIMAL(38, 12) NOT NULL,
    cash_payable_amount DECIMAL(38, 12) NOT NULL,
    accrued_receivable_amount DECIMAL(38, 12) NOT NULL,
    accrued_payable_amount DECIMAL(38, 12) NOT NULL,
    component_manifest_content_id VARCHAR NOT NULL,
    row_content_id VARCHAR NOT NULL
);
```

The fixed state-position relation is over the complete requested asset manifest, not only
open positions; this is how known absent assets remain distinguishable from unknown ones.
Both present and known-absent rows retain the exact valuation mark needed by plan 10;
known-absent rows have zero quantity/value/weight and no lot root.
An unusable state with incomplete/negative NAV may be inspected as a valuation result but
does not publish `portfolio_states` or plan-10 weight rows. `MarginEvaluationId` is required;
a cash book uses its exact cash-account margin policy evaluation rather than null. The
writer proves the cash component identity and exact cash/risky-weight sum across the one
cash row and complete position relation; SQL row checks alone cannot enforce those sums.

### 15.2 `CurrentPortfolioView`

The plan-10 capability contains:

```python no-run
@dataclass(frozen=True, slots=True)
class CurrentPortfolioView:
    portfolio_state_id: PortfolioStateId
    state_content_id: ContentId
    accounting_book_id: AccountingBookId
    owner_run_id: EntityId | None
    decision_at: datetime
    logical_available_at: datetime
    nav: Money
    economic_cash: Money
    cash_weight: Rate
    settled_available_cash: Money
    settled_restricted_cash: Money
    cash_receivable: Money
    cash_payable: Money
    accrued_receivable: Money
    accrued_payable: Money
    positions: tuple[CurrentPosition, ...]
    open_settlements: tuple[SettlementStateView, ...]
    margin: MarginView
    borrow: BorrowView | None
    valuation_policy: ValuationPolicyRef
    valuation_id: ValuationId
    asset_manifest_content_id: ContentId
    safety: SafetySummary
    lineage: LineageSummary
    licensing: LicensingSummary
```

For each known construction-manifest instrument, `CurrentPosition` carries `present`,
signed quantity, signed market value, risky weight, mark/quality, multiplier, settled/
unsettled quantity, long/short lot roots, restriction/borrow state, and reason. `present`
false with complete asset coverage means absent/zero. Missing from the asset-coverage
manifest means unknown and fails any state-dependent plan-10 construction.

`economic_cash = NAV - sum(signed risky market values)`, so `cash_weight` plus risky
weights equals one within the exact plan-10 normalization tolerance even when receivables,
payables, restrictions, or accruals exist. The decomposed fields prevent a constructor or
rebalance policy from treating that residual as spendable cash. NAV must be positive and
complete for a usable weight view; zero/negative/incomplete NAV returns an unavailable
capability with reasons rather than weights.

The view supplies the exact NAV, price, multiplier, and current quantity required to
evaluate plan-10 native-unit expected-cost surfaces. It supplies point-in-time margin and
borrow facts required by registered constraints. Its `MarginView` contains both the
current maintenance evaluation and the exact target-notional pretrade rule capability;
its `BorrowView` contains known/absent/available capacity and rate by covered asset. It
does not round target weights into orders or reserve cash for hypothetical orders; plans
12/13 own that step.

### 15.3 State path

`CurrentPortfolioPath` is an ordered immutable manifest of exact state IDs by decision.
Every requested state-dependent decision has exactly one view. Decisions are strictly
ordered by `(decision_at, schedule sequence)`, each state is available by its decision,
and roots include the originating book/run/strategy. A path cannot splice states from
different books unless a registered external scenario explicitly declares an opaque
composite and records every boundary.

## 16. Materialized projections, rebuild, and reconciliation

### 16.1 Snapshot contract

Projection snapshots may be created at configured transaction counts, session boundaries,
decision instants, or resume checkpoints. A snapshot binds the exact inclusive book
sequence, prior snapshot/root, journal transaction/posting prefix roots, projection schema,
policy/code/environment, and normalized output roots. It is immutable and cannot include
a transaction after its prefix.

Snapshot relations include exact account balances, open lots, lot relief totals,
positions, open settlement obligations, pending accruals, borrow state, entitlements, and
external cash-flow totals. Valuation and margin are separate occurrences because new marks
or rules may evaluate the same journal prefix without changing economic transactions.

```sql
CREATE TABLE accounting.projection_snapshots (
    accounting_snapshot_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    prior_accounting_snapshot_id UUID,
    prior_snapshot_content_id VARCHAR,
    transaction_prefix_content_id VARCHAR NOT NULL,
    posting_prefix_content_id VARCHAR NOT NULL,
    projection_schema_content_id VARCHAR NOT NULL,
    account_manifest_content_id VARCHAR NOT NULL,
    lot_manifest_content_id VARCHAR NOT NULL,
    position_manifest_content_id VARCHAR NOT NULL,
    settlement_manifest_content_id VARCHAR NOT NULL,
    accrual_manifest_content_id VARCHAR NOT NULL,
    borrow_manifest_content_id VARCHAR NOT NULL,
    entitlement_manifest_content_id VARCHAR NOT NULL,
    cash_flow_manifest_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    snapshot_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (accounting_book_id, journal_prefix_sequence, projection_schema_content_id),
    CHECK (
        (prior_accounting_snapshot_id IS NULL) =
        (prior_snapshot_content_id IS NULL)
    )
);

CREATE TABLE accounting.reconciliations (
    reconciliation_id UUID PRIMARY KEY,
    accounting_book_id UUID NOT NULL,
    journal_prefix_sequence BIGINT NOT NULL CHECK (journal_prefix_sequence >= 0),
    accounting_snapshot_id UUID,
    valuation_id UUID,
    reconciliation_state VARCHAR NOT NULL CHECK (
        reconciliation_state IN ('matched', 'mismatched', 'blocked')
    ),
    check_manifest_content_id VARCHAR NOT NULL,
    mismatch_manifest_content_id VARCHAR NOT NULL,
    rebuilt_output_manifest_content_id VARCHAR NOT NULL,
    reconciliation_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);
```

Resume loads the latest verified compatible snapshot and replays the remaining prefix.
If verification fails, it ignores the cache and rebuilds from sequence one or an earlier
verified snapshot; it never repairs authority from a corrupt cache.

### 16.2 Reconciliation checks

Reconciliation performs at least:

1. gap-free book sequence and unique exact source application;
2. complete acyclic source-dependency closure and matching dependency manifests;
3. posting/account dimension match and contiguous ordinals;
4. exact general/memorandum money and per-instrument quantity balance per transaction;
5. complete/legal reversals and no double reversal;
6. trial balance by account normal side;
7. lot opened/relieved/remaining quantity and carrying-basis conservation;
8. position quantities equal lot and quantity-journal projections;
9. receivable/payable balances equal unsettled obligation projections;
10. settled transitions do not exceed or duplicate obligations;
11. borrow open/returned quantities equal short-lot needs under policy;
12. entitlement capture/effect/payment amounts and states reconcile to action postings;
13. accrual intervals do not overlap and accrued balances equal postings/payments;
14. external cash-flow totals equal capital accounts;
15. snapshot rows/counts/manifests equal a clean journal replay; and
16. valuation identity, mark coverage, NAV, exposure, and margin component totals agree.

There is no balance tolerance. Valuation analytic comparisons may declare a display/
float tolerance, but stored decimal components and NAV reconcile exactly. A mismatch
publishes a `mismatched` reconciliation with bounded diagnostics and blocks new
`PortfolioStateId` creation; it never writes correcting journal entries automatically.

## 17. Pure transition kernel and simulation integration

`AccountingKernel.apply(state, command)` is deterministic and side-effect free. Input
state is an immutable verified kernel state; commands are typed opening cash flow, fill,
settlement transition, accrual, borrow transition, corporate-action application, or
correction facts. Output contains:

- next immutable kernel state;
- complete transactions/postings and normalized lifecycle records;
- source application/result roots;
- findings and emitted domain-event payloads; and
- any required valuation/margin follow-up decisions.

The kernel does not allocate wall-clock time, query moving data, persist, emit orders, or
invoke user code. Its caller supplies exact selected market/rate/action/borrow inputs and
IDs from a deterministic allocator. The repository validates output again before atomic
publication.

Plan 12 may use a restricted vectorized command adapter that aggregates economically
equivalent fills under its fidelity policy. It still produces balanced journal entries,
lots, settlement/corporate-action/accrual effects, and exact realized costs. Plan 13 uses
the granular adapter. Differential equality is required only for their explicitly common
profile; byte-identical journal IDs are not required, but economic component identities
must reconcile under the declared aggregation map.

Custom accounting policies receive immutable bounded facts and return registered decision
types such as settlement dates, accrual components, mark selections, basis allocations, or
liquidation intents. All outputs undergo built-in validation. A custom component cannot
construct postings directly or obtain `AccountingKernel` mutation capability.

## 18. Public APIs and bounded dataframes

```python no-run
book = project.services.accounting.books.create(request)
project.services.accounting.apply_cash_flow(book, request)
project.services.accounting.apply_fill(book, facts)
project.services.accounting.apply_settlement(book, settlement_transition_request)
project.services.accounting.apply_accrual(book, request)
project.services.accounting.apply_corporate_action(book, request)
valuation = project.services.accounting.valuations.create(request)
state = project.services.accounting.states.create(state_create_request)
reconciliation = project.services.accounting.reconcile(request)

state.current_portfolio_view(decision_at=decision_at)
state.positions.frame(limit=...)
book.journal.transactions(limit=..., after_sequence=...)
book.journal.postings(transaction_ids=..., limit=...)
```

Write methods are absent or reject outside `research_write` unless invoked through the
simulation-owned persistence adapter. Lookup by friendly book label is never an execution
input. Handles pin IDs/content and provide bounded metadata, summaries, exact row iterators,
and explicit frames. They expose no relation name, SQL fragment, raw connection, mutable
account, or posting method.

Frames use stable column order, UTC-aware timestamps, canonical UUID/string IDs, Python
decimal-compatible amount/quantity values, and categorical enum strings. Empty frames
retain full schema. Conversion to pandas is refused above the requested/project limit;
chunk iteration preserves sequence/ordinal order and content-root concatenation.

## 19. Execution identity, idempotency, concurrency, and recovery

Book identity includes owner, opening source, policy/chart roots, implementation,
environment, schema, safety/licensing, and limits. Each source application identity
includes exact prior state prefix, source kind/ID/version/content, selected external input
roots, policies, command schema, and implementation identity. A different prior prefix or
input root is a different application even when numeric postings match.

Exact retry:

1. resolves and freezes the request;
2. checks the unique source key;
3. if present, requires identical source/request/result content and verifies transaction,
   posting, lifecycle, manifest, and event rows before returning the prior handle;
4. if absent, computes in transaction-local state, validates all invariants and roots, and
   atomically inserts; and
5. on unique conflict, re-reads and performs the same verification.

Two different commands cannot race on one book prefix. The exclusive research writer and
book sequence check serialize them. Simulation has one owning event-loop transaction.
Independent books may be processed in isolated files by later plans, not concurrent
writers to one DuckDB file.

Process death before commit exposes nothing. DuckDB recovery handles the database; on open,
Persistra validates schema and completed occurrences. Internal staging is removable only
after proving no completed manifest references it. A gap, unbalanced transaction, broken
root, unknown account, or corrupt snapshot blocks the affected book and produces doctor/
reconciliation guidance; automatic balancing plugs are forbidden.

## 20. Numeric precision and deterministic behavior

- Money, price, carrying basis, fees, P&L, marks, NAV, and postings use plan-01
  `DECIMAL(38,12)`/`Money`/`Price`.
- Quantities and posted action quantities use `DECIMAL(38,12)`/`Quantity`.
- Rates, ratios, action ratios, and exact unquantized entitlement quantities use
  `DECIMAL(38,18)`/`Rate` where their owning schema permits it.
- Intermediate arithmetic uses local decimal precision 80 with traps and explicit final
  quantization. No global decimal context is read.
- Journal balance is exact after quantization. The writer computes one deterministic
  residual posting only when a named allocation/payment policy requires it; it never adds
  an unexplained plug.
- Pro-rata allocation uses largest remainder: quantize each child down to the quantum,
  rank remaining fractions descending, then stable business order, and distribute quanta
  until the exact parent total is reached. The allocation manifest records all fractions.
- FIFO, source/action legs, postings, settlements, accrual partitions, marks, and state
  assets use explicit business keys; hash/dictionary order is irrelevant.
- Locale, host timezone, supported worker count, insertion order, and caller decimal context
  cannot change roots. Wall time is diagnostic only and never an economic input.
- Overflow, nonfinite float conversion, precision loss, negative zero ambiguity, currency
  mismatch, or unrepresentable quantity fails before publication.

## 21. Events, errors, reasons, and observability

### 21.1 Domain events

Normalized changes emit plan-01 envelopes transactionally:

| Event type | Aggregate | When emitted |
| --- | --- | --- |
| `persistra.accounting.book_created@1` | accounting book | Opening book commits |
| `persistra.accounting.transaction_posted@1` | accounting book | Each balanced transaction commits |
| `persistra.accounting.transaction_reversed@1` | accounting book | Linked reversal commits |
| `persistra.accounting.settlement_transitioned@1` | settlement obligation | Legal transition commits |
| `persistra.accounting.borrow_transitioned@1` | borrow lot/authorization | Borrow state changes |
| `persistra.accounting.corporate_action_applied@1` | action application | Applied/no-position/blocked outcome commits |
| `persistra.accounting.valuation_completed@1` | valuation | Complete/stale/incomplete valuation publishes |
| `persistra.accounting.state_completed@1` | portfolio state | Reconciled usable state publishes |
| `persistra.accounting.margin_breached@1` | margin evaluation | New exact breach is found |
| `persistra.accounting.liquidation_intent_created@1` | liquidation intent | Policy returns forced intent |
| `persistra.accounting.reconciliation_completed@1` | reconciliation | Matched/mismatched/blocked result publishes |

One command may emit correlated transaction, settlement, borrow, action, and margin events
with gap-free aggregate sequences. Payloads contain bounded IDs, counts, roots, states, and
reasons—not every posting or licensed mark. Exact retry emits no duplicate event.

### 21.2 Exceptions

Typed exceptions include:

- `AccountingBookError`
- `JournalInvariantError`
- `JournalImbalanceError`
- `SourceApplicationConflictError`
- `AccountingCorrectionError`
- `IllegalReversalError`
- `LotReliefError`
- `SettlementPolicyError`
- `SettlementTransitionError`
- `AccrualPolicyError`
- `BorrowAuthorizationError`
- `BorrowInvariantError`
- `MarginPolicyError`
- `CorporateActionAccountingError`
- `ValuationPolicyError`
- `ReconciliationError`
- `AccountingResourceLimitError`
- `AccountingCorruptionError`

Expected business unavailability—missing mark/rate/borrow, blocked action, overdue
settlement, margin deficit, or unavailable state—is a typed result/reason unless the
caller's declared policy is fail-fast. Invalid configuration, structural safety failure,
corruption, imbalance, or transaction failure is exceptional.

### 21.3 Stable reason codes

Initial stable reasons include:

```text
accounting.currency_unsupported
accounting.book_owner_mismatch
accounting.source_duplicate_conflict
accounting.correction_dependency_blocked
journal.account_dimension_mismatch
journal.money_unbalanced
journal.quantity_unbalanced
journal.zero_posting
journal.sequence_gap
journal.reversal_illegal
lot.insufficient_long_quantity
lot.insufficient_short_quantity
lot.relief_basis_mismatch
settlement.policy_unavailable
settlement.calendar_unavailable
settlement.overdue
settlement.transition_illegal
cash.insufficient_settled_available
accrual.rate_missing
accrual.interval_overlap
borrow.view_missing
borrow.quantity_unavailable
borrow.authorization_expired
borrow.recalled
borrow.rate_missing
margin.mark_unavailable
margin.rule_unavailable
margin.initial_deficit
margin.maintenance_deficit
action.revision_unavailable
action.ambiguous
action.cancelled
action.terms_unresolved
action.basis_allocation_missing
action.fractional_terms_missing
action.target_instrument_unresolved
valuation.mark_missing
valuation.mark_stale
valuation.halt_without_mark
valuation.nav_nonpositive
valuation.incomplete
state.not_reconciled
state.asset_unknown
state.available_after_decision
reconciliation.journal_mismatch
reconciliation.projection_mismatch
reconciliation.valuation_mismatch
accounting.resource_limit
```

Logs use stable event names and IDs, bounded counts/ranges, durations, roots, and reasons.
They exclude licensed payloads, account-holder secrets, complete position lists, raw custom
state, and unrestricted journal dumps. Warnings persist with the occurrence that caused
them.

## 22. Required edge-case behavior

| Case | Required behavior |
| --- | --- |
| Exact source retry | Verify and return original application; no new sequence/event |
| Same source ID, changed content | Conflict; publish nothing |
| Corrected fill after settlement/disposal | Dependency-aware compensating cascade or explicit blocked result; never blind reversal |
| Transaction rounds out of balance | Explicit residual policy or reject; never tolerance/plug |
| Fee exceeds sale proceeds | Separate payable or reject under exact policy; no negative posting |
| Sell more than long position | Reject or split exact close/open-short facts supplied by plan 13 |
| Cover more than short | Reject; never create a long implicitly |
| Simultaneous fills | Plan-13 sequence is authority; UUID only final tie-breaker |
| Same-session buy and sell | FIFO by exact fill ordering; no end-of-day net shortcut |
| Position both long and short | Reject initial 3.0 book unless future typed sleeve model |
| Holiday/weekend settlement | Pinned plan-04 settlement calendar; never venue/host weekday or calendar-day addition |
| Settlement event absent | Remains overdue/unsettled; do not auto-settle |
| Settlement fail then success | Preserve failed transition, settle once on later event |
| Use unsettled sale proceeds | Margin buying-power credit only; journal remains receivable |
| Negative cash in cash account | Reject before commit |
| Negative cash in margin account | Financing balance and accrual under explicit policy |
| Zero borrow availability | Valid zero-capacity view, distinct from missing |
| Synthetic unlimited borrow | Allowed only explicit; optimistic fidelity finding persists |
| Borrow recall without fill liquidity | Keep recalled/open borrow and breach/intent history |
| Missing borrow rate | Block accrual or explicit estimated fallback; never assume zero |
| Margin mark missing | Unavailable evaluation, not zero requirement/equity |
| Margin breach | Intent only; no synthetic forced fill |
| Deposit at decision timestamp | Plan-12/13 event priority decides whether state includes it |
| Dividend ex-date short | Manufactured obligation, distinct from borrow expense |
| Dividend announced then cancelled | Apply selected point-in-time status; later correction reverses visibly |
| Split creates 12+ decimal shares | Post representable quantity and exact fractional claim |
| Reverse split below one share | Do not erase; retain fractional claim until explicit resolution |
| Stock dividend target unresolved | Block action/state; do not use subject instrument automatically |
| Spinoff basis unavailable | Entitlement exists but valuation/state incomplete |
| Cash merger payment delayed | Position/receivable follow exact action policy; cash remains unsettled |
| Symbol change | No journal economics or new position identity |
| Delisting with no proceeds | Retain quantity/unresolved mark; never invent zero |
| Missing price during halt | `halted_without_mark` only with status evidence; otherwise missing |
| Stale mark inside allowance | Complete-with-stale plus age/finding |
| Stale mark outside allowance | Incomplete; never unlimited forward-fill |
| Corrected historical price | Earlier completed run remains pinned; new valuation has new root |
| Zero/negative NAV | Journal may be valid; Plan-10 weight view unavailable |
| Snapshot mismatch | Ignore cache, rebuild, publish diagnostic; never mutate journal |
| Reconciliation mismatch | Block new state and downstream construction |
| Custom policy returns postings | Reject capability violation; policies return typed decisions only |

## 23. Security, licensing, and resource behavior

- No arbitrary SQL, journal account creation, posting injection, import-path callback,
  pickle, dynamic class loading, or physical-table access is public.
- Custom policy execution follows plan-08 bounded/conformance rules and receives copied
  immutable values. Registration does not grant safety.
- Market, borrow, custom, and action licensing/sensitive restrictions propagate to marks,
  states, frames, logs, events, exports, and later results. Metadata remains inspectable
  when values are denied.
- Public frames and iterators require explicit row/range bounds. Journal scans use book
  sequence pruning; valuation requests use bounded instrument manifests.
- Rebuild preflights prefix size, lots, obligations, entitlements, marks, memory, temp
  storage, and time. It never samples or omits checks.
- Generated relation names are migration-owned and hidden. User-qualified names cannot
  collide with managed schemas/accounts/event names.
- Decimal arithmetic, content hashing, selected market reads, and policy execution observe
  cancellation only at safe boundaries. Interrupted writes roll back fully.
- Events/logs contain content roots and bounded summaries, not full positions, proprietary
  rates, licensed marks, or custom policy state.

## 24. Migration, compatibility, and extension policy

### 24.1 Clean v3 boundary

This is a greenfield v3 schema. V2 portfolio values, trades, cash tables, and backtest
results are not imported as a trusted journal. A user may create an explicit opening
fixture from validated USD cash/positions with exact acquisition-basis policy; that fixture
is not historical transaction provenance and is safe only at its declared opening decision.

Research migrations add `accounting` and `journal_data` schemas and every fixed table,
constraint, index, generated relation registry, and event codec. Migration fixtures cover
fresh create, every supported earlier v3 schema, read-only reopen, verified copy, schema
introspection, and corrupt/foreign ownership. Downgrade and in-place rollback remain out
of scope under plan 02.

### 24.2 Versioning and reuse

A changed chart, posting template, lot method, settlement interval/calendar, unsettled-
cash policy, accrual/rate/day-count rule, borrow/collateral model, margin rule, liquidation
selection, corporate-action timing/basis/fractional policy, valuation source/staleness,
precision, schema, implementation, or safety rule changes identity. Cosmetic labels do not.

Exact reuse requires the same book prefix, source/input roots, policy/code/environment,
and output content. Plan 14 may record compatible scenario reuse, but cannot relabel one
journal, state, or valuation as another exact occurrence. Plan 15 comparisons preserve
original roots and fidelity differences.

### 24.3 Extension contracts

Registered custom settlement, accrual, borrow, margin, action-basis, valuation, and
liquidation policies declare typed inputs/outputs, effective intervals, temporal behavior,
required source capabilities, precision, determinism, resources, failure states, safety,
and conformance fixtures. They return decisions, never postings or mutation handles.

New currencies, tax methods, derivatives, portfolio margin, broker subaccounts, or asset
classes require new typed commodity/account/valuation/settlement/margin contracts and
acceptance suites. Opaque account kinds or JSON posting metadata cannot stretch this
listed-equity schema.

## 25. Implementation sequence

1. Add IDs/enums/value objects, book/chart/policy registries, schemas, migrations, and
   bounded repositories.
2. Implement commodity-balanced journal validation, source idempotency, reversals,
   canonical posting roots, and the pure transition kernel.
3. Implement opening/external cash flows, fill templates, FIFO long/short lots, realized
   P&L, fees, and position/cash projections.
4. Implement effective-dated settlement schedules, obligations/transitions, available/
   restricted/unsettled cash, and settlement reconciliation.
5. Implement risk-free/cash/financing/borrow accruals, residual policy, borrow views,
   authorizations, lots, returns, and recalls.
6. Implement generic margin, simplified US-equity default, pretrade/maintenance views,
   breaches, and liquidation intents.
7. Implement exact action selection, entitlements, dividends, splits, stock dividends,
   resolved exchanges/spinoffs/cash-outs, fractionals, corrections, and blocked cases.
8. Implement mark policies, valuation/NAV/exposure/unrealized P&L, quality findings, and
   exact state/current-view/path adapters for plan 10.
9. Implement snapshots, clean rebuild, full reconciliation/doctor, fault recovery,
   events/logs, frames, and simulation-owned persistence adapters.
10. Complete golden/property/stateful/fault/resource/determinism tests, docs workflow,
    strict docs build, and cumulative plans 01–11 review.

Each checkpoint is one coherent migration/API/test unit. No step may expose an unbalanced
journal, mutable authority cache, guessed action, incomplete mark as NAV, or unreconciled
current state.

## 26. Acceptance tests and exit criteria

### 26.1 Identity, schema, and journal tests

- All seventeen IDs round-trip through canonical JSON, SQL UUID, event payloads,
  repositories, and kind-mismatch rejection.
- Book/chart/policy registration covers exact retry/conflict, USD-only scope, owner/run,
  opening fixture classification, content roots, and reserved names.
- Fresh/supported migration, constraints/indexes, reopen/read-only, verified copy,
  generated-name hiding, and corrupt ownership pass.
- Golden transactions cover money-only, quantity-only, mixed, general/memorandum, exact
  balance, zero/negative/overflow rejection, account mismatch, source retry/conflict,
  book/per-source sequence allocation, multi-transaction source commands, full reversal,
  replacement, and double-reversal rejection.
- Correction golden cases cover price/fee changes before and after settlement, partial and
  complete FIFO relief, short borrow/return, intervening split/dividend, quantity still
  sufficient or insufficient for later disposals, incomplete dependency closure, atomic
  cascade rollback, and preservation of prior valuation/state roots.
- Property tests generate postings and prove every committed commodity group balances
  exactly; any deleted/changed/duplicated posting is detected by count/root/reconciliation.

### 26.2 Fill, lot, cash, and settlement tests

- Hand-worked long buy/sell and short/open/cover examples validate cash receivable/payable,
  quantity control, carrying basis, FIFO partial relief, realized gain/loss, direct fees,
  and balanced memorandum execution attribution.
- Same-instant fills, partial closes, cross-zero splits, fee-greater-than-proceeds,
  insufficient inventory, exact retry, and source correction preserve deterministic lots.
- Deposits/withdrawals/negative margin cash validate capital accounts, external-flow roots,
  available cash, financing classification, and plan-15 handoff.
- Settlement fixtures cover T+3/T+2/T+1 boundaries, Memorial Day/weekends/early closes,
  pre-1995 built-in unavailability, the exact plan-04 settlement calendar versus venue/
  host weekdays, cash/security legs, restricted short proceeds, fail/retry/late/cancel,
  overdue state, and unsettled-proceeds buying-power without ledger relabeling.
- Journal cash/position/lot projections equal obligation and settlement projections after
  every generated transition.

### 26.3 Accrual, borrow, and margin tests

- Rate fixtures cover simple/periodic/continuous/discount conventions as supported,
  act/360, act/365f, principal/rate partitions, negative/zero rates, missing points,
  no interpolation, 12-place accrual, cent payment, and explicit residual gain/loss.
- Positive cash, restricted cash, negative financing, borrow fee, manufactured dividend,
  and payment examples reconcile without double counting.
- Borrow fixtures distinguish missing/zero/unlimited, availability and expiry boundaries,
  partial authorization consumption, duplicate fill, FIFO returns, rate changes, recall,
  failed cover, and open quantity/fee continuity.
- Simplified margin golden cases validate long/short/nonmarginable initial/maintenance
  requirements, restricted proceeds counted once, unsettled credit, negative equity,
  missing mark/rule, conservative rounding, and fidelity finding.
- Pretrade tests do not journal hypothetical effects. Maintenance breach tests produce
  deterministic intents only, preserve prior intents, and require plan-13 fills to recover.

### 26.4 Corporate-action tests

- Exact revision/source/cutoff fixtures cover announced/confirmed/completed/cancelled,
  later corrections, ambiguous fingerprints, no-position outcomes, availability at event
  boundaries, and action-event ordering.
- Hand-worked long/short cash dividends validate receivable/income, manufactured expense/
  payable, payment, correction, and no withholding inference.
- Split/reverse-split/stock-dividend property tests preserve total lot basis, transform
  quantity exactly, derive per-unit basis, create deterministic fractional claims, and
  balance action control.
- Cash merger/liquidation examples close FIFO lots and retain receivable until payment;
  security exchange/spinoff examples preserve ancestry and exact registered basis.
- Missing target, basis allocation, fractional terms, consideration, or unresolved legs
  block completion. Symbol change has zero economic postings. Delisting without proceeds
  retains quantity and never invents zero.
- Generated sequences combine fills, settlements, splits, dividends, reversals, short
  obligations, and action corrections while checking invariants after every command.

### 26.5 Valuation, state, rebuild, and reconciliation tests

- Mark selection covers quote midpoint/side, trade, raw completed close, source precedence,
  exact cutoff, no-trade/partial/crossed/locked, known halt, missing status, finite stale
  allowance, stale rejection, delisting, action value, and no adjusted/current fallback.
- The plan-12/13 bar-open mark preserves canonical later `available_at`, uses exact
  `simulation_revealed_at`, exposes only open after its event, is unavailable standalone,
  and cannot leak other bar fields or current-session volume into state/construction.
- Hand-worked long/short/cash/receivable/payable/accrual/restricted examples prove NAV,
  gross/net exposure, unrealized P&L, trial-balance equity, and no memorandum/collateral
  double count.
- Any required missing mark yields incomplete valuation with null NAV. Stale-allowed marks
  yield complete-with-stale and retain age/finding. Zero marks require exact extinguishment.
- `CurrentPortfolioView` validates positive NAV, weights plus economic cash equal one,
  decomposed spendability, quantities/prices/multipliers, absent versus unknown assets,
  settlement/margin/borrow roots, noncircular state-basis identity, logical availability,
  and plan-10 expected-cost inputs.
- Paths reject missing/duplicate/future states, cross-book splicing, wrong run/strategy,
  and unsafe future fixtures; opening fixtures work only at their one declared decision.
- Rebuild from sequence one and every compatible snapshot yields identical account/lot/
  settlement/borrow/action/state roots under different partition sizes.
- Fault injection at every transaction/posting/lifecycle/hash/event/snapshot boundary
  exposes no partial publication. Every seeded corruption is detected and no automatic
  correcting entry is posted.

### 26.6 API, concurrency, resources, and documentation

- Read-only/write/simulation adapters enforce ownership; public handles never expose
  connections, physical names, posting mutation, unbounded frames, or custom state.
- Concurrent identical source applications yield one result/event; conflicting source or
  stale-prefix applications fail without gaps. Independent worker files do not imply
  concurrent writes to one database.
- Frame schemas, empty frames, ordering, decimal values, chunk/root concatenation, close
  invalidation, licensing, and sensitive redaction pass.
- Every transaction/posting/dependency/lot/settlement/entitlement/position/mark/rebuild/
  frame/memory/temp/time limit fails explicitly without sampling, truncation, skipped
  reconciliation, or partial state.
- Hash/insertion order, locale, timezone, caller decimal context, partition size, and
  supported worker settings do not change replay roots.
- Base installation imports the accounting namespace safely; custom optional dependencies
  fail only when invoked with actionable diagnostics.
- API/docs snippets compile or execute, SQL examples parse in the documentation harness,
  internal links resolve, and strict MkDocs succeeds.

### 26.7 End-to-end exit

A documented USD long/short book must:

1. open from an exact capital contribution;
2. post long and short fills with fees, lots, borrow, and T+ settlement;
3. accrue cash financing and borrow cost from exact point-in-time rates;
4. process a split, long cash dividend, short manufactured dividend, fractional claim,
   and one blocked unresolved action;
5. value complete and stale/missing cases with exact NAV/quality;
6. evaluate sufficient and breached margin and emit a liquidation intent without a fill;
7. rebuild every projection and reconcile from the journal;
8. supply plan 10 with an exact endogenous `CurrentPortfolioView`; and
9. replay through pure kernel plus repository persistence with identical economic roots.

Plan 11 is complete only when these tests pass with `make lint type test`, docs checks,
strict docs build, and cumulative review finds no contradiction with the umbrella or
focused plans 01–10.

## 27. Review checklist for dependent plans

Plans 12 through 15 and 18 must preserve:

- one immutable USD book per economic portfolio/run and exact source idempotency;
- commodity-balanced general/memorandum postings and no direct balance mutation;
- full reversal/replacement rather than edits or backdated knowledge;
- FIFO lots, cost basis, long/short separation, and no implicit cross-zero fill;
- trade-date economics versus later effective-dated cash/security settlement;
- settled, available, restricted, receivable, payable, accrued, and economic cash as
  distinct values;
- direct fees versus embedded memorandum execution costs without double counting;
- explicit accrual rate/day-count/quantization/residual evidence;
- point-in-time borrow authorization/use/return/recall/rate and continued recalled state
  until an actual cover fill;
- generic margin and exact rule/mark roots, with breach producing intent rather than a
  synthetic accounting fill;
- exact plan-05 action revision/leg/timing, separate capture/effect/payment, short
  obligations, fractions, basis allocation, and blocked unresolved terms;
- missing/stale/halted/delisted mark distinctions and prohibition on invented zero or
  unlimited forward-fill;
- exact NAV/component identity and restricted collateral counted once;
- snapshot-as-cache, clean replay, reconciliation before `PortfolioStateId`, and no
  automatic balancing entries;
- Plan-10 state semantics: positive complete NAV, economic cash plus risky weights,
  absent-versus-unknown coverage, decomposed restrictions, and exact margin/borrow/mark
  roots available by decision;
- simulation-time use of the pure kernel with persistence owned by the isolated run
  transaction, not a second research writer;
- immutable external cash-flow and fidelity evidence for plan-15 performance/attribution;
  and
- bounded handles, hidden physical names, licensing/safety propagation, deterministic
  ordering, complete manifests, atomic publication, and typed unavailable outcomes.

A dependent plan needing portfolio margin, tax lots, broker subaccounts, multicurrency,
derivatives, live custody, or regulatory reporting defines a new typed capability rather
than adding opaque fields or changing these accounting meanings.

## 28. Consistency statement

This plan implements the umbrella journal, lots, settlement, valuation, cash-flow,
financing, borrow, margin, and corporate-action requirements without assigning order/fill
authority to accounting. It uses plan-01 precision exactly, follows plan-02 connection and
transaction ownership, consumes plan-05 action identity without inference, consumes
plan-06 rates without moving-as-of selection, and supplies the reconciled state promised
by plan 10.

The design makes both monetary and inventory movements auditable: general and memorandum
books balance independently, and quantity balances by instrument through explicit control
accounts. It preserves target intent versus realized execution, recognizes fills once at
trade time, reclassifies rather than re-recognizes at settlement, and keeps snapshots as
rebuildable caches. Missing market or action facts remain visible unavailable state rather
than being converted into plausible but false economics.

No project-level direction in the umbrella specification is revised. The focused choices
are FIFO lot relief, a simplified and explicitly non-broker US-equity margin default,
effective-dated T+3/T+2/T+1 settlement fixtures, and decision-returning custom policies
that cannot write postings. These choices narrow implementation while retaining explicit
extension boundaries.

The cumulative plans 01–11 review also makes accounting a top-level package/authority in
the umbrella, records its research and isolated-run schemas in plan 02, and replaces plan
10's future-only state language with this plan's reconciled state-basis/margin/view adapter.
The noncircular state-basis root lets margin feed final state identity without either
occurrence depending on its own content. No earlier identity, temporal-safety, market,
rate, validation, target, or database-ownership contract is relaxed.

The cumulative plan-12 review adds the matching simulation-only bar-open valuation kind so
execution-time NAV and synthetic fills use one exact field-restricted outcome. Canonical
bar availability remains later and visible in lineage; only the open is revealed at the
open event, ordinary accounting/research valuations cannot select it, and current-session
volume remains unavailable to causal open-time capacity. This does not weaken Plan 05 or
the Plan-10 current-state cutoff.

The cumulative Plan-13 review fixes the same-timestamp event boundary: action effects,
settlement, cash flows/accruals, fills, valuation/reconciliation, and margin occur in the
Plan-13 total priority before its strategy callback. A callback therefore receives the
fully committed visible accounting prefix, including a deposit effective at that instant,
but orders it creates cannot consume a market occurrence or fill bucket that already ran.
Forced liquidation remains a Plan-11 intent until Plan 13 creates and actually fills an
engine-owned order; accounting never manufactures execution or liquidity.
