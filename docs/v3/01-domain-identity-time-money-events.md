# Focused specification 01: domain identity, time, money, and events

**Status:** Implementation-ready draft  
**Umbrella:** [`../v3-spec.md`](../v3-spec.md)  
**Owners:** `persistra.domain`  
**Required before:** focused specifications 02–18  
**Last reviewed:** 2026-07-15

## 1. Purpose

This specification defines the dependency-free domain primitives shared by every Persistra
v3 subsystem. It fixes the representation and validation rules for internal identities,
content identities, names, versions, instants, intervals, currencies, fixed-precision
numbers, and immutable event envelopes.

It turns the umbrella specification's identity, temporal, numerical, determinism, and
auditability requirements into contracts that later focused specifications must reuse.
It does not define instrument reference data, database ownership, accounting entries,
order states, or simulator event priority. Those contracts build on the primitives here.

## 2. Scope and boundaries

### 2.1 In scope

- Assigned opaque identifiers for persisted entities and lifecycle records
- Content identifiers for immutable byte sequences
- Stable qualified names and explicit schema versions
- UTC instant normalization and serialization
- Half-open observation and effective intervals
- Injected clocks for deterministic state-changing operations
- ISO-style currency codes and fixed-precision decimal scalar types
- Explicit quantization and rounding policies
- Immutable, versioned domain event envelopes and event-type registration
- Canonical hashing and wire representations for these primitives
- Typed validation failures and stable reason codes

### 2.2 Out of scope

- Issuer, security, listing, instrument, venue, and external-identifier semantics
- Dataset natural keys, source revision keys, and snapshot manifests
- Database schemas, migrations, leases, and transaction ownership
- Exchange calendars and conversion from venue-local wall times
- Foreign-exchange conversion and cross-currency accounting
- Journal accounts, posting precision, lots, valuation, and reconciliation
- Order types, order-state transitions, fills, and execution priority
- Experiment design, execution, attempt, artifact, and analysis identity hashes
- A general event bus, distributed messaging, or event sourcing of every subsystem

The owning focused specification may add a domain-specific identifier class or event
payload, but it may not change the primitive representation rules without revising this
document and the umbrella specification when the change is project-wide.

## 3. Normative conventions

The terms **must**, **should**, and **may** retain the meanings defined in the umbrella
specification. Unless stated otherwise:

- Text is Unicode normalized to NFC before validation or identity hashing.
- Persisted enum values and reason codes are lowercase ASCII and never depend on Python
  enum member names.
- Public dataclasses are frozen and use slots.
- Public collection fields are immutable tuples or read-only mappings.
- `None` means unavailable or not applicable; it never means an implicit default instant,
  currency, quantity, or identifier.
- Canonical serialization sorts mapping keys, preserves list order, and rejects values
  without a defined canonical representation.

## 4. Package and public API

The implementation lives under:

```text
src/persistra/domain/
├── __init__.py
├── errors.py
├── identity.py
├── time.py
├── numbers.py
└── events.py
```

`persistra.domain` re-exports only:

```python no-run
from persistra.domain import (
    AvailabilityQuality,
    Clock,
    ContentId,
    Currency,
    DomainEvent,
    Duration,
    EffectiveInterval,
    EntityId,
    EventId,
    EventType,
    FixedClock,
    Money,
    NonNegativeQuantity,
    Price,
    QualifiedName,
    Quantity,
    Rate,
    RoundingMode,
    SchemaVersion,
    SystemClock,
    TimeInterval,
    utc_now,
    validate_instant,
)
```

The concrete error classes in section 11 are public from `persistra.domain.errors` and
from the eventual common `persistra.errors` namespace. Domain types are not re-exported
from top-level `persistra` except where a later public API demonstrably needs one of them
as a foundational configuration type.

## 5. Identity model

### 5.1 Identity families

Persistra uses four distinct identity families:

| Family | Meaning | Generated from | Mutable referent | Canonical storage |
| --- | --- | --- | --- | --- |
| Opaque entity ID | Stable identity of an entity | Cryptographic randomness | The entity may gain revisions | DuckDB `UUID` |
| Lifecycle ID | Stable identity of an occurrence | Cryptographic randomness | No; history is append-only | DuckDB `UUID` |
| Content ID | Identity of immutable bytes | SHA-256 digest | No | lowercase text |
| Natural key | Domain uniqueness within a source or dataset | Domain fields | May receive revisions | Owning schema columns |

An opaque or lifecycle ID is not a content hash. A content ID is not used as the primary
identity of a mutable catalog entity. A natural key is never collapsed into an opaque
string when its component fields are needed for validation and temporal selection.

External identifiers such as tickers, FIGIs, and CUSIPs are effective-dated reference
data, not members of these internal identity families.

### 5.2 `EntityId` and typed subclasses

`EntityId` is an abstract frozen value object around an RFC 4122 UUID. Persisted entity
types expose final subclasses such as `InstrumentId` and `DatasetId`; the owning focused
specification declares each subclass and its lowercase kind token.

```python no-run
class EntityId:
    @classmethod
    def new(cls) -> Self: ...

    @classmethod
    def parse(cls, value: str | UUID | Self) -> Self: ...

    @property
    def value(self) -> UUID: ...

    def to_wire(self) -> str: ...
```

Rules:

- `new()` uses UUID version 4 from the operating system's cryptographic random source.
- The all-zero UUID is invalid.
- A subclass accepts only its own instances, UUID objects, a bare canonical UUID string,
  or its typed wire form.
- The typed wire form is `<kind>:<lowercase-hyphenated-uuid>`, for example
  `instrument:7f22b7c8-07f8-4a4b-bab3-a6ae90c70fb4`.
- `str(identifier)` and `to_wire()` return the typed wire form. `repr()` must also expose
  the kind and value.
- DuckDB stores only the UUID value in a type-specific column; the column contract supplies
  the kind. Public pandas dataframes expose the typed wire form as pandas `string` dtype.
- IDs are compared and ordered only with the same concrete class. Cross-kind equality is
  false; cross-kind ordering raises `TypeError`.
- IDs are never silently generated while deserializing a record with a missing identity.
- UUID version is validation metadata, not a sorting promise. Chronological ordering uses
  an explicit instant and deterministic tie-breaker.

`EventId` is the required lifecycle-ID subclass with kind token `event`. Other lifecycle
types may define their own final subclasses under the same rules.

### 5.3 Deterministic fixture identifiers

Production APIs do not derive opaque identities from user-visible names. Test and example
fixture builders may use UUID version 5 with a repository-owned namespace UUID and a
canonical fixture key. Such IDs must be marked as fixture-generated in builder code and
must not become the ingestion deduplication algorithm.

### 5.4 `ContentId`

`ContentId` represents the SHA-256 digest of an immutable byte sequence:

```python no-run
@dataclass(frozen=True, slots=True)
class ContentId:
    algorithm: Literal["sha256"]
    digest: bytes

    @classmethod
    def from_bytes(cls, value: bytes) -> Self: ...

    @classmethod
    def parse(cls, value: str) -> Self: ...

    def to_wire(self) -> str: ...
```

The wire and database form is `sha256:<64 lowercase hexadecimal digits>`. Uppercase,
missing algorithm prefixes, truncated digests, and unsupported algorithms are rejected.
The digest is calculated over the exact bytes supplied. Hashing structured values first
uses the canonical serialization contract in section 10.

Content hashes establish byte identity, not semantic safety, trustworthy provenance, or
causal correctness. Later identity plans must name every component included in a compound
identity rather than relying on the existence of a hash.

### 5.5 Qualified names

`QualifiedName` is the stable, user-facing name for datasets, definitions, components,
event types, and registered extensions. Its canonical text:

- contains 1 to 255 ASCII characters;
- contains two or more dot-separated segments;
- uses the pattern `[a-z][a-z0-9_]*` for each segment;
- cannot start with `persistra._` or contain a segment beginning with `_`;
- is compared case-sensitively after validation; and
- is never inferred from a Python import path.

Names beginning with `persistra.` are reserved for built-ins. Third-party and project
names use a stable owner or project prefix. Renaming a definition creates a distinct
definition identity; display labels are separate mutable metadata.

### 5.6 Schema versions

`SchemaVersion` is an integer in `[1, 2_147_483_647]`. It versions a serialized payload or
table contract, not the package. Version zero is reserved for unpersisted prototypes and
is rejected by managed writes. Readers must either support the exact version or perform a
registered forward read transformation; they never guess from field presence.

Semantic versions used by feature and label definitions use plan-08
`ResearchComponentVersion`, whose strict `MAJOR.MINOR.PATCH` contract is not
interchangeable with `SchemaVersion`. Experiment-version semantics remain owned by their
focused specification.

## 6. Time model

### 6.1 Instants

The public Python representation of an instant is an aware `datetime.datetime`. A valid
instant must:

- have non-`None` `tzinfo` and `utcoffset()`;
- convert to UTC without ambiguity;
- fall in the inclusive year range 0001–9999 supported by Python; and
- have microsecond precision.

`validate_instant(value)` returns the equivalent UTC datetime with `timezone.utc`. It
rejects naive datetimes and non-datetime values; it does not assume the machine timezone.
Python datetimes cannot carry precision below one microsecond, so no silent truncation is
needed at this boundary. Inputs from higher-precision sources must declare and apply a
rounding policy during ingestion before construction of the public record.

DuckDB stores instants as `TIMESTAMPTZ`, normalized to UTC. Wire and canonical forms use
RFC 3339 with exactly six fractional digits and `Z`, for example
`2026-07-15T14:30:00.000000Z`. Public pandas dataframes use
`datetime64[us, UTC]` where pandas and the installed backend support it; otherwise they use
the narrowest UTC-aware datetime dtype that round-trips every selected value. A query must
not return naive timestamps.

Leap seconds are not representable by Python or DuckDB and are rejected rather than
coerced. Persistra uses the civil UTC timeline exposed by those dependencies and does not
claim TAI or leap-second-aware elapsed-time accounting.

### 6.2 Domain dates

A venue session, fiscal period date, ex-date, record date, payment date, and similar civil
date is a `datetime.date`, stored as DuckDB `DATE` and serialized as ISO `YYYY-MM-DD`.
Such a date is not converted to an instant without an explicit calendar, timezone, and
boundary rule owned by the relevant domain plan.

### 6.3 Fixed durations

`Duration` is a frozen value object containing a nonnegative integer number of
microseconds in the range `[0, 9_223_372_036_854_775_807]`. It is stored as DuckDB
`BIGINT`, and its canonical text form is `<integer>us`, such as `90000000us` for 90
seconds.

Construction accepts an integer microsecond count or a `datetime.timedelta` whose exact
value fits the supported range. It rejects floats, booleans, negative values, and any
input that would lose sub-microsecond precision. `to_timedelta()` is exact for every valid
stored value. Addition and subtraction check overflow; subtraction cannot produce a
negative duration.
Multiplication and division require an integer operand and an exact result. A context that
requires positive duration, such as a bar width, validates `duration.microseconds > 0`.

`Duration` represents elapsed fixed time only. Calendar days, sessions, months, quarters,
and years are schedule concepts because their elapsed lengths vary. Latency, embargo, and
fixed-time bar plans must state whether they use elapsed `Duration` or calendar/session
counts and must not interchange them silently.

### 6.4 Intervals

All Persistra intervals are half-open: `[start, end)`. This applies to observation
windows, identifier validity, universe membership, leases, folds, and query ranges unless
a focused specification explicitly defines a point event instead.

`TimeInterval(start, end)` contains two valid UTC instants and requires `start < end`.
`contains(value)` implements `start <= value < end`; `overlaps(other)` returns true only
when the intersection has positive duration. Adjacent intervals do not overlap.

`EffectiveInterval(valid_from, valid_to=None)` uses the same membership rules. `None` for
`valid_to` means unbounded future validity, not an unknown end. `valid_from` is required.
When a source truly has unknown interval bounds, the record must carry an explicit quality
or unknown-bound field defined by its owning schema; it must not overload `None`.

Zero-duration observations are point events represented by one instant, not invalid empty
intervals. Date intervals are also half-open and use a separate owning record with
`date`-typed boundaries rather than coercing midnight UTC.

### 6.5 Temporal field meanings

Later canonical schemas must reuse these meanings:

| Field | Exact meaning |
| --- | --- |
| `event_at` | Instant when the represented market or business event occurred |
| `published_at` | Source-reported publication instant for this exact revision |
| `available_at` | Resolved first public-eligibility instant under the recorded policy |
| `ingested_at` | Instant Persistra durably received this exact revision into a batch |
| `source_updated_at` | Distinct source-reported update instant, when supplied |
| `recorded_at` | Instant Persistra durably created an internal lifecycle record |
| `valid_from`, `valid_to` | Half-open effective interval for an identity or state |
| `interval_start`, `interval_end` | Half-open period covered by an observation |

`event_at`, `published_at`, and `available_at` have no universal ordering. For example, an
announced corporate action may be publicly available before its future effective event.
For a record actually received by Persistra, `ingested_at` and `recorded_at` cannot be
later than the transaction's durable commit instant and cannot be generated from market
event time.

### 6.6 Availability quality

`AvailabilityQuality` has these stable persisted values:

| Value | Meaning | Safe by itself |
| --- | --- | --- |
| `observed` | Source supplied the revision-specific publication or availability instant | Yes |
| `policy_derived` | A versioned dataset policy derived availability from source fields | Policy-dependent |
| `ingestion_bounded` | Availability is no earlier than Persistra receipt because source timing is missing | No |
| `unknown` | No defensible availability bound is available | No |

Safety depends on the dataset policy and full lineage, not only this enum. A later
correction without revision-specific source timing must be `ingestion_bounded` with
`available_at >= ingested_at`; it cannot inherit the original revision's quality.

### 6.7 Clocks and deterministic time

State-changing services receive a `Clock` dependency:

```python no-run
class Clock(Protocol):
    def now(self) -> datetime: ...

@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime: ...

@dataclass(frozen=True, slots=True)
class FixedClock:
    instant: datetime
    def now(self) -> datetime: ...
```

`SystemClock.now()` returns `datetime.now(timezone.utc)`. `FixedClock` validates and
returns one UTC instant. The convenience `utc_now()` delegates to a process-default
`SystemClock` only for non-identity-bearing convenience code. Managed writes, tests, and
deterministic workflows must use their injected clock; monkeypatching global time is not
the primary test contract.

One transaction captures its operation timestamp once and reuses it for records intended
to be atomic peers. Ordering among peers uses an explicit sequence, never repeated calls
to obtain slightly different timestamps.

If the injected wall clock returns an instant earlier than the last locally persisted
`recorded_at`, the writer preserves the observed instant, allocates the next authoritative
sequence, and persists warning code `domain.time.clock_regression`. It does not rewrite the
instant or reorder records. A caller may configure clock regression as a fatal operational
policy, but that policy and failure are recorded.

### 6.8 Local time and daylight-saving behavior

Core domain primitives never accept a naive local datetime. A later calendar API may
accept a venue-local date and named boundary, then resolve it through the effective-dated
venue timezone. Ambiguous or nonexistent wall times require explicit resolution and may
not use the host timezone. UTC instants remain the persisted authority.

## 7. Fixed-precision numbers and money

### 7.1 Numeric storage profiles

Persistra uses these v3 profiles at domain and storage boundaries:

| Profile | DuckDB type | Canonical scale | Examples |
| --- | --- | --- | --- |
| `amount` | `DECIMAL(38, 12)` | 12 | cash, fees, P&L, prices |
| `quantity` | `DECIMAL(38, 12)` | 12 | shares, lots, order quantities |
| `rate` | `DECIMAL(38, 18)` | 18 | returns, rates, ratios |
| `source_numeric` | `DECIMAL(38, 18)` | semantic-tag dependent | mixed-kind canonical market-input/result columns only |

The corresponding maximum absolute value is determined by the DuckDB precision and scale.
Construction or arithmetic that cannot fit the target profile raises
`DecimalOverflowError`; it never saturates or falls back to float.

These are exact boundary and persistence profiles. Vectorized research calculations use
`float64` as required by the umbrella specification and convert explicitly at execution,
optimization, or accounting boundaries. Later accounting and order plans may impose a
coarser instrument, venue, broker, or currency quantum but may not increase stored
precision without revising this contract.

`source_numeric` is a tagged storage envelope, not an arithmetic or public value-object
profile. It is permitted only when one canonical market-input or normalization-result
column must hold values whose registered semantic kind varies by row or linked definition.
Amount-kind values must round-trip through `amount`; count-kind values must round-trip
through `quantity`; and rate/pure-kind values must round-trip through `rate`. The owning
dataset separately declares whether a quantity/count must be integral. The semantic tag
and unit are required lineage. Amount/quantity values therefore have six zero trailing
decimal places in the envelope and accept its explicit 20-integer-digit bound even though
their ordinary profile has a wider range.
Values outside the selected profile or envelope quarantine rather than round, saturate, or
change kind. Managed money, price, quantity, order, execution, and accounting columns never
use `source_numeric`.

Canonical serialization includes the semantic kind and uses the selected domain profile's
canonical text (12 fractional digits for amount/quantity, 18 for rate), not the envelope's
physical trailing-zero representation. This keeps identity independent of the generic
column encoding while preserving the exact tagged value.

### 7.2 Decimal input

`Money`, `Price`, `Quantity`, `NonNegativeQuantity`, and `Rate` accept `Decimal`, `int`, or
canonical decimal string input. They reject `float`, NumPy floating scalars, booleans,
NaN, positive or negative infinity, exponent-only strings, thousands separators, leading
or trailing whitespace, and locale-specific formats.

Input is quantized to its profile only when the discarded digits are all zero. Otherwise
construction raises `PrecisionLossError`. Negative zero is canonicalized to positive zero.
Canonical text has no exponent and exactly the profile's number of fractional digits.

Explicit conversion from a research float uses a separately named boundary function that
requires a quantum and rounding mode. The function first converts through the float's
shortest round-trippable decimal string; it records the chosen policy where the converted
value affects an artifact.

### 7.3 Currency

`Currency` is a frozen value object containing exactly three uppercase ASCII letters. It
accepts lowercase input by normalizing to uppercase, rejects surrounding whitespace, and
serializes as the three-letter code. The built-in registry contains active ISO 4217 codes
and their minor-unit metadata, including `USD` with quantum `0.01`.

The implemented market scope accepts only USD-denominated instruments and accounts in
ordinary workflows. The type is deliberately currency-explicit so unsupported currencies
fail at capability boundaries instead of requiring a domain-model replacement. A
syntactically valid but unregistered code may be preserved only in quarantined source
records; it cannot construct managed `Money` without an explicit registered metadata
entry.

No arithmetic converts currencies. Addition, subtraction, comparison, allocation, or
aggregation of different currencies raises `CurrencyMismatchError`. FX rates and base-
currency translation are outside 3.0.

### 7.4 `Money`

```python no-run
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    @classmethod
    def zero(cls, currency: Currency) -> Self: ...

    def quantize(self, quantum: Decimal, mode: RoundingMode) -> Self: ...

    def scaled_by(
        self,
        factor: Decimal,
        *,
        quantum: Decimal,
        mode: RoundingMode,
    ) -> Self: ...

    def ratio(self, other: Money, *, mode: RoundingMode) -> Rate: ...
```

`Money` uses the `amount` profile and permits positive, zero, or negative values. Same-
currency addition and subtraction return `Money`. `scaled_by()` is the only primitive
scalar multiplication operation and requires the output quantum and mode. `ratio()` uses
the fixed `rate` quantum, requires an explicit rounding mode, the same currency, and a
nonzero denominator. `__mul__` and `__truediv__` are not implemented because they cannot
carry the required rounding policy.

Cash settlement quantum is not applied at every intermediate calculation. The accounting
plan defines the posting and residual policy and must use explicit quantization so debits
and credits remain equal.

### 7.5 `Price`, `Quantity`, and `Rate`

- `Price` contains a nonnegative `amount`-profile decimal and `Currency`. It permits zero
  at the primitive layer so missing, liquidation, and validation workflows can represent
  source values before domain-specific disposition; a valid executable equity price must
  be strictly positive under the market and execution plans.
- `Quantity` contains a signed `quantity`-profile decimal. It represents position direction
  and changes, not an order-side convention.
- `NonNegativeQuantity` uses the same profile and requires a value greater than or equal to
  zero. Submitted order quantity must be strictly positive under the order plan.
- `Rate` contains a signed `rate`-profile decimal. Percent display is presentation only;
  `0.05` means five percent.

`Price.notional(quantity, *, quantum, mode)` returns `Money` in the price currency.
`Price.__mul__` is not implemented. The named method prevents multiplication from silently
discarding the up to 24 fractional digits in the exact product.

### 7.6 Rounding and quantization

`RoundingMode` has stable values:

- `half_even`
- `half_up`
- `down`
- `up`
- `floor`
- `ceiling`

They map directly to Python `decimal` modes. `down` and `up` mean toward and away from
zero; `floor` and `ceiling` retain their mathematical meanings. The project-wide default
for accounting amounts is `half_even`, but every execution, settlement, fee, tax-like
charge, and allocation boundary records its resolved mode and quantum. There is no
implicit process-global decimal context.

Arithmetic uses a local decimal context with precision 80 and traps enabled for invalid
operations, division by zero, and overflow. Final values are explicitly quantized and
checked against the target 38-digit profile. Eighty digits cover the exact product of two
38-digit supported operands plus guard digits for division into an 18-place result. An
operation raises a typed error when it cannot resolve into the requested target profile.
It must not inherit caller changes to `decimal.getcontext()`.

### 7.7 Equality and hashing

Fixed-precision values compare by exact canonical decimal and, where present, currency.
They do not compare equal to bare decimals, integers, or floats. Their Python hashes use
the canonical tuple of type, fixed-scale decimal text, and currency code. Tolerances are
query, reconciliation, and analysis policies; they are never part of value-object equality.

## 8. Domain events

### 8.1 Event roles

Persistra distinguishes:

- **Source observations:** revisioned facts ingested into canonical dataset tables.
- **Domain events:** immutable, typed lifecycle facts or decisions produced by managed
  services.
- **Simulation events:** scheduled visibility or processing items ordered by the event
  simulator.
- **Structured log events:** operational diagnostics that do not change domain state.

A source bar does not need to be duplicated into a generic domain-event table. A domain
event does not replace normalized order, fill, journal, or result tables. Simulation event
priority is defined by focused specification 13. Structured logs are defined by focused
specification 02 and never serve as accounting authority.

### 8.2 `EventType`

`EventType` contains a `QualifiedName` and a `SchemaVersion`. Its wire form is
`<qualified-name>@<version>`, for example `persistra.order.submitted@1`.

Built-in event names use a domain noun followed by a past-tense occurrence or explicit
availability transition. Required initial namespaces are:

- `persistra.catalog.*`
- `persistra.project.*`
- `persistra.database.*`
- `persistra.ingestion.*`
- `persistra.snapshot.*`
- `persistra.reference.*`
- `persistra.calendar.*`
- `persistra.universe.*`
- `persistra.market_data.*`
- `persistra.corporate_action.*`
- `persistra.adjustment.*`
- `persistra.fundamental.*`
- `persistra.estimate.*`
- `persistra.macro.*`
- `persistra.benchmark.*`
- `persistra.risk_free.*`
- `persistra.research.*`
- `persistra.portfolio.*`
- `persistra.order.*`
- `persistra.execution.*`
- `persistra.accounting.*`
- `persistra.experiment.*`
- `persistra.analysis.*`

Owning plans enumerate concrete event types. An event name/version pair is never reused
for a payload with changed meaning. Additive optional fields still require a new schema
version when their presence changes identity, replay, or consumer behavior.

### 8.3 `DomainEvent`

```python no-run
@dataclass(frozen=True, slots=True)
class DomainEvent(Generic[PayloadT]):
    event_id: EventId
    event_type: EventType
    event_at: datetime
    available_at: datetime
    recorded_at: datetime
    aggregate_kind: QualifiedName
    aggregate_id: EntityId
    aggregate_sequence: int
    payload: PayloadT
    correlation_id: EventId | None = None
    causation_id: EventId | None = None
```

Rules:

- All instants satisfy section 6.1.
- `aggregate_sequence` is a positive, gap-free integer within one aggregate's committed
  event history. The writer, not an event constructor, allocates it transactionally.
- `event_at` is the represented occurrence or effective instant. `available_at` is the
  earliest instant at which the event may be visible to research or simulation under its
  policy. Neither is universally ordered relative to the other.
- `recorded_at` is the internal durable-record timestamp and must not be used as public
  availability unless the event's policy explicitly says it is ingestion-bounded.
- `causation_id` identifies the immediate event that caused this event. `correlation_id`
  groups one workflow. A root event uses its own `event_id` as `correlation_id` when a
  workflow correlation is needed and has no causation ID.
- The payload is a registered frozen dataclass or an explicitly registered immutable
  scalar/tuple schema. Mutable mappings, arbitrary Python objects, and import-path-based
  class loading are rejected.
- Event construction validates shape but does not persist, publish, or mutate an aggregate.
- Committed events are append-only. Corrections are new event types or versions linked by
  causation; an old envelope is never edited.

An aggregate is a consistency and sequencing boundary, not an instruction to reconstruct
all state by replaying a generic event store. Owning repositories may persist normalized
state and an audit transition table in the same transaction.

### 8.4 Registration and serialization

Event payload codecs are registered explicitly on a project-owned immutable registry:

```python no-run
registry.register(
    event_type=EventType("persistra.order.submitted", 1),
    payload_type=OrderSubmittedV1,
    encoder=encode_order_submitted_v1,
    decoder=decode_order_submitted_v1,
)
```

Registration is explicit during project construction; importing a module does not mutate
a global registry. Duplicate registration is allowed only when the payload type and codec
identity are exactly equal. Unknown names or unsupported versions can be inspected as raw
canonical payload bytes but cannot be decoded into a managed payload or applied to state.

JSON is the required event wire encoding in 3.0. It uses UTF-8, sorted keys, no insignificant
whitespace, no NaN or infinity, canonical primitive serialization from section 10, and an
object as the top-level payload. Database tables may normalize payload fields and retain
the canonical payload plus content ID for audit.

### 8.5 Delivery and idempotency

Domain-event persistence is transactional with the state change it describes. In-process
delivery is at least once if a subscriber retries. Consumers persist an idempotency key of
`(consumer qualified name, event_id)` before exposing derived managed state. Duplicate
delivery must be a no-op with the original result, not a second state transition.

Persistra v3 does not promise an external message broker, cross-process delivery, or a
public subscribe-forever service. Callers observe events through repositories, result
queries, or bounded progress callbacks defined by owning plans.

## 9. Deterministic ordering

Opaque UUIDs never determine business order. Every ordered persisted sequence includes:

1. the relevant UTC instant;
2. an owning-plan priority or sequence field; and
3. the opaque ID as a final deterministic tie-breaker only.

For aggregate histories, `aggregate_sequence` is authoritative. For source observations,
revision and source sequence are defined by the ingestion plan. For simulation, the event
clock plan owns priority and visibility. SQL queries returning ordered public dataframes
must state and implement their full deterministic ordering; insertion order is never a
contract.

## 10. Canonical serialization

Identity-bearing structured values use canonical UTF-8 JSON with these rules:

- object keys are sorted lexicographically by Unicode code point;
- strings are NFC-normalized and escaped according to JSON;
- arrays preserve declared order;
- sets are forbidden unless the schema first converts them to a sorted array using an
  explicitly declared key;
- booleans and null use JSON literals;
- opaque IDs, content IDs, names, versions, dates, instants, currencies, and fixed-precision
  values use their canonical text forms;
- binary data uses unpadded base64url inside an explicitly typed field;
- integers use base-10 without leading zeros;
- floats are forbidden in identity material unless the owning specification defines a
  finite normalization algorithm; and
- unknown fields are rejected by managed encoders.

The serialized bytes include the owning schema's qualified name and schema version. A
compound identity hashes `b"persistra\x00" + canonical_bytes` with SHA-256 to prevent
accidental reuse of an unscoped external digest. Later identity specifications must supply
golden canonical byte and digest fixtures.

Canonical JSON provides stable internal identity input, not a promise that arbitrary JSON
from another implementation hashes identically without following this contract.

## 11. Failures and reason codes

All domain validation exceptions derive from `DomainValidationError` and expose a stable
`reason_code`, human message, field path when applicable, and non-secret context. Required
types and codes are:

| Exception | Reason code | Trigger |
| --- | --- | --- |
| `InvalidEntityIdError` | `domain.identity.invalid` | Malformed, zero, or wrong-kind ID |
| `InvalidContentIdError` | `domain.content_id.invalid` | Malformed or unsupported digest |
| `InvalidQualifiedNameError` | `domain.name.invalid` | Name violates section 5.5 |
| `UnsupportedSchemaVersionError` | `domain.schema_version.unsupported` | Reader cannot handle version |
| `NaiveDatetimeError` | `domain.time.naive` | Aware instant required |
| `InvalidInstantError` | `domain.time.invalid` | Instant cannot normalize or serialize |
| `InvalidDurationError` | `domain.duration.invalid` | Duration is negative, inexact, or malformed |
| `DurationOverflowError` | `domain.duration.overflow` | Duration arithmetic or conversion exceeds its target |
| `InvalidIntervalError` | `domain.interval.invalid` | Missing start or nonpositive duration |
| `InvalidCurrencyError` | `domain.currency.invalid` | Currency absent or unsupported |
| `CurrencyMismatchError` | `domain.currency.mismatch` | Cross-currency operation attempted |
| `InvalidDecimalError` | `domain.decimal.invalid` | Non-finite or disallowed input |
| `PrecisionLossError` | `domain.decimal.precision_loss` | Construction would discard digits |
| `DecimalOverflowError` | `domain.decimal.overflow` | Value exceeds profile precision |
| `InvalidPriceError` | `domain.price.invalid` | Price is negative or otherwise malformed |
| `InvalidQuantityError` | `domain.quantity.invalid` | Quantity violates signedness constraint |
| `UnknownEventTypeError` | `domain.event.unknown_type` | Event type is not registered |
| `InvalidEventError` | `domain.event.invalid` | Envelope or payload violates its schema |
| `DuplicateEventError` | `domain.event.duplicate` | ID reused with different content |

Normal absence remains a typed optional or owning-plan unavailable result. Programmer
type errors may still raise `TypeError`, but persisted validation and public service
boundaries translate actionable domain failures to the stable errors above.

## 12. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Same UUID text supplied to different ID classes | Values remain different; wrong typed prefix is rejected |
| UUID collision | Transaction fails; caller generates a new ID only for a genuinely new uncommitted entity |
| Same immutable content received twice | Content IDs match; owning service decides deduplication without changing lineage |
| Renamed dataset or component | New qualified name; aliases, if supported later, are explicit metadata |
| Naive datetime | Reject; never assume UTC or local time |
| Non-UTC aware datetime | Normalize to equivalent UTC instant |
| DST fold or gap | Calendar boundary must resolve explicitly; core primitive does not guess |
| Adjacent effective intervals | Valid and non-overlapping |
| Open-ended interval | `valid_to=None`; query cutoff still required where point-in-time safety demands it |
| Source precision finer than microseconds | Ingestion applies and records a dataset-specific rounding policy |
| Leap-second timestamp | Reject and quarantine at ingestion when applicable |
| Decimal with extra trailing zeros | Accept and canonicalize to fixed scale |
| Decimal with nonzero digits beyond scale | Reject unless caller invokes explicit quantization |
| Float passed to a domain numeric constructor | Reject even when apparently exact |
| Negative zero | Canonicalize to positive zero |
| Currency mismatch | Reject before arithmetic or aggregation |
| Unsupported currency source record | Preserve only in quarantine; do not construct managed money |
| Unknown event payload version | Preserve raw bytes for inspection; do not decode or apply |
| Duplicate event delivery | Idempotent no-op for the same ID and content |
| Duplicate event ID with different content | Invariant failure; never overwrite |
| Two events at the same instant | Owning priority and a validated stable source sequence decide; UUID never supplies business order |
| System clock moves backward | Preserve observed time, advance sequence, persist warning; optional strict policy may fail visibly |

## 13. Security and resource behavior

- Parsing an ID, name, decimal, or event payload is bounded by declared length and nesting
  limits. Event JSON defaults to 1 MiB and depth 32 unless an owning plan sets a smaller
  bound.
- Event decoding never imports a class named in serialized data and never executes an
  arbitrary object hook.
- Error context must omit credentials, unrestricted payload contents, and machine-local
  secrets.
- Canonical hashing streams large byte artifacts; callers are not required to load an
  entire file into memory merely to construct a `ContentId`.
- Decimal operations use local contexts and do not mutate process-global state.
- The system clock is not a security authority for provider publication time. Availability
  derives from source evidence and versioned policy.

## 14. Migration and compatibility effect

This is a greenfield v3 contract. No v2 identifier, timestamp, float-money, event, pickle,
or artifact representation is accepted or migrated. The clean-slate checkpoint deletes v2
application data and examples; no compatibility shim is added.

Before v3 schema stability, development databases may be declared disposable. Once a
primitive is persisted in a supported schema:

- changing UUID, fixed-decimal, timestamp, interval, or canonical serialization formats is
  a schema migration and identity-compatibility event;
- changing an event payload requires a new `SchemaVersion` and registered reader path;
- changing identity canonicalization cannot silently alter existing content identities;
  and
- supported copy/export migration is always forward and verified, never an in-place guess.

Configuration compatibility is owned by focused specification 02. Portable result-format
compatibility is owned by focused specification 15.

## 15. Acceptance tests

### 15.1 Identity tests

- Generate at least 10,000 IDs per concrete class and assert valid version-4, nonzero,
  unique values and round-trip through UUID, wire text, DuckDB, and pandas forms.
- Assert that a typed ID rejects a different kind prefix and never compares equal across
  classes even when the UUID bytes match.
- Verify UUID ordering is not used by repositories that promise chronological output.
- Verify SHA-256 content IDs against published FIPS 180-4 vectors and repository golden
  structured-value fixtures.
- Property-test qualified names at every length and grammar boundary.

### 15.2 Time tests

- Property-test aware datetimes across fixed offsets and IANA-zone DST transitions; all
  round-trip to the same UTC microsecond.
- Reject naive times, leap-second strings, invalid calendar values, and implicit host-
  timezone conversion.
- Property-test half-open interval membership, adjacency, intersection, and open-ended
  effective intervals.
- Round-trip duration boundaries through integer, `timedelta`, canonical text, DuckDB, and
  pandas; reject negative, inexact, overflow, and calendar-unit coercion.
- Assert all DuckDB and pandas query round-trips remain UTC-aware and microsecond-exact.
- Use `FixedClock` to prove atomic peer records receive one captured operation instant and
  deterministic explicit sequences.

### 15.3 Numeric tests

- Round-trip minimum, maximum, zero, and representative values for the three domain
  profiles through Python, DuckDB, canonical JSON, and pandas object/string boundaries
  without precision loss. Separately test every `source_numeric` semantic tag, trailing-
  zero rule, narrower integer bound, exact decode, and rejection path.
- Property-test every rounding mode for positive and negative halfway values.
- Reject float, non-finite, overflow, hidden precision loss, unsupported currency, and
  cross-currency arithmetic cases.
- Assert caller mutation of the global decimal context does not affect results.
- Verify `Price.notional()` and `Money.scaled_by()` cannot execute without a target quantum
  and rounding policy and that their special multiplication operators are unavailable.
- Verify accounting-style equal and opposite values remain exact after the same explicit
  quantization.

### 15.4 Event tests

- Round-trip every registered built-in event payload through canonical JSON with stable
  bytes and `ContentId` across processes.
- Reject global import-time registration, duplicate conflicting codecs, mutable payloads,
  unknown fields, oversized payloads, and unsupported versions.
- Transactionally persist an event and its normalized state change, then inject a failure
  at each write boundary and prove neither becomes partially visible.
- Deliver each event twice and prove consumer state changes once; reuse an ID with changed
  content and prove the invariant fails.
- Property-test gap-free aggregate sequence allocation under rollback and retry.
- Assert domain event order never depends solely on insertion order or UUID value.

### 15.5 Exit criteria

This plan is implementation-complete when:

- the package surface in section 4 exists and imports with base dependencies only;
- every primitive satisfies its unit and property tests;
- a DuckDB integration fixture round-trips all storage profiles;
- canonical identity fixtures are checked into textual test data;
- Pyright proves concrete entity-ID classes cannot be interchanged in public APIs;
- no domain module imports database, market, research, simulation, result, or presentation
  code; and
- lint, static types, tests, documentation checks, and the agreed coverage gate pass.

## 16. Review checklist for dependent plans

Every later focused specification must answer, where applicable:

- Which fields are opaque IDs, content IDs, natural keys, or external identifiers?
- Which timestamp expresses event, publication, availability, ingestion, recording,
  interval, or effective time?
- Is each interval half-open, and is an open end truly unbounded rather than unknown?
- What full key gives deterministic ordering when instants tie?
- Which decimal profile applies, and where are quantum and rounding resolved?
- Which values are vectorized floats and where do they cross into fixed precision?
- Which lifecycle changes emit registered domain events, and which normalized tables remain
  authoritative?
- What schema version and canonical serialization enter immutable identities?
- Which normal unavailable states are data and which invariant failures are exceptions?
- What migration or identity effect follows from a future contract change?

## 17. Umbrella-spec consistency

This plan resolves details intentionally delegated by the umbrella specification without
changing its project-level direction. In particular, it preserves:

- ticker-independent and revision-preserving identity;
- explicit event, availability, ingestion, effective, interval, and session time;
- UTC-aware instants and venue-local session dates;
- `float64` research calculations with fixed-precision execution and accounting boundaries;
- explicit rounding, precision, and tolerance policy;
- deterministic event ordering through later engine-owned priorities; and
- separation of source observations, simulation events, accounting authority, results,
  and presentation.

No umbrella requirement is relaxed. The concrete UUID, decimal-scale, canonical-JSON, and
event-envelope choices are local refinements owned by this focused specification.
