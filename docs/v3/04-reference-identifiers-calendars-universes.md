# Focused specification 04: reference identity, calendars, and universes

**Status:** Implementation-ready draft  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md),
[focused specification 02](02-project-databases-leases-copies-migrations.md),
[focused specification 03](03-catalog-ingestion-quarantine-snapshots.md)  
**Owners:** `persistra.domain.instruments`, `persistra.market.instruments`,
`persistra.market.calendars`, `persistra.market.universes`  
**Required before:** focused specifications 05–18  
**Last reviewed:** 2026-07-15

## 1. Purpose

This specification makes ticker-independent, point-in-time reference data concrete. It
defines the stable issuer, security, listing, instrument, venue, identifier, calendar,
classification, membership, and universe contracts used by every market, research,
portfolio, simulation, and result table.

It fixes which relationships are identity-defining, how source observations resolve to
those entities, how identifiers and memberships change over time, how venue schedules are
materialized and revised, and how universe evaluation preserves both eligible and rejected
candidates with exact reasons.

## 2. Scope and boundaries

### 2.1 In scope

- Issuer, security, listing, instrument, and venue identities and immutable relationships
- Supported and representable security kinds for US-listed equities and ETFs
- Effective-dated listing state and tradeable instrument terms
- Ticker, exchange ticker, FIGI, composite FIGI, CUSIP, ISIN, CIK, LEI, and vendor IDs
- Identifier namespace registration, normalization, resolution, ambiguity, and reuse
- Reference entity resolution without fuzzy or present-day shortcuts
- Versioned venue calendar definitions and materialized civil-date/session schedules
- Timezone, DST, holidays, breaks, early closes, and emergency schedule revisions
- Effective-dated classification schemes, hierarchies, and assignments
- Source universe membership observations
- Immutable research universe definitions, point-in-time evaluation, and eligibility audit
- Exact typed schemas, Python APIs, dataframe contracts, validation, errors, and tests

### 2.2 Out of scope

- Bars, trades, quotes, trading-status observations, corporate actions, and adjustments
- Fundamental, estimate, macro, benchmark, and risk-free datasets
- Broker symbology, broker asset IDs, or live symbol routing
- Warrants, rights, units, OTC instruments, and pre-separation SPAC units
- Specialized preferred-share or closed-end-fund analytics
- Full exchange rulebooks, auction imbalance data, or order-book schedules
- Index methodology calculation beyond supplied point-in-time membership
- Taxonomies for arbitrary alternative-data entities
- Feature, label, signal, portfolio, and simulation behavior

Corporate actions may cause new entities or effective reference changes, but focused
specification 05 owns their economic and entitlement records.

## 3. Normative decisions

1. Tickers and all external identifiers are attributes, never entity or relational keys.
2. Issuer, security, listing, and instrument identities are distinct and never reused.
3. One v3 listing represents one continuous venue admission of one security.
4. One v3 instrument maps one-to-one to one listing; it is the key used by market,
   portfolio, order, and accounting records.
5. A ticker change preserves listing and instrument identity; a venue move or genuine
   relisting creates a new listing and instrument.
6. Immutable identity relationships never change in place. A mistaken source mapping is
   corrected by a new resolution/revision, leaving any orphan identity auditable.
7. Identifier, listing, classification, and membership intervals are half-open and have
   revision-specific information availability.
8. Identifier resolution may return not found or ambiguous; it never chooses arbitrarily.
9. Calendar schedules are materialized, content-addressed, snapshot-pinned data. A library
   upgrade cannot silently change historical sessions.
10. Unsupported venues never receive a weekday-calendar fallback.
11. Universe evaluation starts from an explicit point-in-time candidate source, evaluates
    all applicable rules, and retains every candidate with reasons.
12. Present-day membership or identity data is unsafe for historical simulation.

## 4. Identity and enum surface

This plan adds these plan-01 typed IDs:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `IssuerId` | `issuer` | Legal/reporting entity |
| `SecurityId` | `security` | Financial claim issued by one issuer |
| `VenueId` | `venue` | Exchange or market segment lineage |
| `ListingId` | `listing` | Continuous admission of one security to one venue |
| `InstrumentId` | `instrument` | Tradeable listing used by market/simulation records |
| `EntityResolutionId` | `entity_resolution` | One source-key/entity mapping decision |
| `IdentifierNamespaceId` | `identifier_namespace` | Versioned external-ID normalization domain |
| `IdentifierAssignmentId` | `identifier_assignment` | One effective entity/identifier relationship |
| `CalendarId` | `calendar` | Venue calendar lineage |
| `ClassificationSchemeId` | `classification_scheme` | One hierarchy/methodology lineage |
| `ClassificationNodeId` | `classification_node` | One effective classification concept |
| `ClassificationAssignmentId` | `classification_assignment` | One entity classification relationship |
| `UniverseDefinitionId` | `universe_definition` | Immutable-versioned candidate/rule design |
| `UniverseEvaluationId` | `universe_evaluation` | One resolved point-in-time evaluation artifact |

### 4.1 Security kinds

`EntityKind` has stable values `issuer`, `security`, `venue`, `listing`, and `instrument`.
Every generic entity reference is the pair `(EntityKind, matching typed ID)` and validates
that the ID kind agrees; a bare UUID is not a public entity reference.

`SecurityKind` has stable values and support levels:

| Value | 3.0 support |
| --- | --- |
| `common_stock` | Direct |
| `etf` | Direct |
| `reit` | Direct, represented as an equity security with REIT classification |
| `adr` | Direct, with depositary and underlying links optional |
| `spac_common` | Direct after unit separation |
| `preferred_stock` | Representable; no specialized dividend/call guarantee |
| `closed_end_fund` | Representable; no specialized NAV/distribution guarantee |

Excluded kinds are `warrant`, `right`, `unit`, `otc_security`, `option`, `future`,
`fixed_income`, and `unknown_tradeable`. A source record for an excluded kind is
quarantined with `reference.security.unsupported_kind`; it is not coerced to common stock.

`SecurityStatus` is `active`, `inactive`, `merged`, `liquidated`, or `unknown`.
`ListingStatus` is `pending`, `active`, `suspended`, `inactive`, or `delisted`.
Trading halts are observations owned by plan 05 and do not mutate listing status.

### 4.2 Identifier kinds

`IdentifierKind` has stable values `ticker`, `exchange_ticker`, `figi`,
`composite_figi`, `cusip`, `isin`, `cik`, `lei`, and `vendor`. A namespace additionally
declares entity kinds, venue scope, uniqueness, case policy, licensing class, validation
algorithm, and normalization codec identity.

### 4.3 Information cutoffs and as-of context

`CutoffMode` has exact stable values `public` and `public_and_project`. Public mode applies
the revision-specific public-information cutoff only. Public-and-project mode additionally
requires one nonnull fixed project-knowledge cutoff and excludes revisions received later.
The mode is shared by reference queries, universe evaluation, and focused specification
07's research-dataset builder; those consumers do not define local variants.

The immutable `PublicCutoffPolicy` initially supports only exact fixed elapsed-time lag:

```python no-run
@dataclass(frozen=True, slots=True)
class PublicCutoffPolicy:
    lag: Duration = Duration(0)
    schema_version: int = 1
```

`PublicCutoffPolicy.at_decision()` is zero lag and
`PublicCutoffPolicy.lagged(Duration(...))` resolves `C(d) = d - lag`. Lag is nonnegative;
subtraction is plan-01 UTC/microsecond arithmetic and underflow fails. The canonical policy
schema/content ID and every resolved cutoff schedule enter evaluation identity. A new
policy kind requires a new schema version, algorithm identity, and calendar/cutoff fixtures.

`AsOfContext` contains exact snapshot/composite-snapshot identity, effective instant,
public cutoff instant, `CutoffMode`, optional project cutoff, and source-precedence policy
identity. It requires `project_cutoff_at` exactly in public-and-project mode and never
supplies clock-derived defaults. `CompositeAsOfContext` is the variant plans 12/13 consume:
identical fields with the snapshot identity fixed to one plan-03 `CompositeSnapshotId`,
whose recorded manifest resolves exactly one market snapshot per attached database; member
snapshots are never overridden per query, and a member absent from the composite manifest
is a validation error, not a fallback to `latest`. There is no universal ordering between effective and
public-cutoff instants for retrospective inspection; universe/decision consumers using a
`PublicCutoffPolicy` additionally require every resolved `C(d) <= d`.

`SessionDecisionAnchor` has stable values `open` and `close`. `SessionSelection` has values
`every_session`, `week_end`, `month_end`, and `quarter_end`. Universe evaluation and later
decision datasets share one immutable schedule specification:

```python no-run
@dataclass(frozen=True, slots=True)
class SessionDecisionSchedule:
    calendar: CalendarRef
    anchor: SessionDecisionAnchor
    selection: SessionSelection
    delay: Duration = Duration(0)
```

Selection uses venue `session_date`: week-end is the last session in the ISO week, and
month/quarter-end are the last sessions in the Gregorian month/quarter. Resolution obtains
enough pinned calendar coverage beyond requested UTC `[start_at, end_at)` to prove each
boundary and then keeps only decision instants inside that range. `decision_at` is the
selected session's open/close UTC instant plus exact nonnegative elapsed delay and must
precede the next session open. Delay overflow, missing boundary coverage,
duplicate/nonmonotone decisions,
or host-local/calendar-day arithmetic fails. The schedule definition, selected calendar
revisions, resolved decisions/session dates, and generator identity form its content ID.

## 5. Identity model and invariants

### 5.1 Entity meanings

- **Issuer:** the legal, reporting, or fund entity. One issuer may issue many securities.
- **Security:** one economic claim/share class. It has exactly one issuer for its lifetime.
- **Venue:** one MIC-defined exchange or segment lineage and its schedule association.
- **Listing:** one continuous admission of one security to one venue. A temporary halt or
  ticker change does not end it; delisting followed by a new admission does.
- **Instrument:** the tradeable key for one listing. In 3.0 each listing has exactly one
  instrument and each instrument exactly one listing.

The one-to-one listing/instrument distinction is deliberate: reference and identifier
records describe listing admission, while prices, orders, holdings, and settlement refer
to a tradeable instrument. Future instrument variants can be added without replacing
historical keys.

### 5.2 Immutable relationships

The following relationships are fixed at identity allocation:

```text
IssuerId 1 ── * SecurityId 1 ── * ListingId 1 ── 1 InstrumentId
                                      *
                                      │
                                      1 VenueId
```

A merger does not mutate `SecurityId.issuer_id`; the action terminates or exchanges the old
security and may introduce another. A venue change creates another listing. A source
correction that proves an allocated relationship wrong maps future/revised observations to
the correct entity and leaves the mistaken unreferenced identity for audit; managed IDs
are never reassigned.

### 5.3 Entity allocation

Entity resolution occurs during plan-03 validation. An adapter may supply a known typed ID
or resolvable external identifiers. The resolver uses snapshot-visible, cutoff-eligible
assignments and explicit source mapping decisions. Exact one-match resolution proceeds;
zero or multiple matches quarantine unless the dataset contract permits creating a new
entity from sufficient source evidence.

New entity creation requires a source-specific stable key, all identity-defining parent
relationships, and an explicit creation rule. Name or ticker similarity never creates or
merges entities. Manual resolution appends a versioned decision with operator, evidence,
source keys, effective interval, and event; it never edits prior mappings.

Every automatic, source-asserted, creation, or manual resolution produces an immutable
`EntityResolutionId` and content identity. Accepted source observations record the exact
resolution decision in lineage; rerunning resolution under a later identifier map cannot
change an older canonical revision.

## 6. Registered canonical datasets

The initial definitions use these exact qualified names and natural keys:

| Dataset | Natural key fields |
| --- | --- |
| `persistra.reference.issuer` | `source_issuer_key` |
| `persistra.reference.security` | `source_security_key` |
| `persistra.reference.venue` | `source_venue_key` |
| `persistra.reference.listing` | `source_listing_key` |
| `persistra.reference.instrument_terms` | `instrument_id`, `valid_from` |
| `persistra.reference.entity_resolution` | source entity kind/key, `valid_from` |
| `persistra.reference.identifier_assignment` | namespace ID/version, normalized value, entity kind/ID, scope, `valid_from` |
| `persistra.reference.calendar_date` | `calendar_id`, calendar version, `calendar_date` |
| `persistra.reference.classification_node` | scheme ID/version, code, `valid_from` |
| `persistra.reference.classification_assignment` | scheme ID/version, entity kind/ID, `valid_from` |
| `persistra.reference.universe_membership` | source universe key, instrument ID, `valid_from` |

Source keys are scoped by plan-03 `SourceId`. Every typed row is one-to-one with
`catalog.canonical_revisions` and inherits snapshot, revision, availability, batch, and
quality semantics. Dataset-specific source precedence is mandatory when a resolved view
combines providers.

### 6.1 Ownership, permissions, and atomicity

Reference masters, namespaces, assignments, calendar definitions/dates,
classifications, and source memberships belong to the selected market database's
`canonical` schema. Their registries and revision metadata remain in that database's
`catalog` schema. Only a `market_write` project naming that database may register or
ingest them, and it holds the plan-02 exclusive market lease. Entity allocation,
resolution lineage, accepted typed rows, catalog revisions, catalog-clock advancement,
and their domain events commit in the same market transaction under plan 03. A rejected
or quarantined disposition publishes none of those accepted-state changes.

Universe definitions, evaluations, eligibility rows, and rule outcomes belong to the
project-owned research database's `research` schema. Definition registration and
evaluation require `research_write`: the research database is exclusively leased and the
attached market databases are read-only under shared leases. One evaluation reads an
exact `CompositeSnapshotId` and publishes its definition/evaluation rows and domain event
in one research transaction. It never depends on a cross-file commit with a market
database. Read APIs work in `read_only` or `research_write`, use the plan-02 connection
manager, and require an explicit snapshot context; a live market writer therefore has the
same bounded wait/lease failure behavior defined by plan 02.

Market-role migrations own the `canonical` tables in sections 7–12. Research-role
migrations own the tables in sections 13–14. These are logical managed records, not
physical copies or portable exports. No operation exposes a connection, interpolated
table name, managed-write callback, or partially published file.

### 6.2 Shared observation lifecycle

The natural-key table above and the exact typed columns below define each dataset's
canonical payload. Plan-03 metadata supplies `SourceId`, dataset/version, payload/source/
observation content IDs, source record/revision keys, revision ordinal, publication,
resolved availability, availability quality, ingestion, batch, disposition, and catalog
sequence. Original observations use their registered source evidence and availability
policy. A correction receives independent publication and availability metadata and never
inherits the original revision's timing; absent correction evidence is at best
`ingestion_bounded` with `available_at >= ingested_at`, or `unknown` when no defensible
bound exists.

Every provider's rows remain separately queryable. A versioned source-precedence policy
selects a complete eligible row after snapshot and cutoff filtering; field-wise synthesis
and generic last-write-wins are forbidden. Quarantined rows can be remediated only through
the plan-03 child-batch mechanism. A corrected identity assertion allocates or resolves to
the proper immutable entity and leaves the mistaken identity auditable rather than
rewriting it.

If a correction changes a natural-key field, including `valid_from`, it uses plan 03's
single atomic disposition group: retract the old key's current revision and upsert the
corrected key. Reference datasets opt into retraction only with a provider withdrawal or
correction reason and exact target evidence. Query selection observes the retraction's own
cutoffs, so earlier information-time queries still see the then-known old value.

Accepted master allocations and observation revisions advance the catalog sequence and
enter the plan-03 rolling state and snapshot manifest through their catalog changes.
Validation and commit stream bounded record groups; provider conformance must cover
temporal evidence, corrections, identity conflicts, quarantine, retries, and atomicity.

## 7. Canonical entity and observation schema

### 7.1 Entity masters

```sql
CREATE TABLE canonical.issuers (
    issuer_id UUID PRIMARY KEY,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE canonical.securities (
    security_id UUID PRIMARY KEY,
    issuer_id UUID NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE canonical.venues (
    venue_id UUID PRIMARY KEY,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE canonical.listings (
    listing_id UUID PRIMARY KEY,
    security_id UUID NOT NULL,
    venue_id UUID NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE canonical.instruments (
    instrument_id UUID PRIMARY KEY,
    listing_id UUID NOT NULL UNIQUE,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

Master rows contain identity relationships only. Source-varying names, status, terms,
dates, and identifiers live in revisioned observation tables. Master creation and the
first accepted observation commit atomically under plan 03.

Resolution lineage is stored as:

```sql
CREATE TABLE canonical.entity_resolutions (
    canonical_revision_id UUID PRIMARY KEY,
    entity_resolution_id UUID NOT NULL UNIQUE,
    source_entity_kind VARCHAR NOT NULL,
    source_entity_key VARCHAR NOT NULL,
    resolved_entity_kind VARCHAR NOT NULL,
    resolved_entity_id UUID NOT NULL,
    resolution_method VARCHAR NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    decided_by VARCHAR,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE canonical.observation_entity_resolutions (
    canonical_revision_id UUID NOT NULL,
    entity_role VARCHAR NOT NULL,
    entity_resolution_id UUID NOT NULL,
    resolved_entity_kind VARCHAR NOT NULL,
    resolved_entity_id UUID NOT NULL,
    PRIMARY KEY (canonical_revision_id, entity_role, entity_resolution_id)
);

CREATE TABLE canonical.reference_temporal_evidence (
    canonical_revision_id UUID PRIMARY KEY,
    source_valid_from_date DATE,
    source_valid_to_date DATE,
    source_interval_convention VARCHAR NOT NULL CHECK (
        source_interval_convention IN ('effective_date', 'inclusive_end', 'exclusive_end')
    ),
    date_resolution_policy_content_id VARCHAR NOT NULL,
    calendar_schedule_content_id VARCHAR,
    CHECK (source_valid_from_date IS NOT NULL OR source_valid_to_date IS NOT NULL)
);
```

`resolution_method` is `source_asserted`, `exact_identifier`, `created`, or `manual`.
`decided_by` is required only for manual decisions and is a bounded local operator label,
not a credential. Conflicting eligible resolutions quarantine the affected disposition
group. Every accepted typed observation links all subject, parent, underlying, or venue
resolution decisions through `observation_entity_resolutions`; those links enter its
observation content and cannot change later. A revision with source civil-date boundaries
also has one `reference_temporal_evidence` row. It preserves whether the source supplied
only an effective date or treated its stated end date as inclusive or exclusive. The
writer requires `source_valid_to_date=NULL` for `effective_date` and a nonnull end for the
other conventions. The content-addressed policy resolves the evidence to the typed row's
UTC half-open interval. `calendar_schedule_content_id` is
required when that policy uses venue sessions and null otherwise. The evidence and policy
enter observation content and cannot be replaced later.

### 7.2 Issuer and security observations

```sql
CREATE TABLE canonical.issuer_observations (
    canonical_revision_id UUID PRIMARY KEY,
    issuer_id UUID NOT NULL,
    legal_name VARCHAR NOT NULL,
    domicile_country VARCHAR,
    incorporation_country VARCHAR,
    entity_status VARCHAR NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE canonical.security_observations (
    canonical_revision_id UUID PRIMARY KEY,
    security_id UUID NOT NULL,
    security_name VARCHAR NOT NULL,
    security_kind VARCHAR NOT NULL,
    share_class_title VARCHAR,
    security_status VARCHAR NOT NULL,
    underlying_security_id UUID,
    depositary_issuer_id UUID,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);
```

Country fields use ISO 3166-1 alpha-2 uppercase codes. ADR underlying/depositary links are
optional because providers often lack reliable mappings; missing links are explicit, not
inferred from names. ETF and REIT legal structures remain issuer/security attributes and
do not collapse those layers.

### 7.3 Venue, listing, and instrument terms

```sql
CREATE TABLE canonical.venue_observations (
    canonical_revision_id UUID PRIMARY KEY,
    venue_id UUID NOT NULL,
    operating_mic VARCHAR NOT NULL,
    segment_mic VARCHAR NOT NULL,
    venue_name VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    timezone_name VARCHAR NOT NULL,
    calendar_id UUID NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE canonical.listing_observations (
    canonical_revision_id UUID PRIMARY KEY,
    listing_id UUID NOT NULL,
    listing_status VARCHAR NOT NULL,
    is_primary_listing BOOLEAN NOT NULL,
    admitted_at TIMESTAMPTZ,
    delisted_at TIMESTAMPTZ,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE canonical.instrument_terms (
    canonical_revision_id UUID PRIMARY KEY,
    instrument_id UUID NOT NULL,
    currency VARCHAR NOT NULL,
    price_quantum DECIMAL(38, 12) NOT NULL,
    quantity_quantum DECIMAL(38, 12) NOT NULL,
    round_lot DECIMAL(38, 12) NOT NULL,
    whole_share_default BOOLEAN NOT NULL,
    settlement_policy_name VARCHAR NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);
```

MIC fields are ISO 10383 uppercase four-character codes. `segment_mic` may equal
`operating_mic`. Timezone names are IANA names accepted by `zoneinfo`, never fixed offsets.
One `VenueId` represents one segment-MIC lineage; a genuine MIC reassignment or replacement
creates a new venue and effective mapping rather than rewriting the old identity.
The 3.0 workflow accepts only `currency='USD'`; other currency rows quarantine at the
capability boundary rather than losing their source evidence.

Price/quantity quantum and round lot must be positive and fit plan-01 profiles. They define
reference constraints; order-specific precision also depends on effective venue/broker
policy in plan 13. Settlement policy names are qualified and effective-dated; plan 11 owns
their cash/asset behavior.

### 7.4 Effective intervals

All `valid_from`/`valid_to` intervals are UTC half-open intervals. `valid_to=NULL` means
unbounded, not unknown. Source-effective civil-date boundaries are preserved in
`canonical.reference_temporal_evidence`. A registered date-resolution policy converts
them to instants—for listing, ticker, and membership changes normally the applicable venue
session open—and its calendar/policy identity enters observation content and safety.

The policy contract is constructible and closed:

```python no-run
@dataclass(frozen=True, slots=True)
class DateResolutionPolicyRef:
    name: QualifiedName
    version: int
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class DateResolutionPolicy:
    name: QualifiedName
    version: int
    anchor: Literal["venue_session_open", "venue_session_close", "utc_midnight", "local_time"]
    non_session: Literal["next_session", "previous_session", "reject"] | None = None
    local_time: time | None = None
    ambiguous_local_time: Literal["earlier", "later", "reject"] = "reject"
    nonexistent_local_time: Literal["shift_forward", "reject"] = "reject"

@dataclass(frozen=True, slots=True)
class DateResolutionRequest:
    source_date: date
    policy: DateResolutionPolicyRef
    venue_id: VenueId | None
    calendar_version_id: CalendarVersionId | None

@dataclass(frozen=True, slots=True)
class ResolvedCivilDate:
    effective_at: datetime
    resolved_session_id: SessionId | None
    policy_content_id: ContentId
    calendar_content_id: ContentId | None
```

The installed policy `persistra.date_resolution.venue_session_open@1` requires venue,
calendar, and `non_session`,
calendar, maps a session date to that session's exact UTC open, maps a non-session date to
the next session, and raises `CalendarCoverageError` if the chosen session is outside
coverage. `venue_session_close` is analogous; `utc_midnight` forbids venue/calendar,
`non_session`, and `local_time` and uses `00:00:00Z`; `local_time` requires venue timezone,
`local_time`, and `non_session`, applies the stated
DST rules, and then converts to UTC. Unused fields are rejected. Registration persists the
canonical policy definition under `(qualified_name, version)`; duplicate unequal content,
unknown variants, missing calendar inputs, and rejected holiday/DST cases raise
`DateResolutionPolicyError`. Policy, source date, venue/timezone, resolved session, calendar
version/root, and output instant enter the observation content ID.

```sql
CREATE TABLE reference.date_resolution_policies (
    policy_name VARCHAR NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
    definition_json JSON NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    PRIMARY KEY (policy_name, policy_version)
);
```

`project.services.reference.date_resolution.register(policy)`, `.resolve(request)`, and
`.get(ref)` are the only public write/resolve/lookup surfaces; registration is
`research_write` only and resolution is bounded read-only.

Intervals for the same resolved entity and observation domain may be adjacent. Overlapping
contradictory rows from one source quarantine as a group. Multiple providers may overlap
only under an explicit source-precedence policy and remain separately queryable.

## 8. External identifier model

### 8.1 Namespace schema

```sql
CREATE TABLE canonical.identifier_namespaces (
    identifier_namespace_id UUID NOT NULL,
    namespace_version INTEGER NOT NULL CHECK (namespace_version >= 1),
    qualified_name VARCHAR NOT NULL,
    identifier_kind VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (identifier_namespace_id, namespace_version),
    UNIQUE (qualified_name, namespace_version)
);

CREATE TABLE canonical.identifier_assignments (
    canonical_revision_id UUID PRIMARY KEY,
    identifier_assignment_id UUID NOT NULL,
    identifier_namespace_id UUID NOT NULL,
    identifier_namespace_version INTEGER NOT NULL CHECK (identifier_namespace_version >= 1),
    raw_value VARCHAR NOT NULL,
    normalized_value VARCHAR NOT NULL,
    entity_kind VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    venue_scope_id UUID,
    is_primary BOOLEAN NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);
```

An assignment pins the namespace ID and version used to normalize it. Its identity remains
stable across source corrections to the same asserted mapping. A changed entity, namespace
ID/version, value, scope, or nonadjacent effective interval is a new assignment. The
canonical revision supplies publication/availability/ingestion time.

Changing normalization, uniqueness, scope, or entity-grain meaning is breaking and creates
a new namespace identity and qualified name. A new version under one identity may only
tighten nonbreaking validation, licensing, or display metadata while accepting every
prior canonical normalized value. Namespace registration is append-only and
snapshot-visible at `created_catalog_sequence`.

### 8.2 Built-in normalization

| Kind | Normalization and validation |
| --- | --- |
| `ticker` | Trim prohibited whitespace, uppercase ASCII, 1–32 chars matching `[A-Z0-9][A-Z0-9._/+^$-]*`; venue scope required |
| `exchange_ticker` | Same symbol grammar plus required MIC-scoped namespace |
| `figi` | Uppercase 12-character FIGI grammar and check digit |
| `composite_figi` | Same FIGI validation, namespace declares composite scope |
| `cusip` | Uppercase 9-character CUSIP with check digit; licensing class required |
| `isin` | Uppercase 12-character ISO 6166 value with Luhn check |
| `cik` | Decimal digits normalized to 10-character zero-padded form; issuer only |
| `lei` | Uppercase 20-character ISO 17442 value with check digits; issuer only |
| `vendor` | Namespace-specific NFC codec, 1–128 characters, no generic case folding |

Raw value is retained for audit when licensing permits. A licensed identifier may be
stored/queryable locally but excluded from sample fixtures, reports, and exports according
to namespace policy. A provider's symbol normalization never silently becomes the global
ticker codec.

### 8.3 Uniqueness and reuse

Namespaces declare whether one normalized value can identify more than one entity at the
same effective instant. Built-in FIGI, CUSIP, ISIN, CIK, and LEI namespaces are unique at
their declared entity grain. Ticker is unique only within venue scope and interval.
Ticker reuse after a nonoverlapping interval is valid and resolves to the historical
instrument. Concurrent conflicting assignments quarantine the entire conflict group.

An entity may have multiple simultaneous vendor IDs and, where the source supports it,
multiple nonprimary symbols. `is_primary` is source assertion, not identity. More than one
eligible primary ticker in the same source/venue interval is a validation conflict.

### 8.4 Resolution result

```python no-run
result = project.services.reference.resolve_identifier(
    IdentifierQuery(
        namespace="persistra.identifier.ticker.xnys",
        value="BRK.B",
        entity_kind=EntityKind.INSTRUMENT,
        effective_at=decision_at,
        public_cutoff=decision_at,
        project_cutoff=receipt_cutoff,
        snapshot=snapshot,
    )
)
```

The result is one of `IdentifierResolved(entity_ref, assignment_ref)`,
`IdentifierNotFound(reason)`, or `IdentifierAmbiguous(candidates, reason)`. Resolution:

1. resolves an explicit namespace version or the greatest version visible in the snapshot,
   then validates the namespace/value;
2. restricts revisions to the market snapshot;
3. applies public and optional project-knowledge cutoffs;
4. applies assignment effective interval and venue scope;
5. selects each assignment's highest eligible revision;
6. applies an explicit source-precedence policy if requested; and
7. returns exactly one, none, or all ambiguous candidates.

Only assignments pinned to the resolved namespace version participate. The result and
query lineage always expose that version; callers requiring long-lived reproducibility pin
it explicitly rather than relying on snapshot-relative latest.

Normal not-found/ambiguous states are data, not exceptions. APIs requiring one instrument
translate them into stable eligibility/rejection reasons or a typed configuration error.

## 9. Reference resolution and public queries

Reference queries require `SnapshotRef`, an information-cutoff mode, and effective instant.
They never default to the machine's current date. The service exposes:

```python no-run
reference.issuers.get(issuer_id, context=as_of)
reference.securities.get(security_id, context=as_of)
reference.listings.get(listing_id, context=as_of)
reference.instruments.get(instrument_id, context=as_of)
reference.instruments.history(instrument_id, snapshot=snapshot)
reference.identifiers.resolve(query)
reference.identifiers.history(entity_ref, snapshot=snapshot)
```

`AsOfContext` contains market snapshot, effective instant, public cutoff, optional project
cutoff, and source-precedence policy identity. The public cutoff may differ from effective
instant for retrospective inspection but simulation safety later verifies decision-time
compatibility.

Resolved views never merge columns from different providers independently. One versioned
source-precedence policy selects a complete eligible observation or returns a structured
conflict. Field-wise coalescing would create a synthetic source record and is forbidden
unless a separately registered normalization dataset explicitly defines it.

## 10. Calendar model

### 10.1 Dependency and materialization

The initial base dependency is `exchange-calendars>=4.13,<5`, with Python `zoneinfo` as the
timezone authority. The library is an audited schedule generator, not runtime truth.
Every generated calendar version records package/Python versions, the installed tzdata
distribution version when available, content IDs of the relevant system TZif files,
generator parameters, source/override content IDs, coverage, and complete output content
ID.

Generated civil-date records are ingested through plan 03 and pinned in market snapshots.
Upgrading `exchange-calendars`, Python, tzdata, or an override produces a new calendar
version and explicit diff; it never changes persisted sessions or a prior snapshot.

Initial release-gating calendar profiles cover at least 1990-01-01 through 2035-12-31:

| Qualified profile | Venue MIC | `exchange-calendars` generator |
| --- | --- | --- |
| `persistra.calendar.xnys` | `XNYS` | `XNYS` |
| `persistra.calendar.xnas` | `XNAS` | `XNAS` |
| `persistra.calendar.arcx` | `ARCX` | `ARCX` |
| `persistra.calendar.bats` | `BATS` | `BATS` |
| `persistra.calendar.baty` | `BATY` | Explicitly validated shared `BATS` schedule |
| `persistra.calendar.edga` | `EDGA` | Explicitly validated shared `BATS` schedule |
| `persistra.calendar.edgx` | `EDGX` | Explicitly validated shared `BATS` schedule |
| `persistra.calendar.us_equity_settlement` | not applicable | Reviewed explicit US securities-settlement fixture |

Each venue mapping requires its own golden official schedule fixture and explicit profile;
sharing a generator is declared and fixture-verified, not inferred from ownership,
country, or weekdays. If a shared schedule diverges, that venue receives a distinct
generator/override and a new calendar version.

The nonvenue settlement profile is consumed by plan 11. Each eligible date reflects the
reviewed intersection of securities-depository/payment-system business days required by
its versioned source policy; it is not inferred at runtime from an exchange session or a
federal-weekday calendar. Its definition records exact official-source/override content,
coverage, generator, and revisions through the same schema and snapshot rules. It has no
open/close trading meaning: an eligible settlement date uses the policy's configured UTC
settlement boundary for `open_at`/`close_at` solely to satisfy the common date schema, and
consumers must use the settlement policy rather than interpret it as a venue session.

### 10.2 Calendar definition and date schema

```sql
CREATE TABLE canonical.calendar_definitions (
    calendar_id UUID NOT NULL,
    calendar_version INTEGER NOT NULL CHECK (calendar_version >= 1),
    qualified_name VARCHAR NOT NULL,
    timezone_name VARCHAR NOT NULL,
    coverage_start DATE NOT NULL,
    coverage_end DATE NOT NULL,
    generator_content_id VARCHAR NOT NULL,
    generator_output_content_id VARCHAR NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (calendar_id, calendar_version),
    UNIQUE (qualified_name, calendar_version)
);

CREATE TABLE canonical.calendar_dates (
    canonical_revision_id UUID PRIMARY KEY,
    calendar_id UUID NOT NULL,
    calendar_version INTEGER NOT NULL CHECK (calendar_version >= 1),
    calendar_date DATE NOT NULL,
    is_session BOOLEAN NOT NULL,
    open_at TIMESTAMPTZ,
    break_start_at TIMESTAMPTZ,
    break_end_at TIMESTAMPTZ,
    close_at TIMESTAMPTZ,
    is_early_close BOOLEAN NOT NULL,
    closure_reason VARCHAR,
    UNIQUE (calendar_id, calendar_version, calendar_date, canonical_revision_id)
);
```

Every civil date in coverage has one applicable revision, including weekends/holidays,
so later emergency closure revisions are explicit. When `is_session=true`, `open_at` and
`close_at` are required with `open_at < close_at`; both break fields are either present and
strictly internal or null. When false, all phase instants are null and closure reason is
required (`weekend`, `scheduled_holiday`, `emergency`, or source-defined qualified code).

`calendar_date` is the venue-local session date when open. UTC instants remain authority.
Open membership is `[open_at, close_at)`; the exact close is a boundary/event, not an
instant inside regular continuous trading. Auction eligibility uses plan-13 policies and
does not infer order-book behavior from these times.

### 10.3 Availability and revisions

Regular-rule dates may be `policy_derived` from a reviewed versioned official calendar
policy. One-off holidays, emergency closures, and time changes use observed announcement
availability when possible. A correction without revision publication is ingestion-bounded
and unsafe, following plans 01 and 03.

Calendar point-in-time selection applies both effective calendar date and information
cutoffs. A strategy scheduling a future session can see only the calendar revision
available at its decision time. Retrospective operational reports may explicitly request
the final revised schedule and are marked retrospective.

A qualified profile resolves one `CalendarId`; an optional positive version pins one
generator version. Without an explicit version, a range query considers definitions in
descending `calendar_version` after restricting `created_catalog_sequence` to the market
snapshot. It chooses the first version that covers the entire requested civil-date range
and has one eligible selected `calendar_dates` revision for every date under the public
and optional project cutoff. It may fall back to an older version when a newer version was
not yet ingested or available. It never combines dates from different calendar versions.
When no version covers the full range, direct calendar APIs (`schedule`, `session`,
session navigation) raise `CalendarCoverageError`; availability-returning surfaces such as
the dataset builder instead record structured unavailability with the same reason code.

Within the chosen version, plan-03 revision selection chooses the highest eligible
revision for each date. The ordered calendar/version/range/date revision content IDs and
cutoff-policy identity form a resolved schedule manifest and
`calendar_schedule_content_id`. This
resolved content ID—not merely `generator_output_content_id`—pins the
decision instants used by universe evaluation and later market/simulation plans.

### 10.4 API and DST behavior

```python no-run
calendar = project.services.calendars.get(
    "persistra.calendar.xnys",
    context=as_of,
)
schedule = calendar.schedule(date(2026, 1, 1), date(2027, 1, 1))
session = calendar.session(date(2026, 7, 15))
next_session = calendar.next_session(date(2026, 7, 15), count=1)
```

Date ranges are half-open. `session()` returns `Session` or `NonSession`, never fabricates
weekday hours. `session_containing(instant)` returns an open session only for
`open_at <= instant < close_at`. `next_open`, `previous_close`, and session shifting require
materialized coverage and fail outside it.

`session_containing()` includes a scheduled break because the civil session still exists;
`is_continuous_trading(instant)` excludes `[break_start_at, break_end_at)`.
`next_session(d, count=1)` is strictly after `d`, and `previous_session` is strictly before
it; callers use `session(d)` when inclusive behavior is intended.

Generator conversion begins with named IANA venue-local wall times. Ambiguous DST times
require explicit `fold`; nonexistent times are errors. The system never uses host timezone
or a fixed EST offset. Validation compares generated UTC instants to official DST boundary
fixtures and rejects overlapping sessions or breaks.

## 11. Classification model

```sql
CREATE TABLE canonical.classification_schemes (
    classification_scheme_id UUID NOT NULL,
    scheme_version INTEGER NOT NULL CHECK (scheme_version >= 1),
    qualified_name VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    hierarchy_kind VARCHAR NOT NULL,
    allows_multiple BOOLEAN NOT NULL,
    licensing_class VARCHAR NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (classification_scheme_id, scheme_version),
    UNIQUE (qualified_name, scheme_version)
);

CREATE TABLE canonical.classification_nodes (
    canonical_revision_id UUID PRIMARY KEY,
    classification_node_id UUID NOT NULL,
    classification_scheme_id UUID NOT NULL,
    scheme_version INTEGER NOT NULL CHECK (scheme_version >= 1),
    code VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    parent_node_id UUID,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);

CREATE TABLE canonical.classification_assignments (
    canonical_revision_id UUID PRIMARY KEY,
    classification_assignment_id UUID NOT NULL,
    classification_scheme_id UUID NOT NULL,
    scheme_version INTEGER NOT NULL CHECK (scheme_version >= 1),
    entity_kind VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    classification_node_id UUID NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ
);
```

Supported entity kinds are issuer, security, and instrument. A hierarchy is acyclic within
each eligible version; parent and child intervals must overlap whenever the child is valid.
Single-valued schemes reject simultaneous assignments from one source. Multiple-valued
schemes declare combination semantics.

GICS, ICB, SIC, NAICS, and vendor schemes fit this contract, but licensing controls whether
definitions/mappings ship in fixtures or exports. Persistra never reverse-engineers a
licensed hierarchy. A missing classification remains unavailable and may cause a universe
rule rejection; it is not mapped to an invented `unknown` sector unless the scheme defines
such a node.

## 12. Source universe membership

```sql
CREATE TABLE canonical.universe_memberships (
    canonical_revision_id UUID PRIMARY KEY,
    source_universe_key VARCHAR NOT NULL,
    instrument_id UUID NOT NULL,
    membership_role VARCHAR NOT NULL,
    weight DECIMAL(38, 18),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    inclusion_reason VARCHAR,
    exclusion_reason VARCHAR
);
```

`membership_role` is `constituent`, `eligible`, `watchlist`, or a registered source value.
Weight is optional and does not become portfolio weight implicitly. An exclusion is a new
revision/effective interval, not deletion. Membership publication/availability and local
receipt come from its plan-03 canonical revision.

Weights must be finite and nonnegative. A source definition that claims normalized
constituent weights also validates each weight at most one and the effective cross-section
sum within its declared tolerance; other score/share fields require a separately named
dataset rather than overloading `weight`.

The adapter must supply historical effective intervals and publication evidence. A
present-day constituent list with no history may be explored but its dataset version is
unsafe for historical universe evaluation and simulation.

## 13. Universe definitions

### 13.1 Candidate sources

A `UniverseDefinition` starts with exactly one typed candidate expression:

- `ExplicitMembership(source_universe, roles)`
- `ActiveListings(venues, security_kinds)`
- `ExplicitInstruments(instrument_ids, effective_intervals)`
- `Union(candidates...)`
- `Intersection(candidates...)`

Every leaf is point-in-time. A bare Python list without effective intervals is valid only
for one declared evaluation instant; reusing it historically is rejected as structurally
unsafe. Candidate expressions deduplicate by `InstrumentId` while retaining all source
lineage and candidate reasons.

Evaluation first forms an **audit candidate envelope** from instrument identities present
in the selected snapshot and relevant to the requested interval. `ExplicitMembership`
includes membership histories whose validity intersects the interval;
`ActiveListings` includes listing lifecycles that intersect it; and
`ExplicitInstruments` includes every declared ID. Both `Union` and `Intersection` use the
union of child envelopes so an instrument rejected by a child is not silently lost.

At each decision instant, every leaf yields `pass`, `fail`, or `unavailable` under that
instant's public and optional project cutoffs. `Union` passes if any child passes, is
`unavailable` if none passes and at least one is unavailable, and otherwise fails.
`Intersection` fails if any child fails, is `unavailable` if none fails and at least one is
unavailable, and otherwise passes. An identity known from the immutable
snapshot but lacking an effective row receives `universe.candidate.not_effective`; a row
that exists in the snapshot but is not information-eligible receives
`universe.candidate.not_available`. Such knowledge is audit-only: simulation and strategy
decision datasets expose only rows that pass the candidate expression and every hard
eligibility rule. Rejected envelope rows remain queryable through the eligibility audit
and can never become strategy inputs, joins, counts, or cross-sectional denominators.

### 13.2 Eligibility rules

Rules are registered, versioned, ordered components with declared inputs, cutoffs,
parameters, missing behavior, safety/trust, and output reason schema. Initial reference
rules are:

- listing active and admitted at decision instant;
- security kind in allowed support levels;
- venue/calendar supported with a decision session;
- required identifier resolves exactly once;
- source membership effective and available;
- classification included/excluded under one scheme/version; and
- instrument terms/currency/quantity support valid.

Price, liquidity, fundamental, estimate, and custom rules plug into this same contract
after plans 05–08. Rule evaluation does not short-circuit after the first failure when later
rules can run safely; the audit retains every applicable reason.

### 13.3 Definition storage

```sql
CREATE TABLE research.universe_definitions (
    universe_definition_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    qualified_name VARCHAR NOT NULL,
    definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    execution_trust VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (universe_definition_id, definition_version),
    UNIQUE (qualified_name, definition_version)
);
```

Registration is explicit through a research-write project, never import-time global state.
A changed candidate expression, rule, parameter, missing policy, code identity, or reason
schema creates another definition version. An unrestricted Python rule is opaque/unsafe;
registration does not grant temporal safety.

## 14. Universe evaluation

### 14.1 Request and algorithm

```python no-run
evaluation = project.services.universes.evaluate(
    definition=UniverseRef("project.universe.liquid_us", version=4),
    composite_snapshot=composite_snapshot,
    decisions=SessionDecisionSchedule(
        calendar=CalendarRef("persistra.calendar.xnys", version=3),
        anchor=SessionDecisionAnchor.CLOSE,
        selection=SessionSelection.MONTH_END,
    ),
    start_at=datetime(2010, 1, 1, tzinfo=UTC),
    end_at=datetime(2026, 1, 1, tzinfo=UTC),
    cutoff_mode=CutoffMode.PUBLIC_AND_PROJECT,
    public_cutoff_policy=PublicCutoffPolicy.at_decision(),
    project_cutoff_at=project_cutoff,
)
```

The service:

1. resolves the immutable definition and composite snapshot;
2. materializes the decision instants from a pinned resolved calendar schedule manifest;
3. materializes the interval-bounded audit candidate envelope from the pinned snapshot;
4. evaluates every candidate leaf at each instant with dual cutoffs and creates one unique
   `(decision_at, instrument_id)` audit row;
5. loads rule inputs point in time without many-to-many expansion;
6. executes rules in declared dependency/order with explicit missing results;
7. records every rule outcome and inherited safety finding;
8. marks eligible only when every hard rule passes; and
9. persists immutable evaluation identity, summary, candidates, and outcomes atomically.

Evaluation is bounded by decision partitions and configurable instrument chunks. It does
not require the complete panel in pandas.

### 14.2 Storage

```sql
CREATE TABLE research.universe_evaluations (
    universe_evaluation_id UUID PRIMARY KEY,
    universe_definition_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    composite_snapshot_id UUID NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    cutoff_mode VARCHAR NOT NULL CHECK (cutoff_mode IN ('public', 'public_and_project')),
    public_cutoff_policy_content_id VARCHAR NOT NULL,
    project_cutoff_at TIMESTAMPTZ,
    calendar_schedule_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (start_at < end_at),
    CHECK (
        (cutoff_mode = 'public' AND project_cutoff_at IS NULL)
        OR (cutoff_mode = 'public_and_project' AND project_cutoff_at IS NOT NULL)
    )
);

CREATE TABLE research.universe_eligibility (
    universe_evaluation_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    session_date DATE,
    instrument_id UUID NOT NULL,
    eligible BOOLEAN NOT NULL,
    primary_reason_code VARCHAR NOT NULL,
    reason_codes_json JSON NOT NULL,
    warning_codes_json JSON NOT NULL,
    candidate_lineage_content_id VARCHAR NOT NULL,
    PRIMARY KEY (universe_evaluation_id, decision_at, instrument_id)
);

CREATE TABLE research.universe_rule_outcomes (
    universe_evaluation_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    rule_name VARCHAR NOT NULL,
    rule_version INTEGER NOT NULL CHECK (rule_version >= 1),
    outcome VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    evidence_json JSON NOT NULL,
    PRIMARY KEY (
        universe_evaluation_id,
        decision_at,
        instrument_id,
        rule_name,
        rule_version
    )
);
```

Candidate-expression outcomes are stored as ordered synthetic rule outcomes before the
eligibility rules, so envelope membership, boolean-expression results, and evidence are
content-addressed rather than inferred later. Outcomes are `pass`, `fail`, `warning`, or
`unavailable`. `primary_reason_code` is
`universe.eligible` for accepted rows; rejected rows choose the first hard failure in
declared rule order. All reasons remain sorted by rule order in canonical JSON.

`public_cutoff_policy_content_id` resolves the public cutoff at every decision (normally
the decision instant). `project_cutoff_at` is required for `public_and_project` and null
for public-only mode. The calendar schedule content ID pins the exact decision instants.
All three fields also enter `execution_content_id`.

The lineage/safety/licensing manifests fold the candidate expression, every rule input and
code identity, selected source/revision evidence, inherited findings, and source export
restrictions. They state whether custom rule behavior is managed-causal or opaque without
allowing an opaque/unsafe evaluation to relabel itself. Focused specification 07 inherits
these manifests before adding dataset inputs.

### 14.3 Required reason codes

Initial stable codes include:

- `universe.eligible`
- `universe.candidate.not_effective`
- `universe.candidate.not_available`
- `universe.listing.inactive`
- `universe.listing.not_admitted`
- `universe.security.unsupported_kind`
- `universe.instrument.terms_unavailable`
- `universe.instrument.currency_unsupported`
- `universe.identifier.not_found`
- `universe.identifier.ambiguous`
- `universe.calendar.unsupported`
- `universe.calendar.no_session`
- `universe.classification.unavailable`
- `universe.classification.excluded`
- `universe.rule.input_missing`
- `universe.rule.unsafe`
- `universe.rule.failed`

Rules may add versioned codes but may not reuse one with changed meaning.

## 15. Dataframe contracts

All public dataframes use explicit columns and plan-01 wire IDs. Initial schema versions:

| Dataframe | Schema | Required columns |
| --- | --- | --- |
| Instrument reference | `persistra.dataframe.instruments@1` | instrument/listing/security/issuer/venue IDs, kind, status, currency, primary ticker, effective and cutoff context |
| Identifier history | `persistra.dataframe.identifiers@1` | namespace ID/name/version, raw/normalized value, entity kind/ID, venue scope, primary flag, validity, availability, source, revision |
| Calendar schedule | `persistra.dataframe.calendar_schedule@1` | calendar ID/version, calendar/session date, is-session, open/break/close, closure, availability, revision |
| Classification | `persistra.dataframe.classifications@1` | scheme/version, entity, node/code/name/parent, validity, availability, source |
| Universe eligibility | `persistra.dataframe.universe_eligibility@1` | evaluation ID, decision, session date, instrument ID, eligible, primary/all reasons, warnings, lineage ID |

IDs use pandas `string`; instants are UTC-aware; civil dates remain explicit date columns;
booleans use nonnullable `bool` where required; decimal weights/terms use `object` Decimal
or canonical decimal string where pandas cannot preserve fixed precision. APIs state
ordering: normally decision/calendar date, instrument/entity ID, then revision ordinal.

## 16. Validation and disposition rules

### 16.1 Entity and instrument rules

- Parent issuer/security/listing/venue identities must exist in the selected validation
  catalog state or be created atomically by the batch's permitted resolution group.
- One security has one issuer; one listing one security/venue; one instrument one listing.
- Listing/instrument one-to-one uniqueness is mandatory.
- Security kind, status, country, MIC, currency, quantums, lots, and intervals validate
  against their exact enum/domain contracts.
- Excluded kinds and non-USD v3 workflow records quarantine, not coerce.
- Contradictory identity-defining parent relationships reject the resolution group.

### 16.2 Identifier rules

- Namespace/version must exist and support the entity kind/scope.
- Built-in checksum/grammar validation is structural for the assignment record.
- Effective intervals must be valid; ticker scope is required.
- Unique namespaces cannot overlap conflicting entity assignments after revision and cutoff
  semantics.
- Primary assignments cannot conflict within source/scope/interval.
- Unknown vendor normalization or licensing policy quarantines the record.

### 16.3 Calendar rules

- Coverage is contiguous in civil dates with exactly one applicable date record.
- Session phase presence/order, UTC awareness, timezone round-trip, DST fold/gap, breaks,
  overlaps, early-close flags, and closure reasons validate.
- Calendar definition/generator/schedule content IDs must reproduce.
- Venue/calendar assignment intervals cannot leave an active listing without declared
  coverage.
- Official golden holiday/emergency fixtures take precedence over package output; an
  unexplained difference rejects the calendar version.

### 16.4 Classification and membership rules

- Hierarchies are acyclic with valid parents and unique codes under scheme/version/interval.
- Assignment target and node exist; single-valued schemes cannot overlap.
- Membership target instrument exists, interval is valid, and optional weight is finite.
- Date-only effect resolution uses a registered calendar/policy and records its identity.
- Present-day-only membership is tagged unsafe rather than relabeled historical.

## 17. Safety and point-in-time behavior

Reference safety requires all of:

- immutable market/composite snapshots;
- revision-specific public and optional project cutoffs;
- effective intervals evaluated at the requested instant;
- explicit source precedence and nonambiguous entity resolution;
- safe calendar/date-resolution and membership policies; and
- safe universe candidate/rule execution.

An unsafe reference input taints the resolved object/evaluation. Exploratory APIs may
return it with findings. Simulation later rejects it by default. A label dependency can
never become a universe rule input.

Selecting `current`, omitting historical publication metadata, using an unversioned symbol
map, resolving by present-day ticker, or applying a current constituent list historically
is unsafe and cannot be hidden by materialization.

## 18. Events, errors, and diagnostics

### 18.1 Domain events

| Event type | Aggregate kind |
| --- | --- |
| `persistra.reference.issuer_created@1` | `persistra.aggregate.issuer` |
| `persistra.reference.security_created@1` | `persistra.aggregate.security` |
| `persistra.reference.venue_created@1` | `persistra.aggregate.venue` |
| `persistra.reference.listing_created@1` | `persistra.aggregate.listing` |
| `persistra.reference.instrument_created@1` | `persistra.aggregate.instrument` |
| `persistra.reference.identifier_namespace_registered@1` | `persistra.aggregate.identifier_namespace` |
| `persistra.reference.identifier_assigned@1` | `persistra.aggregate.identifier_assignment` |
| `persistra.reference.resolution_recorded@1` | `persistra.aggregate.entity_resolution` |
| `persistra.reference.classification_scheme_registered@1` | `persistra.aggregate.classification_scheme` |
| `persistra.calendar.version_registered@1` | `persistra.aggregate.calendar` |
| `persistra.universe.definition_registered@1` | `persistra.aggregate.universe_definition` |
| `persistra.universe.evaluation_completed@1` | `persistra.aggregate.universe_evaluation` |

Observation revisions remain plan-03 canonical rows/events; these events mark identity,
definition, resolution, and evaluation lifecycle changes without duplicating all payloads.
Creation, assignment, resolution, and evaluation occurrence IDs use aggregate sequence 1.
Identifier-namespace, classification-scheme, calendar, and universe-definition lineages
require contiguous versions and use that version as their gap-free aggregate sequence.
Exact registration/evaluation retries emit no event.

These master/definition/evaluation lifecycle events use the transaction's captured instant
for `event_at`, `available_at`, and `recorded_at`; point-in-time source availability remains
on the plan-03 revisions/manifests they reference.

### 18.2 Errors and reason codes

| Exception | Reason code |
| --- | --- |
| `ReferenceNotFoundError` | `reference.not_found` |
| `EntityResolutionError` | `reference.resolution.failed` |
| `EntityRelationshipError` | `reference.relationship.invalid` |
| `UnsupportedSecurityKindError` | `reference.security.unsupported_kind` |
| `IdentifierNamespaceError` | `reference.identifier.namespace_invalid` |
| `IdentifierValueError` | `reference.identifier.value_invalid` |
| `IdentifierConflictError` | `reference.identifier.conflict` |
| `CalendarNotFoundError` | `calendar.not_found` |
| `CalendarCoverageError` | `calendar.coverage.missing` |
| `CalendarInvariantError` | `calendar.invariant.failed` |
| `CalendarAmbiguityError` | `calendar.local_time.ambiguous` |
| `UniverseDefinitionError` | `universe.definition.invalid` |
| `UniverseEvaluationError` | `universe.evaluation.failed` |
| `UniverseInputUnsafeError` | `universe.input.unsafe` |

Identifier not-found/ambiguous and per-candidate rule failure are structured results, not
exceptions. Exceptions cover invalid configuration/API use or broken invariants.

## 19. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Issuer changes legal name | Same issuer; new effective observation |
| Company issues another share class | New security under same issuer |
| Ticker changes on same venue admission | Same listing/instrument; identifier intervals change |
| Security moves venue | New listing and instrument; old listing ends |
| Delisted security later relists | New listing/instrument even on same venue |
| Source mapped security to wrong issuer | New resolution/revision; never rewrite master relationship |
| Same ticker reused years later | Resolve by nonoverlapping interval to historical instrument |
| Same ticker overlaps two instruments on venue | Quarantine conflict; resolution ambiguous |
| Identifier absent | Return not found; universe rule may reject |
| Multiple providers disagree | Require precedence or return conflict; no field-wise synthesis |
| CUSIP cannot be redistributed | Keep licensing restriction through query/export |
| SPAC unit before separation | Quarantine as excluded unit |
| Preferred/CEF selected | Require explicit limited-support opt-in and persistent warning |
| Venue calendar unknown | Fail coverage/eligibility; never weekday fallback |
| Date outside materialized coverage | Raise coverage error |
| Emergency closure learned late | New revision with observed/ingestion-bounded availability |
| DST local time ambiguous | Require explicit fold and official fixture |
| Calendar library upgrade changes dates | New version/diff; old snapshot unchanged |
| Present-day universe used historically | Unsafe finding and simulation rejection by default |
| Candidate fails several rules | Preserve every reason; first hard rule is primary |
| Candidate lacks data for later rule | `unavailable` with configured fail/warn behavior |
| Duplicate candidates from union | One row with combined lineage, no many-to-many expansion |
| Empty candidate set | Valid empty evaluation with explicit coverage summary |

## 20. Security, licensing, and resource behavior

- Identifier and source strings have length/character bounds before normalization.
- No resolver runs fuzzy matching, external web lookup, or arbitrary user callback without
  explicit registered unsafe execution.
- Licensed identifiers/classifications carry a nonremovable licensing class into dataframe,
  report, sample, and export policy.
- Calendar generation has no network access and uses pinned dependency/source fixtures.
- Schedule and universe evaluation push range filters, revision selection, and joins into
  DuckDB and stream bounded decision/instrument partitions.
- Rule evidence is bounded and never includes complete licensed mappings by default.
- Qualified SQL identifiers come only from registered definitions under plan 02.
- A user cannot mutate master IDs, assignment intervals, calendar dates, or evaluation rows
  through public SQL.

## 21. Migration and compatibility effect

This is a greenfield v3 identity model. v2 symbol strings, Parquet partitions, calendar
helpers, universe files, and result symbols are not imported or mapped. There is no
symbol-to-instrument migration shim.

Within v3, changing an immutable parent relationship, identifier normalization, natural
key, interval boundary, calendar generator output, universe reason meaning, or dataframe
schema requires the appropriate new identity/version and plan-02 migration. Existing
entity IDs, assignments, schedule versions, snapshots, and evaluations never change to
match a new library release.

## 22. Acceptance tests

### 22.1 Identity and resolution

- Build hand-worked issuer/security/listing/instrument graphs for common stock, ETF, REIT,
  ADR, SPAC common, preferred, and CEF; verify exact parent and support invariants.
- Property-test that ticker/name/status changes cannot change entity IDs and venue
  move/relisting cannot reuse listing/instrument IDs.
- Generate ambiguous, absent, corrected, and conflicting source mappings; assert quarantine
  or explicit results without fuzzy matching.
- Inject failure around atomic master/first-observation creation and prove no orphan visible
  partial relationship.
- Exercise every operation under every project mode; verify market mutations require the
  named exclusive market lease, research writes use shared snapshot-pinned attachments,
  and failures publish neither partial normalized rows nor events.
- Round-trip source civil-date evidence, inclusive/exclusive conventions, policy/calendar
  identity, resolved UTC intervals, corrections, and snapshot-stable lineage.

### 22.2 Identifier contracts

- Golden-test every built-in normalization/checksum algorithm and boundary; preserve raw
  value and reject malformed/licensing-unknown input.
- Register several compatible namespace versions and a breaking replacement; verify
  composite-key persistence, snapshot-relative latest selection, explicit version pins,
  assignment isolation, and rejection of semantic changes under one identity.
- Generate effective interval adjacency, overlap, ticker reuse, primary conflicts, source
  precedence, and revisions under snapshot/dual cutoffs.
- Prove historical lookup never uses a present-day ticker assignment and returns every
  ambiguous candidate deterministically.
- Verify no canonical, market, research, order, or result table uses ticker as a relational
  key.

### 22.3 Calendars

- Materialize every named XNYS, XNAS, ARCX, BATS, BATY, EDGA, and EDGX 1990–2035 profile
  and compare its official golden sessions for ordinary days, holidays, early closes, DST
  boundaries, breaks, emergency closures, and rule changes.
- Materialize `us_equity_settlement` over the same coverage, compare reviewed depository/
  payment-system eligible dates and revisions, and prove venue sessions, host weekdays,
  exchange early closes, and settlement-boundary instants cannot substitute for its policy.
- Round-trip every local boundary through IANA timezone and UTC; reject gaps, unresolved
  folds, overlap, missing coverage, and unsupported venue mappings.
- Change generator/dependency/tzdata/override inputs and prove a new content/version is
  required while old snapshot schedules remain identical.
- Test future-session queries against historical availability so late closure knowledge
  cannot appear early.
- Seed overlapping generator versions with different ingestion/availability; verify
  deterministic whole-range fallback, explicit pinned-version behavior, and that no
  resolved schedule mixes versions.
- Golden-test every session decision anchor/selection across ISO-week, month, quarter,
  holiday, early-close, year, and requested-range boundaries; verify delay/next-open,
  monotonicity, coverage, and exact schedule content identity.

### 22.4 Classifications and memberships

- Property-test hierarchy acyclicity, interval-valid parents, assignment multiplicity,
  source revisions, licensing propagation, and explicit unavailable nodes.
- Test memberships with additions, removals, backdated corrections, weights, current-only
  unsafe data, date-resolution policies, and snapshot stability.

### 22.5 Universe evaluation

- Hand-calculate candidate union/intersection/dedup and every built-in rule across several
  decision instants; compare exact eligible and rejected rows/reason order.
- Sentinel-test ticker reuse, delisted/relisted instruments, unavailable classifications,
  unsupported calendars/kinds/currencies, and membership publication cutoffs.
- Property-test one row per decision/instrument, complete candidate partition, deterministic
  primary reason, evaluation idempotence, and no unexplained row loss.
- Seed identities whose effective or available rows fail at different decisions; verify
  they remain in the audit envelope with exact reasons while every simulation-facing
  input, join, count, and cross-sectional denominator excludes them.
- Verify opaque custom candidates/rules remain unsafe through persisted evaluation and
  simulation-facing queries.
- Run a large panel with bounded decision/instrument partitions and record peak memory.

### 22.6 Dataframes, events, and docs

- Contract-test exact dataframe columns/dtypes/order/schema versions, empty frames, and
  unavailable/ambiguous results.
- Round-trip every domain event through plan-02 event storage with normalized state atomicity.
- Run deterministic textual fixtures from source reference observations through snapshot,
  identifier history, calendar, classification, membership, and eligibility audit.
- Strict-build docs and execute API snippets once implemented.

### 22.7 Exit criteria

This plan is implementation-complete when:

- every supported market observation can reference stable `InstrumentId` without ticker
  identity;
- effective identifier lookup survives symbol, venue, and listing changes point in time;
- supported venue sessions are materialized, versioned, official-fixture-tested, and never
  replaced by weekday fallback;
- classification and membership histories preserve revision/availability semantics;
- universe evaluation returns every audit-envelope candidate with deterministic reasons
  and lineage while decision datasets expose only eligible members;
- present-day/unsafe inputs cannot masquerade as historical safe data;
- all schemas participate in plan-03 validation, revision, quarantine, and snapshots; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 23. Review checklist for dependent plans

Every later plan must state:

- which entity grain—issuer, security, listing, instrument, or venue—owns each record;
- how it resolves external IDs at effective and information time;
- which calendar/session/version defines intervals, decisions, bars, orders, or settlement;
- how delisting/relisting, ticker reuse, venue changes, unsupported kinds, and missing
  reference state behave;
- which universe evaluation and eligibility reasons gate research rows;
- whether classifications/memberships are source facts or derived features;
- how licensed fields propagate to artifacts/exports;
- which source-precedence policy combines providers; and
- how reference/calendar/universe changes affect snapshot and execution identity.

## 24. Umbrella and completed-plan consistency

This plan reuses plan-01 IDs, half-open intervals, UTC instants, decimal profiles, content
identities, and event envelopes; plan-02 database ownership, schemas, leases, migrations,
and events; and plan-03 datasets, revisions, availability, validation, quarantine, catalog
sequences, and market/composite snapshots.

It implements the umbrella issuer/security/listing/instrument distinction, external-ID
surface, USD US-listed scope, explicit venue and plan-11 settlement calendars, point-in-
time classification and membership, and eligibility audit. Its one-to-one v3 listing/
instrument relationship, materialized civil-date calendars, exact identifier codecs, and
normalized universe audit are local refinements. No ticker key, present-day historical
shortcut, synthetic weekday calendar, unsupported asset claim, mutable fact, or hidden row
loss is introduced.
