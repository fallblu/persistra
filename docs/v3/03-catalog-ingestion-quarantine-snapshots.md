# Focused specification 03: catalog, ingestion, quarantine, and snapshots

**Status:** Implementation-ready draft  
**Umbrella:** [`../v3-spec.md`](../v3-spec.md)  
**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md),
[focused specification 02](02-project-databases-leases-copies-migrations.md)  
**Owners:** `persistra.catalog`, `persistra.ingestion`  
**Required before:** focused specifications 04–18  
**Last reviewed:** 2026-07-15

## 1. Purpose

This specification defines the managed boundary between external provider adapters and
Persistra's append-only market database. It fixes source and dataset registration, staged
batch ingestion, deterministic validation, stable per-record dispositions, atomic full or
partial commits, immutable quarantine, child-batch remediation, append-only source
revisions, catalog sequencing, logical market snapshots, and project composite snapshots.

Domain-specific record columns and rules are supplied by focused specifications 04–06.
The contracts here ensure those datasets share one lifecycle, audit, temporal, safety,
and snapshot model rather than implementing incompatible ingestion paths.

## 2. Scope and boundaries

### 2.1 In scope

- Source, adapter, dataset, schema, validation-policy, and availability-policy registration
- Canonical staging record and streaming batch-writer contracts
- Batch and record state machines, idempotent submission, and recovery
- Structural, referential, temporal, domain, cross-record, and statistical validation
- Immutable findings with stable codes, evidence, severity, and action
- Per-record acceptance, revision, duplicate, quarantine, and rejection dispositions
- Atomic `committed` and `committed_with_quarantine` publication
- Whole-batch rejection and quarantine
- Append-only revision metadata, duplicate resolution, and linear supersession
- Quarantine storage, inspection, immutable remediation links, and child batches
- Gap-free catalog sequencing and rolling content identities
- Immutable market snapshots and research-database composite snapshots
- Public Python services, operational CLI, events, errors, and acceptance tests

### 2.2 Out of scope

- Provider networking, credentials, rate limits, downloads, and vendor payload archives
- Instrument, calendar, universe, market observation, and fundamental field schemas
- Dataset-specific availability algorithms beyond their registration contract
- Point-in-time joins across datasets and simulation safety enforcement
- Feature/label registration and research materialization
- Deletion or compaction of committed canonical revisions
- Distributed ingestion, multiple writers, or cross-database atomic commits
- Arbitrary binary or unstructured payload storage in DuckDB

Adapters may record licensing-permitted raw archive metadata, but Persistra does not become
a generic raw-data archive and never requires opaque vendor bytes in its canonical tables.

## 3. Normative decisions

1. Every managed source observation enters through a typed staged batch.
2. The normal public API has no structural-validation bypass.
3. Every staged record receives exactly one immutable terminal disposition.
4. Accepted canonical records and all terminal dispositions become visible atomically.
5. A partial commit publishes every accepted record and no quarantined record.
6. Findings, rejected batches, quarantined records, and committed revisions are retained.
7. Remediation creates a linked child batch; it never edits its parent.
8. Source corrections are new revisions with revision-specific availability.
9. One market-database writer assigns a gap-free transactional catalog sequence to every
   published catalog change or terminal batch.
10. A logical snapshot pins a catalog high-water sequence and content manifest; it never
    copies every canonical row.
11. `latest` means the newest persisted snapshot, not an unpinned catalog clock.
12. A composite snapshot records one exact market snapshot per configured database.
13. Adapters depend on Persistra's record and batch contract; Persistra has no provider-
    specific network dependency.

## 4. Package and identity surface

```text
src/persistra/
├── catalog/
│   ├── datasets.py
│   ├── sources.py
│   ├── batches.py
│   ├── quality.py
│   └── snapshots.py
└── ingestion/
    ├── records.py
    ├── staging.py
    ├── validation.py
    ├── quarantine.py
    └── writer.py
```

This plan adds these plan-01 typed IDs:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `SourceId` | `source` | Stable provider/source lineage |
| `DatasetId` | `dataset` | Stable dataset semantics and natural-key domain |
| `BatchId` | `batch` | One immutable submission attempt |
| `SubmittedRecordId` | `submitted_record` | One record occurrence inside one batch |
| `ValidationAttemptId` | `validation_attempt` | One immutable validation execution |
| `CanonicalRevisionId` | `revision` | One committed source-observation revision |
| `FindingId` | `finding` | One immutable validation finding |
| `DispositionGroupId` | `disposition_group` | Records requiring one atomic disposition |
| `QuarantineId` | `quarantine` | One immutable quarantined record |
| `RemediationId` | `remediation` | One parent-record/child-record relationship |
| `MarketSnapshotId` | `market_snapshot` | One logical snapshot of one market database |
| `CompositeSnapshotId` | `composite_snapshot` | One project mapping of market snapshots |

Source and dataset *versions* are positive integers scoped to their entity ID. Stable
qualified names identify public definitions, but UUIDs remain the relational identities.
Snapshot IDs are opaque; their manifest `ContentId` proves content identity.

## 5. Public API

The market-write project exposes `project.services.catalog` and
`project.services.ingestion`. Research-write projects expose composite-snapshot creation;
read-only projects expose inspection and query methods only.

```python no-run
batch = project.services.ingestion.begin(
    BatchHeader(
        source=SourceRef("vendor.us_equities", version=3),
        dataset=DatasetRef("persistra.market.daily_bar", version=1),
        submission_key="vendor-export-2026-07-15T120000Z",
        expected_batch_content_id=None,
        adapter=ComponentRef("vendor.adapter.daily_bar", version="2.4.1"),
        raw_manifest=raw_manifest,
    )
)

with batch.writer() as writer:
    writer.write(records)

validation = project.services.ingestion.validate(batch.batch_id)
result = project.services.ingestion.commit(
    batch.batch_id,
    validation_token=validation.token,
    create_snapshot=False,
)
```

The convenience `ingestion.submit(header, records)` composes `begin`, streaming stage,
validate, and commit with identical transactions, state transitions, errors, and return
types. It is not a second semantic path.

Core immutable results are:

- `BatchHandle(batch_id, status, writer_factory)`
- `ValidationResult(batch_id, validation_attempt_id, token, proposed_status,`
  `finding_summary, record_summary)`
- `BatchResult(batch_id, status, catalog_sequence, counts, finding_summary, snapshot_hint)`
- `SnapshotRef(database_id, snapshot_id, catalog_sequence, manifest_content_id)`
- `CompositeSnapshotRef(composite_snapshot_id, manifest_content_id, members)`

`BatchResult.records()` and catalog inspection methods materialize versioned pandas
dataframes with explicit columns. Large payload values are excluded by default and require
an explicit bounded selection.

## 6. Source and dataset registration

### 6.1 Source definitions

A source version declares:

- stable source ID and qualified source name;
- provider display name and licensing classification;
- adapter contract name, supported adapter-version range, and conformance identity;
- source-record key grammar and source revision-token semantics;
- timestamp precision and timezone guarantees;
- raw-archive policy and redistributability classification;
- enabled/disabled state; and
- definition schema version and content ID.

Source metadata changes append a new positive version. Disabling a source prevents new
batches but does not hide old revisions. Renaming creates a new qualified name alias only
when the same source lineage and semantics remain; provider changes allocate a new
`SourceId`.

### 6.2 Dataset definitions

A dataset version declares:

- stable dataset ID, reserved qualified name, and record-model qualified name/version;
- owning canonical table and public view names;
- entity and time grain;
- ordered natural-key field schema and canonical key encoder;
- required and optional columns, domain types, nullability, and units;
- revision policy and source-revision ordering contract;
- availability-policy name, version, configuration, and safety classification;
- validation-policy name/version and complete ordered rule set;
- maximum canonical record bytes and bounded staging chunk size;
- supported source versions and entity-resolution requirements; and
- definition schema version and content ID.

Natural-key fields, entity grain, or temporal meaning cannot change within one `DatasetId`.
Such a break creates a new dataset identity and name. Additive nullable fields or stricter
validation may use a new dataset version plus a database migration. Old versions remain
queryable under their snapshot and schema compatibility contracts.

Built-in canonical datasets use names under `persistra.` and are installed by market
database migrations. Custom datasets register through the same tables and must use a
nonreserved owner prefix. Registration never grants temporal safety by itself.

### 6.3 Registration transaction

Registration requires `ProjectMode.MARKET_WRITE`. The service validates the complete
definition, explicit codec/rule identities, owning schema, and name uniqueness; assigns
one catalog sequence; appends the entity/version rows and catalog change; updates rolling
state; and emits its event in one transaction. Definitions are never updated in place.

## 7. Core market-database schema

The following logical DDL is normative. Role-specific migrations may add physical indexes
and generated projections without changing column meaning.

### 7.1 Catalog clock and changes

```sql
CREATE TABLE catalog.catalog_clock (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    current_sequence BIGINT NOT NULL CHECK (current_sequence >= 0),
    chain_content_id VARCHAR NOT NULL
);

CREATE TABLE catalog.changes (
    catalog_sequence BIGINT PRIMARY KEY CHECK (catalog_sequence >= 1),
    change_kind VARCHAR NOT NULL,
    change_entity_id UUID NOT NULL,
    change_content_id VARCHAR NOT NULL,
    prior_chain_content_id VARCHAR NOT NULL,
    chain_content_id VARCHAR NOT NULL UNIQUE,
    committed_at TIMESTAMPTZ NOT NULL
);
```

The bootstrap clock is sequence 0 with the content ID of canonical schema
`persistra.catalog.genesis@1`. A writer increments `current_sequence` with a transactional
singleton-row update; rollback restores the old value, so committed sequences are gap-free.

The new chain is SHA-256 over the plan-01 canonical object containing schema name/version,
prior chain ID, sequence, change kind, entity ID, and change content ID. It is an audit
chain, not a signature or proof against a malicious database administrator.

### 7.2 Source and dataset registry

```sql
CREATE TABLE catalog.sources (
    source_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE catalog.source_versions (
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    definition_schema_version INTEGER NOT NULL,
    definition_content_id VARCHAR NOT NULL,
    definition_json JSON NOT NULL,
    enabled BOOLEAN NOT NULL,
    catalog_sequence BIGINT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_id, source_version)
);

CREATE TABLE catalog.datasets (
    dataset_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE catalog.dataset_versions (
    dataset_id UUID NOT NULL,
    dataset_version INTEGER NOT NULL CHECK (dataset_version >= 1),
    definition_schema_version INTEGER NOT NULL,
    definition_content_id VARCHAR NOT NULL,
    definition_json JSON NOT NULL,
    catalog_sequence BIGINT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (dataset_id, dataset_version)
);
```

JSON columns contain canonical, size-bounded registered definitions and are always paired
with their schema version and content ID. Public APIs decode them to typed models; callers
do not interpret arbitrary JSON.

### 7.3 Batches and transition history

```sql
CREATE TABLE catalog.batches (
    batch_id UUID PRIMARY KEY,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL,
    dataset_id UUID NOT NULL,
    dataset_version INTEGER NOT NULL,
    submission_key VARCHAR NOT NULL,
    adapter_name VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    adapter_content_id VARCHAR NOT NULL,
    raw_manifest_content_id VARCHAR,
    parent_batch_id UUID,
    current_status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    staged_at TIMESTAMPTZ,
    validated_at TIMESTAMPTZ,
    terminal_at TIMESTAMPTZ,
    batch_content_id VARCHAR,
    validation_content_id VARCHAR,
    current_validation_attempt_id UUID,
    catalog_sequence BIGINT UNIQUE,
    submitted_count BIGINT NOT NULL DEFAULT 0,
    accepted_count BIGINT NOT NULL DEFAULT 0,
    new_count BIGINT NOT NULL DEFAULT 0,
    revision_count BIGINT NOT NULL DEFAULT 0,
    duplicate_count BIGINT NOT NULL DEFAULT 0,
    quarantined_count BIGINT NOT NULL DEFAULT 0,
    rejected_count BIGINT NOT NULL DEFAULT 0,
    UNIQUE (source_id, dataset_id, submission_key)
);

CREATE TABLE catalog.batch_transitions (
    batch_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    from_status VARCHAR,
    to_status VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    event_id UUID NOT NULL UNIQUE,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (batch_id, transition_sequence)
);

CREATE TABLE catalog.validation_attempts (
    validation_attempt_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    input_catalog_sequence BIGINT NOT NULL,
    validation_policy_content_id VARCHAR NOT NULL,
    validation_token_content_id VARCHAR,
    current_status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (batch_id, attempt_number)
);

CREATE TABLE catalog.validation_attempt_transitions (
    validation_attempt_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 1),
    from_status VARCHAR,
    to_status VARCHAR NOT NULL,
    event_id UUID NOT NULL UNIQUE,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (validation_attempt_id, transition_sequence)
);
```

`current_status`, `current_validation_attempt_id`, and count fields are transactionally
maintained projections of immutable transition, attempt, finding, and disposition rows.
They are verified on open/diagnostic rebuild and never treated as independent authority.

### 7.4 Submitted records and dispositions

```sql
CREATE TABLE catalog.batch_records (
    submitted_record_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL,
    record_number BIGINT NOT NULL CHECK (record_number >= 1),
    source_record_key VARCHAR,
    source_revision_key VARCHAR,
    natural_key_content_id VARCHAR NOT NULL,
    natural_key_json JSON NOT NULL,
    payload_content_id VARCHAR NOT NULL,
    source_content_id VARCHAR NOT NULL,
    observation_content_id VARCHAR NOT NULL,
    canonical_payload_json JSON NOT NULL,
    event_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL,
    availability_quality VARCHAR NOT NULL,
    UNIQUE (batch_id, record_number)
);

CREATE TABLE catalog.record_dispositions (
    submitted_record_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL,
    disposition VARCHAR NOT NULL,
    primary_reason_code VARCHAR NOT NULL,
    disposition_group_id UUID,
    canonical_revision_id UUID,
    recorded_at TIMESTAMPTZ NOT NULL
);
```

Dataset-specific typed staging tables may replace `canonical_payload_json` for large or
high-volume records, but the canonical payload content ID and a registered decoder remain
available. The generic row never becomes the public market-data query surface.

### 7.5 Canonical revision metadata

```sql
CREATE TABLE catalog.canonical_revisions (
    canonical_revision_id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL,
    dataset_version INTEGER NOT NULL,
    source_id UUID NOT NULL,
    natural_key_content_id VARCHAR NOT NULL,
    revision_ordinal BIGINT NOT NULL CHECK (revision_ordinal >= 1),
    supersedes_revision_id UUID,
    source_record_key VARCHAR,
    source_revision_key VARCHAR,
    payload_content_id VARCHAR NOT NULL,
    source_content_id VARCHAR NOT NULL UNIQUE,
    observation_content_id VARCHAR NOT NULL UNIQUE,
    batch_id UUID NOT NULL,
    submitted_record_id UUID NOT NULL UNIQUE,
    event_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL,
    availability_quality VARCHAR NOT NULL,
    catalog_sequence BIGINT NOT NULL,
    UNIQUE (dataset_id, source_id, natural_key_content_id, revision_ordinal)
);
```

Every dataset-specific canonical row has `canonical_revision_id` as its primary key and
one-to-one logical reference to this table. Canonical metadata and typed payload insert in
the same transaction. The generic table does not flatten domain-specific dates or fields.

### 7.6 Findings and quarantine

```sql
CREATE TABLE quality.findings (
    finding_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL,
    validation_attempt_id UUID NOT NULL,
    submitted_record_id UUID,
    disposition_group_id UUID,
    rule_name VARCHAR NOT NULL,
    rule_version INTEGER NOT NULL,
    severity VARCHAR NOT NULL,
    action VARCHAR NOT NULL,
    reason_code VARCHAR NOT NULL,
    field_path VARCHAR,
    evidence_content_id VARCHAR NOT NULL,
    evidence_json JSON NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE quality.quarantined_records (
    quarantine_id UUID PRIMARY KEY,
    submitted_record_id UUID NOT NULL UNIQUE,
    batch_id UUID NOT NULL,
    disposition_group_id UUID,
    payload_content_id VARCHAR NOT NULL,
    canonical_payload_json JSON NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE quality.remediation_links (
    remediation_id UUID PRIMARY KEY,
    parent_batch_id UUID NOT NULL,
    parent_submitted_record_id UUID NOT NULL,
    child_batch_id UUID NOT NULL,
    child_submitted_record_id UUID NOT NULL,
    relationship VARCHAR NOT NULL
        CHECK (relationship IN ('corrects', 'replaces', 'supplements')),
    recorded_at TIMESTAMPTZ NOT NULL,
    UNIQUE (parent_submitted_record_id, child_submitted_record_id)
);
```

Evidence JSON is canonical and limited to 16 KiB. Larger evidence is an external artifact
with a content ID and licensing-safe location in the raw manifest.

## 8. Canonical staging record contract

Every dataset record model implements:

```python no-run
class CanonicalStagingRecord(Protocol):
    @property
    def source_record_key(self) -> str | None: ...

    @property
    def source_revision_key(self) -> str | None: ...

    def natural_key(self) -> RegisteredNaturalKey: ...
    def temporal_fields(self) -> TemporalFields: ...
    def to_canonical_payload(self) -> CanonicalPayload: ...
```

Record dataclasses are frozen and registered to one exact dataset-model version. The
writer rejects mappings, arbitrary objects, a model registered to another dataset
version, unknown fields, and values without plan-01 canonical serialization.

The writer assigns `SubmittedRecordId`, gap-free one-based `record_number`, and one captured
`ingested_at` per streaming chunk. `ingested_at` is the instant Persistra durably writes the
staged record, not the provider's download time or later batch commit. The batch
`received_at` is captured once at `begin()`.

Natural-key and payload encoders include dataset ID, dataset version, registered schema,
and field names. Three content identities remain distinct:

- `payload_content_id` covers the typed domain payload only;
- `source_content_id` covers source/dataset identity, natural key, source record/revision
  keys, payload, source-reported temporal evidence, and explicit missing-evidence markers,
  but excludes batch/record IDs, Persistra receipt time, and any availability bound derived
  only from receipt; and
- `observation_content_id` covers `source_content_id` plus resolved `available_at`,
  `availability_quality`, and the first accepted `ingested_at`.

The ordered batch content ID covers header source/dataset/adapter identities, licensing-
permitted raw *source-content* roots, and ordered `source_content_id` values. It excludes
raw archive locations, archive time, and other machine-local manifest metadata. A retry
therefore compares equal despite a new local receipt/archive path, while a timing
correction backed by changed source evidence remains a real revision. Hash equality is
always confirmed against canonical bytes before deduplication, protecting against a digest
collision.

Record staging is bounded: default chunk size is 50,000 records, each dataset declares a
maximum canonical record size no greater than the global 16 MiB ceiling, and database
writes do not require a batch-wide pandas dataframe. An adapter may stream any finite
number of records up to signed 64-bit count limits and resource policy.

## 9. Batch state machine

### 9.1 States

```text
created → staging → staged → validating → validated
   │          │          │         │           ├─→ committed
   │          │          │         │           ├─→ committed_with_quarantine
   │          │          │         │           ├─→ quarantined
   │          │          │         └───────────→ rejected
   └──────────┴──────────┴─────────────────────→ aborted
```

Terminal states are `committed`, `committed_with_quarantine`, `quarantined`, `rejected`,
and `aborted`. Every transition is append-only, gap-free per batch, and reflected in
`current_status` in the same transaction. Invalid transitions raise and write no history.

`created` has no records. `staging` accepts chunks. `staged` is sealed and has an exact
batch content ID. `validating` is internal and recovers to `staged` after process death.
`validated` has immutable findings plus a validation token but no terminal dispositions.
Findings for nonterminal batches are visible only through validation-work APIs. Snapshot-
bounded quality views join through a terminal batch and its catalog sequence, so later
terminal publication cannot change an earlier snapshot.

Each pass allocates a `ValidationAttemptId` and gap-free attempt number. Attempt states are
`running`, `completed`, `stale`, `failed`, and `abandoned`, with immutable transition
history; `completed` may transition only to `stale`. Findings belong to one attempt.
`current_validation_attempt_id` points to the completed attempt authorized for commit and
is cleared when that attempt becomes stale. Prior attempts and findings remain inspectable.

### 9.2 Staging completion and abort

Closing the writer normally flushes, verifies gap-free record numbers, calculates the
ordered batch content ID, and transitions to `staged`. A Python exception rolls back the
current chunk and transitions the batch to `aborted` only when the writer still owns the
batch. Process death may leave `staging`; `data doctor` reports it, and an explicit
`resume_staging()` or `abort_batch()` operation verifies the expected batch content prefix
before proceeding.

Aborting is terminal. Every already staged record receives disposition `rejected` with
reason `ingestion.batch.aborted` in the abort transaction. Empty batches cannot validate
and are rejected with `ingestion.batch.empty`.

### 9.3 Idempotent submissions

`submission_key` is 1–255 printable NFC characters, source-defined, nonsecret, and unique
per `(source_id, dataset_id)`. `begin()` against an existing key requires
`expected_batch_content_id`; an exact match returns the existing handle/result and a
mismatch raises `SubmissionConflictError`. Without an expected ID it fails before opening
a writer rather than assuming equality.

The one-shot `submit()` may compare a retry whose expected ID is unavailable: it streams
candidate canonical bytes into an operation-scoped temporary table, computes the sealed
content ID, returns the existing result on equality, and drops the temporary table. A
mismatch raises and retains neither a second batch nor candidate records. Crash recovery
recognizes comparison tables by operation ID and never treats them as submissions. A new
execution retry may instead use a new submission key and `BatchId`, linking the prior
attempt only as operational context.

## 10. Validation contract

### 10.1 Ordered phases

Validation executes registered rules in this order:

1. model/schema and canonical-encoding integrity;
2. batch structure and natural-key uniqueness;
3. entity and external-identifier resolution;
4. timestamp, availability, interval, timezone, and session alignment;
5. dataset domain rules such as OHLC, quantity, and corporate-action consistency;
6. cross-record and source-revision consistency;
7. expected coverage and missing-session analysis; and
8. statistical anomaly rules.

Within a phase, order is `(priority integer, qualified rule name, rule version)`. Rules are
pure over their declared bounded inputs, receive an injected clock only when their policy
explicitly needs operation time, and cannot write or obtain a raw connection.

Rule output is staged under the attempt ID. One completion transaction publishes the
attempt's complete finding set, token, current batch-attempt projection, transitions, and
events; a failed rule cannot expose a partial finding set. A mandatory batch rejection
also assigns every record disposition, catalog sequence, terminal transition, and catalog
change in that completion transaction. In that case `validate()` returns terminal
`BatchResult`; otherwise it returns `ValidationResult` for explicit commit.

### 10.2 Rule results

`FindingSeverity` has stable values `info`, `warning`, `error`, and `fatal`.
`FindingAction` has stable values `observe`, `warn`, `quarantine_record`,
`quarantine_group`, `quarantine_batch`, and `reject_batch`.

Each rule declares its possible codes, default severity/action, affected-key semantics,
evidence schema, and version. A versioned `ValidationPolicy` may make an action stricter but
cannot downgrade a structural `reject_batch` rule or bypass required rules. Policy identity
enters the validation token, batch audit, catalog change, snapshot chain, and provenance.

Structural failures include undecodable models, missing required fields, invalid canonical
serialization, natural-key hash mismatch, duplicate record numbering, wrong dataset model,
and validation-engine invariant failures. They reject the entire batch. Ordinary record
conflicts may quarantine the affected record/group. Statistical anomalies warn and remain
accepted by default.

### 10.3 Validation token and commit recheck

The token content-addresses validation attempt ID, batch content, source/dataset
definitions, rule/codec code, validation policy, relevant catalog high-water sequence,
findings, and proposed record actions. `commit()` accepts only that exact token and the
batch's current completed attempt.

Because another market write could occur between validation and commit in a resumed
workflow, the commit transaction rechecks identifier resolution, existing observation
content, revision heads, and group conflicts against the current catalog. If relevant
state changed, it returns the batch to `staged`, supersedes no finding, and requires a new
validation pass. The prior attempt transitions to `stale`; no finding is edited or
superseded. It never silently applies a stale proposal.

## 11. Per-record dispositions and batch outcome

`RecordDisposition` has exactly these terminal values:

| Value | Meaning | Canonical row created |
| --- | --- | --- |
| `accepted_new` | First committed revision for the source natural key | Yes |
| `accepted_revision` | New linear revision superseding the current head | Yes |
| `duplicate_ignored` | Exact observation already committed | No |
| `quarantined` | Preserved for inspection but ineligible for canonical queries | No |
| `rejected` | Batch-level rejection/abort prevents acceptance | No |

Every staged record receives one row in `record_dispositions` in the terminal transaction.
The disposition, primary reason, group, and canonical revision link never change.
Additional findings retain all secondary reasons.

Terminal batch status is deterministic:

- any mandatory reject action: `rejected`, and every record is `rejected`;
- no accepted/duplicate records and at least one quarantined record: `quarantined`;
- at least one new/revision/duplicate record and at least one quarantined record:
  `committed_with_quarantine`;
- otherwise, including an all-exact-duplicate batch: `committed`.

For `committed` and `committed_with_quarantine`, the transaction allocates one catalog
sequence, inserts all accepted canonical metadata and typed rows, inserts every
disposition, updates batch counts/status, appends the catalog change and rolling states,
and emits events before commit. A fully quarantined, rejected, or aborted terminal batch
also gets a catalog sequence so snapshot quality/audit state is reproducible, but creates
no canonical revision.

Counts satisfy `accepted_count = new_count + revision_count` and
`submitted_count = accepted_count + duplicate_count + quarantined_count + rejected_count`.
`new_count` is `accepted_new`, `revision_count` is `accepted_revision`, and the remaining
three map directly. The total accepted count matches the umbrella contract while detailed
counts remain available; no disposition is counted twice in the partition.

## 12. Duplicate and revision algorithm

### 12.1 Exact duplicates

Within one batch, records with identical canonical natural-key and source-content bytes are
ordered by `record_number`; the first proceeds and later records become
`duplicate_ignored` with reason `ingestion.record.duplicate_in_batch`. The duplicate rows
remain auditable.

Against committed data, exact `source_content_id` plus byte confirmation produces
`duplicate_ignored` and links the existing revision in the disposition. A duplicate does
not receive a new revision ordinal or canonical row, but its new batch and receipt remain
visible while the canonical revision retains its original accepted `ingested_at`.

### 12.2 Revisions

For `(dataset_id, source_id, natural_key_content_id)`, committed revisions form one linear
chain with positive ordinals. A different observation may become `accepted_revision` only
when the registered revision policy recognizes it as a valid successor. It receives
`head.ordinal + 1` and `supersedes_revision_id=head.id` in the commit transaction.

Reusing a nonnull source revision key with different bytes is a source conflict and
quarantines the disposition group. Concurrent branches cannot occur under the single
writer; a stale validated head requires revalidation. If a source supplies records out of
publication order, the policy may accept the later-ingested record as the next revision
only when source evidence establishes succession. Otherwise it quarantines the conflict.

A correction never inherits temporal metadata. Missing correction publication time uses
the dataset availability policy: at minimum `available_at >= ingested_at` and
`availability_quality='ingestion_bounded'`, or `unknown` when no bound is defensible.

### 12.3 Revision selection primitive

Given one snapshot and temporal cutoffs, the generic primitive first restricts revisions
to `catalog_sequence <= snapshot.catalog_sequence`, then to eligible public/project
knowledge, then selects the highest eligible `revision_ordinal` per
`(dataset_id, source_id, natural_key_content_id)`. A dataset-specific source precedence
policy resolves multiple sources; no generic last-write-wins rule combines providers.

The research dataset plan owns dual-cutoff joins and safety enforcement. This primitive
only guarantees revision and snapshot stability.

## 13. Quarantine

### 13.1 Record and group quarantine

Rules affecting one record set `quarantine_record`. Rules such as duplicate natural keys,
unresolved entity groups, split-action consistency, or mutually dependent rows may assign
one `DispositionGroupId`; every member receives one atomic group outcome. A group cannot
partially enter canonical data.

`quarantine_batch` preserves every record with disposition `quarantined` and publishes no
canonical row. It differs from `rejected`: quarantined content is structurally decodable
and intentionally retained for remediation, while rejected content violates a batch-level
contract or invariant.

### 13.2 Stored state and inspection

Quarantine preserves canonical normalized payload, natural key, all source and temporal
metadata, source/batch/record identities, findings, payload/content hashes, and raw archive
manifest reference when present. It never stores secrets or licensing-prohibited raw
fields merely for convenience.

`quarantine.list()`, `get()`, `findings()`, and `history()` return typed records or explicit
pandas dataframes. Payload access requires dataset-aware decoding and a row/byte limit.
Malformed raw input rejected before canonical decoding is represented by bounded evidence
and raw archive reference, not inserted into `canonical_payload_json`.

Committed quarantine is immutable and retained in 3.0. Mutable notes, acknowledgements,
and operator labels, if added, live in a separate annotation table and do not alter the
finding or disposition.

## 14. Remediation

Remediation submits corrected canonical staging records as a child batch with
`parent_batch_id`. Each child record declares one or more quarantined parent record IDs and
relationship `corrects`, `replaces`, or `supplements`. Parent and child must share the
dataset identity; a cross-dataset correction is a new normal batch plus explicit lineage
owned by that dataset.

The child passes current source, schema, availability, validation, duplicate, and revision
rules exactly like any batch. It cannot reuse the parent's availability, source revision,
or safety classification without evidence. A successful child may create a new canonical
revision or prove an exact duplicate already exists.

Remediation status is a derived projection:

- `open`: no child terminal result resolves the parent;
- `attempted`: at least one child is rejected/quarantined/aborted;
- `resolved_new`: a linked child is `accepted_new`;
- `resolved_revision`: a linked child is `accepted_revision`;
- `resolved_duplicate`: a linked child proves an existing exact canonical revision; or
- `superseded`: an explicit later remediation relationship supersedes an abandoned attempt.

The original quarantine row and findings never change. Multiple attempts remain visible.
Once resolved, another child cannot claim the same issue without an explicit new finding
or `supplements` relationship. Remediation links and child dispositions are committed in
the child's terminal transaction.

## 15. Catalog sequence and rolling state

Every published source version, dataset version, terminal batch, and other future
snapshot-relevant catalog mutation owns one `catalog.changes` sequence. Internal staging,
validation attempts, snapshot creation, and read operations do not advance the clock.

For each dataset version, `catalog.dataset_state` maintains revision count, terminal batch
count, latest catalog sequence, and a rolling chain content ID. A terminal batch change
hashes the prior state plus the sorted tuples of accepted revision IDs/content IDs,
record dispositions, validation-attempt/finding content IDs, and batch summary.
`catalog.source_state` does
the same for source definitions and terminal batches. These tables are rebuildable
projections of append-only rows.

Rolling hashes make snapshot manifests compact and corruption-diagnosable; they do not
replace row-level checks, content IDs, or the database/copy verification in plan 02.

## 16. Logical market snapshots

### 16.1 Schema

```sql
CREATE TABLE snapshots.market_snapshots (
    market_snapshot_id UUID PRIMARY KEY,
    database_id UUID NOT NULL,
    catalog_sequence BIGINT NOT NULL,
    catalog_chain_content_id VARCHAR NOT NULL,
    manifest_schema_version INTEGER NOT NULL,
    manifest_content_id VARCHAR NOT NULL UNIQUE,
    manifest_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (database_id, catalog_sequence)
);

CREATE TABLE snapshots.snapshot_dataset_state (
    market_snapshot_id UUID NOT NULL,
    dataset_id UUID NOT NULL,
    dataset_version INTEGER NOT NULL,
    revision_count BIGINT NOT NULL,
    terminal_batch_count BIGINT NOT NULL,
    latest_catalog_sequence BIGINT NOT NULL,
    state_content_id VARCHAR NOT NULL,
    PRIMARY KEY (market_snapshot_id, dataset_id, dataset_version)
);

CREATE TABLE snapshots.snapshot_source_state (
    market_snapshot_id UUID NOT NULL,
    source_id UUID NOT NULL,
    source_version INTEGER NOT NULL,
    terminal_batch_count BIGINT NOT NULL,
    latest_catalog_sequence BIGINT NOT NULL,
    state_content_id VARCHAR NOT NULL,
    PRIMARY KEY (market_snapshot_id, source_id, source_version)
);
```

The manifest schema is `persistra.snapshot.market_manifest@1`. It includes database ID,
catalog high-water sequence and chain ID, sorted source/dataset definition identities,
sorted dataset/source rolling states and counts, availability/validation policy identities,
schema version, and creation software identity. It excludes machine-local file paths.

### 16.2 Creation and immutability

`snapshots.create()` requires `ProjectMode.MARKET_WRITE`. In one transaction it reads the
catalog clock, rebuild-verifies affected rolling states, creates canonical manifest bytes,
and appends snapshot/state rows. It does not advance the catalog clock because snapshot
metadata is a view of already-published state.

Creating again at the same `(database_id, catalog_sequence)` recomputes and verifies the
manifest, then returns the existing `MarketSnapshotId`. A mismatch is corruption. Snapshot
rows are never updated or deleted.

Sequence 0 may receive an explicit empty snapshot after bootstrap. Later ingestion does
not change any earlier query because canonical selection always includes the snapshot
high-water predicate.

### 16.3 `latest`

`snapshots.latest()` returns the persisted snapshot with greatest catalog sequence, then
`MarketSnapshotId` as deterministic tie-breaker. If the catalog clock is newer, the result
is still the newest *persisted* snapshot and carries warning `snapshot.catalog_unpinned`.
No simulation or study silently treats the unpinned clock as a snapshot.

Ingestion may request `create_snapshot=True`, which appends a snapshot immediately after
the terminal batch while retaining the exclusive market lease; snapshot creation is a
separate transaction and failure does not roll back the already committed batch. The
returned `BatchResult` reports snapshot failure explicitly. Default is false.

## 17. Composite project snapshots

The research database stores:

```sql
CREATE TABLE research.composite_snapshots (
    composite_snapshot_id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    manifest_schema_version INTEGER NOT NULL,
    manifest_content_id VARCHAR NOT NULL UNIQUE,
    manifest_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE research.composite_snapshot_members (
    composite_snapshot_id UUID NOT NULL,
    database_name VARCHAR NOT NULL,
    database_id UUID NOT NULL,
    market_snapshot_id UUID NOT NULL,
    market_manifest_content_id VARCHAR NOT NULL,
    verified_copy_id UUID,
    PRIMARY KEY (composite_snapshot_id, database_name),
    UNIQUE (composite_snapshot_id, database_id)
);
```

`composite_snapshots.create(mapping)` requires research-write mode and shared leases on
every member market database. Each value is an exact `MarketSnapshotId` or explicit
`LatestSnapshot`; latest references resolve once before the research transaction. The
service verifies database IDs, manifests, configured names, and physical-copy manifests,
sorts members by database name, and stores schema
`persistra.snapshot.composite_manifest@1` in one research transaction.

Resolving a latest snapshot whose market catalog is newer preserves
`snapshot.catalog_unpinned` in the composite manifest. The selected member remains
immutable but is explicitly stale relative to unpinned catalog state.

An identical member manifest returns the existing composite snapshot. No member can be
added or replaced later. A run, materialization, or study records the composite ID and
content ID, never a moving collection of per-database latest values.

This transaction cannot make market and research files jointly atomic. It relies only on
already immutable market snapshots held under shared leases, consistent with plan 02.

## 18. Provider adapter contract

An external adapter package may import only public source/dataset refs, registered staging
record models, `BatchHeader`, writer interfaces, and conformance fixtures. It is responsible
for network access, credentials, retries, raw payload licensing, and translation to exact
canonical models. It may not receive a connection, table name, or managed-write callback.

The adapter identity includes package/version, relevant code content IDs, source-version
contract, record-model version, dependency versions material to translation, and raw
manifest content ID. An unresolved material identity prevents exact reuse claims but does
not bypass validation.

The provider conformance suite tests:

- record model and canonical byte stability;
- source keys, revision tokens, and revision-specific availability;
- chunk-boundary independence and bounded streaming;
- retry/submission-key behavior;
- malformed response and partial-download failure behavior;
- entity resolution and source contractual rules;
- no direct managed SQL writes; and
- full/partial commit atomicity using adapter fixtures.

Passing conformance establishes contract compatibility, not provider data correctness.

## 19. Transactions, concurrency, and recovery

- Registration, terminal batch publication, remediation linkage, and snapshot creation each
  use one market-database transaction under an exclusive market lease.
- Staging chunks use bounded transactions under the same batch-owning market writer; one
  process remains the only writer.
- Validation may use read transactions but cannot overlap an external market writer because
  the project retains its exclusive lease.
- There is no cross-market batch and no cross-file atomic commit.
- A failed terminal transaction leaves the batch `validated`, publishes no disposition or
  canonical row, and may be retried with the same token only if catalog dependencies remain
  unchanged.
- Recovery scans nonterminal transitions, temporary staging tables, count projections,
  catalog-chain continuity, typed canonical/revision pairs, and orphan disposition links.
  It reports corruption instead of synthesizing missing rows.
- Failed snapshot creation leaves no snapshot rows and does not advance the catalog clock.
- A committed batch cannot be rolled back by deleting it; a source correction is a new
  revision and a software/schema defect requires a forward migration or database rebuild.

## 20. Events, logs, and warnings

Required domain event types are:

| Event type | Aggregate |
| --- | --- |
| `persistra.catalog.source_registered@1` | `persistra.aggregate.source` |
| `persistra.catalog.dataset_registered@1` | `persistra.aggregate.dataset` |
| `persistra.ingestion.batch_created@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_staging_started@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_staged@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_validation_started@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_validated@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_revalidation_required@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.validation_attempt_started@1` | `persistra.aggregate.validation_attempt` |
| `persistra.ingestion.validation_attempt_completed@1` | `persistra.aggregate.validation_attempt` |
| `persistra.ingestion.validation_attempt_stale@1` | `persistra.aggregate.validation_attempt` |
| `persistra.ingestion.validation_attempt_failed@1` | `persistra.aggregate.validation_attempt` |
| `persistra.ingestion.validation_attempt_abandoned@1` | `persistra.aggregate.validation_attempt` |
| `persistra.ingestion.batch_committed@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_quarantined@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_rejected@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.batch_aborted@1` | `persistra.aggregate.batch` |
| `persistra.ingestion.remediation_linked@1` | `persistra.aggregate.remediation` |
| `persistra.snapshot.market_created@1` | `persistra.aggregate.market_snapshot` |
| `persistra.snapshot.composite_created@1` | `persistra.aggregate.composite_snapshot` |

Every legal batch or validation-attempt transition maps to exactly one corresponding event
in this table; its aggregate sequence equals `transition_sequence`.
`batch_committed@1` payload includes status so it covers full and partial commit.
Per-record details stay normalized in disposition tables rather than creating millions of
large events. Every event is persisted transactionally with its state transition.

Structured operational logs cover chunk progress, validation timings, rule counts,
snapshot verification, and failures. Warning codes persist in findings, batch results,
snapshot manifests, or downstream artifacts rather than existing only in console output.

## 21. Errors and stable reason codes

| Exception | Reason code |
| --- | --- |
| `SourceNotFoundError` | `catalog.source.not_found` |
| `DatasetNotFoundError` | `catalog.dataset.not_found` |
| `DefinitionConflictError` | `catalog.definition.conflict` |
| `AdapterContractError` | `ingestion.adapter.contract` |
| `BatchStateError` | `ingestion.batch.invalid_state` |
| `SubmissionConflictError` | `ingestion.submission.conflict` |
| `RecordSchemaError` | `ingestion.record.schema` |
| `BatchValidationError` | `ingestion.validation.failed` |
| `StaleValidationError` | `ingestion.validation.stale` |
| `DispositionInvariantError` | `ingestion.disposition.invariant` |
| `RevisionConflictError` | `ingestion.revision.conflict` |
| `QuarantineNotFoundError` | `ingestion.quarantine.not_found` |
| `RemediationConflictError` | `ingestion.remediation.conflict` |
| `SnapshotNotFoundError` | `snapshot.not_found` |
| `SnapshotManifestError` | `snapshot.manifest.invalid` |
| `CompositeSnapshotError` | `snapshot.composite.invalid` |
| `CatalogCorruptionError` | `catalog.invariant.failed` |

Expected record invalidity is a finding/disposition, not an exception from whole-batch
processing. Exceptions indicate invalid API use, unavailable registration, stale state,
transaction failure, or broken invariants. All contexts are bounded and redacted.

## 22. Edge-case decisions

| Case | Required behavior |
| --- | --- |
| Empty batch | Reject with zero records and stable reason |
| Exception during a staging chunk | Roll back that chunk; earlier chunks remain noncanonical |
| Process dies during staging | Leave resumable nonterminal batch; doctor reports it |
| Same submission key and same content | Return existing batch/result idempotently |
| Same submission key and different content | Raise conflict; preserve original |
| Same observation twice in one batch | Lowest record number proceeds; later row is duplicate |
| Same committed observation received again | Duplicate disposition, no new revision |
| Same source revision key with changed bytes | Quarantine conflict group |
| Two changed rows share one natural key in a batch | Apply registered order only if unambiguous; otherwise quarantine group |
| Correction lacks publication time | Ingestion-bound or unknown; never inherit original availability |
| Structural error affects one record | Reject batch when decoding/key integrity is compromised |
| Referential error affects a separable record | Quarantine record under policy |
| Cross-record invariant fails | Quarantine atomic disposition group or batch |
| Statistical outlier | Commit with warning by default |
| Every record is an exact duplicate | `committed`, zero new canonical rows, audit sequence advances |
| Every record is quarantined | `quarantined`, no canonical rows |
| Partial commit transaction fails | No accepted row, disposition, or terminal status is visible |
| Validation catalog dependency changes | Return to staged and require revalidation |
| Remediation child fails | Parent remains immutable and status derives as attempted |
| Later ingestion after a snapshot | Earlier snapshot queries remain byte/row stable |
| Snapshot requested at unchanged sequence | Verify and return existing ID |
| Catalog newer than latest snapshot | Return latest snapshot with unpinned warning |
| Composite member path is a copy | Require matching verified copy/database/snapshot manifest |
| Hash collision candidate | Compare canonical bytes; invariant-fail on unequal bytes |
| Record contains prohibited raw payload | Reject/quarantine according to structural licensing rule |

## 23. Security and resource behavior

- No ingestion API accepts SQL, table names, pickle, arbitrary object codecs, or raw
  connections from an adapter.
- Record, evidence, definition, raw-manifest, and event payload sizes have explicit limits
  checked before allocation-heavy decoding.
- Canonical JSON rejects NaN, infinity, unknown fields, object hooks, and import-path class
  loading under plan 01.
- Raw archive locations use normalized URI metadata; credentials and signed query strings
  are rejected or redacted before persistence.
- Validation rules declare bounded row/column inputs. Whole-batch rules execute in DuckDB
  or bounded partitions rather than materializing unlimited pandas frames.
- Error evidence defaults to keys and summary statistics, not entire provider records.
- Adapter code executes in the caller's Python process and is not sandboxed; provider
  packages are trusted code but still cannot bypass managed database validation APIs.
- Quarantined licensed data follows the same local access and export restrictions as its
  source definition. Portable exports exclude it unless an explicit licensing-safe option
  is later specified.

## 24. Migration and compatibility effect

This is a greenfield v3 schema. No v2 Parquet store, symbol-keyed record, universe file,
source archive, or ingestion result is imported or mapped. Existing v2 data must be
reacquired or independently translated by a provider adapter into v3 canonical staging
records and then pass normal validation.

Within v3, adding catalog columns/tables or changing physical indexes uses plan-02 market
migrations. Changing natural-key bytes, revision semantics, canonical payload encoding,
catalog chain, disposition meaning, or snapshot manifest canonicalization is an identity
and compatibility change requiring a new dataset/manifest schema and cumulative review.
Committed rows are never rewritten merely to adopt a new source or validation policy.

## 25. Acceptance tests

### 25.1 Registry and canonicalization

- Register source/dataset definitions and verify exact name/version/content identity,
  catalog sequence, chain, events, and rollback at every write boundary.
- Reject breaking dataset changes under one identity, unknown codecs/rules, global import-
  time registration, unsupported source versions, and name conflicts.
- Golden-test natural key, payload, observation, definition, change-chain, and manifest
  canonical bytes and content IDs across processes.

### 25.2 Batch lifecycle and atomicity

- Statefully generate every legal and illegal batch transition and verify gap-free history,
  current projection, captured timestamps, and terminal immutability.
- Inject failure before and after every staging, validation, disposition, canonical insert,
  chain update, event, and commit boundary; prove no partial terminal visibility.
- Property-test that terminal disposition counts exactly partition staged records.
- Test same/different submission-key retries, process-death staging recovery, explicit
  abort, empty batches, and all-duplicate batches.
- Prove retry batch/source content IDs exclude local receipt identity while accepted
  observation identity preserves the first canonical `ingested_at`.

### 25.3 Validation and revision behavior

- Contract-test every required validation phase, deterministic rule ordering, policy
  strictness, evidence bounds, stable codes, and structural no-bypass behavior.
- Generate duplicates, corrections, out-of-order revisions, source-token conflicts,
  natural-key hash collisions, and stale validation heads; assert exact outcomes.
- Run completed, stale, failed, abandoned, and replacement validation attempts; rebuild
  current attempt state while retaining every immutable finding.
- Prove unknown correction availability is ingestion-bounded/unsafe and never inherits
  original temporal metadata.
- Verify revision selection under snapshot, public cutoff, and project cutoff against a
  small hand-worked history.

### 25.4 Partial quarantine and remediation

- Hand-work mixed batches with accepted-new, accepted-revision, duplicate, record/group
  quarantine, warnings, and rejection; verify exact terminal status and canonical rows.
- Property-test that no quarantined or rejected record appears in canonical views and no
  accepted member is omitted from a successful partial commit.
- Submit failed and successful child remediations, multiple attempts, duplicate resolutions,
  and supplements; rebuild derived status entirely from immutable links/dispositions.
- Verify parent batch, record, finding, payload, and disposition bytes never change.

### 25.5 Snapshot stability

- At every catalog sequence, create a snapshot, ingest later revisions/definitions/failed
  batches, and prove all earlier canonical and quality queries remain stable.
- Rebuild catalog and per-dataset/source rolling chains from append-only rows and compare
  every snapshot manifest.
- Test idempotent same-sequence creation, manifest mismatch corruption, sequence-0 snapshot,
  unpinned latest warning, and snapshot failure after a committed batch.
- Create composite snapshots over multiple market databases/copies, resolve latest once,
  reject mismatched IDs/manifests, and prove immutable idempotence.

### 25.6 Provider and resource contracts

- Run external-style adapters through chunk sizes 1, 49,999, 50,000, 50,001, and larger;
  results and content identities must be chunk-boundary independent.
- Assert bounded memory for streaming and validation fixtures and reject oversized records,
  evidence, definitions, and manifests before publication.
- Prove adapters have no supported connection/table/write access and that raw manifest
  redaction removes credentials.

### 25.7 CLI and documentation

- Implement and contract-test `persistra data validate`, `persistra data quarantine`, and
  `persistra data snapshot` list/inspect/create operations with plan-02 JSON/exit rules.
- Run deterministic textual provider fixtures through full, partial, rejected, quarantined,
  remediated, revised, and snapshot workflows using only public APIs.
- Strict-build docs and execute implementation-ready snippets when their APIs exist.

### 25.8 Exit criteria

This plan is implementation-complete when:

- every canonical dataset can reuse one published provider/batch/validation contract;
- batch and disposition state machines pass generated and fault-injection tests;
- full and partial commits are atomic and every submitted record remains auditable;
- quarantine and remediation are immutable, linked, inspectable, and reproducible;
- append-only revision and catalog chains rebuild exactly;
- later writes cannot change a pinned market or composite snapshot query;
- provider conformance fixtures cover retry, temporal, revision, and atomicity behavior;
- no public structural-validation or managed-write bypass exists; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 26. Review checklist for dependent plans

Every dataset-owning focused specification must state:

- dataset/source qualified names, IDs, versions, natural keys, and typed tables;
- exact event, publication, availability, ingestion, interval, and effective fields;
- original-observation and correction availability policies and safety classifications;
- revision ordering, duplicate, conflict, and multi-source precedence behavior;
- required validation rules, stable codes, severities, disposition actions, and groups;
- canonical payload and public dataframe schemas with units/nullability;
- which records can be remediated and how child records relate;
- which rolling state and snapshot manifest fields cover the dataset;
- bounded staging/validation behavior and provider conformance fixtures; and
- migration effects of any schema, key, codec, policy, or meaning change.

Every research-owning plan must state which exact `CompositeSnapshotId` it consumes and
must never replace it with moving latest attachments.

## 27. Umbrella and completed-plan consistency

This plan reuses plan 01 typed UUIDs, content IDs, UTC instants, availability quality,
canonical JSON, immutable event envelopes, and deterministic sequences. It reuses plan 02
market/research roles, schemas, project modes, exclusive/shared leases, connection
ownership, transactions, verified physical copies, and forward migrations.

It makes the umbrella batch lifecycle more explicit without changing its outcomes. It
implements stable per-record dispositions, atomic partial quarantine, linked child
remediation, append-only revisions, revision-specific availability, logical snapshot
high-water marks, and composite snapshots. No structural validation bypass, mutable
canonical fact, hidden latest state, provider-specific client, cross-file atomicity claim,
or database-backend abstraction is introduced.
