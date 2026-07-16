# Focused specification 06: Fundamental, estimate, macro, benchmark, and rate data

**Status:** implementation-ready greenfield v3 plan

**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md),
[focused specification 02](02-project-databases-leases-copies-migrations.md),
[focused specification 03](03-catalog-ingestion-quarantine-snapshots.md),
[focused specification 04](04-reference-identifiers-calendars-universes.md), and
[focused specification 05](05-market-bars-trades-quotes-actions-adjustments.md)

**Owners:** `persistra.market.fundamentals`, `persistra.market.estimates`,
`persistra.market.macro`, `persistra.market.benchmarks`,
`persistra.market.rates`

**Required before:** focused specifications 07–18

## 1. Purpose

This plan defines the remaining standardized external research inputs for v3: issuer
filings and numeric facts, curated concept normalization, analyst estimates and consensus,
reported actuals, macroeconomic release vintages, benchmark instruments/series/
constituents, and risk-free rate series/curves.

These domains share source revision, snapshot, availability, and dual-cutoff mechanics,
but they do not share one flattened “value” table. Their identity grains, periods,
publication evidence, amendment/vintage rules, units, and safety boundaries stay explicit.
Derived ratios, surprises, macro regimes, benchmark returns from constituents, and curve
interpolation belong to later research definitions, not overwritten canonical facts.

## 2. Scope and boundaries

### 2.1 In scope

- Filing/accession and original/amendment report identity
- Numeric instant/duration facts with taxonomy concepts, units, periods, dimensions, and
  source precision
- Versioned curated normalized fundamental concepts and immutable raw-to-normalized rows
- Individual estimate observations, source consensus snapshots, and reported actuals
- Fiscal-target and fixed-horizon estimate semantics
- Macro series definitions, observation periods, release identities, and complete vintages
- Benchmark definitions backed by an instrument, source level/return series, or
  point-in-time constituents
- Effective/available benchmark weights and source methodology identity
- USD risk-free rate series and curve points with tenor, quote convention, compounding,
  day count, release, and availability
- Exact schemas, source precedence, APIs, dataframes, safety, validation, errors, and tests

### 2.2 Out of scope

- Text filing search, NLP, document rendering, and unstructured filing assets
- Taxonomy-wide semantic inference or automatically deciding that two concepts are equal
- Derived ratios, trailing-twelve-month values, growth, quality, estimate surprise, or
  estimate revision features
- Scraping analyst identities or redistributing licensed contributor-level data
- Forecast models, nowcasts, macro regimes, seasonal adjustment, and frequency conversion
- Reconstructing a proprietary benchmark methodology from constituents
- Benchmark-relative analytics, attribution, or optimizer constraints
- Yield-curve fitting, interpolation, extrapolation, bootstrapping, and term-premium models
- FX curves, inflation-linked curves, credit curves, or implemented non-USD workflows

Plan 08 owns derived features, plan 10 consumes forecasts/benchmarks, plan 11 consumes
financing curves, and plan 15 owns performance/benchmark analytics.

## 3. Normative decisions

1. A filing is not an issuer. Facts are issuer-grain observations tied to one exact filing
   and report lineage; instrument-level ratios are later derived joins.
2. An amended filing is another immutable `FilingId` in one `ReportId` lineage. It never
   overwrites the original report or borrows its availability.
3. Raw taxonomy facts remain queryable. Curated normalization appends mapping-derived rows
   tied to exact raw revisions and mapping/code identity.
4. Only finite numeric facts are standardized initially. Text blocks and documents remain
   external assets with hashes/metadata.
5. Estimate observations, source consensus, and actuals are distinct datasets. Persistra
   never represents a recomputed subset as the vendor's consensus.
6. A surprise cannot exist before the exact actual revision becomes available; surprise
   remains a derived feature.
7. Every macro vintage is independently identifiable. A latest-revised-only source is
   persistently unsafe for historical simulation.
8. Benchmark instrument, source series, and constituent definitions are explicit kinds.
   Constituents do not silently reproduce an official source series.
9. Risk-free canonical data preserves the source quote convention. Conversion,
   interpolation, and extrapolation require separately versioned research policies.
10. Filing acceptance, estimate publication, macro release, benchmark publication, and
    rate release are information events. Period end, fiscal target, benchmark effective
    date, and rate effective date cannot substitute for missing availability.
11. All source rows use plan-03 revision/retraction rules, plan-04 entity resolution, exact
    snapshots, and explicit source precedence.
12. Market writes are atomic in one exclusively leased market database. Query-time
    normalized/derived views read immutable snapshots and never mutate source rows.

## 4. Identity and enum surface

This plan adds these plan-01 typed IDs:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `ReportId` | `report` | Original/amendment lineage for one reporting obligation |
| `FilingId` | `filing` | One exact submitted filing/accession |
| `NormalizedConceptId` | `normalized_concept` | Curated financial concept lineage |
| `FundamentalMappingId` | `fundamental_mapping` | One source-concept normalization rule lineage |
| `FundamentalNormalizationId` | `fundamental_normalization` | One immutable raw-fact normalization result |
| `FundamentalNormalizationRunId` | `fundamental_normalization_run` | One atomic bounded normalization execution |
| `EstimateMeasureId` | `estimate_measure` | Versioned estimated/actual measure lineage |
| `EstimateContributorId` | `estimate_contributor` | Source-scoped licensed contributor identity |
| `MacroSeriesId` | `macro_series` | One economic series lineage |
| `MacroReleaseId` | `macro_release` | One source release/vintage event |
| `BenchmarkId` | `benchmark` | One benchmark lineage |
| `RiskFreeCurveId` | `risk_free_curve` | One rate series/curve lineage |

Stable enums are:

| Enum | Values |
| --- | --- |
| `FactPeriodKind` | `instant`, `duration` |
| `FactNumericKind` | `amount`, `rate`, `count`, `pure` |
| `FiscalPeriodKind` | `fy`, `q1`, `q2`, `q3`, `q4`, `h1`, `h2`, `ytd`, `ltm`, `other` |
| `FilingStatus` | `filed`, `accepted`, `withdrawn` |
| `EstimateObservationKind` | `individual`, `consensus`, `actual` |
| `EstimateTargetKind` | `fiscal_period`, `fixed_horizon` |
| `MacroVintageStatus` | `advance`, `preliminary`, `revised`, `final`, `benchmark_revision` |
| `VintageCompleteness` | `complete`, `latest_only`, `unknown` |
| `BenchmarkKind` | `instrument`, `source_series`, `constituents` |
| `BenchmarkSeriesKind` | `price_index`, `total_return_index`, `period_return` |
| `RateQuoteKind` | `simple_yield`, `bond_equivalent_yield`, `periodic_zero`, `continuous_zero`, `discount_factor`, `overnight_rate` |
| `CompoundingKind` | `simple`, `periodic`, `continuous`, `discount_factor` |
| `DayCountKind` | `act_360`, `act_365f`, `act_act_isda`, `thirty_360_us` |
| `TenorKind` | `days`, `months` |

## 5. Dataset registration, ownership, and lifecycle

### 5.1 Exact dataset names and natural keys

`SourceId` scopes every natural key:

| Dataset | Natural key fields |
| --- | --- |
| `persistra.fundamental.filing` | `source_filing_key` |
| `persistra.fundamental.raw_fact` | filing ID, taxonomy concept, period, unit, dimensions |
| `persistra.estimate.individual` | `source_estimate_key` |
| `persistra.estimate.consensus` | `source_consensus_key` |
| `persistra.estimate.actual` | `source_actual_key` |
| `persistra.macro.release` | macro series ID, `source_release_key` |
| `persistra.macro.observation` | macro series ID, observation period, source vintage key |
| `persistra.benchmark.series` | benchmark ID/version, interval end or event instant |
| `persistra.benchmark.constituent` | benchmark ID/version, instrument ID, `valid_from` |
| `persistra.risk_free.point` | curve ID/version, effective date, tenor/maturity, source release key |

Source keys and dimension/vintage codecs are registered, bounded, canonical, and
reproducible. Local receipt order/random IDs cannot enter a natural key. Corrections use
linear revisions. A corrected natural-key byte uses plan-03 atomic old-key retraction/new-
key upsert. Source withdrawals use registered exact-target retractions; a real filing
amendment, new estimate, new macro vintage, or changed benchmark membership is an upsert,
not a deletion.

### 5.2 Modes, schemas, and transactions

All source observations and definitions in sections 6–15 belong to the selected market
database's `canonical` schema with plan-03 revision/catalog/quality state. Registration,
master allocation, normalization mapping/results, and ingestion require `market_write`
under one exclusive market lease. Market-role migrations own their tables.

Raw and normalized queries work under `read_only` or `research_write` using shared market
leases and exact market/composite snapshots. Later features/materializations live in the
research database; plan 06 does not write derived ratios/surprises/curves there. No
operation requires a cross-file atomic commit, exposes a connection/table name, or creates
a physical copy/export.

One ingestion completion transaction publishes all accepted typed payloads, required
masters/entity-resolution links, dispositions, catalog state, findings, and events.
Filing/fact or multi-point curve batches use atomic disposition groups where incomplete
publication would change meaning.

### 5.3 Shared temporal and source behavior

Plan-03 metadata stores revision-specific `event_at`, `published_at`, `available_at`,
`source_updated_at`, `ingested_at`, and availability quality. Domain period/effective
fields remain in typed rows. Every subject issuer/security/instrument and constituent
links exact plan-04 entity resolutions into observation content.

Query selection applies snapshot, public and optional project cutoff, revision/retraction,
then source precedence. A precedence policy selects one complete provider observation;
field-wise coalescing and generic latest-ingested wins are forbidden. Corrections never
inherit original availability. Unknown correction timing is ingestion-bounded/unsafe or
unknown.

Every dataset declares whether plan-03 retraction is allowed and its reason schema.
`market.retraction.source_withdrawal` and
`market.retraction.natural_key_correction` are the only initially permitted exact-target
reasons for every dataset in section 5.1; a dataset version may forbid either but may not
invent an unregistered reason. Filing amendments, legal withdrawal statuses, estimate
revisions, macro vintages, benchmark rebalances, and new rate releases never use retraction
to erase their history.

## 6. Filing and report identity

### 6.1 Masters

```sql
CREATE TABLE canonical.reports (
    report_id UUID PRIMARY KEY,
    issuer_id UUID NOT NULL,
    report_kind VARCHAR NOT NULL,
    fiscal_period_end DATE NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (issuer_id, report_kind, fiscal_period_end)
);

CREATE TABLE canonical.filings (
    filing_id UUID PRIMARY KEY,
    accession_namespace VARCHAR NOT NULL,
    normalized_accession VARCHAR NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (accession_namespace, normalized_accession)
);
```

`ReportId` groups an original report and amendments for one issuer/report kind/fiscal
period. `FilingId` identifies one immutable submission/accession without freezing its
fallible issuer/report resolution into the master. Exact accession identity or immutable
manual evidence may resolve sources to an existing filing; issuer/name/date similarity
cannot. A correction preserves the `FilingId`, appends a corrected filing observation and
affected facts, and allocates a new `ReportId` when the reporting-obligation identity was
wrong. The mistaken report and observation remain auditable.

### 6.2 Filing observations

```sql
CREATE TABLE canonical.filing_observations (
    canonical_revision_id UUID PRIMARY KEY,
    filing_id UUID NOT NULL,
    report_id UUID NOT NULL,
    issuer_id UUID NOT NULL,
    source_filing_key VARCHAR NOT NULL,
    form_type VARCHAR NOT NULL,
    filing_status VARCHAR NOT NULL CHECK (
        filing_status IN ('filed', 'accepted', 'withdrawn')
    ),
    filing_date DATE NOT NULL,
    accepted_at TIMESTAMPTZ,
    report_period_start DATE,
    report_period_end DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_period_kind VARCHAR,
    is_amendment BOOLEAN NOT NULL,
    amends_filing_id UUID,
    taxonomy_namespace VARCHAR,
    taxonomy_version VARCHAR,
    document_content_id VARCHAR NOT NULL,
    document_location VARCHAR,
    document_redistributable BOOLEAN NOT NULL,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (is_amendment AND amends_filing_id IS NOT NULL)
        OR (NOT is_amendment AND amends_filing_id IS NULL)
    )
);
```

For an accepted safely usable filing revision, `accepted_at` is required and plan-03
`event_at` equals it. A withdrawal revision retains `accepted_at` and uses its withdrawal
occurrence/publication as revision-specific event/publication evidence. Source
`published_at` normally equals the authoritative status publication; `available_at` may add
a reviewed dissemination latency but cannot precede that publication. Filing date alone is
not an instant and cannot establish availability. Missing acceptance or status-transition
timing is exploratory/unsafe.

An amendment points to an earlier filing in the same `ReportId`; chains are acyclic and
ordered by acceptance, source sequence, then filing ID. Withdrawal is an observed filing
status and does not delete prior filings. Document bytes remain external when configured;
location is normalized/credential-free and content ID is always retained.

## 7. Raw fundamental facts

### 7.1 Schema

```sql
CREATE TABLE canonical.fundamental_raw_facts (
    canonical_revision_id UUID PRIMARY KEY,
    filing_id UUID NOT NULL,
    report_id UUID NOT NULL,
    issuer_id UUID NOT NULL,
    taxonomy_namespace VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    source_concept_name VARCHAR NOT NULL,
    period_kind VARCHAR NOT NULL CHECK (period_kind IN ('instant', 'duration')),
    period_start DATE,
    period_end DATE NOT NULL,
    period_policy_content_id VARCHAR NOT NULL,
    fiscal_year INTEGER,
    fiscal_period_kind VARCHAR,
    numeric_kind VARCHAR NOT NULL CHECK (
        numeric_kind IN ('amount', 'rate', 'count', 'pure')
    ),
    value_decimal DECIMAL(38, 18),
    is_nil BOOLEAN NOT NULL,
    nil_reason_code VARCHAR,
    unit_name VARCHAR NOT NULL,
    currency VARCHAR,
    source_decimals INTEGER,
    source_precision INTEGER,
    dimensions_content_id VARCHAR NOT NULL,
    dimensions_json JSON NOT NULL,
    source_fact_key VARCHAR,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (period_kind = 'instant' AND period_start IS NULL)
        OR (period_kind = 'duration'
            AND period_start IS NOT NULL
            AND period_start <= period_end)
    ),
    CHECK (
        (is_nil AND value_decimal IS NULL AND nil_reason_code IS NOT NULL)
        OR (NOT is_nil AND value_decimal IS NOT NULL AND nil_reason_code IS NULL)
    )
);
```

`period_end` is the instant date for instant facts and the source reporting-period end date
for duration facts. `period_start`/`period_end` preserve the source civil dates; the
content-addressed period policy records whether the source end is inclusive and derives a
half-open interval only for temporal joins. Fiscal labels are reported metadata, not a
substitute for dates. LTM is representable only when the source explicitly reports it;
Persistra does not derive it in the raw table.

`dimensions_json` is a canonical sorted list of typed axis/member qualified names with
optional geography/segment identifiers. Empty dimensions identify the consolidated fact.
Unknown dimensions remain exact source concepts; they are not dropped to force a match.
Duplicate facts at the same complete natural key with unequal values quarantine their
filing/concept group unless source revision evidence establishes succession.

Currency is required and USD for monetary facts in the implemented workflow. Nonmonetary
unit names are registered UCUM-style/qualified units such as shares or pure. Counts must
be integral at the declared source precision. Rates/pure facts use the plan-01 rate
profile; amounts/counts must fit the amount profile after source scale. Nonfinite/overflow
input quarantines rather than rounding into range.

`source_decimals` and `source_precision` preserve reported accuracy; they do not authorize
binary-float comparison. Text facts and footnotes stay in the external filing asset or a
custom dataset.

### 7.2 Filing/fact query modes

Fundamental queries explicitly choose:

- `as_reported`: exact `FilingId` and its fact revisions;
- `original`: earliest eligible nonwithdrawn filing in a `ReportId`;
- `latest_filing_in_report`: greatest eligible accepted original/amendment in one
  `ReportId` at the cutoff;
- `latest_known_fact`: greatest eligible filing for each complete fact semantic key across
  report lineages, including a later filing's comparative restatement; or
- `all_filings`: complete eligible filing history.

The complete semantic key is issuer, taxonomy namespace/source concept, period kind/source
dates/period policy, numeric kind, unit/currency, and dimensions; taxonomy version and
filing/report IDs remain lineage rather than silently splitting the same reported meaning.
The mode enters query identity. Neither latest mode at a historical cutoff can see a later
amendment/restatement. `latest_known_fact` may return a mixed-filing fact panel and marks
every filing ID; it is never presented as one filed statement. Facts never automatically
fall back from an amended filing to missing concepts in the original; such coalescing
would create a synthetic statement. A later feature may declare an explicit statement-
completion policy and unsafe findings.

```python no-run
facts = project.services.market.fundamentals.raw_facts(
    issuers=issuer_ids,
    concepts=source_concepts,
    periods=period_range,
    filing_mode=FilingMode.LATEST_KNOWN_FACT,
    context=as_of,
)
```

Rows order by issuer, period end/start, taxonomy namespace/version/concept, dimension
content ID, filing acceptance, and canonical revision ID.

## 8. Curated fundamental normalization

### 8.1 Concept and mapping definitions

```sql
CREATE TABLE canonical.normalized_concepts (
    normalized_concept_id UUID NOT NULL,
    concept_version INTEGER NOT NULL CHECK (concept_version >= 1),
    qualified_name VARCHAR NOT NULL,
    period_kind VARCHAR NOT NULL,
    numeric_kind VARCHAR NOT NULL,
    canonical_unit_name VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (normalized_concept_id, concept_version),
    UNIQUE (qualified_name, concept_version)
);

CREATE TABLE canonical.fundamental_mappings (
    fundamental_mapping_id UUID NOT NULL,
    mapping_version INTEGER NOT NULL CHECK (mapping_version >= 1),
    mapping_policy_name VARCHAR NOT NULL,
    source_taxonomy_namespace VARCHAR NOT NULL,
    source_taxonomy_version_pattern VARCHAR NOT NULL,
    source_concept_name VARCHAR NOT NULL,
    normalized_concept_id UUID NOT NULL,
    normalized_concept_version INTEGER NOT NULL,
    sign_multiplier DECIMAL(38, 18) NOT NULL,
    scale_multiplier DECIMAL(38, 18) NOT NULL,
    dimension_policy_content_id VARCHAR NOT NULL,
    applicability_json JSON NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (fundamental_mapping_id, mapping_version)
);
```

Initial curated qualified concepts are:

- `persistra.fundamental.revenue`
- `persistra.fundamental.net_income`
- `persistra.fundamental.assets`
- `persistra.fundamental.liabilities`
- `persistra.fundamental.equity`
- `persistra.fundamental.cash_and_equivalents`
- `persistra.fundamental.operating_cash_flow`
- `persistra.fundamental.capital_expenditure`
- `persistra.fundamental.common_shares_outstanding`
- `persistra.fundamental.weighted_average_shares_basic`
- `persistra.fundamental.weighted_average_shares_diluted`
- `persistra.fundamental.eps_basic`
- `persistra.fundamental.eps_diluted`

Definitions pin period/numeric kind, units, sign, inclusion/exclusion, dimensional behavior,
and documentation. A mapping is exact and reviewable; tag-name similarity cannot register
one. Mapping/code changes append versions. A breaking concept meaning allocates a new
concept identity/name.

### 8.2 Immutable normalization results

```sql
CREATE TABLE canonical.fundamental_normalization_runs (
    fundamental_normalization_run_id UUID PRIMARY KEY,
    mapping_policy_content_id VARCHAR NOT NULL,
    input_catalog_sequence BIGINT NOT NULL,
    input_catalog_chain_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR NOT NULL,
    result_count BIGINT NOT NULL CHECK (result_count >= 0),
    normalized_count BIGINT NOT NULL CHECK (normalized_count >= 0),
    not_applicable_count BIGINT NOT NULL CHECK (not_applicable_count >= 0),
    unavailable_count BIGINT NOT NULL CHECK (unavailable_count >= 0),
    conflict_count BIGINT NOT NULL CHECK (conflict_count >= 0),
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        result_count = normalized_count + not_applicable_count
            + unavailable_count + conflict_count
    )
);

CREATE TABLE canonical.fundamental_normalizations (
    fundamental_normalization_id UUID PRIMARY KEY,
    normalization_run_id UUID NOT NULL,
    raw_canonical_revision_id UUID NOT NULL,
    fundamental_mapping_id UUID NOT NULL,
    mapping_version INTEGER NOT NULL CHECK (mapping_version >= 1),
    normalized_concept_id UUID NOT NULL,
    normalized_concept_version INTEGER NOT NULL CHECK (normalized_concept_version >= 1),
    normalized_value DECIMAL(38, 18),
    canonical_unit_name VARCHAR NOT NULL,
    normalization_status VARCHAR NOT NULL CHECK (
        normalization_status IN ('normalized', 'not_applicable', 'unavailable', 'conflict')
    ),
    reason_codes_json JSON NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (normalization_status = 'normalized' AND normalized_value IS NOT NULL)
        OR (normalization_status <> 'normalized' AND normalized_value IS NULL)
    ),
    UNIQUE (raw_canonical_revision_id, fundamental_mapping_id, mapping_version)
);
```

Normalization is deterministic bounded market-database work performed during accepted fact
commit or an explicit market-write backfill. A run pins its mapping policy, input catalog
sequence/chain content ID, execution content, output manifest, and status counts; the run
and all new output rows commit atomically. Each result ties one raw revision and mapping
version to its first producing run; it never changes the raw payload. An exact retry
resolves the existing run by execution content, while a later bounded run processes only
missing result keys. A mapping backfill appends results and catalog state, then requires a
new snapshot.
Conflict and not-applicable rows remain visible so normalization does not create silent row
loss.

The result inherits the raw fact's public availability/safety and additionally records its
own `created_at` for project-knowledge conformance. Query selection pins a mapping policy
and snapshot, then requires normalization creation by the project cutoff when enabled.
No mapping result is given an earlier public-information time than its source fact.

Multiple source facts mapping to one concept/period/dimension remain multiple candidates.
The mapping policy must choose an exact priority or return conflict; it cannot sum or
coalesce unless the concept definition explicitly declares an aggregation with complete
input lineage. Ratios, TTM, growth, and per-share calculations remain plan-08 features.

## 9. Estimate measure and contributor definitions

```sql
CREATE TABLE canonical.estimate_measures (
    estimate_measure_id UUID NOT NULL,
    measure_version INTEGER NOT NULL CHECK (measure_version >= 1),
    qualified_name VARCHAR NOT NULL,
    entity_kind VARCHAR NOT NULL,
    numeric_kind VARCHAR NOT NULL,
    canonical_unit_name VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (estimate_measure_id, measure_version),
    UNIQUE (qualified_name, measure_version)
);

CREATE TABLE canonical.estimate_contributors (
    estimate_contributor_id UUID PRIMARY KEY,
    source_id UUID NOT NULL,
    source_contributor_key_content_id VARCHAR NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, source_contributor_key_content_id)
);

CREATE TABLE canonical.estimate_contributor_versions (
    estimate_contributor_id UUID NOT NULL,
    contributor_version INTEGER NOT NULL CHECK (contributor_version >= 1),
    display_label VARCHAR,
    licensing_class VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (estimate_contributor_id, contributor_version)
);
```

Initial measure definitions include revenue, EBITDA, EBIT, EPS basic/diluted, net income,
free cash flow, capital expenditure, and target price. Measure definitions state issuer/
security/instrument grain, fiscal/horizon support, currency/unit, split basis, and actual-
link policy. A changed economic meaning allocates a new measure identity.

Contributor identity is source-scoped and optional in public output. Corrected labels or
licensing changes append contributor versions. Queries resolve and return the exact version
eligible in their snapshot/project cutoff; estimate observations retain only the stable ID
so metadata corrections do not rewrite economic records. Licensed names may be null/redacted
while stable local IDs retain revision lineage. Persistra never attempts to identify an
anonymized contributor across providers.

## 10. Individual estimates, consensus, and actuals

### 10.1 Shared target contract

Every estimate-like row has exactly one target form:

- `fiscal_period`: fiscal year/kind and target period end, optionally linked `ReportId`; or
- `fixed_horizon`: positive horizon days and explicit target instant/date under a versioned
  horizon policy.

Source labels such as “FY1” or “next twelve months” are preserved but must resolve through
a registered policy at the observation's event/publication time. A moving label without
resolved target is unsafe and cannot join historical actuals.

### 10.2 Individual observations

```sql
CREATE TABLE canonical.individual_estimates (
    canonical_revision_id UUID PRIMARY KEY,
    source_estimate_key VARCHAR NOT NULL,
    estimate_measure_id UUID NOT NULL,
    measure_version INTEGER NOT NULL CHECK (measure_version >= 1),
    subject_entity_kind VARCHAR NOT NULL,
    subject_entity_id UUID NOT NULL,
    estimate_contributor_id UUID,
    target_kind VARCHAR NOT NULL CHECK (target_kind IN ('fiscal_period', 'fixed_horizon')),
    target_fiscal_year INTEGER,
    target_fiscal_period_kind VARCHAR,
    target_period_end DATE,
    target_report_id UUID,
    horizon_days INTEGER,
    target_at TIMESTAMPTZ,
    target_policy_content_id VARCHAR NOT NULL,
    value_decimal DECIMAL(38, 18) NOT NULL,
    unit_name VARCHAR NOT NULL,
    currency VARCHAR,
    split_basis_content_id VARCHAR,
    source_revision_label VARCHAR,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (target_kind = 'fiscal_period'
            AND target_fiscal_year IS NOT NULL
            AND target_fiscal_period_kind IS NOT NULL
            AND target_period_end IS NOT NULL
            AND horizon_days IS NULL
            AND target_at IS NULL)
        OR (target_kind = 'fixed_horizon'
            AND target_fiscal_year IS NULL
            AND target_fiscal_period_kind IS NULL
            AND target_report_id IS NULL
            AND horizon_days IS NOT NULL
            AND horizon_days > 0
            AND target_at IS NOT NULL
            AND target_period_end IS NULL)
    )
);
```

Plan-03 `event_at` is the estimate observation/revision instant when the source supplies
it. Safe estimates require revision-specific `published_at`/`available_at`; an undated
current estimate is unsafe. Values must be finite, unit/currency compatible, and subject/
measure grain valid. Split-sensitive per-share values pin the share-basis action policy.

### 10.3 Consensus snapshots

```sql
CREATE TABLE canonical.estimate_consensus (
    canonical_revision_id UUID PRIMARY KEY,
    source_consensus_key VARCHAR NOT NULL,
    estimate_measure_id UUID NOT NULL,
    measure_version INTEGER NOT NULL CHECK (measure_version >= 1),
    subject_entity_kind VARCHAR NOT NULL,
    subject_entity_id UUID NOT NULL,
    target_kind VARCHAR NOT NULL CHECK (target_kind IN ('fiscal_period', 'fixed_horizon')),
    target_fiscal_year INTEGER,
    target_fiscal_period_kind VARCHAR,
    target_period_end DATE,
    target_report_id UUID,
    horizon_days INTEGER,
    target_at TIMESTAMPTZ,
    target_policy_content_id VARCHAR NOT NULL,
    contributor_count INTEGER NOT NULL CHECK (contributor_count >= 0),
    mean_value DECIMAL(38, 18),
    median_value DECIMAL(38, 18),
    high_value DECIMAL(38, 18),
    low_value DECIMAL(38, 18),
    standard_deviation DECIMAL(38, 18),
    unit_name VARCHAR NOT NULL,
    currency VARCHAR,
    methodology_content_id VARCHAR NOT NULL,
    constituent_manifest_content_id VARCHAR,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (target_kind = 'fiscal_period'
            AND target_fiscal_year IS NOT NULL
            AND target_fiscal_period_kind IS NOT NULL
            AND target_period_end IS NOT NULL
            AND horizon_days IS NULL
            AND target_at IS NULL)
        OR (target_kind = 'fixed_horizon'
            AND target_fiscal_year IS NULL
            AND target_fiscal_period_kind IS NULL
            AND target_report_id IS NULL
            AND horizon_days IS NOT NULL
            AND horizon_days > 0
            AND target_at IS NOT NULL
            AND target_period_end IS NULL)
    ),
    CHECK (
        (contributor_count = 0
            AND mean_value IS NULL
            AND median_value IS NULL
            AND high_value IS NULL
            AND low_value IS NULL
            AND standard_deviation IS NULL)
        OR (contributor_count > 0
            AND COALESCE(mean_value, median_value, high_value, low_value) IS NOT NULL)
    ),
    CHECK (
        (high_value IS NULL AND low_value IS NULL)
        OR (high_value IS NOT NULL AND low_value IS NOT NULL AND low_value <= high_value)
    ),
    CHECK (standard_deviation IS NULL OR standard_deviation >= 0),
    CHECK (
        mean_value IS NULL OR low_value IS NULL
        OR (low_value <= mean_value AND mean_value <= high_value)
    ),
    CHECK (
        median_value IS NULL OR low_value IS NULL
        OR (low_value <= median_value AND median_value <= high_value)
    )
);
```

Consensus is a source observation with its own event/publication/revision time and method.
At least one location statistic is required unless contributor count is zero and the source
explicitly publishes an empty consensus, in which case every statistic is null. High/low
are supplied together; when present they bound mean/median, and dispersion is nonnegative.
A constituent manifest is optional/licensing-controlled.

Persistra may later compute a separately named derived consensus from eligible individual
estimates, but it never stores that calculation as this source consensus or silently
compares unequal methodologies.

### 10.4 Reported actuals

```sql
CREATE TABLE canonical.estimate_actuals (
    canonical_revision_id UUID PRIMARY KEY,
    source_actual_key VARCHAR NOT NULL,
    estimate_measure_id UUID NOT NULL,
    measure_version INTEGER NOT NULL CHECK (measure_version >= 1),
    subject_entity_kind VARCHAR NOT NULL,
    subject_entity_id UUID NOT NULL,
    target_fiscal_year INTEGER,
    target_fiscal_period_kind VARCHAR,
    target_period_end DATE NOT NULL,
    value_decimal DECIMAL(38, 18) NOT NULL,
    unit_name VARCHAR NOT NULL,
    currency VARCHAR,
    filing_id UUID,
    raw_fact_revision_id UUID,
    fundamental_normalization_id UUID,
    actual_policy_content_id VARCHAR NOT NULL,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (target_fiscal_year IS NULL AND target_fiscal_period_kind IS NULL)
        OR (target_fiscal_year IS NOT NULL AND target_fiscal_period_kind IS NOT NULL)
    )
);
```

An actual may point to an accepted filing/raw/normalized fact or be an independent source
observation. Its own publication/availability remains authority and cannot precede linked
filing/fact availability. Corrected actuals are revisions with independent timing. Surprise
and “beat/miss” are absent from canonical storage and cannot be computed until both exact
estimate/consensus and actual revisions are eligible.

## 11. Macroeconomic series and vintages

### 11.1 Series definitions

```sql
CREATE TABLE canonical.macro_series (
    macro_series_id UUID NOT NULL,
    series_version INTEGER NOT NULL CHECK (series_version >= 1),
    qualified_name VARCHAR NOT NULL,
    frequency VARCHAR NOT NULL,
    seasonal_adjustment_status VARCHAR NOT NULL,
    geography_code VARCHAR NOT NULL,
    unit_name VARCHAR NOT NULL,
    numeric_kind VARCHAR NOT NULL,
    vintage_completeness VARCHAR NOT NULL CHECK (
        vintage_completeness IN ('complete', 'latest_only', 'unknown')
    ),
    period_policy_content_id VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (macro_series_id, series_version),
    UNIQUE (qualified_name, series_version)
);
```

Frequency is a registered value such as daily, weekly, monthly, quarterly, or annual;
irregular releases declare `irregular`. Seasonal adjustment is `seasonally_adjusted`,
`not_seasonally_adjusted`, or a registered source status. Geography uses a registered ISO/
statistical-area code. Definitions pin units, scaling, aggregation interpretation, period
boundaries, release authority, and vintage guarantees.

### 11.2 Releases and observations

```sql
CREATE TABLE canonical.macro_releases (
    macro_release_id UUID PRIMARY KEY,
    macro_series_id UUID NOT NULL,
    source_id UUID NOT NULL,
    source_release_key VARCHAR NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_id, macro_series_id, source_release_key)
);

CREATE TABLE canonical.macro_release_observations (
    canonical_revision_id UUID PRIMARY KEY,
    macro_release_id UUID NOT NULL,
    macro_series_id UUID NOT NULL,
    series_version INTEGER NOT NULL CHECK (series_version >= 1),
    release_at TIMESTAMPTZ NOT NULL,
    release_sequence BIGINT NOT NULL CHECK (release_sequence >= 1),
    release_manifest_content_id VARCHAR NOT NULL,
    source_metadata_json JSON NOT NULL
);

CREATE TABLE canonical.macro_observations (
    canonical_revision_id UUID PRIMARY KEY,
    macro_series_id UUID NOT NULL,
    series_version INTEGER NOT NULL CHECK (series_version >= 1),
    macro_release_id UUID NOT NULL,
    macro_release_revision_id UUID NOT NULL,
    source_vintage_key VARCHAR NOT NULL,
    observation_period_start DATE NOT NULL,
    observation_period_end DATE NOT NULL,
    vintage_status VARCHAR NOT NULL CHECK (
        vintage_status IN ('advance', 'preliminary', 'revised', 'final', 'benchmark_revision')
    ),
    value_decimal DECIMAL(38, 18),
    is_missing BOOLEAN NOT NULL,
    missing_reason_code VARCHAR,
    unit_name VARCHAR NOT NULL,
    source_metadata_json JSON NOT NULL,
    CHECK (observation_period_start <= observation_period_end),
    CHECK (
        (is_missing AND value_decimal IS NULL AND missing_reason_code IS NOT NULL)
        OR (NOT is_missing AND value_decimal IS NOT NULL AND missing_reason_code IS NULL)
    )
);
```

One stable release master identifies a source-scoped series/release key. Its revisioned
release observation carries the exact time, sequence, and atomic payload manifest; every
macro point pins that release revision. For the original release, plan-03 `event_at` and
normally `published_at` equal `release_at`; a correction keeps the source release instant
but uses correction-specific publication/availability evidence. A reviewed dissemination
policy may make `available_at` later, never earlier. Period end is not release time.

Observation start/end preserve source civil dates, including equal dates for daily point
observations. The series version's period policy defines whether endpoints are labels or
inclusive/exclusive boundaries and derives any half-open join interval; queries do not
invent a universal end convention.

For each series/observation period, vintages order by release time, release sequence,
source vintage key bytes, then revision ID. A provider correction to release time,
sequence, or manifest appends a release-observation revision and atomically revises every
affected point so each continues to pin exact release evidence. A correction to the same
source vintage key is a plan-03 point revision; a newly published vintage/rebenchmark is
another natural key/release. Point-in-time queries select the latest eligible vintage, not
the greatest value or latest database row.

`latest_only` means the provider cannot supply historical vintages. Such rows may support
current exploration but every historical panel/materialization is unsafe; snapshotting
does not cure survivorship. `unknown` is also unsafe until conformance evidence upgrades a
new series version.

```python no-run
macro = project.services.market.macro.query(
    series=MacroSeriesRef("persistra.macro.us.cpi_all_items", version=1),
    periods=period_range,
    context=as_of,
    vintage_mode=MacroVintageMode.LATEST_KNOWN,
)
```

Modes are exact release, first release, latest known at cutoff, or all eligible vintages.
No query seasonally adjusts, forward-fills, resamples, or revises observations implicitly.

## 12. Benchmark definitions

```sql
CREATE TABLE canonical.benchmarks (
    benchmark_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_catalog_sequence BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE canonical.benchmark_versions (
    benchmark_id UUID NOT NULL,
    benchmark_version INTEGER NOT NULL CHECK (benchmark_version >= 1),
    benchmark_kind VARCHAR NOT NULL CHECK (
        benchmark_kind IN ('instrument', 'source_series', 'constituents')
    ),
    instrument_id UUID,
    currency VARCHAR NOT NULL,
    calendar_id UUID NOT NULL,
    methodology_content_id VARCHAR NOT NULL,
    licensing_class VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (benchmark_id, benchmark_version),
    CHECK (
        (benchmark_kind = 'instrument' AND instrument_id IS NOT NULL)
        OR (benchmark_kind <> 'instrument' AND instrument_id IS NULL)
    )
);
```

Initial built-in definition name `persistra.benchmark.sp500` is a versioned reference
whose concrete kind/source is configured and licensed; Persistra does not ship proprietary
constituent history without permission. Instrument benchmarks point to plan-04
`InstrumentId` and use plan-05 raw/adjusted bar policies selected later. Source-series and
constituent benchmarks use the schemas below.

A version change may update source/methodology/licensing while preserving benchmark
lineage. A change to the economic benchmark allocates a new `BenchmarkId`/qualified name.
All definitions are snapshot-pinned.

## 13. Benchmark source series and constituents

### 13.1 Source series

```sql
CREATE TABLE canonical.benchmark_series_observations (
    canonical_revision_id UUID PRIMARY KEY,
    benchmark_id UUID NOT NULL,
    benchmark_version INTEGER NOT NULL CHECK (benchmark_version >= 1),
    series_kind VARCHAR NOT NULL CHECK (
        series_kind IN ('price_index', 'total_return_index', 'period_return')
    ),
    interval_start TIMESTAMPTZ,
    interval_end TIMESTAMPTZ NOT NULL,
    session_date DATE,
    value_decimal DECIMAL(38, 18) NOT NULL,
    currency VARCHAR NOT NULL,
    calendar_schedule_content_id VARCHAR NOT NULL,
    source_methodology_content_id VARCHAR NOT NULL,
    CHECK (
        (series_kind IN ('price_index', 'total_return_index')
            AND interval_start IS NULL
            AND value_decimal > 0)
        OR (series_kind = 'period_return'
            AND interval_start IS NOT NULL
            AND interval_start < interval_end)
    )
);
```

Index levels are positive point values at `interval_end`; `interval_start` is null.
Period returns require a nonnull half-open interval and may be negative but greater than
`-1` unless the source methodology explicitly permits a complete loss boundary. Source
levels/returns are canonical observations, not recalculated from constituents. Availability
must follow source publication, not session date alone.

### 13.2 Constituents

```sql
CREATE TABLE canonical.benchmark_constituents (
    canonical_revision_id UUID PRIMARY KEY,
    benchmark_id UUID NOT NULL,
    benchmark_version INTEGER NOT NULL CHECK (benchmark_version >= 1),
    instrument_id UUID NOT NULL,
    membership_role VARCHAR NOT NULL,
    weight DECIMAL(38, 18),
    index_shares DECIMAL(38, 12),
    divisor_contribution DECIMAL(38, 18),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    source_valid_from_date DATE NOT NULL,
    source_valid_to_date DATE,
    source_interval_convention VARCHAR NOT NULL,
    date_policy_content_id VARCHAR NOT NULL,
    calendar_schedule_content_id VARCHAR NOT NULL,
    methodology_content_id VARCHAR NOT NULL,
    source_metadata_json JSON NOT NULL,
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (
        source_valid_to_date IS NULL
        OR source_valid_from_date <= source_valid_to_date
    )
);
```

Resolved intervals are UTC half-open. Source civil dates and their inclusive/exclusive
convention remain exact; a content-addressed date policy and exact plan-04 calendar schedule
derive the instants. Publication/availability comes from the canonical revision and never
from a resolved effective instant alone. Exclusion closes an effective interval through a
new revision; it does not delete the earlier observation. Weights/shares are optional source
facts and never become portfolio weights implicitly.

When a source claims normalized weights, eligible effective cross-sections validate finite
nonnegative weights, each at most one, and sum within the declared tolerance. Current-only
constituents are unsafe historically. Multiple providers remain separate; precedence
selects one complete cross-section. Source constituents do not prove that a locally
calculated return equals the official series because divisor, float, action, timing, and
methodology data may be incomplete.

Benchmark queries return a typed definition plus exactly one of instrument reference,
source series, or constituent audit. Later consumers must record the benchmark version,
snapshot, calendar, source policy, return/adjustment policy, and any reconstruction warning.

## 14. Risk-free curve definitions

```sql
CREATE TABLE canonical.risk_free_curves (
    risk_free_curve_id UUID NOT NULL,
    curve_version INTEGER NOT NULL CHECK (curve_version >= 1),
    qualified_name VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    quote_kind VARCHAR NOT NULL CHECK (
        quote_kind IN (
            'simple_yield', 'bond_equivalent_yield', 'periodic_zero',
            'continuous_zero', 'discount_factor', 'overnight_rate'
        )
    ),
    compounding_kind VARCHAR NOT NULL CHECK (
        compounding_kind IN ('simple', 'periodic', 'continuous', 'discount_factor')
    ),
    compounding_periods_per_year INTEGER,
    day_count_kind VARCHAR NOT NULL CHECK (
        day_count_kind IN ('act_360', 'act_365f', 'act_act_isda', 'thirty_360_us')
    ),
    calendar_id UUID NOT NULL,
    business_day_policy_content_id VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    created_catalog_sequence BIGINT NOT NULL,
    PRIMARY KEY (risk_free_curve_id, curve_version),
    UNIQUE (qualified_name, curve_version),
    CHECK (
        (compounding_kind = 'periodic'
            AND compounding_periods_per_year IS NOT NULL
            AND compounding_periods_per_year > 0)
        OR (compounding_kind <> 'periodic' AND compounding_periods_per_year IS NULL)
    ),
    CHECK (
        (quote_kind = 'discount_factor' AND compounding_kind = 'discount_factor')
        OR (quote_kind <> 'discount_factor' AND compounding_kind <> 'discount_factor')
    )
);
```

Initial definitions cover a reviewed USD overnight/risk-free series and US Treasury-style
curve only when a redistributable provider is configured. Names such as
`persistra.risk_free.usd_overnight` identify definitions, not bundled claims about a
particular proprietary rate.

Quote kind, compounding, day count, currency, effective-date calendar, source scaling, and
business-day convention are immutable definition semantics. Changing one incompatibly
allocates a new curve identity/name. Canonical quotes are not converted to a supposedly
equivalent convention in place.

## 15. Risk-free series and curve points

```sql
CREATE TABLE canonical.risk_free_points (
    canonical_revision_id UUID PRIMARY KEY,
    risk_free_curve_id UUID NOT NULL,
    curve_version INTEGER NOT NULL CHECK (curve_version >= 1),
    source_release_key VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    release_at TIMESTAMPTZ NOT NULL,
    tenor_kind VARCHAR NOT NULL CHECK (tenor_kind IN ('days', 'months')),
    tenor_count INTEGER NOT NULL CHECK (tenor_count > 0),
    maturity_date DATE,
    rate_or_factor DECIMAL(38, 18) NOT NULL,
    quote_kind VARCHAR NOT NULL CHECK (
        quote_kind IN (
            'simple_yield', 'bond_equivalent_yield', 'periodic_zero',
            'continuous_zero', 'discount_factor', 'overnight_rate'
        )
    ),
    compounding_kind VARCHAR NOT NULL CHECK (
        compounding_kind IN ('simple', 'periodic', 'continuous', 'discount_factor')
    ),
    compounding_periods_per_year INTEGER,
    day_count_kind VARCHAR NOT NULL CHECK (
        day_count_kind IN ('act_360', 'act_365f', 'act_act_isda', 'thirty_360_us')
    ),
    source_curve_manifest_content_id VARCHAR NOT NULL,
    source_metadata_json JSON NOT NULL,
    CHECK (
        (compounding_kind = 'periodic'
            AND compounding_periods_per_year IS NOT NULL
            AND compounding_periods_per_year > 0)
        OR (compounding_kind <> 'periodic' AND compounding_periods_per_year IS NULL)
    ),
    CHECK (
        (quote_kind = 'discount_factor'
            AND compounding_kind = 'discount_factor'
            AND rate_or_factor > 0)
        OR (quote_kind <> 'discount_factor' AND compounding_kind <> 'discount_factor')
    )
);
```

One-day tenor represents an overnight series; no zero tenor is invented. Month tenors use
the definition's business-day/end-of-month policy. When supplied, maturity date must equal
the policy-resolved effective date plus tenor. Each point repeats its source convention so
corruption/mismatch is detectable against the definition.

Rate/yield quotes may be negative when the source convention permits. Discount factors
must be positive. Values are canonical decimals; percent/basis-point source scaling is
resolved by the registered codec and preserved in source metadata. For an original source
release, plan-03 `event_at` and normally `published_at` equal `release_at`; a correction
uses its own publication/availability evidence and never inherits the original cutoff.

All points sharing `(curve, version, source release key, effective date)` form an atomic
disposition group and one manifest. Missing expected tenors warn or quarantine under the
definition; partial curve publication cannot masquerade as complete. Provider corrections
to a release are revisions with independent availability.

Point queries perform no interpolation/extrapolation by default. Exact tenor/maturity
lookup returns selected, missing, unavailable, unsafe, or ambiguous with lineage. A
versioned `RateConversionPolicy` may produce an ephemeral research view declaring target
compounding/day count, exact formula, tenor selection, interpolation (`none` initially),
extrapolation (`forbid` initially), code identity, and safety. It never writes back to the
canonical table.

```python no-run
rate = project.services.market.rates.at(
    curve=RiskFreeCurveRef("persistra.risk_free.usd_overnight", version=1),
    effective_date=decision_date,
    tenor=Tenor.days(1),
    context=as_of,
)
```

## 16. Unified point-in-time APIs and bounded behavior

All queries require one exact market/composite snapshot, bounded subject/series/period
selection, public cutoff or cutoff policy, optional project cutoff, and source precedence.
They never default to current filing, latest consensus, final macro vintage, current
benchmark constituents, or today's curve.

Service surface:

```python no-run
fundamentals.filings(issuers, periods, context=as_of)
fundamentals.raw_facts(concepts, issuers, periods, filing_mode, context=as_of)
fundamentals.normalized(
    concepts, issuers, periods, filing_mode, mapping_policy, context=as_of
)
estimates.individual(measures, subjects, targets, context=as_of)
estimates.consensus(measures, subjects, targets, context=as_of)
estimates.actuals(measures, subjects, periods, context=as_of)
macro.query(series, periods, context=as_of, vintage_mode=MacroVintageMode.LATEST_KNOWN)
benchmarks.resolve(benchmark, context=as_of)
benchmarks.series(benchmark, periods, context=as_of)
benchmarks.constituents(benchmark, effective_range, context=as_of)
rates.points(curve, effective_dates, tenors, context=as_of)
```

Fundamental/estimate queries require issuer/entity bounds and period/target ranges. Macro,
benchmark-series/constituent, and rate queries require series/benchmark/curve plus date
range; resolving only a benchmark definition does not. Default
dataframe ceiling is 2,000,000 rows and deterministic chunk size is 100,000. Filing fact
dimensions and contributor/constituent manifests are excluded by default and require an
explicit bounded/licensing-permitted projection.

Results include coverage audits distinguishing selected, missing, unavailable by cutoff,
nil/source-missing, retracted, conflict/quarantined summary, unsafe, and definition/mapping
not applicable. Audit detail about future/unavailable candidates is excluded from
strategy-facing datasets and cross-sectional counts under plan 07.

## 17. Public dataframe contracts

Frames use plan-01 wire IDs, UTC microsecond timestamps, Python dates, canonical JSON,
nullable pandas dtypes, and finite `float64` analytical values converted explicitly from
stored decimals. Exact-record APIs preserve `Decimal`, `Money`, and `Rate`. Empty frames
retain schema/dtypes.

| Frame | Schema | Required columns |
| --- | --- | --- |
| Filings | `persistra.dataframe.filings@1` | filing/report/issuer/source/revision IDs, accession/form/status, filing/acceptance/report period/fiscal fields, amendment link, taxonomy/document/availability/safety |
| Raw facts | `persistra.dataframe.fundamental_raw@1` | revision/filing/report/issuer/source IDs, concept/taxonomy, source dates/period policy/fiscal kind, value/nil/unit/currency/precision, dimensions, acceptance/availability/safety |
| Normalized facts | `persistra.dataframe.fundamental_normalized@1` | normalization/run/raw revision/mapping/concept IDs+versions, normalized value/unit/status/reasons, source availability, normalization creation/safety |
| Individual estimates | `persistra.dataframe.estimates_individual@1` | revision/measure/subject/contributor/source IDs and contributor version, target/horizon, value/unit/currency, event/publication/availability/revision/split basis/safety |
| Consensus | `persistra.dataframe.estimates_consensus@1` | revision/measure/subject/source IDs, target, count/statistics/unit/currency/method, event/publication/availability/safety |
| Actuals | `persistra.dataframe.estimate_actuals@1` | revision/measure/subject/source and linked fact IDs, fiscal target, value/unit/currency, publication/availability/safety |
| Macro | `persistra.dataframe.macro@1` | revision/series/release/release-revision/source IDs, period, release/vintage/status, value/missing/unit, availability/completeness/safety |
| Benchmark series | `persistra.dataframe.benchmark_series@1` | revision/benchmark/version/source IDs, kind/interval/session/value/currency/calendar/method/availability/safety |
| Benchmark constituents | `persistra.dataframe.benchmark_constituents@1` | revision/benchmark/version/instrument/source IDs, role/weight/shares/divisor, source dates/convention, resolved validity/date policy/calendar, availability/method/safety |
| Risk-free points | `persistra.dataframe.risk_free_points@1` | revision/curve/version/source IDs, effective/release/availability, tenor/maturity, quote/rate/factor, compounding/day-count/manifest/safety |

Deterministic order is entity/series/benchmark/curve, target or observation period/effective
date, release/publication, source key/revision ordinal, then canonical revision ID.

## 18. Validation and disposition rules

### 18.1 Fundamental rules

- Filing accession, issuer/report/amendment, form, acceptance, document content, and
  taxonomy identities resolve exactly.
- Facts reference the same filing/report/issuer, have valid instant/duration periods,
  finite scaled decimals, conditional nil fields, registered units, canonical dimensions,
  and source precision.
- Same filing/concept/period/unit/dimension conflicts quarantine atomically.
- Mapping definitions are type/unit/period compatible, finite, bounded, and nonambiguous.
- Normalization run inputs, output manifest, status counts, row ownership, and execution
  content reproduce exactly and never overwrite raw facts.

### 18.2 Estimate rules

- Measure and subject grain, target form, fiscal/horizon policy, unit/currency, split basis,
  finite values, contributor licensing, and publication/revision evidence validate.
- Consensus conditional statistics, counts, ordering, dispersion, methodology, and target
  validate as one record; Persistra does not fill absent statistics.
- Actual links match measure/subject/period/unit and cannot be available before linked
  filing/fact. Estimate/actual mismatches remain explicit rather than coerced.

### 18.3 Macro, benchmark, and rate rules

- Macro series/release/period/frequency/unit/geography/seasonal/vintage contracts validate;
  one release manifest is complete and internally ordered.
- Benchmark kind-specific definitions, series interval/value, constituent effective
  intervals/weights, calendar, source method, and licensing validate.
- Rate curve/point conventions repeat consistently; release/effective/tenor/maturity,
  numeric domain, atomic curve manifests, expected tenors, and calendar rules validate.
- Cross-series statistical anomalies, yield-curve inversions, benchmark jumps, estimate
  dispersion, and fundamental changes warn by default; economically plausible extremes
  are not structural errors.

### 18.4 Stable codes

| Code | Default action |
| --- | --- |
| `filing.identity.unresolved` | quarantine group |
| `filing.amendment.invalid` | quarantine group |
| `filing.acceptance.missing` | accept unsafe or quarantine under safe-only policy |
| `filing.document.invalid` | quarantine record |
| `fundamental.period.invalid` | quarantine record |
| `fundamental.value.invalid` | quarantine record |
| `fundamental.unit.invalid` | quarantine record |
| `fundamental.dimensions.invalid` | quarantine group |
| `fundamental.fact.conflict` | quarantine group |
| `fundamental.mapping.incompatible` | reject definition |
| `fundamental.normalization.conflict` | persisted conflict result |
| `estimate.measure.unresolved` | quarantine record |
| `estimate.target.invalid` | quarantine record |
| `estimate.publication.missing` | accept unsafe or quarantine under policy |
| `estimate.value.invalid` | quarantine record |
| `estimate.consensus.inconsistent` | quarantine record |
| `estimate.actual.link_invalid` | quarantine group |
| `macro.series.unresolved` | quarantine record |
| `macro.period.invalid` | quarantine record |
| `macro.release.invalid` | quarantine group |
| `macro.vintage.latest_only` | persistent unsafe finding |
| `macro.value.anomalous` | warning |
| `benchmark.definition.invalid` | reject definition |
| `benchmark.series.invalid` | quarantine record |
| `benchmark.constituent.invalid` | quarantine group |
| `benchmark.weights.inconsistent` | warning/quarantine under methodology |
| `rate.curve.definition_invalid` | reject definition |
| `rate.point.convention_mismatch` | quarantine group |
| `rate.point.invalid` | quarantine record |
| `rate.curve.incomplete` | warning/quarantine under definition |
| `rate.interpolation.forbidden` | structured unavailable result |

Structural model/content failures reject batches. Separable invalid rows quarantine;
filing/fact, consensus, macro-release, benchmark cross-section, and curve-release
invariants use atomic groups. Anomaly rules cannot invent a correction.

## 19. Safety and point-in-time behavior

Safe inputs require exact snapshots, dual cutoffs, resolved entities/definitions, explicit
source precedence, revision-specific publication/availability, complete vintage history
when historically required, compatible normalization, and licensed/bounded execution.

Unsafe states include missing filing acceptance, present-day-only fundamentals, undated
current estimates, consensus without methodology when required, moving forecast labels,
latest-only macro histories, current benchmark constituents applied historically,
unversioned benchmark methodology, final-revised source series used at old cutoffs,
unidentified rate quote conventions, and interpolated/extrapolated rates without a
conforming versioned policy.

Source revision availability and derived normalization creation are separate. A fact can
be public at an old date while a particular mapping was unavailable to a project until
later. Similarly, actual publication—not fiscal period end—gates surprise; macro release—not
observation period—gates macro values; benchmark publication—not effective date alone—gates
constituents; and rate release—not effective date—gates rates.

Unsafe/materialized/exported data cannot shed findings. Normal missing/nil/no-consensus/
no-release/no-exact-tenor states are typed data. Strategy-facing contexts receive no labels,
future-candidate evidence, or retrospective latest values.

## 20. Events, exceptions, and diagnostics

### 20.1 Domain events

Source observations remain plan-03 canonical rows/batch events; no event is emitted per
fact, estimate, macro point, constituent, or curve point. Definition/master lifecycle
events are:

| Event type | Aggregate kind |
| --- | --- |
| `persistra.fundamental.report_created@1` | `persistra.aggregate.report` |
| `persistra.fundamental.filing_created@1` | `persistra.aggregate.filing` |
| `persistra.fundamental.mapping_registered@1` | `persistra.aggregate.fundamental_mapping` |
| `persistra.fundamental.normalization_completed@1` | `persistra.aggregate.fundamental_normalization_run` |
| `persistra.estimate.measure_registered@1` | `persistra.aggregate.estimate_measure` |
| `persistra.estimate.contributor_version_registered@1` | `persistra.aggregate.estimate_contributor` |
| `persistra.macro.series_registered@1` | `persistra.aggregate.macro_series` |
| `persistra.macro.release_created@1` | `persistra.aggregate.macro_release` |
| `persistra.benchmark.version_registered@1` | `persistra.aggregate.benchmark` |
| `persistra.risk_free.curve_registered@1` | `persistra.aggregate.risk_free_curve` |

Events commit atomically with normalized state. A normalization event uses the run ID as
aggregate ID and summarizes its input chain/output manifest and counts, not every output
row. Macro
release creation emits once for the stable master; release-observation corrections remain
covered by plan-03 batch/catalog events.

### 20.2 Exceptions

| Exception | Reason code |
| --- | --- |
| `FilingResolutionError` | `filing.resolution.failed` |
| `FundamentalQueryError` | `fundamental.query.invalid` |
| `FundamentalMappingError` | `fundamental.mapping.invalid` |
| `EstimateQueryError` | `estimate.query.invalid` |
| `MacroQueryError` | `macro.query.invalid` |
| `BenchmarkResolutionError` | `benchmark.resolution.failed` |
| `RateConventionError` | `rate.convention.invalid` |
| `RateUnavailableError` | `rate.unavailable` |
| `MarketDataLimitError` | `market.query.row_limit` |

Expected absent/nil/conflict/unavailable/unsafe results are data. Exceptions cover invalid
API/configuration, resource limits, broken identities/invariants, or atomic-operation
failure. `RateUnavailableError` is used only by an explicit strict `require` accessor; the
default point lookup returns typed unavailability. Logs/evidence are bounded and redact
licensed documents, contributors, constituents, and source payloads.

## 21. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Filing date exists but acceptance missing | Unsafe/unknown availability; never use midnight filing date |
| Amendment omits a prior fact | Do not coalesce original statement silently |
| Same raw tag has different dimensions | Distinct facts; dimensions never dropped |
| Two tags map to one normalized concept | Exact mapping priority or conflict, no arbitrary sum |
| Mapping improves after snapshot | New normalization/catalog state and snapshot; old query stable |
| Exact normalization run retried | Resolve the existing execution/run; do not duplicate rows |
| Fact decimal exceeds storage | Quarantine with original external evidence, no saturation |
| Contributor is licensed/anonymized | Stable source-scoped ID, label redacted |
| Estimate says FY1 | Resolve fixed fiscal target with policy or mark unsafe |
| Consensus count zero | Explicit empty consensus only; statistics null |
| Actual published after period end | Available only at actual publication |
| Actual later corrected | New revision/availability; prior cutoff unchanged |
| Macro source exposes latest only | Persistently unsafe historical panel |
| Macro release time is corrected | Revise release evidence and affected points atomically |
| Benchmark constituents available after effective date | Hidden until publication cutoff |
| Constituent weights do not sum to one | Methodology finding; never silently renormalize |
| Official series differs from local constituent return | Preserve both with comparison warning |
| Overnight rate missing on weekend | No fill unless explicit calendar/carry policy later |
| Exact tenor missing | Structured missing; no interpolation by default |
| Negative source yield | Valid only when quote convention permits |
| Discount factor nonpositive | Quarantine |
| Curve release omits required tenor | Atomic warning/quarantine, never claim complete |
| Rate convention changes | New curve identity/version; no in-place conversion |

## 22. Security, licensing, and resources

- Filing locations reject credentials/signed secrets; document bytes stay external and
  licensing policy controls redistribution.
- Taxonomy names, dimensions, contributor IDs, methodology fields, constituent lists, and
  curve manifests have bounded counts/bytes and canonical codecs.
- Query projections and chunks enforce row/memory ceilings before pandas allocation.
- No adapter accepts SQL, pickle, arbitrary imports, raw connections, table names, or
  managed-write callbacks.
- Licensed contributor/constituent/fact data carries nonremovable classification into
  frames, features, reports, samples, and exports.
- Normalization/mapping/rate-conversion code is registered and bounded; opaque external
  computation is unsafe and cannot write canonical source tables.
- Evidence defaults to IDs, hashes, counts, ranges, and summary statistics rather than
  complete licensed statements or panels.

## 23. Migration and compatibility effect

This is a greenfield v3 model. V2 dataframes/Parquet fundamentals, estimates, macro files,
benchmark helpers, or scalar risk-free configuration are not imported. Adapters reacquire
or independently translate source data through normal validation. There is no latest-
fundamental, current-consensus, final-vintage, current-constituent, or scalar-rate
compatibility shortcut.

Within v3, changing natural keys, period/date meanings, taxonomy/dimension/unit codecs,
concept/mapping semantics, estimate targets/measures, vintage completeness, benchmark
methodology/kind, rate quote/tenor/compounding/day-count meaning, dataframe schema, or
content canonicalization requires new identity/version and appropriate market migration.
Old source revisions, normalizations, snapshots, and definitions remain immutable.

## 24. Acceptance tests

### 24.1 Filings, facts, and normalization

- Build original/amendment/withdrawal report histories across every cutoff and verify exact
  filing/report/accession identity, acceptance, documents, and no silent coalescing.
- Correct a filing's issuer/report resolution without changing its accession identity, and
  select later comparative restatements in `latest_known_fact` without calling the mixed-
  filing result one statement.
- Generate instant/duration facts with fiscal labels, units, currencies, scales, nils,
  dimensions, duplicates, conflicts, corrections, retractions, overflow, and precision.
- Golden-test every initial normalized concept and mapping across taxonomy versions,
  signs/scales/dimensions; preserve conflicts/not-applicable rows.
- Backfill mapping versions with failure injection and prove raw immutability, catalog/
  snapshot stability, project-cutoff creation gating, run manifests/counts, exact retry reuse,
  and deterministic output content.

### 24.2 Estimates and actuals

- Generate issuer/security/instrument measures, fiscal and fixed horizons, FY1 resolution,
  split-sensitive per-share values, contributor-version redaction, revisions, and missing
  timing.
- Hand-check consensus zero/nonzero counts, statistics/order/dispersion, methods,
  constituent manifests, and source-vs-derived separation.
- Link independent and filing-backed actuals; sentinel-test actual publication/corrections
  and prove no surprise/actual value leaks before availability.

### 24.3 Macro vintages

- Hand-build advance/preliminary/revised/final/benchmark releases over many periods and
  compare exact/first/latest-known/all modes at every release/project cutoff.
- Property-test release ordering, atomic manifests, missing values, frequency/period/unit/
  geography/seasonal metadata, daily equal-date periods, release-metadata and point
  corrections, exact release-revision pins, and snapshot stability.
- Prove latest-only/unknown vintage completeness remains unsafe through query,
  materialization, and export.

### 24.4 Benchmarks and rates

- Resolve instrument/source-series/constituent benchmarks under versions/snapshots and
  validate exact calendars, source methodology, licensing, and kind-specific behavior.
- Generate constituent adds/removes/backdated corrections/weights/shares, current-only
  history, source interval conventions/calendar resolution, publication delays, source
  precedence, and official-series disagreement.
- Golden-test every rate quote/compounding/day-count/tenor convention, release/effective/
  maturity policy, negative yields, positive discount factors, and exact lookup.
- Generate complete/incomplete/revised curve releases and prove atomic group disposition,
  missing-tenor result, no implicit carry/interpolation/extrapolation, and cutoff safety.

### 24.5 APIs, dataframes, failure, and exit

- Contract-test exact columns/dtypes/order/empty frames/coverage states, decimal-to-float
  conversion, bounded projections/chunks, and licensing redaction.
- Inject failure around every master, definition, observation, normalization, group,
  catalog change, event, and commit boundary; prove no partial visibility and idempotent
  retry.
- Run deterministic external-style fixtures through ingest, quarantine/remediation,
  snapshot, cutoff query, normalization, and audit using public APIs.
- Round-trip all events through plan-02 storage; strict-build docs and execute snippets.

This plan is implementation-complete when:

- filings/amendments and raw/normalized facts remain fully auditable and point in time;
- individual/consensus/actual estimates have exact target/publication/revision semantics;
- complete macro vintages select correctly and latest-only history cannot appear safe;
- benchmark kinds/constituents/series are versioned, available, and noninterchangeable;
- risk-free points preserve exact quote/tenor/compounding/day-count and never interpolate
  implicitly;
- all datasets use plan-03 validation/revision/quarantine/snapshot and plan-04 identities;
- boundedness, licensing, failure atomicity, and no-lookahead sentinels pass; and
- lint, static types, tests, docs checks, strict docs build, and coverage gate pass.

## 25. Review checklist for dependent plans

Every later plan must state:

- which issuer/security/instrument/series/benchmark/curve grain and exact revisions it uses;
- which filing mode, mapping policy/version, taxonomy/dimensions, fiscal period, and unit
  semantics apply;
- which estimate measure/target/method/contributor/actual revisions and split basis apply;
- which macro release/vintage/completeness and observation period apply;
- which benchmark kind/version/calendar/series/constituents/methodology and return policy
  apply;
- which rate curve/version/tenor/maturity/quote/compounding/day-count/conversion policy
  applies;
- how missing, nil, conflict, unavailable, unsafe, latest-only, current-only, and licensed
  states propagate without coalescing/fill;
- which snapshot, cutoffs, source precedence, entity resolutions, definitions, code, and
  bounded query enter identity; and
- how changes affect migrations, reuse, comparisons, and simulation eligibility.

## 26. Umbrella and completed-plan consistency

This plan reuses plan-01 IDs/time/decimals/content/events; plan-02 market ownership,
leases, transactions, SQL boundaries, and migrations; plan-03 datasets, revisions/
retractions, availability, validation, dispositions, remediation, catalog state, and
snapshots; plan-04 issuer/security/instrument identities, calendars, memberships, and
resolution lineage; and plan-05 raw price/action/split-basis contracts.

It implements the umbrella's filing/fact/amendment, estimate/consensus/actual, macro
vintage, benchmark, and risk-free requirements while preserving USD US-listed scope.
Explicit report lineages, immutable normalization rows, resolved estimate targets, macro
release masters, three benchmark kinds, and convention-preserving rate points are local
refinements. No synthetic statement, early actual, final-vintage leak, current-constituent
shortcut, proprietary methodology claim, scalar rate shortcut, silent interpolation, or
hidden row loss is introduced.
