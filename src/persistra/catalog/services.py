"""Project-owned catalog, ingestion, revision, and snapshot services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast

from persistra.catalog.models import (
    BatchCounts,
    BatchHandle,
    BatchHeader,
    BatchId,
    BatchResult,
    BatchStatus,
    CanonicalObservation,
    CanonicalRevisionId,
    ComponentRef,
    CompositeSnapshotId,
    CompositeSnapshotMember,
    CompositeSnapshotRef,
    DatasetDefinition,
    DatasetId,
    DatasetRef,
    IngestionRecord,
    MarketSnapshotId,
    QuarantinedRecord,
    QuarantineId,
    RecordDisposition,
    ResolvedDatasetRef,
    ResolvedSourceRef,
    RevisionEffect,
    SnapshotRef,
    SourceDefinition,
    SourceId,
    SourceRef,
    SubmittedRecordId,
    ValidationAttemptId,
    ValidationResult,
)
from persistra.db import DatabaseRole, ProjectMode
from persistra.domain import ContentId, EntityId, QualifiedName, SchemaVersion
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    BatchConflictError,
    BatchStateError,
    CapabilityUnavailableError,
    CatalogDefinitionError,
    CatalogReferenceError,
    ValidationTokenError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.db.models import DatabaseName
    from persistra.project import Project

T = TypeVar("T")


def _fields(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise CatalogDefinitionError("stored string fields are malformed")
    result: list[tuple[str, str]] = []
    for item in cast("list[Any]", value):
        sequence = cast("list[Any]", item) if isinstance(item, list) else []
        if (
            not isinstance(item, list)
            or len(sequence) != 2
            or not all(isinstance(part, str) for part in sequence)
        ):
            raise CatalogDefinitionError("stored string fields are malformed")
        result.append((cast("str", sequence[0]), cast("str", sequence[1])))
    return tuple(result)


def _json_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise CatalogDefinitionError("stored catalog definition is malformed")
    return cast("dict[str, Any]", value)


def _component(value: Any) -> ComponentRef:
    if not isinstance(value, dict):
        raise CatalogDefinitionError("stored component reference is malformed")
    typed = cast("dict[str, Any]", value)
    return ComponentRef(QualifiedName(typed["name"]), cast("str", typed["version"]))


def _source_definition(text: str) -> SourceDefinition:
    value = _json_object(text)
    return SourceDefinition(
        name=QualifiedName(value["name"]),
        provider_display_name=cast("str", value["provider_display_name"]),
        licensing_class=cast("str", value["licensing_class"]),
        adapter_contract=_component(value["adapter_contract"]),
        adapter_version_range=cast("str", value["adapter_version_range"]),
        conformance_content_id=ContentId.parse(cast("str", value["conformance_content_id"])),
        source_key_schema_content_id=ContentId.parse(
            cast("str", value["source_key_schema_content_id"])
        ),
        revision_token_policy=QualifiedName(value["revision_token_policy"]),
        timestamp_precision=cast("str", value["timestamp_precision"]),
        timezone_guarantee=cast("str", value["timezone_guarantee"]),
        raw_archive_policy=QualifiedName(value["raw_archive_policy"]),
        redistributable=cast("bool", value["redistributable"]),
        enabled=cast("bool", value["enabled"]),
        schema_version=SchemaVersion(int(cast("str", value["schema_version"]))),
    )


def _dataset_definition(text: str) -> DatasetDefinition:
    value = _json_object(text)
    raw_sources = cast("list[dict[str, Any]]", value["supported_sources"])
    sources = tuple(
        SourceRef(QualifiedName(item["name"]), int(item["version"])) for item in raw_sources
    )
    retraction_schema = value["retraction_schema_content_id"]
    return DatasetDefinition(
        name=QualifiedName(value["name"]),
        record_model=_component(value["record_model"]),
        entity_grain=QualifiedName(value["entity_grain"]),
        time_grain=QualifiedName(value["time_grain"]),
        natural_key_schema_content_id=ContentId.parse(
            cast("str", value["natural_key_schema_content_id"])
        ),
        row_schema_content_id=ContentId.parse(cast("str", value["row_schema_content_id"])),
        revision_policy=QualifiedName(value["revision_policy"]),
        retractions_allowed=cast("bool", value["retractions_allowed"]),
        retraction_schema_content_id=(
            None
            if retraction_schema is None
            else ContentId.parse(cast("str", retraction_schema))
        ),
        availability_policy=QualifiedName(value["availability_policy"]),
        validation_policy=QualifiedName(value["validation_policy"]),
        supported_sources=sources,
        maximum_record_bytes=int(value["maximum_record_bytes"]),
        staging_chunk_rows=int(value["staging_chunk_rows"]),
        schema_version=SchemaVersion(int(cast("str", value["schema_version"]))),
    )


class _OwnedService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def _connection(self) -> ManagedConnection:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        return self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]

    def _require_market_write(self) -> ManagedConnection:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("operation requires market_write mode")
        return self._connection()

    def _transaction(self, name: str, function: Callable[[ManagedConnection, datetime], T]) -> T:
        connection = self._require_market_write()
        return self._project.services.transactions.run(
            name, lambda context: function(connection, context.recorded_at)
        )


def _advance_catalog(
    connection: ManagedConnection,
    *,
    change_kind: str,
    entity_id: EntityId,
    change_content_id: ContentId,
    recorded_at: datetime,
) -> int:
    sequence, prior = connection.execute(
        "SELECT current_sequence, chain_content_id FROM catalog.catalog_clock"
    ).fetchone()
    next_sequence = int(sequence) + 1
    chain = scoped_content_id(
        {
            "catalog_sequence": next_sequence,
            "change_content_id": change_content_id,
            "change_kind": change_kind,
            "prior_chain_content_id": prior,
        }
    )
    connection.execute(
        "INSERT INTO catalog.changes VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            next_sequence,
            change_kind,
            entity_id.value,
            str(change_content_id),
            prior,
            str(chain),
            recorded_at,
        ],
    )
    connection.execute(
        "UPDATE catalog.catalog_clock SET current_sequence = ?, chain_content_id = ?",
        [next_sequence, str(chain)],
    )
    return next_sequence


class SourceRegistry(_OwnedService):
    def register(self, definition: SourceDefinition) -> ResolvedSourceRef:
        """Idempotently register one immutable source definition version."""
        if definition.timestamp_precision not in {"second", "millisecond", "microsecond"}:
            raise CatalogDefinitionError("source timestamp precision is unsupported")
        if definition.timezone_guarantee not in {"utc", "explicit_offset", "source_local"}:
            raise CatalogDefinitionError("source timezone guarantee is unsupported")
        content_id = scoped_content_id(definition)
        encoded = canonical_bytes(definition).decode()

        def operation(connection: ManagedConnection, now: datetime) -> ResolvedSourceRef:
            entity = connection.execute(
                "SELECT source_id FROM catalog.sources WHERE qualified_name = ?",
                [str(definition.name)],
            ).fetchone()
            if entity is None:
                source_id = SourceId.new()
                version = 1
                connection.execute(
                    "INSERT INTO catalog.sources VALUES (?, ?, ?)",
                    [source_id.value, str(definition.name), now],
                )
            else:
                source_id = SourceId.parse(entity[0])
                latest = connection.execute(
                    "SELECT source_version, definition_content_id FROM catalog.source_versions "
                    "WHERE source_id = ? ORDER BY source_version DESC LIMIT 1",
                    [source_id.value],
                ).fetchone()
                assert latest is not None
                if latest[1] == str(content_id):
                    return ResolvedSourceRef(source_id, int(latest[0]), content_id)
                version = int(latest[0]) + 1
            sequence = _advance_catalog(
                connection,
                change_kind="source.registered",
                entity_id=source_id,
                change_content_id=content_id,
                recorded_at=now,
            )
            connection.execute(
                "INSERT INTO catalog.source_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    source_id.value,
                    version,
                    int(definition.schema_version.value),
                    str(content_id),
                    encoded,
                    definition.enabled,
                    sequence,
                    now,
                ],
            )
            return ResolvedSourceRef(source_id, version, content_id)

        return self._transaction("catalog.source.register", operation)

    def resolve(self, reference: SourceRef) -> ResolvedSourceRef:
        row = self._connection().execute(
            "SELECT s.source_id, v.definition_content_id FROM catalog.sources s "
            "JOIN catalog.source_versions v USING (source_id) "
            "WHERE s.qualified_name = ? AND v.source_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise CatalogReferenceError("source reference is not registered")
        return ResolvedSourceRef(
            SourceId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def get(self, reference: ResolvedSourceRef) -> SourceDefinition:
        row = self._connection().execute(
            "SELECT definition_content_id, definition_json FROM catalog.source_versions "
            "WHERE source_id = ? AND source_version = ?",
            [reference.source_id.value, reference.version],
        ).fetchone()
        if row is None or row[0] != str(reference.definition_content_id):
            raise CatalogReferenceError("resolved source reference is unavailable")
        return _source_definition(row[1])


class DatasetRegistry(_OwnedService):
    def register(self, definition: DatasetDefinition) -> ResolvedDatasetRef:
        """Idempotently register one dataset definition after resolving every source."""
        if not 1 <= definition.maximum_record_bytes <= 16 * 1024 * 1024:
            raise CatalogDefinitionError("dataset maximum record bytes is invalid")
        if not 1 <= definition.staging_chunk_rows <= 50_000:
            raise CatalogDefinitionError("dataset staging chunk size is invalid")
        for source in definition.supported_sources:
            SourceRegistry(self._project).resolve(source)
        content_id = scoped_content_id(definition)
        encoded = canonical_bytes(definition).decode()

        def operation(connection: ManagedConnection, now: datetime) -> ResolvedDatasetRef:
            entity = connection.execute(
                "SELECT dataset_id FROM catalog.datasets WHERE qualified_name = ?",
                [str(definition.name)],
            ).fetchone()
            if entity is None:
                dataset_id = DatasetId.new()
                version = 1
                connection.execute(
                    "INSERT INTO catalog.datasets VALUES (?, ?, ?)",
                    [dataset_id.value, str(definition.name), now],
                )
            else:
                dataset_id = DatasetId.parse(entity[0])
                latest = connection.execute(
                    "SELECT dataset_version, definition_content_id "
                    "FROM catalog.dataset_versions WHERE dataset_id = ? "
                    "ORDER BY dataset_version DESC LIMIT 1",
                    [dataset_id.value],
                ).fetchone()
                assert latest is not None
                if latest[1] == str(content_id):
                    return ResolvedDatasetRef(dataset_id, int(latest[0]), content_id)
                version = int(latest[0]) + 1
            sequence = _advance_catalog(
                connection,
                change_kind="dataset.registered",
                entity_id=dataset_id,
                change_content_id=content_id,
                recorded_at=now,
            )
            connection.execute(
                "INSERT INTO catalog.dataset_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    dataset_id.value,
                    version,
                    int(definition.schema_version.value),
                    str(content_id),
                    encoded,
                    sequence,
                    now,
                ],
            )
            return ResolvedDatasetRef(dataset_id, version, content_id)

        return self._transaction("catalog.dataset.register", operation)

    def resolve(self, reference: DatasetRef) -> ResolvedDatasetRef:
        row = self._connection().execute(
            "SELECT d.dataset_id, v.definition_content_id FROM catalog.datasets d "
            "JOIN catalog.dataset_versions v USING (dataset_id) "
            "WHERE d.qualified_name = ? AND v.dataset_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise CatalogReferenceError("dataset reference is not registered")
        return ResolvedDatasetRef(
            DatasetId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def get(self, reference: ResolvedDatasetRef) -> DatasetDefinition:
        row = self._connection().execute(
            "SELECT definition_content_id, definition_json FROM catalog.dataset_versions "
            "WHERE dataset_id = ? AND dataset_version = ?",
            [reference.dataset_id.value, reference.version],
        ).fetchone()
        if row is None or row[0] != str(reference.definition_content_id):
            raise CatalogReferenceError("resolved dataset reference is unavailable")
        return _dataset_definition(row[1])


@dataclass(frozen=True, slots=True)
class CatalogService:
    sources: SourceRegistry
    datasets: DatasetRegistry
    revisions: RevisionService


class RevisionService(_OwnedService):
    def history(
        self, dataset: DatasetRef, *, natural_key: tuple[tuple[str, str], ...] | None = None
    ) -> tuple[CanonicalObservation, ...]:
        """Return immutable source revision history in deterministic chain order."""
        resolved = DatasetRegistry(self._project).resolve(dataset)
        clauses = ["dataset_id = ?", "dataset_version = ?"]
        parameters: list[Any] = [resolved.dataset_id.value, resolved.version]
        if natural_key is not None:
            clauses.append("natural_key_content_id = ?")
            parameters.append(str(ContentId.from_bytes(canonical_bytes(natural_key))))
        rows = self._connection().execute(
            "SELECT canonical_revision_id, source_id, natural_key_json, "
            "canonical_payload_json, revision_effect, available_at, ingested_at, "
            "catalog_sequence FROM catalog.canonical_revisions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY natural_key_content_id, source_id, revision_ordinal",
            parameters,
        ).fetchall()
        return tuple(
            CanonicalObservation(
                CanonicalRevisionId.parse(row[0]),
                resolved.dataset_id,
                SourceId.parse(row[1]),
                _fields(json.loads(row[2])),
                _fields(json.loads(row[3])),
                RevisionEffect(row[4]),
                row[5],
                row[6],
                int(row[7]),
            )
            for row in rows
        )


class QuarantineService(_OwnedService):
    def list(self, *, batch_id: BatchId | None = None) -> tuple[QuarantinedRecord, ...]:
        """Return quarantined immutable staging records in stable order."""
        sql = (
            "SELECT quarantine_id, batch_id, submitted_record_id, reason_code, "
            "canonical_payload_json, quarantined_at FROM quality.quarantined_records"
        )
        parameters: list[Any] = []
        if batch_id is not None:
            sql += " WHERE batch_id = ?"
            parameters.append(batch_id.value)
        rows = self._connection().execute(
            sql + " ORDER BY quarantined_at, quarantine_id", parameters
        ).fetchall()
        return tuple(
            QuarantinedRecord(
                QuarantineId.parse(row[0]),
                BatchId.parse(row[1]),
                SubmittedRecordId.parse(row[2]),
                row[3],
                _fields(json.loads(row[4])),
                row[5],
            )
            for row in rows
        )


def _record_material(record: IngestionRecord) -> tuple[ContentId, ContentId, bytes, bytes]:
    if not record.natural_key or len({item[0] for item in record.natural_key}) != len(
        record.natural_key
    ):
        raise CatalogDefinitionError("record natural key must have unique named fields")
    if record.revision_effect is RevisionEffect.UPSERT and not record.payload:
        raise CatalogDefinitionError("upsert record payload cannot be empty")
    natural = canonical_bytes(record.natural_key)
    payload = canonical_bytes(record.payload)
    natural_id = ContentId.from_bytes(natural)
    payload_id = ContentId.from_bytes(payload)
    source_id = scoped_content_id(
        {
            "available_at": record.available_at,
            "event_at": record.event_at,
            "natural_key_content_id": natural_id,
            "payload_content_id": payload_id,
            "revision_effect": record.revision_effect,
            "source_record_key": record.source_record_key,
            "source_revision_key": record.source_revision_key,
        }
    )
    return natural_id, source_id, natural, payload


def _batch_content(header: BatchHeader, records: tuple[IngestionRecord, ...]) -> ContentId:
    return scoped_content_id(
        {
            "adapter": header.adapter,
            "dataset": header.dataset,
            "records": tuple(_record_material(record)[1] for record in records),
            "source": header.source,
        }
    )


class IngestionService(_OwnedService):
    @property
    def quarantine(self) -> QuarantineService:
        return QuarantineService(self._project)

    def get(self, batch_id: BatchId) -> BatchHandle:
        row = self._connection().execute(
            "SELECT current_status FROM catalog.batches WHERE batch_id = ?", [batch_id.value]
        ).fetchone()
        if row is None:
            raise CatalogReferenceError("batch is not registered")
        return BatchHandle(batch_id, BatchStatus(row[0]))

    def begin(self, header: BatchHeader) -> BatchHandle:
        if not header.submission_key or len(header.submission_key.encode()) > 512:
            raise CatalogDefinitionError("submission key is required and bounded")
        source = SourceRegistry(self._project).resolve(header.source)
        dataset = DatasetRegistry(self._project).resolve(header.dataset)

        def operation(connection: ManagedConnection, now: datetime) -> BatchHandle:
            existing = connection.execute(
                "SELECT batch_id, current_status, batch_content_id FROM catalog.batches "
                "WHERE source_id = ? AND dataset_id = ? AND submission_key = ?",
                [source.source_id.value, dataset.dataset_id.value, header.submission_key],
            ).fetchone()
            if existing is not None:
                if header.expected_batch_content_id is None or existing[2] != str(
                    header.expected_batch_content_id
                ):
                    raise BatchConflictError("submission key is already in use")
                return BatchHandle(BatchId.parse(existing[0]), BatchStatus(existing[1]))
            batch_id = BatchId.new()
            connection.execute(
                "INSERT INTO catalog.batches "
                "(batch_id, source_id, source_version, dataset_id, dataset_version, "
                "submission_key, adapter_name, adapter_version, current_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    source.source_id.value,
                    source.version,
                    dataset.dataset_id.value,
                    dataset.version,
                    header.submission_key,
                    str(header.adapter.name),
                    header.adapter.version,
                    BatchStatus.CREATED.value,
                    now,
                ],
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 1, NULL, ?, ?, ?)",
                [batch_id.value, BatchStatus.CREATED.value, "ingestion.batch.created", now],
            )
            return BatchHandle(batch_id, BatchStatus.CREATED)

        return self._transaction("ingestion.batch.begin", operation)

    def stage(
        self, batch_id: BatchId, records: Iterable[IngestionRecord]
    ) -> BatchHandle:
        materialized = tuple(records)
        if not materialized:
            raise CatalogDefinitionError("a batch must contain at least one record")

        def operation(connection: ManagedConnection, now: datetime) -> BatchHandle:
            batch = connection.execute(
                "SELECT current_status, source_id, source_version, dataset_id, dataset_version, "
                "adapter_name, adapter_version, batch_content_id FROM catalog.batches "
                "WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            header_material = {
                "adapter": ComponentRef(QualifiedName(batch[5]), batch[6]),
                "dataset_id": DatasetId.parse(batch[3]),
                "dataset_version": int(batch[4]),
                "records": tuple(_record_material(record)[1] for record in materialized),
                "source_id": SourceId.parse(batch[1]),
                "source_version": int(batch[2]),
            }
            batch_content = scoped_content_id(header_material)
            status = BatchStatus(batch[0])
            if status is not BatchStatus.CREATED:
                if batch[7] == str(batch_content):
                    return BatchHandle(batch_id, status)
                raise BatchConflictError("staged batch content does not match exact retry")
            for number, record in enumerate(materialized, 1):
                encoded_record = canonical_bytes(record)
                dataset_limit = connection.execute(
                    "SELECT definition_json FROM catalog.dataset_versions "
                    "WHERE dataset_id = ? AND dataset_version = ?",
                    [batch[3], batch[4]],
                ).fetchone()[0]
                maximum = _dataset_definition(dataset_limit).maximum_record_bytes
                if len(encoded_record) > maximum:
                    raise CatalogDefinitionError("record exceeds dataset maximum bytes")
                natural_id, source_content_id, natural, payload = _record_material(record)
                connection.execute(
                    "INSERT INTO catalog.batch_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?)",
                    [
                        SubmittedRecordId.new().value,
                        batch_id.value,
                        number,
                        record.source_record_key,
                        record.source_revision_key,
                        record.revision_effect.value,
                        str(natural_id),
                        natural.decode(),
                        str(ContentId.from_bytes(payload)),
                        str(source_content_id),
                        payload.decode(),
                        record.event_at,
                        record.available_at,
                        now,
                    ],
                )
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, staged_at = ?, "
                "batch_content_id = ?, submitted_count = ? WHERE batch_id = ?",
                [
                    BatchStatus.STAGED.value,
                    now,
                    str(batch_content),
                    len(materialized),
                    batch_id.value,
                ],
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 2, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    BatchStatus.CREATED.value,
                    BatchStatus.STAGED.value,
                    "ingestion.batch.staged",
                    now,
                ],
            )
            return BatchHandle(batch_id, BatchStatus.STAGED)

        return self._transaction("ingestion.batch.stage", operation)

    def validate(self, batch_id: BatchId) -> ValidationResult:
        def operation(connection: ManagedConnection, now: datetime) -> ValidationResult:
            batch = connection.execute(
                "SELECT current_status, batch_content_id FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None or BatchStatus(batch[0]) is not BatchStatus.STAGED:
                raise BatchStateError("only staged batches can be validated")
            invalid = int(
                connection.execute(
                    "SELECT count(*) FROM catalog.batch_records WHERE batch_id = ? "
                    "AND event_at IS NOT NULL AND available_at < event_at",
                    [batch_id.value],
                ).fetchone()[0]
            )
            attempt = ValidationAttemptId.new()
            catalog_sequence = int(
                connection.execute(
                    "SELECT current_sequence FROM catalog.catalog_clock"
                ).fetchone()[0]
            )
            token = scoped_content_id(
                {
                    "batch_content_id": ContentId.parse(batch[1]),
                    "input_catalog_sequence": catalog_sequence,
                    "quarantined_count": invalid,
                    "validation_attempt_id": attempt,
                }
            )
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, validated_at = ?, "
                "validation_token_content_id = ?, validation_attempt_id = ? WHERE batch_id = ?",
                [
                    BatchStatus.VALIDATED.value,
                    now,
                    str(token),
                    attempt.value,
                    batch_id.value,
                ],
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 3, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    BatchStatus.STAGED.value,
                    BatchStatus.VALIDATED.value,
                    "ingestion.batch.validated",
                    now,
                ],
            )
            proposed = (
                BatchStatus.COMMITTED_WITH_QUARANTINE
                if invalid
                else BatchStatus.COMMITTED
            )
            return ValidationResult(batch_id, attempt, token, proposed, invalid)

        return self._transaction("ingestion.batch.validate", operation)

    def commit(
        self,
        batch_id: BatchId,
        *,
        validation_token: ContentId,
        create_snapshot: bool = False,
    ) -> BatchResult:
        def operation(connection: ManagedConnection, now: datetime) -> BatchResult:
            batch = connection.execute(
                "SELECT current_status, validation_token_content_id, batch_content_id, "
                "source_id, source_version, dataset_id, dataset_version, submitted_count, "
                "catalog_sequence FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            status = BatchStatus(batch[0])
            if status in {
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
            }:
                return self._result(connection, batch_id, status, int(batch[8]))
            if status is not BatchStatus.VALIDATED:
                raise BatchStateError("only validated batches can be committed")
            if batch[1] != str(validation_token):
                raise ValidationTokenError("validation token does not match the batch")
            sequence = _advance_catalog(
                connection,
                change_kind="batch.committed",
                entity_id=batch_id,
                change_content_id=ContentId.parse(batch[2]),
                recorded_at=now,
            )
            dataset_definition = _dataset_definition(
                connection.execute(
                    "SELECT definition_json FROM catalog.dataset_versions "
                    "WHERE dataset_id = ? AND dataset_version = ?",
                    [batch[5], batch[6]],
                ).fetchone()[0]
            )
            counts = {
                RecordDisposition.ACCEPTED_NEW: 0,
                RecordDisposition.ACCEPTED_REVISION: 0,
                RecordDisposition.DUPLICATE_IGNORED: 0,
                RecordDisposition.QUARANTINED: 0,
            }
            records = connection.execute(
                "SELECT submitted_record_id, source_record_key, source_revision_key, "
                "revision_effect, natural_key_content_id, natural_key_json, payload_content_id, "
                "source_content_id, canonical_payload_json, event_at, available_at, ingested_at "
                "FROM catalog.batch_records WHERE batch_id = ? ORDER BY record_number",
                [batch_id.value],
            ).fetchall()
            for record in records:
                duplicate = connection.execute(
                    "SELECT canonical_revision_id FROM catalog.canonical_revisions "
                    "WHERE source_content_id = ?",
                    [record[7]],
                ).fetchone()
                if duplicate is not None:
                    disposition = RecordDisposition.DUPLICATE_IGNORED
                    revision_id = CanonicalRevisionId.parse(duplicate[0])
                    reason = "ingestion.record.duplicate"
                else:
                    head = connection.execute(
                        "SELECT canonical_revision_id, revision_ordinal "
                        "FROM catalog.canonical_revisions WHERE dataset_id = ? "
                        "AND source_id = ? AND natural_key_content_id = ? "
                        "ORDER BY revision_ordinal DESC LIMIT 1",
                        [batch[5], batch[3], record[4]],
                    ).fetchone()
                    invalid_time = record[9] is not None and record[10] < record[9]
                    invalid_retraction = record[3] == RevisionEffect.RETRACT.value and (
                        not dataset_definition.retractions_allowed or head is None
                    )
                    if invalid_time or invalid_retraction:
                        disposition = RecordDisposition.QUARANTINED
                        revision_id = None
                        reason = (
                            "ingestion.availability.before_event"
                            if invalid_time
                            else "ingestion.retraction.target_missing"
                        )
                        connection.execute(
                            "INSERT INTO quality.quarantined_records VALUES (?, ?, ?, ?, ?, ?)",
                            [
                                QuarantineId.new().value,
                                record[0],
                                batch_id.value,
                                reason,
                                record[8],
                                now,
                            ],
                        )
                    else:
                        revision_id = CanonicalRevisionId.new()
                        ordinal = 1 if head is None else int(head[1]) + 1
                        disposition = (
                            RecordDisposition.ACCEPTED_NEW
                            if head is None
                            else RecordDisposition.ACCEPTED_REVISION
                        )
                        reason = "ingestion.record.accepted"
                        connection.execute(
                            "INSERT INTO catalog.canonical_revisions VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                revision_id.value,
                                batch[5],
                                batch[6],
                                batch[3],
                                record[4],
                                record[5],
                                ordinal,
                                None if head is None else head[0],
                                record[1],
                                record[2],
                                record[3],
                                record[6],
                                record[7],
                                record[8],
                                batch_id.value,
                                record[0],
                                record[9],
                                record[10],
                                record[11],
                                sequence,
                            ],
                        )
                counts[disposition] += 1
                connection.execute(
                    "INSERT INTO catalog.record_dispositions VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        record[0],
                        batch_id.value,
                        disposition.value,
                        reason,
                        None if revision_id is None else revision_id.value,
                        now,
                    ],
                )
            final_status = (
                BatchStatus.COMMITTED_WITH_QUARANTINE
                if counts[RecordDisposition.QUARANTINED]
                else BatchStatus.COMMITTED
            )
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, terminal_at = ?, "
                "catalog_sequence = ? WHERE batch_id = ?",
                [final_status.value, now, sequence, batch_id.value],
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 4, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    BatchStatus.VALIDATED.value,
                    final_status.value,
                    "ingestion.batch.committed",
                    now,
                ],
            )
            return BatchResult(
                batch_id,
                final_status,
                sequence,
                BatchCounts(
                    int(batch[7]),
                    counts[RecordDisposition.ACCEPTED_NEW],
                    counts[RecordDisposition.ACCEPTED_REVISION],
                    counts[RecordDisposition.DUPLICATE_IGNORED],
                    counts[RecordDisposition.QUARANTINED],
                    0,
                ),
            )

        result = self._transaction("ingestion.batch.commit", operation)
        if create_snapshot:
            snapshot = SnapshotService(self._project).create()
            return BatchResult(
                result.batch_id,
                result.status,
                result.catalog_sequence,
                result.counts,
                snapshot,
            )
        return result

    def _result(
        self,
        connection: ManagedConnection,
        batch_id: BatchId,
        status: BatchStatus,
        sequence: int,
    ) -> BatchResult:
        values = dict(
            connection.execute(
                "SELECT disposition, count(*) FROM catalog.record_dispositions "
                "WHERE batch_id = ? GROUP BY disposition",
                [batch_id.value],
            ).fetchall()
        )
        submitted = int(
            connection.execute(
                "SELECT submitted_count FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()[0]
        )
        return BatchResult(
            batch_id,
            status,
            sequence,
            BatchCounts(
                submitted,
                int(values.get(RecordDisposition.ACCEPTED_NEW.value, 0)),
                int(values.get(RecordDisposition.ACCEPTED_REVISION.value, 0)),
                int(values.get(RecordDisposition.DUPLICATE_IGNORED.value, 0)),
                int(values.get(RecordDisposition.QUARANTINED.value, 0)),
                int(values.get(RecordDisposition.REJECTED.value, 0)),
            ),
        )

    def submit(
        self,
        header: BatchHeader,
        records: Iterable[IngestionRecord],
        *,
        create_snapshot: bool = False,
    ) -> BatchResult:
        materialized = tuple(records)
        _ = _batch_content(header, materialized)
        source = SourceRegistry(self._project).resolve(header.source)
        dataset = DatasetRegistry(self._project).resolve(header.dataset)
        existing = self._connection().execute(
            "SELECT batch_id, current_status, batch_content_id, catalog_sequence "
            "FROM catalog.batches WHERE source_id = ? AND dataset_id = ? AND submission_key = ?",
            [source.source_id.value, dataset.dataset_id.value, header.submission_key],
        ).fetchone()
        if existing is not None:
            submitted_content = scoped_content_id(
                {
                    "adapter": header.adapter,
                    "dataset_id": dataset.dataset_id,
                    "dataset_version": dataset.version,
                    "records": tuple(
                        _record_material(record)[1] for record in materialized
                    ),
                    "source_id": source.source_id,
                    "source_version": source.version,
                }
            )
            if existing[2] != str(submitted_content):
                raise BatchConflictError("submission retry content does not match")
            status = BatchStatus(existing[1])
            if status in {
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
            }:
                return self._result(
                    self._connection(), BatchId.parse(existing[0]), status, int(existing[3])
                )
            raise BatchStateError("submission retry is not terminal")
        handle = self.begin(header)
        self.stage(handle.batch_id, materialized)
        validation = self.validate(handle.batch_id)
        return self.commit(
            handle.batch_id,
            validation_token=validation.token,
            create_snapshot=create_snapshot,
        )


class SnapshotService(_OwnedService):
    def create(self) -> SnapshotRef:
        def operation(connection: ManagedConnection, now: datetime) -> SnapshotRef:
            sequence, chain = connection.execute(
                "SELECT current_sequence, chain_content_id FROM catalog.catalog_clock"
            ).fetchone()
            opened = self._project._databases[0]  # pyright: ignore[reportPrivateUsage]
            if opened.metadata.role is not DatabaseRole.MARKET:
                raise CapabilityUnavailableError("market snapshots require a market database")
            existing = connection.execute(
                "SELECT market_snapshot_id, manifest_content_id FROM snapshots.market_snapshots "
                "WHERE database_id = ? AND catalog_sequence = ?",
                [opened.metadata.database_id.value, sequence],
            ).fetchone()
            if existing is not None:
                return SnapshotRef(
                    opened.metadata.database_id,
                    MarketSnapshotId.parse(existing[0]),
                    int(sequence),
                    ContentId.parse(existing[1]),
                )
            snapshot_id = MarketSnapshotId.new()
            manifest = {
                "catalog_chain_content_id": chain,
                "catalog_sequence": int(sequence),
                "database_id": opened.metadata.database_id,
                "manifest_schema": "persistra.market_snapshot@1",
                "snapshot_id": snapshot_id,
            }
            encoded = canonical_bytes(manifest)
            content_id = ContentId.from_bytes(encoded)
            connection.execute(
                "INSERT INTO snapshots.market_snapshots VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                [
                    snapshot_id.value,
                    opened.metadata.database_id.value,
                    sequence,
                    chain,
                    str(content_id),
                    encoded.decode(),
                    now,
                ],
            )
            return SnapshotRef(
                opened.metadata.database_id, snapshot_id, int(sequence), content_id
            )

        return self._transaction("catalog.snapshot.create", operation)

    def latest(self) -> SnapshotRef | None:
        connection = self._connection()
        opened = self._project._databases[0]  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT market_snapshot_id, catalog_sequence, manifest_content_id "
            "FROM snapshots.market_snapshots WHERE database_id = ? "
            "ORDER BY catalog_sequence DESC LIMIT 1",
            [opened.metadata.database_id.value],
        ).fetchone()
        if row is None:
            return None
        return SnapshotRef(
            opened.metadata.database_id,
            MarketSnapshotId.parse(row[0]),
            int(row[1]),
            ContentId.parse(row[2]),
        )

    def create_composite(
        self, members: Mapping[DatabaseName, SnapshotRef]
    ) -> CompositeSnapshotRef:
        """Bind exact market snapshots into one immutable research-owned manifest."""
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "composite snapshots require research_write mode"
            )
        if not members:
            raise CatalogDefinitionError("a composite snapshot requires at least one member")
        opened_markets = {
            item.logical_name: item
            for item in self._project._databases  # pyright: ignore[reportPrivateUsage]
            if item.metadata.role is DatabaseRole.MARKET
        }
        normalized: list[CompositeSnapshotMember] = []
        for name, snapshot in sorted(members.items(), key=lambda item: item[0].value):
            opened = opened_markets.get(name.value)
            if opened is None or opened.metadata.database_id != snapshot.database_id:
                raise CatalogReferenceError(
                    "composite snapshot member does not match the configured database"
                )
            normalized.append(
                CompositeSnapshotMember(
                    name,
                    snapshot.database_id,
                    snapshot.snapshot_id,
                    snapshot.manifest_content_id,
                )
            )
        immutable_members = tuple(normalized)
        manifest = {
            "manifest_schema": "persistra.composite_snapshot@1",
            "members": immutable_members,
            "project_id": self._project._config.project_id,  # pyright: ignore[reportPrivateUsage]
        }
        encoded = canonical_bytes(manifest)
        content_id = ContentId.from_bytes(encoded)

        def operation(_context: object) -> CompositeSnapshotRef:
            connection = self._connection()
            database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
            qualified = f'"{database_name.replace(chr(34), chr(34) * 2)}"."research"'
            existing = connection.execute(
                f"SELECT composite_snapshot_id FROM {qualified}.composite_snapshots "
                "WHERE manifest_content_id = ?",
                [str(content_id)],
            ).fetchone()
            if existing is not None:
                return CompositeSnapshotRef(
                    CompositeSnapshotId.parse(existing[0]), content_id, immutable_members
                )
            snapshot_id = CompositeSnapshotId.new()
            now = self._project._clock.now()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                f"INSERT INTO {qualified}.composite_snapshots VALUES (?, ?, 1, ?, ?, ?)",
                [
                    snapshot_id.value,
                    self._project._config.project_id.value,  # pyright: ignore[reportPrivateUsage]
                    str(content_id),
                    encoded.decode(),
                    now,
                ],
            )
            for member in immutable_members:
                connection.execute(
                    f"INSERT INTO {qualified}.composite_snapshot_members "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        snapshot_id.value,
                        member.database_name.value,
                        member.database_id.value,
                        member.market_snapshot_id.value,
                        str(member.market_manifest_content_id),
                    ],
                )
            return CompositeSnapshotRef(snapshot_id, content_id, immutable_members)

        return self._project.services.transactions.run(
            "catalog.composite_snapshot.create", operation
        )

    def select(
        self,
        dataset: DatasetRef,
        *,
        snapshot: SnapshotRef,
        public_cutoff: datetime,
        project_cutoff: datetime,
    ) -> tuple[CanonicalObservation, ...]:
        resolved = DatasetRegistry(self._project).resolve(dataset)
        definition = DatasetRegistry(self._project).get(resolved)
        source_priority = {
            SourceRegistry(self._project).resolve(reference).source_id: number
            for number, reference in enumerate(definition.supported_sources)
        }
        rows = self._connection().execute(
            "SELECT canonical_revision_id, source_id, natural_key_json, "
            "canonical_payload_json, revision_effect, available_at, ingested_at, "
            "catalog_sequence, revision_ordinal FROM catalog.canonical_revisions "
            "WHERE dataset_id = ? AND dataset_version = ? AND catalog_sequence <= ? "
            "AND available_at <= ? AND ingested_at <= ? "
            "ORDER BY natural_key_content_id, source_id, revision_ordinal DESC",
            [
                resolved.dataset_id.value,
                resolved.version,
                snapshot.catalog_sequence,
                public_cutoff,
                project_cutoff,
            ],
        ).fetchall()
        per_source: dict[tuple[str, SourceId], Any] = {}
        for row in rows:
            source_id = SourceId.parse(row[1])
            natural_text = cast("str", row[2])
            per_source.setdefault((natural_text, source_id), row)
        winners: dict[str, Any] = {}
        for (natural_text, source_id), row in per_source.items():
            current = winners.get(natural_text)
            candidate_priority = (
                source_priority[source_id] if source_id in source_priority else 2**31
            )
            current_source = None if current is None else SourceId.parse(current[1])
            current_priority = (
                source_priority[current_source]
                if current_source is not None and current_source in source_priority
                else 2**31
            )
            if current is None or candidate_priority < current_priority:
                winners[natural_text] = row
        return tuple(
            CanonicalObservation(
                CanonicalRevisionId.parse(row[0]),
                resolved.dataset_id,
                SourceId.parse(row[1]),
                _fields(json.loads(row[2])),
                _fields(json.loads(row[3])),
                RevisionEffect(row[4]),
                row[5],
                row[6],
                int(row[7]),
            )
            for _, row in sorted(winners.items())
        )
