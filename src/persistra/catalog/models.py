"""Immutable catalog, ingestion, revision, and snapshot value models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName, SchemaVersion

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.db.models import DatabaseId


class SourceId(EntityId):
    KIND: ClassVar[str] = "source"


class DatasetId(EntityId):
    KIND: ClassVar[str] = "dataset"


class BatchId(EntityId):
    KIND: ClassVar[str] = "batch"


class SubmittedRecordId(EntityId):
    KIND: ClassVar[str] = "submitted_record"


class ValidationAttemptId(EntityId):
    KIND: ClassVar[str] = "validation_attempt"


class CanonicalRevisionId(EntityId):
    KIND: ClassVar[str] = "revision"


class QuarantineId(EntityId):
    KIND: ClassVar[str] = "quarantine"


class MarketSnapshotId(EntityId):
    KIND: ClassVar[str] = "market_snapshot"


class CompositeSnapshotId(EntityId):
    KIND: ClassVar[str] = "composite_snapshot"


class RevisionEffect(StrEnum):
    UPSERT = "upsert"
    RETRACT = "retract"


class BatchStatus(StrEnum):
    CREATED = "created"
    STAGED = "staged"
    VALIDATED = "validated"
    COMMITTED = "committed"
    COMMITTED_WITH_QUARANTINE = "committed_with_quarantine"
    REJECTED = "rejected"
    ABORTED = "aborted"


class RecordDisposition(StrEnum):
    ACCEPTED_NEW = "accepted_new"
    ACCEPTED_REVISION = "accepted_revision"
    DUPLICATE_IGNORED = "duplicate_ignored"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ComponentRef:
    name: QualifiedName
    version: str


@dataclass(frozen=True, slots=True)
class SourceRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class DatasetRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    name: QualifiedName
    provider_display_name: str
    licensing_class: str
    adapter_contract: ComponentRef
    adapter_version_range: str
    conformance_content_id: ContentId
    source_key_schema_content_id: ContentId
    revision_token_policy: QualifiedName
    timestamp_precision: str
    timezone_guarantee: str
    raw_archive_policy: QualifiedName
    redistributable: bool
    enabled: bool
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    name: QualifiedName
    record_model: ComponentRef
    entity_grain: QualifiedName
    time_grain: QualifiedName
    natural_key_schema_content_id: ContentId
    row_schema_content_id: ContentId
    revision_policy: QualifiedName
    retractions_allowed: bool
    retraction_schema_content_id: ContentId | None
    availability_policy: QualifiedName
    validation_policy: QualifiedName
    supported_sources: tuple[SourceRef, ...]
    maximum_record_bytes: int = 1_048_576
    staging_chunk_rows: int = 50_000
    schema_version: SchemaVersion = field(default_factory=lambda: SchemaVersion(1))


@dataclass(frozen=True, slots=True)
class ResolvedSourceRef:
    source_id: SourceId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ResolvedDatasetRef:
    dataset_id: DatasetId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class BatchHeader:
    source: SourceRef
    dataset: DatasetRef
    submission_key: str
    adapter: ComponentRef
    expected_batch_content_id: ContentId | None = None


StringFields = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class IngestionRecord:
    natural_key: StringFields
    payload: StringFields
    available_at: datetime
    event_at: datetime | None = None
    source_record_key: str | None = None
    source_revision_key: str | None = None
    revision_effect: RevisionEffect = RevisionEffect.UPSERT


@dataclass(frozen=True, slots=True)
class BatchHandle:
    batch_id: BatchId
    status: BatchStatus


@dataclass(frozen=True, slots=True)
class ValidationResult:
    batch_id: BatchId
    validation_attempt_id: ValidationAttemptId
    token: ContentId
    proposed_status: BatchStatus
    quarantined_count: int


@dataclass(frozen=True, slots=True)
class BatchCounts:
    submitted: int
    accepted_new: int
    accepted_revision: int
    duplicate_ignored: int
    quarantined: int
    rejected: int


@dataclass(frozen=True, slots=True)
class BatchResult:
    batch_id: BatchId
    status: BatchStatus
    catalog_sequence: int
    counts: BatchCounts
    snapshot: SnapshotRef | None = None


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    database_id: DatabaseId
    snapshot_id: MarketSnapshotId
    catalog_sequence: int
    manifest_content_id: ContentId


@dataclass(frozen=True, slots=True)
class CanonicalObservation:
    revision_id: CanonicalRevisionId
    dataset_id: DatasetId
    source_id: SourceId
    natural_key: StringFields
    payload: StringFields
    effect: RevisionEffect
    available_at: datetime
    ingested_at: datetime
    catalog_sequence: int


@dataclass(frozen=True, slots=True)
class QuarantinedRecord:
    quarantine_id: QuarantineId
    batch_id: BatchId
    submitted_record_id: SubmittedRecordId
    reason_code: str
    payload: StringFields
    quarantined_at: datetime
