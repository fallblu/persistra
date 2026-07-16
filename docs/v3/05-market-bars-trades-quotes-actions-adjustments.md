# Focused specification 05: Market observations, actions, and adjustments

**Status:** implementation-ready greenfield v3 plan  
**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md),
[focused specification 02](02-project-databases-leases-copies-migrations.md),
[focused specification 03](03-catalog-ingestion-quarantine-snapshots.md), and
[focused specification 04](04-reference-identifiers-calendars-universes.md)  
**Owners:** `persistra.market.bars`, `persistra.market.trades`,
`persistra.market.quotes`, `persistra.market.status`,
`persistra.market.actions`, `persistra.market.adjustments`  
**Required before:** focused specifications 06–18  

## 1. Purpose

This plan defines the first price- and activity-bearing canonical datasets for v3. It
turns the umbrella requirements for raw fixed-time bars, executed trades, top-of-book
quotes, trading status, corporate actions, and adjustment views into exact identities,
schemas, temporal behavior, validation, APIs, and acceptance cases.

The design keeps source observations immutable and revision-aware. Adjusted prices are
derived research data, never replacement market facts. Corporate-action dates remain
domain-specific, and action visibility remains separate from economic effect. Missing
data, explicit no-trade observations, partial bars, halts, retractions, unsupported
entitlements, and adjustment failures are distinguishable rather than coerced into a
plausible-looking price.

## 2. Scope and boundaries

### 2.1 In scope

- Versioned session and fixed-duration bar specifications
- Raw regular- and extended-session OHLCV observations
- Executed trade prints with normalized and source condition metadata
- Venue top-of-book and consolidated best-bid/offer quote observations
- Optional trading-status observations, including explicit halts and resumes
- Corporate-action identity, revisions, source mappings, dates, terms, and consideration
  legs
- Ordinary/special dividends, splits, stock dividends, symbol/listing changes, mergers,
  acquisitions, spinoffs, delistings, liquidations, ETF distributions, and unresolved
  entitlements
- Raw, split-adjusted, total-return-adjusted, point-in-time, and retrospective views
- Immutable adjustment policy definitions, factor audit, and cached research
  materializations
- Exact source precedence, dataframe schemas, safety propagation, errors, events, and tests

### 2.2 Out of scope

- Full-depth order books, queue reconstruction, and quote/trade market replay
- Treating trades or quotes as required inputs to a 3.0 simulator
- Volume, dollar, tick, imbalance, or other non-time canonical bars
- Vendor-specific network clients, symbology clients, credentials, and raw archives
- Order eligibility, bar fill paths, spread/impact models, and execution costs
- Journal entries, entitlement posting, fractional-share handling, withholding, and tax
  accounting
- Cross-currency prices, FX conversion, and non-USD implemented workflows
- Automatic stitching across distinct instruments, listings, mergers, or spinoffs
- Fundamental, estimate, macro, benchmark, risk-free, feature, and label schemas

Plans 11 and 13 consume the action and bar contracts but own accounting and execution.
Nothing here claims tick-level simulator fidelity.

## 3. Normative decisions

1. Canonical prices are unadjusted source observations stored at plan-01 fixed precision.
2. Every observation references stable `InstrumentId`; ticker is display metadata only.
3. Bar authority is the explicit UTC half-open interval plus venue-local session date, not
   a provider's ambiguous timestamp label.
4. Session bars and fixed-duration bars use versioned `BarSpec`; actual start/end instants
   always remain on each observation.
5. A complete bar cannot be safely available before its interval ends. Partial bars are
   representable but unsafe and excluded by default.
6. Trades and quotes preserve deterministic source ordering and conditions but do not
   manufacture an order book or replay guarantee.
7. A halt exists only when an eligible trading-status observation says so. Missing price
   data never implies a halt.
8. Corporate-action availability, announcement, ex, record, effective, and payment time
   are distinct and never collapsed into one action date.
9. Action cancellation is a selected action status; a plan-03 retraction is reserved for
   withdrawal of an erroneous source observation.
10. Adjustments are backward-to-anchor derived views. Split factors affect price and
    volume inversely; cash-distribution factors affect price only.
11. Point-in-time adjustment applies only selected action revisions that are information-
    eligible and economically effective by the query cutoff. Retrospective adjustment is
    persistently unsafe for strategy or simulation input.
12. A missing reference price, ambiguous action, unsupported entitlement, nonpositive
    factor, or series-changing action produces explicit unavailable/segment-break output;
    no factor is guessed.
13. Market mutations use one exclusively leased market database. Adjustment definitions
    and materializations use the exclusively leased research database while reading exact
    composite snapshots through shared market leases.
14. Query and materialization identities include snapshot, source precedence, cutoffs,
    selected revisions, policies, calendars, code, and schema versions.

## 4. Identity and enum surface

This plan adds these plan-01 typed IDs:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `BarSpecId` | `bar_spec` | One versioned bar grid/phase lineage |
| `CorporateActionId` | `corporate_action` | One resolved economic action lineage |
| `AdjustmentPolicyId` | `adjustment_policy` | One versioned adjustment-method lineage |
| `AdjustmentMaterializationId` | `adjustment_materialization` | One immutable cached adjusted dataset |

Canonical source rows retain plan-03 `CanonicalRevisionId`; a separate opaque ID is not
allocated for every bar, trade, quote, or status observation. Provider keys remain natural
keys scoped by `SourceId` and are not public entity identities.

Stable enums are:

| Enum | Values |
| --- | --- |
| `BarIntervalKind` | `session`, `fixed` |
| `BarAlignment` | `session_open`, `utc_epoch` |
| `BarPhase` | `regular`, `pre_market`, `post_market`, `extended_combined` |
| `BarState` | `complete`, `partial`, `no_trade` |
| `MarketObservationScope` | `venue`, `consolidated` |
| `QuoteScope` | `venue_top`, `consolidated_nbbo` |
| `QuoteState` | `active`, `empty` |
| `TradingStatus` | `trading`, `halted`, `paused`, `auction`, `closed`, `suspended`, `unknown` |
| `CorporateActionStatus` | `announced`, `confirmed`, `completed`, `cancelled` |
| `ActionLegKind` | `cash`, `security`, `unresolved` |
| `AdjustmentPriceMode` | `raw`, `split`, `total_return` |
| `AdjustmentKnowledgeMode` | `point_in_time`, `retrospective` |
| `AdjustmentDirection` | `backward_to_anchor` |
| `AdjustmentRowStatus` | `adjusted`, `raw`, `unavailable`, `segment_break` |
| `PriceObservationState` | `selected`, `missing`, `stale`, `no_trade`, `partial_excluded`, `unavailable`, `invalid_summary` |

`CorporateActionKind` has these initial values:

- `ordinary_cash_dividend`
- `special_cash_dividend`
- `split`
- `reverse_split`
- `stock_dividend`
- `symbol_change`
- `listing_change`
- `merger`
- `acquisition`
- `spinoff`
- `delisting`
- `liquidation`
- `etf_distribution`
- `unresolved_entitlement`

New action kinds require a schema/version review; source strings do not become enum values
implicitly.

## 5. Registered datasets and ownership

### 5.1 Canonical dataset definitions

Initial plan-03 datasets use these exact names and natural keys. `SourceId` is implicit in
every revision chain.

| Dataset | Natural key fields |
| --- | --- |
| `persistra.market.bar` | instrument, bar spec ID/version, scope/venue or aggregation name/version, interval start/end |
| `persistra.market.trade` | `source_trade_key` |
| `persistra.market.quote` | `source_quote_key` |
| `persistra.market.trading_status` | `source_status_key` |
| `persistra.market.corporate_action` | `source_action_key` |

Source trade, quote, status, and action keys are required, bounded canonical strings. A
provider with partition/sequence keys combines them through its registered codec; it may
not substitute local row number, receipt order, or a random UUID. Source timestamp-label,
condition-code, sequence, correction, cancellation, and aggregation semantics are part of
the source/dataset definition identity.

All accepted upserts have one typed payload keyed one-to-one by
`canonical_revision_id`. Provider corrections use plan-03 linear revisions; cancellations
or withdrawals of erroneous rows use its exact-target retraction contract. A correction
to a natural-key byte uses one atomic old-key retraction/new-key upsert disposition group.

Every dataset opts into only these registered retraction reasons. “Shared reasons” below
means `market.retraction.source_withdrawal` and
`market.retraction.natural_key_correction`:

| Dataset | Allowed reasons |
| --- | --- |
| Bar | `market.retraction.source_withdrawal`, `market.retraction.natural_key_correction` |
| Trade | the shared reasons plus `trade.retraction.source_cancelled` |
| Quote | the shared reasons; an explicit empty quote is an upsert, not a retraction |
| Trading status | the shared reasons; a resume is another status upsert |
| Corporate action | the shared reasons; cancellation of a real action is an action-status revision |

The shared natural-key-correction reason requires the atomic replacement defined by plan
03. Dataset definitions pin reason/evidence schemas; arbitrary provider text cannot trigger
retraction.

### 5.2 Database modes and transactions

Bar-spec registration, action-master allocation, and observation ingestion require
`market_write` for one named market database under its exclusive lease. Typed payloads,
action masters, plan-03 revision metadata, resolution lineage, catalog state, findings,
and domain events publish in the same market transaction. Market-role migrations own all
`canonical` tables in this plan.

Raw queries work in `read_only` or `research_write` with shared market leases and explicit
market/composite snapshots. Adjustment-policy registration and materialization require
`research_write`; research-role migrations own their `research` tables. A materialization
reads already immutable market snapshots and commits all metadata, factors, adjusted rows,
and its event in one research transaction. It never relies on a cross-database write.

Plan-02 lease waits, live-writer failures, connection ownership, SQL identifier controls,
and transactional recovery apply unchanged. These records are logical database state, not
verified physical copies or portable exports.

### 5.3 Shared revision and availability behavior

Plan-03 metadata supplies source/dataset version, source and observation content IDs,
revision ordinal, event/publication/availability/ingestion time, availability quality,
batch, disposition, and catalog sequence. Each provider remains independently queryable.
Resolved views apply snapshot and dual cutoffs before one versioned source-precedence
policy chooses a complete row. No field-wise coalescing or generic last-write-wins occurs.

Original complete bars normally derive availability from interval end plus a registered
publication latency; trades, quotes, and status normally derive it from event time plus a
reviewed feed latency. Direct source publication evidence takes precedence. Corporate
actions use revision-specific announcement/publication evidence, never ex or payment date
as a silent availability substitute. Every correction has independent timing; missing
correction evidence is `ingestion_bounded` or `unknown` under plans 01 and 03.

Quarantine remediation uses linked child batches. Every accepted observation/retraction,
bar/action definition, and action-master allocation advances catalog state and is covered
by later market snapshots. Validation and ingestion remain chunked and bounded.

Every accepted bar, trade, quote, status, and action upsert links its exact subject,
instrument, venue, target, successor, and other entity-resolution decisions through plan
04's `canonical.observation_entity_resolutions`. Those immutable links enter observation
content; rerunning a later identifier map cannot redirect an older market revision.

## 6. Point-in-time query context

Raw market APIs require:

- one exact `MarketSnapshotId` or containing `CompositeSnapshotId` plus market database
  name;
- half-open event/interval range;
- public cutoff or versioned public-cutoff policy;
- optional project-knowledge cutoff;
- source-precedence policy identity;
- selected instruments or a pinned `UniverseEvaluationId`; and
- explicit inclusion policies for partial, no-trade, condition, and unsafe rows.

Selection first applies snapshot high-water, then public/project knowledge, then plan-03
revision/retraction state, source precedence, effective reference identity, and domain
filters. Query output exposes selected `CanonicalRevisionId`, availability quality, source,
and warnings. Simulation-facing callers cannot request moving `latest` or retrospective
selection.

A `UniverseEvaluationId` selector uses only rows whose persisted eligibility is true.
Rejected audit-envelope candidates and their existence never enter joins, row counts, or
cross-sectional market frames. Exploratory callers may instead provide explicit instrument
IDs, but that choice and any missing eligibility audit remain visible in lineage/safety.

Empty results are valid typed frames with coverage reasons. Tick queries require both a
bounded instant range and an instrument/venue restriction. The default dataframe ceiling
is 5,000,000 rows; callers may lower it or stream deterministic 250,000-row pandas chunks.
Crossing the ceiling raises before unbounded materialization and recommends narrower
partitions or streaming.

## 7. Bar specifications and schema

### 7.1 Versioned `BarSpec`

```sql
CREATE TABLE canonical.bar_specs (
    bar_spec_id UUID NOT NULL,
    bar_spec_version INTEGER NOT NULL CHECK (bar_spec_version >= 1),
    qualified_name VARCHAR NOT NULL,
    interval_kind VARCHAR NOT NULL CHECK (interval_kind IN ('session', 'fixed')),
    nominal_interval_us BIGINT,
    alignment VARCHAR NOT NULL CHECK (alignment IN ('session_open', 'utc_epoch')),
    phase VARCHAR NOT NULL CHECK (
        phase IN ('regular', 'pre_market', 'post_market', 'extended_combined')
    ),
    phase_boundary_policy_content_id VARCHAR NOT NULL,
    allow_short_final_interval BOOLEAN NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (bar_spec_id, bar_spec_version),
    UNIQUE (qualified_name, bar_spec_version),
    CHECK (
        (interval_kind = 'session'
            AND nominal_interval_us IS NULL
            AND alignment = 'session_open'
            AND NOT allow_short_final_interval)
        OR (interval_kind = 'fixed'
            AND nominal_interval_us IS NOT NULL
            AND nominal_interval_us > 0)
    )
);
```

For `session`, `nominal_interval_us` is null, alignment is `session_open`, short-final is
false, and one bar covers the selected pinned calendar phase. For `fixed`, duration is a
positive plan-01 `Duration`. `session_open` grids restart at the selected phase open;
`utc_epoch` grids align to integer duration multiples from Unix epoch. Fixed bars may not
cross session/phase boundaries. A registered short-final policy permits the last phase bar
to be shorter; otherwise a remainder is an explicit coverage gap, not a stretched bar.

The regular phase uses the pinned plan-04 open/close/break schedule. Pre-market,
post-market, and combined extended phases require a separately versioned local-time/
holiday/override boundary policy whose content ID is stored on `BarSpec`; they are never
inferred from a generic fixed offset. Its resolved UTC boundaries and the calendar
schedule both enter validation and query lineage.

Initial installed specs are:

- `persistra.bar.session.regular`
- `persistra.bar.1h.regular`
- `persistra.bar.1m.regular`
- `persistra.bar.1s.regular`

The fixed specs use `session_open`; 1h permits a short final interval, while 1m and 1s tile
the regular US session. Arbitrary positive durations can be registered with explicit
alignment, phase, remainder, schema, and validation identity. A changed grid meaning
creates a new spec version; a changed interval kind/duration allocates a new `BarSpecId`
and qualified name.

### 7.2 Canonical bars

```sql
CREATE TABLE canonical.bars (
    canonical_revision_id UUID PRIMARY KEY,
    instrument_id UUID NOT NULL,
    bar_spec_id UUID NOT NULL,
    bar_spec_version INTEGER NOT NULL CHECK (bar_spec_version >= 1),
    observation_scope VARCHAR NOT NULL CHECK (
        observation_scope IN ('venue', 'consolidated')
    ),
    venue_id UUID,
    aggregation_name VARCHAR,
    aggregation_version INTEGER CHECK (aggregation_version >= 1),
    aggregation_content_id VARCHAR,
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    observed_through_at TIMESTAMPTZ NOT NULL,
    session_date DATE NOT NULL,
    bar_phase VARCHAR NOT NULL CHECK (
        bar_phase IN ('regular', 'pre_market', 'post_market', 'extended_combined')
    ),
    calendar_schedule_content_id VARCHAR NOT NULL,
    bar_state VARCHAR NOT NULL CHECK (bar_state IN ('complete', 'partial', 'no_trade')),
    currency VARCHAR NOT NULL,
    open_price DECIMAL(38, 12),
    high_price DECIMAL(38, 12),
    low_price DECIMAL(38, 12),
    close_price DECIMAL(38, 12),
    volume DECIMAL(38, 12) NOT NULL,
    vwap DECIMAL(38, 12),
    notional_amount DECIMAL(38, 12),
    trade_count BIGINT,
    source_condition_codes_json JSON NOT NULL,
    CHECK (interval_start < interval_end),
    CHECK (
        interval_start < observed_through_at
        AND observed_through_at <= interval_end
    ),
    CHECK (volume >= 0),
    CHECK (trade_count IS NULL OR trade_count >= 0),
    CHECK (
        (observation_scope = 'venue'
            AND venue_id IS NOT NULL
            AND aggregation_name IS NULL
            AND aggregation_version IS NULL
            AND aggregation_content_id IS NULL)
        OR (
            observation_scope = 'consolidated'
            AND venue_id IS NULL
            AND aggregation_name IS NOT NULL
            AND aggregation_version IS NOT NULL
            AND aggregation_content_id IS NOT NULL
        )
    )
);
```

The aggregation name/version/content ID pin a registered qualified definition such as a
licensed US consolidated-feed aggregation; it is never mislabeled as the instrument's
listing venue.
Venue-scoped rows identify the actual observation venue. The effective listing and terms
remain reachable through immutable `InstrumentId` and exact plan-04 resolution lineage.

For `complete` and `partial`, all OHLC fields are nonnull, strictly positive, quantum-valid,
and volume is positive; a nonnull trade count is positive. For `no_trade`, all OHLC/VWAP/
notional fields are null, volume and nonnull trade count are zero, and the source must
explicitly assert no activity. Persistra never creates a no-trade row merely because a bar
is missing. `vwap` and notional are optional source observations, not recomputed silently.

Canonical rows retain raw decimals. Analytical frames convert prices, quantities, and
amounts explicitly to finite `float64`; exact-record APIs return plan-01 `Price`,
`Quantity`, and `Money` values with effective instrument quantums.

### 7.3 Interval and session rules

Every bar interval is UTC half-open `[interval_start, interval_end)`. `session_date` and
phase resolve against one plan-04 `calendar_schedule_content_id` recorded in the payload
and validation lineage. A session bar exactly matches that phase. A fixed bar matches its
spec grid and actual duration except the explicitly permitted short final interval. No bar
crosses a calendar session, declared phase, or scheduled break boundary unless the
session-bar spec explicitly covers that break. Trading halts do not change the bar grid;
a halt may overlap an interval and remains independent status evidence.

`observed_through_at` is the source observation's actual activity horizon and equals the
plan-03 `event_at`. It equals `interval_end` for complete/no-trade rows and is strictly
before end for partial rows. Complete/no-trade `available_at` must be at or after
`interval_end`; partial availability must be at or after `observed_through_at`. A provider
claim earlier than its activity horizon quarantines as temporally impossible. A partial
bar remains unsafe and never supersedes complete data invisibly. Valid state progression
is partial to later partial/complete/no-trade, or final complete/no-trade to an explicitly
evidenced final correction; a final row cannot regress to partial. Every revision has its
own availability. Daily/session-close decisions can use a bar only after its selected
revision is available.

Plans 12–13 may create a narrowly typed **execution-outcome projection** from one exact
later-completed pinned raw bar. At the session open event it can reveal only `open` as the
modeled execution/mark outcome, with instrument, session, price quantum, exact revision,
snapshot, project cutoff, and projection implementation root. It cannot expose high, low,
close, VWAP, notional, trade count, or full-session volume; it is unavailable to ordinary
market queries, research datasets, features, signals, forecasts, constructors, and any
strategy context before the open event. The canonical bar remains unavailable until its
own source `available_at`, which is preserved separately in lineage.

This projection models an economically observed open using archived daily data; it does
not claim the provider published a complete bar at open. Its simulation reveal instant is
the open, while source availability remains at/after interval end. Using the same bar's
eventual volume to constrain an open fill is a separate retrospective fidelity assumption;
the causal default uses lagged volume/ADV. Any new field-level reveal requires a focused
schema/safety/fidelity review rather than a generic OHLC row slice.

## 8. Bar validation and query behavior

Required structural/domain rules include:

- instrument, spec, venue/aggregation, currency, terms, and calendar resolution;
- exact spec version, interval grid, phase, session date, and calendar coverage;
- `low <= open <= high`, `low <= close <= high`, and, when present,
  `low <= vwap <= high`;
- positive prices, finite nonnegative quantities/amounts, quantum compliance, and no
  float/NaN/infinity ingestion;
- state-dependent nullability and activity consistency;
- observed-through/event equality, final-state horizon, and nonregressing revision state;
- no conflicting same-source intervals or duplicate natural keys;
- complete-bar availability not before interval end;
- source condition and aggregation codes declared by the dataset version; and
- deterministic cross-record coverage checks for missing, overlap, and unexpected phase
  intervals.

An OHLC/domain/grid violation quarantines its record or atomic interval group. Missing
expected bars and statistically implausible gaps, returns, volumes, or VWAP deviations are
warnings by default; they do not fabricate replacements. A source contract can make a
declared coverage failure stricter.

```python no-run
bars = project.services.market.bars.query(
    instruments=instrument_ids,
    spec=BarSpecRef("persistra.bar.session.regular", version=1),
    start=datetime(2010, 1, 1, tzinfo=UTC),
    end=datetime(2026, 1, 1, tzinfo=UTC),
    context=as_of,
    include_partial=False,
    include_no_trade=True,
)
```

Rows order by `(interval_start, instrument_id, observation_scope, venue/aggregation,
canonical_revision_id)`. Default queries exclude partial bars, retain explicit no-trade
rows, and return a separate coverage audit for expected intervals with selected, missing,
no-trade, partial-excluded, quarantined-summary, unavailable, and retracted states. A
missing bar never becomes a carried close or zero-volume synthetic bar.

`bars.classify_at(instrument, decision_at, context, staleness_policy)` returns a value and
status audit without silently carrying one:

- `selected`: one complete eligible bar satisfies the versioned maximum age/session rule;
- `stale`: the last eligible complete bar exists but exceeds that rule, retaining its age
  and revision only as diagnostic evidence;
- `no_trade`: an exact eligible source no-trade row covers the expected interval;
- `partial_excluded`: only a partial eligible row exists under the default policy;
- `unavailable`: a snapshot-visible candidate exists but fails an information cutoff;
- `invalid_summary`: only quarantined/conflicting candidate findings exist, with no value;
- `missing`: no selected, unavailable, or invalid candidate exists for expected coverage.

Trading status is an orthogonal axis returned beside this state: eligible halt/pause/etc.,
or `status.unavailable`. Thus stale, missing, invalid, unavailable, no-trade, and halted are
distinct. A stale result never becomes selected without a later explicit valuation/fidelity
policy, and even then retains its stale warning and source revision.

Stable audit reason codes are `market.price.selected`, `market.price.missing`,
`market.price.stale`, `market.price.no_trade`, `market.price.partial_excluded`,
`market.price.unavailable`, and `market.price.invalid_summary`; status absence is
`status.unavailable`. The staleness-policy content ID and evaluated age/session distance
enter the audit identity.

Unavailable-candidate and quarantined-finding detail is audit-only. Strategy-facing
datasets receive no value, future candidate key, source, or evidence and cannot distinguish
future existence through joins/counts; plan 07 maps these diagnostics into its safe no-value
contract while retaining the full audit outside strategy context.

## 9. Executed trades

### 9.1 Schema

```sql
CREATE TABLE canonical.trades (
    canonical_revision_id UUID PRIMARY KEY,
    source_trade_key VARCHAR NOT NULL,
    instrument_id UUID NOT NULL,
    venue_id UUID NOT NULL,
    currency VARCHAR NOT NULL,
    source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
    price DECIMAL(38, 12) NOT NULL CHECK (price > 0),
    quantity DECIMAL(38, 12) NOT NULL CHECK (quantity > 0),
    trade_condition_codes_json JSON NOT NULL,
    raw_condition_codes_json JSON NOT NULL,
    price_forming BOOLEAN NOT NULL,
    volume_forming BOOLEAN NOT NULL,
    extended_hours BOOLEAN NOT NULL,
    correction_reference_key VARCHAR
);
```

The plan-03 `event_at` is execution/print event time. `source_sequence` is the provider's
registered deterministic sequence within its partition; its partition identity is part of
`source_trade_key` when needed. A source without reproducible ordering is structurally
unsafe and uses canonical revision ID only as a final tie-breaker, never receipt order as
market chronology.

`venue_id` is the resolved execution/reporting market center represented by the source.
Off-exchange prints of listed instruments may resolve to a registered reporting-facility
venue; they are not relabeled as the listing venue. Unresolved required venue identity
quarantines. The normalized condition list is sorted and deduplicated under a versioned
source codec. Raw codes remain ordered exactly as supplied when licensing permits.

`price_forming` and `volume_forming` are audited results of the registered condition policy,
not universal facts inferred ad hoc by callers. A policy change creates a new dataset
version and does not rewrite prints. `correction_reference_key` preserves source linkage;
the corrected print is a normal revision or old-key retract/new-key upsert under plan 03.
A cancelled print becomes a retraction with source evidence.

### 9.2 Query and validation

Trade validation requires resolved instrument/venue/terms at `event_at`, USD currency,
positive quantum-valid price/quantity, known condition codes or an explicit vendor-code
namespace, monotone unique sequence within the declared partition, and consistent
correction lineage. Sale-condition oddities that are contractually valid persist as
warnings/flags. Impossible values, unresolved identity, reused sequence/key conflicts, or
invalid correction targets quarantine the atomic group.

```python no-run
trades = project.services.market.trades.query(
    instruments=instrument_ids,
    start=start_at,
    end=end_at,
    context=as_of,
    price_forming=None,
    chunk_rows=250_000,
)
```

Rows order by `(event_at, source_sequence, source_trade_key UTF-8 bytes,
canonical_revision_id)`. Filters for price-/volume-forming and extended-hours prints are
explicit. No query converts prints into fills or assumes that source sequence represents
queue priority across venues.

## 10. Top-of-book quotes

### 10.1 Schema

```sql
CREATE TABLE canonical.quotes (
    canonical_revision_id UUID PRIMARY KEY,
    source_quote_key VARCHAR NOT NULL,
    instrument_id UUID NOT NULL,
    quote_state VARCHAR NOT NULL CHECK (quote_state IN ('active', 'empty')),
    quote_scope VARCHAR NOT NULL CHECK (
        quote_scope IN ('venue_top', 'consolidated_nbbo')
    ),
    venue_id UUID,
    bid_venue_id UUID,
    ask_venue_id UUID,
    currency VARCHAR NOT NULL,
    source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
    bid_price DECIMAL(38, 12),
    bid_size DECIMAL(38, 12),
    ask_price DECIMAL(38, 12),
    ask_size DECIMAL(38, 12),
    quote_condition_codes_json JSON NOT NULL,
    raw_condition_codes_json JSON NOT NULL,
    indicative BOOLEAN NOT NULL,
    CHECK ((bid_price IS NULL) = (bid_size IS NULL)),
    CHECK ((ask_price IS NULL) = (ask_size IS NULL)),
    CHECK (bid_price IS NOT NULL OR bid_venue_id IS NULL),
    CHECK (ask_price IS NOT NULL OR ask_venue_id IS NULL),
    CHECK (
        (quote_state = 'active' AND (bid_price IS NOT NULL OR ask_price IS NOT NULL))
        OR (quote_state = 'empty'
            AND bid_price IS NULL
            AND bid_size IS NULL
            AND ask_price IS NULL
            AND ask_size IS NULL
            AND bid_venue_id IS NULL
            AND ask_venue_id IS NULL)
    ),
    CHECK (bid_price IS NULL OR bid_price > 0),
    CHECK (ask_price IS NULL OR ask_price > 0),
    CHECK (bid_size IS NULL OR bid_size >= 0),
    CHECK (ask_size IS NULL OR ask_size >= 0),
    CHECK (
        (quote_scope = 'venue_top' AND venue_id IS NOT NULL
            AND bid_venue_id IS NULL AND ask_venue_id IS NULL)
        OR (quote_scope = 'consolidated_nbbo' AND venue_id IS NULL)
    )
);
```

The plan-03 `event_at` is the source quote-state event time. A row is a source-observed
top-of-book state/change, not depth and not a promise that all earlier states were
received. One-sided active quotes are valid and explicit. A size of zero means the source
reported zero; null means the side is absent. `empty` means the source explicitly cleared
all displayed top-of-book sides. It does not mean a feed gap, stale quote, closure, or halt.

For `venue_top`, `venue_id` identifies the quoting venue. For `consolidated_nbbo`, bid/ask
venue IDs identify contributing venues when supplied and may be null only when the
registered feed omits them. The source definition identifies the consolidated feed and
NBBO method. Persistra does not synthesize NBBO from incomplete venue rows in the
canonical table.

### 10.2 Locks, crosses, staleness, and query

Two-sided quotes derive exact diagnostic state:

- `bid < ask`: normal positive spread;
- `bid = ask`: locked;
- `bid > ask`: crossed.

Locked/crossed states are not rewritten. A source condition explicitly allowing them
commits with a diagnostic; otherwise the record quarantines or warns according to the
registered policy. Spread and midpoint are derived `float64` query columns and never
stored as canonical authority. Quote age/staleness is a query/fidelity policy measured
from `event_at` and selected availability, not a mutation of the quote.

Validation also requires instrument/venue/terms resolution, USD, quantum-valid sides,
known condition semantics, deterministic keys/sequences, and consistent consolidated
venue fields. Query rows order by `(event_at, source_sequence, source_quote_key UTF-8
bytes, canonical_revision_id)` and use the same bounded streaming API as trades.

```python no-run
quotes = project.services.market.quotes.query(
    instruments=instrument_ids,
    scope=QuoteScope.CONSOLIDATED_NBBO,
    start=start_at,
    end=end_at,
    context=as_of,
    include_indicative=False,
)
```

Observed quotes may later inform a spread model, but unavailable arrival quotes cannot be
replaced with an unmarked estimate and this query does not drive market replay.

Immutable public `TradeObservation`, `QuoteObservation`, and later status record models
expose canonical revision ID, `event_at`, `available_at`, source sequence/key, instrument/
venue identity, and the typed payload above. A future replay simulator can reference those
records from plan-01 simulation events without changing their schema. Plan 05 neither
persists one generic domain event per tick nor assigns replay priority/queue semantics.

## 11. Trading-status observations

```sql
CREATE TABLE canonical.trading_status_observations (
    canonical_revision_id UUID PRIMARY KEY,
    source_status_key VARCHAR NOT NULL,
    instrument_id UUID NOT NULL,
    venue_id UUID NOT NULL,
    source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
    trading_status VARCHAR NOT NULL CHECK (
        trading_status IN (
            'trading', 'halted', 'paused', 'auction', 'closed', 'suspended', 'unknown'
        )
    ),
    status_reason_code VARCHAR,
    expected_resume_at TIMESTAMPTZ,
    source_condition_codes_json JSON NOT NULL
);
```

The plan-03 `event_at` is the effective status-transition instant. Eligible observations
from one selected source define a step function ordered by `(event_at, source_sequence,
canonical_revision_id)` until another status row arrives. Source precedence selects one
complete status stream; fields are not merged across feeds. A `halted` or `paused` state
remains in force until an explicit eligible transition says otherwise. An expected resume
is informational and never ends a halt by itself.

Status data is optional. Its absence yields `status.unavailable`; it does not imply
`trading`, `halted`, or `closed`. Calendar closure is distinct from an instrument/venue
status. Bars may be absent during a halt, but validation does not fabricate status from
that absence. Later execution policies may reject or defer orders only when their pinned
status source and cutoffs make the state eligible.

Validation requires resolved instrument/venue, known registered status/reason semantics,
nondecreasing source order, and `expected_resume_at > event_at` when present. Contradictory
same-sequence transitions quarantine as a group.

## 12. Corporate-action identity and schema

### 12.1 Economic identity and source resolution

`CorporateActionId` identifies one economic action on one subject security, optionally
limited to one instrument/listing. It is not a vendor announcement ID. Multiple source
action keys may resolve to the same action only through exact vendor cross-reference,
issuer/exchange evidence, or an immutable manual resolution. Similar dates or amounts
alone never auto-merge actions.

```sql
CREATE TABLE canonical.corporate_actions (
    corporate_action_id UUID PRIMARY KEY,
    action_kind VARCHAR NOT NULL,
    subject_security_id UUID NOT NULL,
    subject_instrument_id UUID,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

Action kind and subject relationship are identity-defining. If source evidence later
proves them wrong, revised observations resolve to a new action and the mistaken master
remains orphan-auditable. Master creation and the first accepted source observation are
atomic. One action may affect every instrument for a security when
`subject_instrument_id` is null; expansion to instruments uses effective plan-04 reference
state at the action instant and is persisted in downstream lineage.

### 12.2 Observation and leg storage

```sql
CREATE TABLE canonical.corporate_action_observations (
    canonical_revision_id UUID PRIMARY KEY,
    corporate_action_id UUID NOT NULL,
    source_action_key VARCHAR NOT NULL,
    action_status VARCHAR NOT NULL CHECK (
        action_status IN ('announced', 'confirmed', 'completed', 'cancelled')
    ),
    resolution_method VARCHAR NOT NULL CHECK (
        resolution_method IN (
            'source_cross_reference', 'issuer_or_exchange_evidence', 'created', 'manual'
        )
    ),
    resolution_evidence_content_id VARCHAR NOT NULL,
    announced_date DATE,
    announced_at TIMESTAMPTZ,
    declaration_date DATE,
    ex_date DATE,
    ex_at TIMESTAMPTZ,
    record_date DATE,
    payable_date DATE,
    payment_at TIMESTAMPTZ,
    effective_date DATE,
    effective_at TIMESTAMPTZ,
    expiration_date DATE,
    share_ratio DECIMAL(38, 18),
    terms_basis VARCHAR CHECK (
        terms_basis IN ('pre_action', 'post_action', 'not_applicable')
    ),
    date_policy_content_id VARCHAR NOT NULL,
    calendar_schedule_content_id VARCHAR,
    action_fingerprint_content_id VARCHAR NOT NULL,
    reference_revision_ids_json JSON NOT NULL,
    source_terms_json JSON NOT NULL,
    CHECK (share_ratio IS NULL OR share_ratio > 0)
);

CREATE TABLE canonical.corporate_action_legs (
    canonical_revision_id UUID NOT NULL,
    leg_ordinal INTEGER NOT NULL CHECK (leg_ordinal >= 1),
    leg_kind VARCHAR NOT NULL CHECK (leg_kind IN ('cash', 'security', 'unresolved')),
    target_security_id UUID,
    target_instrument_id UUID,
    cash_per_subject_unit DECIMAL(38, 12),
    quantity_per_subject_unit DECIMAL(38, 18),
    currency VARCHAR,
    entitlement_code VARCHAR,
    terms_basis VARCHAR NOT NULL CHECK (
        terms_basis IN ('pre_action', 'post_action', 'not_applicable')
    ),
    leg_details_json JSON NOT NULL,
    PRIMARY KEY (canonical_revision_id, leg_ordinal),
    CHECK (
        (leg_kind = 'cash'
            AND cash_per_subject_unit IS NOT NULL
            AND cash_per_subject_unit > 0
            AND currency IS NOT NULL
            AND currency = 'USD'
            AND target_security_id IS NULL
            AND target_instrument_id IS NULL
            AND quantity_per_subject_unit IS NULL)
        OR (leg_kind = 'security'
            AND quantity_per_subject_unit IS NOT NULL
            AND quantity_per_subject_unit > 0
            AND (target_security_id IS NOT NULL OR target_instrument_id IS NOT NULL)
            AND cash_per_subject_unit IS NULL
            AND currency IS NULL)
        OR (leg_kind = 'unresolved'
            AND entitlement_code IS NOT NULL
            AND target_security_id IS NULL
            AND target_instrument_id IS NULL
            AND cash_per_subject_unit IS NULL
            AND quantity_per_subject_unit IS NULL
            AND currency IS NULL)
    )
);
```

The observation plus all ordered legs form one canonical payload/content identity and
publish atomically. `source_terms_json` and leg details are bounded registered typed JSON,
not an escape hatch for required fields. Unknown fields or meanings quarantine.
`reference_revision_ids_json` is a sorted unique list of exact accepted plan-04 identifier,
listing, or other reference revisions required by the action; it is empty when none apply.
Every subject, target, successor, or venue ID also links its exact plan-04 entity-resolution
decision through `canonical.observation_entity_resolutions`.

Source civil dates are preserved exactly. Resolved `ex_at`, `effective_at`, and
`payment_at` use one content-addressed date policy and, when session based, a pinned
calendar schedule. `published_at`/`available_at` remain in plan-03 revision metadata.
`announced_at` is the business event when supplied and never silently substitutes for
publication availability.

`share_ratio` is shares after per share before. It is required and positive for forward/
reverse splits; stock dividend uses `1 + additional_shares_per_old_share`. Other action
kinds leave it null unless their exact contract declares a supported meaning. A leg's
cash/quantity is per subject unit on its declared pre- or post-action `terms_basis`.

`resolution_method` is `source_cross_reference`, `issuer_or_exchange_evidence`, `created`,
or `manual`; manual resolution records a bounded operator label in plan-03 evidence.
`terms_basis` values are `pre_action`, `post_action`, and `not_applicable`.

- A cash leg requires positive `cash_per_subject_unit`, `currency='USD'`, null target IDs,
  and null security quantity.
- A security leg requires positive `quantity_per_subject_unit`, at least one resolved
  target security/instrument ID, and null cash/currency.
- An unresolved leg requires a registered `entitlement_code`; raw source claims may remain
  in bounded `leg_details_json`, but every typed amount/target field is null and no consumer
  may apply those claims as resolved terms.

For corporate-action revisions, plan-03 `event_at` equals `announced_at` when an exact
announcement instant exists and is null otherwise. It never equals ex/effective/payment
time merely to populate a generic field.

### 12.3 Action-specific minimum terms

| Kind | Required minimum |
| --- | --- |
| Ordinary/special cash dividend | subject, ex date/instant, one positive USD cash leg; record/payment dates when source supplies them |
| Split/reverse split | effective/ex instant and positive `share_ratio`; no cash leg except explicit fractional treatment deferred to accounting |
| Stock dividend | ex/effective instant and ratio greater than one or a resolved security leg |
| Symbol change | effective instant and linked reference identifier revision; no price factor |
| Listing change | effective instant and linked old/new listing evidence; no automatic instrument stitch |
| Merger/acquisition | effective instant and one or more cash/security/unresolved consideration legs |
| Spinoff | ex/effective instant and one or more resolved or explicitly unresolved security legs |
| Delisting | effective instant, reason, and optional liquidation/successor evidence |
| Liquidation | effective/payment evidence and cash or unresolved entitlement leg |
| ETF distribution | ex date/instant, classified cash or unresolved leg |
| Unresolved entitlement | effective evidence and stable unsupported/unresolved code |

The minimum-term table applies to noncancelled observations. A cancellation revision may
omit economic legs/dates that the source cancellation message does not repeat, but it must
supersede the exact same-source action revision and carry a registered cancellation reason
and evidence. It never copies fields from another provider. A registered same-source delta
codec may reconstruct a complete correction from the immediate prior revision only when
the prior revision ID, delta bytes, codec identity, and reconstructed payload all enter
source/observation lineage.

Announcement may precede effect. Record date may precede or follow ex date under a
documented market rule. Payment may occur later. Rules validate action-specific ordering
instead of imposing one universal date ordering.

## 13. Corporate-action resolution and behavior

Resolved action queries:

1. restrict source observations to the selected snapshot and dual cutoffs;
2. apply plan-03 revision/retraction selection per source action key;
3. exclude `cancelled` observations from economic application but retain them in audit;
4. group observations by resolved `CorporateActionId`;
5. use one versioned source-precedence policy to choose one complete observation/leg set;
6. detect overlapping economic fingerprints mapped to different action IDs; and
7. return selected, cancelled, ambiguous, unresolved, unavailable, and unsafe states.

An ambiguous fingerprint cannot be silently applied twice. Manual resolution appends
source mapping evidence in a new observation revision; it never merges master IDs in
place. Action corrections use their own availability and can change terms/status/dates
within one natural-key chain. A correction to `source_action_key` uses plan-03 atomic
retract/upsert behavior.

Cancellation of a real announced action is `action_status='cancelled'` and remains visible
at its cancellation revision's information time. A provider retraction means the prior
source observation itself was erroneous; it removes that source/key value only after the
retraction becomes eligible. These histories produce different audits.

Normal same-source status transitions are announced to confirmed/completed/cancelled and
confirmed to completed/cancelled. A completed or cancelled action can change status only
as an explicitly evidenced source correction with independent availability; it is not a
routine state regression. Conflicting transitions quarantine their source/action group.

Symbol/listing changes must point to accepted plan-04 identifier/listing revisions under
the same or an earlier catalog state. They do not change instrument identity unless the
reference plan requires a new listing/instrument. Merger, acquisition, spinoff, delisting,
and liquidation rows expose terms; plans 11 and 13 decide position/order behavior and
cannot infer missing entitlements.

## 14. Adjustment policy and algorithms

### 14.1 Policy identity

An immutable `AdjustmentPolicy` declares:

- price mode: raw, split, or total return;
- knowledge mode: point in time or retrospective;
- backward-to-anchor direction and anchor semantics;
- eligible action kinds/statuses and source-precedence policy;
- split/stock-dividend terms-basis handling;
- eligible cash-distribution classifications;
- prior-close reference-price query and missing-price behavior;
- simultaneous-action ordering/grouping;
- unsupported/ambiguous action and series-break behavior;
- float conversion, tolerance, overflow, and output schema;
- safety policy and implementation code content ID; and
- definition schema version and content ID.

Raw mode has identity too: it selects and converts exact raw revisions but applies no
action factor. Point-in-time mode takes an exact public-cutoff policy and optional project
cutoff. Retrospective mode selects the final eligible action state in the pinned snapshot,
ignores historical decision visibility, and is always `unsafe_retrospective`.

### 14.2 Applicability and anchor

The initial direction is `backward_to_anchor`. For an output bar ending at `t` and anchor
`A`, an action can affect that bar only when:

- the action subject expands to the bar's instrument;
- its selected status is announced, confirmed, or completed, not cancelled;
- its resolved economic/ex instant `e` satisfies `t <= e <= A` under the action policy;
- point-in-time selection makes that exact revision available by the query's public and
  optional project cutoff;
- all required terms and reference prices are safe and resolved; and
- the action kind is eligible for the requested price mode.

An action announced but not economically effective by the anchor contributes no factor.
An action effective at a bar's start affects earlier bars, not the post-action bar. The
policy's interval-boundary rule is content-addressed and acceptance-tested.

For ordinary/special/ETF cash distributions and stock dividends, `e` is the resolved
`ex_at`. For splits/reverse splits it is `effective_at` when supplied, otherwise `ex_at`;
when both are present the action/date policy must declare and validate their relationship.
Symbol/listing changes, mergers, acquisitions, spinoffs, delistings, and liquidations use
`effective_at`. A missing required resolved instant makes the action unavailable rather
than falling back to announcement, record, or payment date.

### 14.3 Split and stock-dividend factors

For a split-like action, let `r` be shares after per share before. Required `r > 0`.
For every prior bar affected by the action:

```text
split price multiplier before e  = 1 / r
split volume multiplier before e = r
```

Open, high, low, close, and VWAP use the price multiplier. Share volume uses the volume
multiplier; trade count and total raw notional do not change. A stock
dividend with additional-share rate `s` uses `r = 1 + s`. Exact decimal terms convert once
to finite `float64` under the policy; no display rounding occurs during factor accumulation.

For several eligible actions, cumulative multipliers are products ordered by
`(effective_at, corporate_action_id bytes)`. Mathematically commutative factors still
retain this order for deterministic evidence and floating-point replay.

`factor_ordinal` is one-based in ascending `(effective_at, action-ID bytes)` order. A factor
row's cumulative multipliers equal its component group multiplied by every later eligible
group through the anchor; they are the multipliers for a bar ending immediately before
that effective instant. Implementations accumulate in reverse ordinal order, then emit in
ascending order.

### 14.4 Cash-distribution factor

For one eligible USD cash distribution with per-share amount `D`, resolve raw regular-
session close `P` from the immediately preceding eligible session under the same snapshot,
bar-source policy, dual cutoffs, and terms basis. Split-normalize `P` and `D` to the same
share basis for any simultaneous split group. Then:

```text
cash price multiplier before e = (P - D) / P
cash volume multiplier before e = 1
```

`P` and `D` must be finite with `P > 0`, `D > 0`, and `P - D > 0`. Missing/no-trade/
partial/unsafe reference price, currency mismatch, ambiguous terms basis, or a nonpositive
factor makes the affected history `unavailable`; the policy never clips or substitutes a
later close.

Ordinary/special cash dividends and classified ETF cash distributions are eligible.
Liquidations, merger cash, rights, return-of-capital tax treatment, and unresolved
distributions are not silently interpreted as dividends. A future policy may add another
versioned method without changing these factors.

This factor is a research price-series convention approximating reinvestment at the ex
boundary. It does not create an entitlement, cash receipt, withholding, payable-date
event, journal entry, or tax classification; plan 11 uses the canonical action dates/legs
for those separate accounting effects.

### 14.5 Combined modes and series breaks

Split mode uses only split/stock-dividend price and volume factors. Total-return mode uses
the split factors and eligible cash price factors; volume still uses only split factors.
For a prior bar:

```text
adjusted price = raw price * cumulative split price factor * cumulative cash factor
adjusted volume = raw volume * cumulative split volume factor
```

Raw mode uses factors of one. All adjusted OHLC components share one price factor, so OHLC
ordering remains invariant apart from declared floating tolerance. The factor audit
retains each action group, reference price, component multiplier, cumulative multiplier,
input revision IDs, and evidence content ID.

For each raw bar, the service selects the earliest factor row whose effective instant is
at or after the bar's interval end and uses that row's cumulative multipliers; if none
exists, both multipliers are one. Resolved simultaneous actions form one factor group when
their basis permits, or deterministic same-instant subgroups when an explicit terms-basis
order is required.

Merger, acquisition, spinoff, liquidation, unresolved entitlement, or an action that
changes to another `InstrumentId` creates `segment_break` at its effective instant unless
a later explicitly unsafe stitching policy is requested. Delisting stops where raw data
stops; no terminal price or delisting return is invented. Symbol changes on the same
instrument contribute a no-op lineage marker. Listing changes to a new instrument are not
stitched by ticker.

### 14.6 Point-in-time behavior

For scalar `AsOfContext`, point-in-time adjustment may restate earlier raw bars using an
action only after that action is both effective and information-eligible. Before its
availability, the same snapshot/cutoff query produces factors that exclude it. A later
correction changes factors only at cutoffs that can see the correction. Plan 07 generalizes
this scalar contract to per-decision dataset panels; it may not replace it with one
retrospective adjusted history.

Safety is the maximum severity inherited from bar/action/reference-price revisions,
availability policies, source precedence, calendar/date resolution, custom code, and
knowledge mode. Materialization cannot launder unsafe inputs.

## 15. Adjustment storage and API

### 15.1 Research schema

```sql
CREATE TABLE research.adjustment_policies (
    adjustment_policy_id UUID NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
    qualified_name VARCHAR NOT NULL,
    definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adjustment_policy_id, policy_version),
    UNIQUE (qualified_name, policy_version)
);

CREATE TABLE research.adjustment_materializations (
    adjustment_materialization_id UUID PRIMARY KEY,
    adjustment_policy_id UUID NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
    composite_snapshot_id UUID NOT NULL,
    market_database_name VARCHAR NOT NULL,
    bar_query_content_id VARCHAR NOT NULL,
    public_cutoff_policy_content_id VARCHAR NOT NULL,
    project_cutoff_at TIMESTAMPTZ,
    anchor_at TIMESTAMPTZ NOT NULL,
    action_selection_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    safety_status VARCHAR NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    factor_count BIGINT NOT NULL CHECK (factor_count >= 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE research.adjustment_factors (
    adjustment_materialization_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    factor_ordinal INTEGER NOT NULL CHECK (factor_ordinal >= 1),
    split_price_multiplier DOUBLE NOT NULL,
    cash_price_multiplier DOUBLE NOT NULL,
    volume_multiplier DOUBLE NOT NULL,
    cumulative_price_multiplier DOUBLE NOT NULL,
    cumulative_volume_multiplier DOUBLE NOT NULL,
    reference_price DOUBLE,
    corporate_action_ids_json JSON NOT NULL,
    input_revision_ids_json JSON NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        adjustment_materialization_id,
        instrument_id,
        effective_at,
        factor_ordinal
    ),
    UNIQUE (adjustment_materialization_id, instrument_id, factor_ordinal)
);

CREATE TABLE research.adjusted_bars (
    adjustment_materialization_id UUID NOT NULL,
    raw_canonical_revision_id UUID NOT NULL,
    instrument_id UUID NOT NULL,
    interval_start TIMESTAMPTZ NOT NULL,
    interval_end TIMESTAMPTZ NOT NULL,
    session_date DATE NOT NULL,
    adjusted_open DOUBLE,
    adjusted_high DOUBLE,
    adjusted_low DOUBLE,
    adjusted_close DOUBLE,
    adjusted_volume DOUBLE,
    adjusted_vwap DOUBLE,
    price_multiplier DOUBLE,
    volume_multiplier DOUBLE,
    adjustment_status VARCHAR NOT NULL CHECK (
        adjustment_status IN ('adjusted', 'raw', 'unavailable', 'segment_break')
    ),
    reason_codes_json JSON NOT NULL,
    lineage_content_id VARCHAR NOT NULL,
    PRIMARY KEY (adjustment_materialization_id, raw_canonical_revision_id),
    CHECK (interval_start < interval_end)
);
```

Factor and adjusted numeric columns must be finite when nonnull. `unavailable` and
`segment_break` rows retain the raw revision and null adjusted values with complete reason
codes. They do not disappear. Materialization counts, factor rows, adjusted rows, metadata,
and completion event publish atomically; interruption leaves no visible partial identity.

`execution_content_id` covers policy definition, composite/market snapshot manifests,
market database name, exact bar query and selected raw revisions, cutoffs, anchor,
reference/calendar/precedence policies, selected action/retraction states, factor code and
dependency identity, output schema, safety findings, and canonical factor evidence. An
identical request verifies bytes and returns the existing materialization ID.

### 15.2 API

```python no-run
view = project.services.market.adjustments.view(
    bars=BarQuery(
        instruments=instrument_ids,
        spec=BarSpecRef("persistra.bar.session.regular", version=1),
        start=start_at,
        end=end_at,
    ),
    policy=AdjustmentPolicyRef("persistra.adjustment.total_return_pit", version=1),
    context=as_of,
    anchor_at=decision_at,
)

materialization = view.materialize()
frame = materialization.bars()
factors = materialization.factors()
```

`view` may stream derived rows without persistence. `materialize()` requires
`research_write`, an exact composite snapshot, and a scalar cutoff/anchor. Raw market
tables are never updated. Public objects expose policy/snapshot/cutoff/safety summaries and
no database connection or workspace table name.

Initial built-in policies are:

- `persistra.adjustment.raw_pit@1`
- `persistra.adjustment.split_pit@1`
- `persistra.adjustment.total_return_pit@1`
- `persistra.adjustment.raw_retrospective@1`
- `persistra.adjustment.split_retrospective@1`
- `persistra.adjustment.total_return_retrospective@1`

The `@1` suffix denotes policy version in documentation; the stored qualified name and
positive version remain separate fields.

## 16. Public dataframe contracts

All frames have fixed column order, UTC-aware `datetime64[us, UTC]` instants, Python date
session/action dates, plan-01 wire-ID strings, pandas nullable `Int64`/`boolean` for nullable
scalars, canonical JSON strings for bounded list/evidence fields, and finite `float64`
analytical numeric values. Exact record APIs preserve decimals. Empty frames retain these
dtypes and schema identity.

| Frame | Schema | Required columns |
| --- | --- | --- |
| Bars | `persistra.dataframe.bars@1` | revision/instrument/spec/source IDs, scope/venue/aggregation, interval/observed-through/session/phase/schedule/state, currency, OHLCV/VWAP/notional/count, availability/quality/warnings |
| Bar coverage | `persistra.dataframe.bar_coverage@1` | expected interval key, state/reason, selected revision/source, calendar schedule ID |
| Trades | `persistra.dataframe.trades@1` | revision/instrument/venue/source IDs, source key/sequence, event/availability, currency, price/quantity, normalized/raw conditions, price-/volume-forming, extended-hours |
| Quotes | `persistra.dataframe.quotes@1` | revision/instrument/source/venue IDs, source key/sequence, event/availability, state/scope, sides/sizes, spread/midpoint, lock/cross/indicative, conditions |
| Trading status | `persistra.dataframe.trading_status@1` | revision/instrument/venue/source IDs, key/sequence, event/availability, status/reason/resume, conditions |
| Corporate actions | `persistra.dataframe.corporate_actions@1` | revision/action/subject/source IDs, source key, kind/status, every action date/instant, ratio/terms basis, availability/quality, fingerprint, resolution/safety |
| Action legs | `persistra.dataframe.corporate_action_legs@1` | revision/action ID, ordinal/kind, target IDs, cash/quantity/currency, entitlement, terms basis/details |
| Adjustment factors | `persistra.dataframe.adjustment_factors@1` | materialization/instrument/action IDs, effective time/order, component/cumulative factors, reference price, input revisions/evidence |
| Adjusted bars | `persistra.dataframe.adjusted_bars@1` | materialization/raw revision/instrument IDs, interval/session, adjusted OHLCV/VWAP, factors, status/reasons/lineage |

Market frames order by the keys specified in their query sections. Actions order by
`(effective_at NULLS LAST, ex_at NULLS LAST, corporate_action_id,
canonical_revision_id)` and legs by revision/ordinal. Adjustment factors order by
instrument/effective time/ordinal; adjusted bars order by interval/instrument/raw revision.

## 17. Validation, disposition, and diagnostics

### 17.1 Ordered rule ownership

Plan-03 phases remain authoritative. This plan registers domain rules after schema,
natural-key, entity, and temporal checks:

1. market/reference/currency/terms resolution;
2. bar interval/calendar/grid and state-dependent fields;
3. trade/quote/status key, sequence, condition, and side semantics;
4. price/quantity/amount domain and quantum checks;
5. corporate-action identity, date, status, terms, leg, and reference linkage;
6. correction/retraction and cross-record conflict groups;
7. expected session/feed/action coverage; and
8. statistical anomalies.

Structural decoding, unknown required fields, invalid canonical JSON/decimal, wrong record
model, or broken content identity rejects the batch. Separable invalid rows quarantine.
Conflicting intervals, trade corrections, quote sequences, status transitions, or action
legs use one `DispositionGroupId`. Coverage/statistical rules warn by default.

### 17.2 Stable validation codes

Initial codes and default actions are:

| Code | Default action |
| --- | --- |
| `market.instrument.unresolved` | quarantine record/group |
| `market.venue.unresolved` | quarantine record/group |
| `market.currency.unsupported` | quarantine record |
| `market.terms.unavailable` | quarantine record |
| `bar.spec.unresolved` | quarantine record |
| `bar.interval.invalid` | quarantine group |
| `bar.interval.off_grid` | quarantine group |
| `bar.calendar.misaligned` | quarantine group |
| `bar.state.invalid_fields` | quarantine record |
| `bar.ohlc.inconsistent` | quarantine record |
| `bar.price.invalid` | quarantine record |
| `bar.quantity.invalid` | quarantine record |
| `bar.availability.before_end` | quarantine record |
| `bar.availability.before_observed` | quarantine record |
| `bar.coverage.missing` | warning |
| `bar.coverage.overlap` | quarantine group |
| `bar.return.implausible` | warning |
| `bar.volume.implausible` | warning |
| `trade.key.invalid` | quarantine record |
| `trade.sequence.conflict` | quarantine group |
| `trade.condition.unknown` | quarantine record |
| `trade.correction.invalid` | quarantine group |
| `quote.key.invalid` | quarantine record |
| `quote.sequence.conflict` | quarantine group |
| `quote.side.invalid` | quarantine record |
| `quote.locked` | warning |
| `quote.crossed` | warning or quarantine under source policy |
| `quote.condition.unknown` | quarantine record |
| `status.sequence.conflict` | quarantine group |
| `status.value.unknown` | quarantine record |
| `action.identity.ambiguous` | quarantine group |
| `action.date.invalid` | quarantine group |
| `action.terms.invalid` | quarantine group |
| `action.legs.incomplete` | quarantine group |
| `action.reference.unresolved` | quarantine group |
| `action.possible_duplicate` | quarantine group |
| `adjustment.action.ambiguous` | unavailable derived row |
| `adjustment.action.unsupported` | segment break/unavailable |
| `adjustment.reference_price.missing` | unavailable derived row |
| `adjustment.reference_price.unsafe` | unavailable derived row |
| `adjustment.factor.nonpositive` | unavailable derived row |
| `adjustment.series.break` | segment break |
| `adjustment.retrospective` | persistent unsafe finding |

Registered source policies may make anomaly/lock/cross actions stricter but cannot weaken
structural or identity requirements. Evidence is bounded and licensing-safe.

### 17.3 Cross-dataset reconciliation

Bars and trades from different providers or scopes are not required to reconcile exactly.
A registered reconciliation rule may compare trade-derived OHLCV to source bars only after
aligning snapshot, cutoffs, instruments, venues, conditions, sessions, currency, and
aggregation policy. Deviations are findings with both source lineages; they do not replace
either canonical dataset.

Corporate-action price-gap diagnostics are likewise warnings, not action invention. A
large return does not prove a split, and a split announcement does not authorize changing
raw OHLC. Status/bar gaps may be correlated in diagnostics but never infer missing status
or prices.

## 18. Safety and temporal conformance

Safe simulation/research inputs require:

- immutable market/composite snapshots;
- exact public and optional project-knowledge cutoff semantics;
- observed or reviewed safe availability policies for originals;
- correction timing that is observed or conservatively bounded and visibly tainted;
- effective instrument/venue/terms/calendar resolution;
- explicit source precedence without unresolved duplicates;
- complete bars unless a later fidelity policy explicitly accepts partial input;
- nonretrospective action selection and adjustment;
- no unsupported/ambiguous action inside an asserted continuous adjusted segment; and
- registered/bounded code with content identity.

Partial bars, present-day final action histories, unversioned vendor adjustment factors,
current ticker joins, inferred halts, unmarked carried prices, or current-only adjusted
files are unsafe. Persisting or exporting them cannot remove that status. A raw bar can be
safe even when an adjusted view is unavailable; availability is per requested derived
contract.

Trades and quotes may be temporally safe for research while still ineligible for market
replay fidelity. Those are separate safety/fidelity dimensions. Future execution plans
must not interpret temporal conformance as evidence of queue or depth completeness.

## 19. Events, errors, and logs

### 19.1 Domain events

Source observation revisions remain authoritative plan-03 rows and batch lifecycle events;
Persistra does not emit one domain event per bar, trade, quote, or status row. Initial
domain events are:

| Event type | Aggregate kind |
| --- | --- |
| `persistra.market_data.bar_spec_registered@1` | `persistra.aggregate.bar_spec` |
| `persistra.corporate_action.created@1` | `persistra.aggregate.corporate_action` |
| `persistra.adjustment.policy_registered@1` | `persistra.aggregate.adjustment_policy` |
| `persistra.adjustment.materialization_completed@1` | `persistra.aggregate.adjustment_materialization` |

Master/definition rows and their events commit atomically. A materialization failure logs
bounded diagnostics but emits no completion event or visible rows. Corporate-action
observation status is canonical source data, not duplicated into generic lifecycle events.
Bar-spec and adjustment-policy registrations require contiguous versions and use the
registered version as aggregate sequence. Corporate-action creation and adjustment-
materialization occurrence IDs use sequence 1. Exact retries emit no duplicate event.

These definition/master/materialization lifecycle events use the transaction's captured
instant for `event_at`, `available_at`, and `recorded_at`; market/action information times
remain authoritative on plan-03 canonical revisions.

### 19.2 Exceptions and stable reasons

| Exception | Reason code |
| --- | --- |
| `BarSpecError` | `bar.spec.invalid` |
| `MarketDataQueryError` | `market.query.invalid` |
| `MarketDataLimitError` | `market.query.row_limit` |
| `MarketDataCoverageError` | `market.coverage.insufficient` |
| `TradeConditionError` | `trade.condition.invalid` |
| `QuoteConditionError` | `quote.condition.invalid` |
| `TradingStatusError` | `status.query.invalid` |
| `CorporateActionResolutionError` | `action.resolution.failed` |
| `CorporateActionTermsError` | `action.terms.invalid` |
| `AdjustmentPolicyError` | `adjustment.policy.invalid` |
| `AdjustmentUnavailableError` | `adjustment.unavailable` |
| `AdjustmentMaterializationError` | `adjustment.materialization.failed` |

Expected missing bars, absent status, one-sided quotes, cancelled actions, segment breaks,
and per-row adjustment unavailability are structured results. Exceptions indicate invalid
API/configuration, violated invariants, resource ceilings, or failed atomic operations.
Logs contain IDs, bounded ranges/counts, reason codes, safety summaries, and remediation
guidance—not licensed payloads or complete tick streams.

## 20. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Provider labels bar by close only | Adapter resolves explicit start/end using registered convention/calendar |
| Daily early close | Session bar ends at pinned early close, never normal close |
| DST boundary | UTC interval/calendar fixture is authority; no fixed EST offset |
| One-hour final 30-minute phase remainder | Allowed only by spec's short-final policy |
| Complete bar published before end | Quarantine as impossible |
| Partial then complete bar | Linear revisions with independent availability; default query selects complete when eligible |
| Explicit no-trade session | Null OHLC, zero activity, source assertion retained |
| Missing session bar | Coverage reason only; no synthetic row |
| Halt overlaps a time bar | Keep the configured bar interval and separate status lineage |
| Provider consolidated bar | Use registered aggregation, never listing venue label |
| Same trade received twice | Plan-03 duplicate disposition, no second print |
| Trade cancellation | Exact-target retraction visible at cancellation availability |
| Unknown sale condition | Quarantine unless registered vendor namespace/policy defines it |
| One-sided quote | Valid active state with explicit missing side |
| Source clears both quote sides | Persist explicit `empty`; do not treat as missing feed/halt |
| Locked quote | Persist with diagnostic |
| Crossed quote | Persist or quarantine only under registered source policy |
| Quote goes stale | Query diagnostic; canonical row unchanged |
| No status feed | `status.unavailable`, never infer trading/halt |
| Halt has expected resume but no resume event | Halt remains selected |
| Action announced then cancelled | Later selected cancelled status, prior cutoff still sees announcement |
| Provider withdraws erroneous action | Plan-03 retraction, distinct from cancellation |
| Two providers describe same action | One resolved action plus precedence; ambiguous fingerprints block application |
| Split and dividend share ex instant | Terms basis and deterministic group required; otherwise unavailable |
| Missing pre-ex close | Total-return history unavailable across factor; no later-price fallback |
| Cash amount exceeds reference close | Nonpositive factor, unavailable |
| Action correction learned later | Earlier cutoffs retain earlier factor; later cutoffs use correction |
| Symbol changes on same instrument | No price factor; lineage marker only |
| Venue move creates new instrument | Segment break; no ticker stitching |
| Merger/spinoff/unresolved right | Segment break unless future explicit policy handles terms |
| Delisted instrument has no final print | Stop raw series; do not invent zero/terminal return |
| Retrospective vendor adjusted file | May import only as unsafe custom derived data, never canonical bar |

## 21. Security, licensing, and resource behavior

- Source keys, condition lists, JSON terms, codes, and evidence have registered length,
  count, and character ceilings before allocation-heavy decoding.
- Tick queries require bounded predicates, stream fixed-size chunks, and enforce row/memory
  limits before dataframe materialization.
- No adapter/query accepts SQL, table names, pickle, arbitrary class paths, raw connection,
  or managed-write callback.
- Adjustment code cannot perform network access or read paths outside plan-02 approved
  resources. Custom opaque adjustment code is unsafe even when bounded.
- Licensed condition codes, action text, venue data, and tick records retain licensing
  class through frames, factors, materializations, reports, and exports.
- Evidence defaults to IDs, factors, hashes, and summaries rather than redistributing
  complete licensed records.
- Factors and content IDs are not integrity signatures against a malicious database owner;
  verified copies and external manifests retain plan-02 semantics.

## 22. Migration and compatibility effect

This is a greenfield v3 schema. V2 symbol-keyed Parquet bars, adjusted-close columns,
calendar helpers, action files, or trade/quote data are not imported or mapped. Provider
adapters must reacquire or independently translate them into v3 staging records and pass
normal identity, timing, validation, and snapshot rules. There is no legacy adjusted-price
compatibility view.

Within v3, changing a dataset natural key, source timestamp/sequence convention, bar grid,
condition meaning, action-kind/terms semantics, factor equation, boundary rule, reference-
price policy, dataframe schema, or content codec requires a new relevant identity/version
and market/research migration. Existing raw revisions, action masters, snapshots, factors,
and materializations remain immutable. A new adjustment policy never rewrites a prior
materialization.

## 23. Acceptance tests

### 23.1 Bar specifications and observations

- Register session, 1h, 1m, 1s, arbitrary duration, UTC-aligned, and short-final specs;
  verify content identity, compatibility rejection, snapshots, and events.
- Golden-test regular sessions, early closes, holidays, DST boundaries, phase edges, fixed
  grids, and final remainders against every plan-04 release calendar profile.
- Property-test OHLC ordering, decimals/quantums, state nullability, interval bounds,
  consolidated/venue fields, and deterministic natural keys/order.
- Generate complete, partial, no-trade, missing, duplicate, revised, retracted, overlapping,
  and implausible bars; assert exact disposition, coverage, availability, and warnings.
- Classify selected, stale, no-trade, partial-excluded, unavailable, invalid-summary, and
  missing prices with orthogonal halt/status state; prove audit-only candidate details
  cannot reach strategy-facing joins or counts.
- Sentinel-test that complete bars cannot appear before interval end and corrections cannot
  inherit original availability.
- Prove the plan-12/13 execution-outcome projection reveals only exact raw `open` at the
  open event, preserves later canonical source availability, requires frozen snapshot/
  project evidence, cannot enter ordinary/strategy adapters before open, and cannot leak
  high/low/close/full-session volume through values, schemas, counts, errors, or lineage.

### 23.2 Trades, quotes, and status

- Contract-test source key/partition/sequence codecs, normalized/raw conditions, correction
  and exact-target cancellation behavior under chunking/retries.
- Generate positive/invalid prices and sizes, odd-lot/extended/condition combinations,
  same-instant multi-venue trades, and deterministic ordering.
- Test empty, one-/two-sided, locked, crossed, indicative, venue, and NBBO quotes with
  absent or resolved side venues, zero sizes, stale queries, and policy-specific outcomes.
- Hand-build halt/resume/pause/auction streams, missing status, expected resume without
  transition, conflicting sequences, source precedence, and cutoff boundaries.
- Prove no trade/quote/status API or dataframe claims depth, queue, or replay completeness.

### 23.3 Corporate actions

- Hand-build every initial action kind with exact required/missing terms, all dates,
  resolved instants, action legs, identities, source mappings, and reference links.
- Generate duplicate-provider fingerprints, exact cross-references, ambiguous actions,
  manual resolutions, source precedence, corrections, cancellation, retraction, and
  natural-key replacement.
- Verify action-specific date rules rather than one universal ordering and prove no action
  date substitutes for missing availability.
- Property-test positive split/share ratios, leg conditional nullability, USD cash terms,
  atomic action/leg disposition, and unresolved entitlement preservation.
- Prove ticker/listing changes follow plan-04 identities and do not rewrite or stitch
  instruments silently.

### 23.4 Adjustment algorithms

- Golden-test 2-for-1, 1-for-10, stock dividend, ordinary/special cash dividend, multiple
  sequential actions, and same-instant split/dividend with hand-calculated factors.
- Verify adjusted OHLC order, inverse split volume, unchanged trade count, cash-volume
  factor one, factor ordering, float tolerance, and no intermediate display rounding.
- Sentinel-test every cutoff around announcement, correction, cancellation, ex/effective,
  reference-price availability, project receipt, and anchor boundaries.
- Exercise missing/no-trade/partial/unsafe pre-ex prices, nonpositive cash factors,
  ambiguous actions, currency mismatch, unsupported legs, segment breaks, and delisting
  without any guessed factor or row loss.
- Compare raw/split/total-return and point-in-time/retrospective outputs; prove
  retrospective safety cannot be cleared through materialization.

### 23.5 Storage, APIs, and failure recovery

- Contract-test every dataframe schema, dtype, column order, empty frame, exact-domain
  record conversion, deterministic sorting, coverage reason, and bounded chunk boundary.
- Run queries just below/at/above row ceilings and record peak memory for large tick and bar
  ranges.
- Inject failure before/after every definition, master, typed payload, leg, factor, adjusted
  row, event, and completion write; prove atomic visibility and idempotent retry.
- Materialize identical/different inputs and verify execution-content reuse never crosses
  snapshots, cutoffs, source policies, action revisions, calendars, code, or schema.
- Round-trip domain events through plan-02 event storage and rebuild action/factor lineage
  from immutable normalized rows.

### 23.6 Documentation and exit criteria

- Run deterministic text fixtures from external-style staging records through validation,
  snapshot, raw query, action audit, adjustment view, and materialization using public APIs.
- Strict-build documentation and execute implementation-ready snippets once implemented.

This plan is implementation-complete when:

- daily and intraday canonical bars are raw, explicit-interval, calendar-aligned, validated,
  revision-aware, and point-in-time queryable;
- trades, top-of-book quotes, and status are bounded research datasets with honest fidelity;
- every supported action kind preserves identity, dates, terms, legs, availability,
  resolution, ambiguity, cancellation, retraction, and unresolved state;
- split/total-return factors match golden cases and never use future-known actions silently;
- missing/partial/no-trade/halted/unavailable/unsafe states remain distinct;
- adjusted caches are immutable research artifacts tied to exact snapshots/policies;
- all schemas participate in plan-02 migrations and plan-03 validation/snapshots;
- fault injection proves no partial canonical or materialized publication; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 24. Review checklist for dependent plans

Every later plan must state:

- which `InstrumentId`, venue/scope, `BarSpec`, calendar schedule, and interval grain it
  consumes;
- which exact raw revision/source/condition/status policy is eligible;
- whether it uses raw, split, total-return, point-in-time, or retrospective prices;
- which adjustment policy, anchor, action revisions, reference-price policy, and segment
  breaks enter identity;
- how partial/no-trade/missing/stale/halted/unavailable rows behave without fabrication;
- whether trades/quotes are research inputs or are being given an unsupported replay
  interpretation;
- which corporate-action dates and legs drive eligibility, entitlement, accounting, or
  execution;
- how action cancellation, retraction, ambiguity, successor instruments, and unresolved
  entitlements behave;
- how fixed-decimal raw values cross into float research and back into execution/accounting;
- which snapshot, dual cutoffs, source precedence, safety, licensing, and bounded-query
  rules apply; and
- how market/action/policy changes alter execution identity, migrations, and comparison.

## 25. Umbrella and completed-plan consistency

This plan reuses plan-01 IDs, UTC microsecond instants, half-open intervals, fixed decimals,
canonical content, deterministic ordering, and event envelopes; plan-02 database roles,
modes, leases, connection boundaries, transactions, and migrations; plan-03 registered
datasets, revisions/retractions, availability, dispositions, quarantine/remediation,
catalog state, and snapshots; and plan-04 instrument/venue identity, calendars, terms,
source resolution, and universe eligibility.

It implements the umbrella's raw bars, trades, top-of-book quotes, action/lifecycle terms,
adjustment modes, missing/halt distinction, USD US-listed scope, and honest market-replay
boundary. Versioned bar grids, explicit no-trade rows, optional status streams, resolved
economic-action identity, factor formulas, and normalized adjusted caches are local
refinements. No ticker key, adjusted canonical fact, inferred halt, future-known action,
synthetic price, guessed entitlement, hidden row loss, or tick-replay claim is introduced.

The cumulative plan-12 review adds only a field-restricted simulation execution-outcome
projection for an economically observed session open. It preserves the complete bar's
later canonical availability, blocks every other bar field and ordinary research adapter,
and makes retrospective same-session capacity a fidelity assumption. It therefore does not
weaken the complete-bar or strategy-visibility contracts above.
