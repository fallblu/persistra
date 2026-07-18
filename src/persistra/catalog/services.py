"""Project-owned catalog, ingestion, revision, and snapshot services."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

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
    DispositionGroupId,
    FindingId,
    IngestionRecord,
    MarketSnapshotId,
    QuarantinedRecord,
    QuarantineId,
    RecordDisposition,
    RemediationAttempt,
    RemediationHistory,
    RemediationId,
    ResolvedDatasetRef,
    ResolvedSourceRef,
    RevisionEffect,
    SelectionAudit,
    SnapshotFailure,
    SnapshotRef,
    SnapshotSelection,
    SourceDefinition,
    SourceId,
    SourceRef,
    SubmittedRecordId,
    ValidationAttemptId,
    ValidationFinding,
    ValidationResult,
)
from persistra.db import DatabaseRole, ProjectMode
from persistra.domain import ContentId, EntityId, EventId, QualifiedName, SchemaVersion
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.domain.time import validate_instant
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
    __slots__ = ("_project", "_selected_connection")

    def __init__(
        self, project: Project, *, connection: ManagedConnection | None = None
    ) -> None:
        self._project = project
        self._selected_connection = connection

    def _market_database(
        self,
        *,
        database_id: EntityId | None = None,
        name: DatabaseName | None = None,
    ) -> Any:
        markets = [
            item
            for item in self._project._databases  # pyright: ignore[reportPrivateUsage]
            if item.metadata.role is DatabaseRole.MARKET
            and (database_id is None or item.metadata.database_id == database_id)
            and (name is None or item.logical_name == name.value)
        ]
        if len(markets) != 1:
            raise CapabilityUnavailableError(
                "operation requires one explicit configured market database"
            )
        return markets[0]

    def _connection(self) -> ManagedConnection:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        self._project._validate_leases()  # pyright: ignore[reportPrivateUsage]
        if self._selected_connection is not None:
            return self._selected_connection
        if self._project._mode is ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            return self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return self._market_database().connection

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
            "schema": "persistra.catalog.change_chain",
            "version": 1,
            "catalog_sequence": next_sequence,
            "change_content_id": change_content_id,
            "change_entity_id": entity_id,
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


def _insert_event(
    connection: ManagedConnection,
    *,
    event_name: str,
    aggregate_kind: str,
    aggregate_id: EntityId,
    aggregate_sequence: int,
    recorded_at: datetime,
    payload: dict[str, Any],
) -> None:
    encoded = canonical_bytes(payload)
    connection.execute(
        "INSERT INTO _persistra.domain_events VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, "
        "NULL, NULL, ?, ?)",
        [
            EventId.new().value,
            event_name,
            recorded_at,
            recorded_at,
            recorded_at,
            aggregate_kind,
            aggregate_id.value,
            aggregate_sequence,
            str(ContentId.from_bytes(encoded)),
            encoded,
        ],
    )


# Shared subsystem writers use these two transaction-local primitives.  The public aliases
# keep cross-namespace code out of the catalog service's private implementation surface.
advance_catalog = _advance_catalog
insert_event = _insert_event


def _registered_state_material(
    connection: ManagedConnection,
    *,
    kind: str,
    entity_id: Any,
    entity_version: int,
) -> tuple[int, int, int, int, int, int, ContentId]:
    if kind not in {"dataset", "source"}:
        raise CatalogDefinitionError("catalog state kind is invalid")
    id_column = f"{kind}_id"
    version_column = f"{kind}_version"
    definition_table = f"{kind}_versions"
    definition = connection.execute(
        f"SELECT catalog_sequence, definition_content_id FROM catalog.{definition_table} "
        f"WHERE {id_column} = ? AND {version_column} = ?",
        [entity_id, entity_version],
    ).fetchone()
    if definition is None:
        raise CatalogDefinitionError("registered catalog state definition is missing")
    parameters = [entity_id, entity_version]
    revision_sql = (
        "SELECT count(*) FROM catalog.canonical_revisions "
        "WHERE dataset_id = ? AND dataset_version = ?"
        if kind == "dataset"
        else "SELECT count(*) FROM catalog.canonical_revisions r "
        "JOIN catalog.batches b ON b.batch_id = r.batch_id "
        "WHERE b.source_id = ? AND b.source_version = ?"
    )
    revision_count = int(connection.execute(revision_sql, parameters).fetchone()[0])
    terminal_batch_count, latest_batch = connection.execute(
        f"SELECT count(*), coalesce(max(catalog_sequence), 0) FROM catalog.batches "
        f"WHERE {id_column} = ? AND {version_column} = ? AND catalog_sequence IS NOT NULL",
        parameters,
    ).fetchone()
    disposition_count = int(
        connection.execute(
            "SELECT count(*) FROM catalog.record_dispositions d "
            "JOIN catalog.batches b ON b.batch_id = d.batch_id "
            f"WHERE b.{id_column} = ? AND b.{version_column} = ?",
            parameters,
        ).fetchone()[0]
    )
    validation_attempt_count = int(
        connection.execute(
            "SELECT count(*) FROM catalog.validation_attempts a "
            "JOIN catalog.batches b ON b.batch_id = a.batch_id "
            f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
            "AND b.catalog_sequence IS NOT NULL",
            parameters,
        ).fetchone()[0]
    )
    finding_count = int(
        connection.execute(
            "SELECT count(*) FROM quality.findings f "
            "JOIN catalog.batches b ON b.batch_id = f.batch_id "
            f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
            "AND b.catalog_sequence IS NOT NULL",
            parameters,
        ).fetchone()[0]
    )
    latest_sequence = max(int(definition[0]), int(latest_batch))
    evidence_root = _query_root(
        connection,
        f"persistra.catalog.{kind}_state_evidence@1",
        "SELECT b.batch_content_id, b.current_status, b.catalog_sequence, "
        "d.submitted_record_id, d.disposition, d.primary_reason_code, "
        "d.canonical_revision_id, d.disposition_group_id FROM catalog.batches b "
        "LEFT JOIN catalog.record_dispositions d ON d.batch_id = b.batch_id "
        f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
        "AND b.catalog_sequence IS NOT NULL "
        "ORDER BY b.catalog_sequence, d.submitted_record_id",
        parameters,
    )
    revision_root = _query_root(
        connection,
        f"persistra.catalog.{kind}_state_revisions@1",
        "SELECT r.canonical_revision_id, r.dataset_id, r.dataset_version, r.source_id, "
        "r.natural_key_content_id, r.natural_key_json, r.revision_ordinal, "
        "r.supersedes_revision_id, r.source_record_key, r.source_revision_key, "
        "r.revision_effect, r.payload_content_id, r.source_content_id, "
        "r.canonical_payload_json, r.batch_id, r.submitted_record_id, r.event_at, "
        "r.available_at, r.ingested_at, r.catalog_sequence, "
        "x.retracted_revision_id, x.retraction_reason_code, x.evidence_content_id "
        "FROM catalog.canonical_revisions r "
        "JOIN catalog.batches b ON b.batch_id = r.batch_id "
        "LEFT JOIN catalog.canonical_retractions x "
        "ON x.canonical_revision_id = r.canonical_revision_id "
        f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
        "ORDER BY r.catalog_sequence, r.canonical_revision_id",
        parameters,
    )
    validation_root = _query_root(
        connection,
        f"persistra.catalog.{kind}_state_validation@1",
        "SELECT a.validation_attempt_id, a.attempt_number, a.input_catalog_sequence, "
        "a.validation_token_content_id, a.current_status FROM catalog.validation_attempts a "
        "JOIN catalog.batches b ON b.batch_id = a.batch_id "
        f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
        "AND b.catalog_sequence IS NOT NULL ORDER BY b.catalog_sequence, a.attempt_number",
        parameters,
    )
    finding_root = _query_root(
        connection,
        f"persistra.catalog.{kind}_state_findings@1",
        "SELECT f.finding_id, f.submitted_record_id, f.severity, f.action, "
        "f.reason_code, f.evidence_content_id, f.disposition_group_id "
        "FROM quality.findings f "
        "JOIN catalog.batches b ON b.batch_id = f.batch_id "
        f"WHERE b.{id_column} = ? AND b.{version_column} = ? "
        "AND b.catalog_sequence IS NOT NULL ORDER BY b.catalog_sequence, f.finding_id",
        parameters,
    )
    state_content_id = scoped_content_id(
        {
            "definition_content_id": ContentId.parse(definition[1]),
            "disposition_count": disposition_count,
            "entity_id": str(entity_id),
            "entity_version": entity_version,
            "evidence_root": evidence_root,
            "finding_count": finding_count,
            "finding_root": finding_root,
            "latest_catalog_sequence": latest_sequence,
            "revision_count": revision_count,
            "revision_root": revision_root,
            "schema": f"persistra.catalog.{kind}_state",
            "terminal_batch_count": int(terminal_batch_count),
            "validation_attempt_count": validation_attempt_count,
            "validation_root": validation_root,
            "version": 1,
        }
    )
    return (
        latest_sequence,
        revision_count,
        int(terminal_batch_count),
        disposition_count,
        validation_attempt_count,
        finding_count,
        state_content_id,
    )


def _advance_registered_state(
    connection: ManagedConnection,
    *,
    dataset_id: Any,
    dataset_version: int,
    source_id: Any,
    source_version: int,
) -> None:
    for kind, entity_id, entity_version in (
        ("dataset", dataset_id, dataset_version),
        ("source", source_id, source_version),
    ):
        material = _registered_state_material(
            connection,
            kind=kind,
            entity_id=entity_id,
            entity_version=entity_version,
        )
        connection.execute(
            f"UPDATE catalog.{kind}_state SET latest_catalog_sequence = ?, "
            "revision_count = ?, terminal_batch_count = ?, disposition_count = ?, "
            "validation_attempt_count = ?, finding_count = ?, state_content_id = ? "
            f"WHERE {kind}_id = ? AND {kind}_version = ?",
            [*material[:-1], str(material[-1]), entity_id, entity_version],
        )


def verify_registered_state(connection: ManagedConnection) -> None:
    for kind in ("dataset", "source"):
        rows = connection.execute(
            f"SELECT {kind}_id, {kind}_version, latest_catalog_sequence, "
            "revision_count, terminal_batch_count, disposition_count, "
            "validation_attempt_count, finding_count, state_content_id "
            f"FROM catalog.{kind}_state ORDER BY {kind}_id, {kind}_version"
        ).fetchall()
        for row in rows:
            material = _registered_state_material(
                connection,
                kind=kind,
                entity_id=row[0],
                entity_version=int(row[1]),
            )
            expected = (*material[:-1], str(material[-1]))
            if tuple(row[2:]) != expected:
                raise CatalogDefinitionError(
                    f"registered {kind} state projection does not rebuild"
                )


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
            state_material = _registered_state_material(
                connection,
                kind="source",
                entity_id=source_id.value,
                entity_version=version,
            )
            connection.execute(
                "INSERT INTO catalog.source_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [source_id.value, version, *state_material[:-1], str(state_material[-1])],
            )
            _insert_event(
                connection,
                event_name="persistra.catalog.source_registered",
                aggregate_kind="persistra.aggregate.source",
                aggregate_id=source_id,
                aggregate_sequence=version,
                recorded_at=now,
                payload={"definition_content_id": content_id, "version": version},
            )
            return ResolvedSourceRef(source_id, version, content_id)

        return self._transaction("catalog.source.register", operation)

    def resolve(self, reference: SourceRef) -> ResolvedSourceRef:
        row = self._connection().execute(
            "SELECT s.source_id, v.definition_content_id FROM catalog.sources s "
            "JOIN catalog.source_versions v USING (source_id) "
            "WHERE s.qualified_name = ? AND v.source_version = ? AND v.enabled",
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
    def register(
        self, definition: DatasetDefinition, *, allow_reserved: bool = False
    ) -> ResolvedDatasetRef:
        """Idempotently register one dataset definition after resolving every source.

        Names under the reserved ``persistra.`` owner prefix belong to built-in
        canonical datasets installed by market migrations (spec 03 §6.2); a custom
        registration must use a nonreserved prefix unless ``allow_reserved`` is set
        by the built-in family installer.
        """
        if not allow_reserved and str(definition.name).startswith("persistra."):
            raise CatalogDefinitionError(
                "dataset name prefix 'persistra.' is reserved for built-in canonical datasets"
            )
        if not 1 <= definition.maximum_record_bytes <= 16 * 1024 * 1024:
            raise CatalogDefinitionError("dataset maximum record bytes is invalid")
        if not 1 <= definition.staging_chunk_rows <= 50_000:
            raise CatalogDefinitionError("dataset staging chunk size is invalid")
        if not definition.supported_sources or len(set(definition.supported_sources)) != len(
            definition.supported_sources
        ):
            raise CatalogDefinitionError(
                "dataset supported sources must be nonempty and unique"
            )
        if definition.retractions_allowed != (
            definition.retraction_schema_content_id is not None
        ):
            raise CatalogDefinitionError(
                "dataset retraction policy and schema must be consistent"
            )
        if str(definition.revision_policy).split(".")[-1] != "append_revision":
            raise CatalogDefinitionError("dataset revision policy is unsupported")
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
            state_material = _registered_state_material(
                connection,
                kind="dataset",
                entity_id=dataset_id.value,
                entity_version=version,
            )
            connection.execute(
                "INSERT INTO catalog.dataset_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [dataset_id.value, version, *state_material[:-1], str(state_material[-1])],
            )
            _insert_event(
                connection,
                event_name="persistra.catalog.dataset_registered",
                aggregate_kind="persistra.aggregate.dataset",
                aggregate_id=dataset_id,
                aggregate_sequence=version,
                recorded_at=now,
                payload={"definition_content_id": content_id, "version": version},
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
    def list(
        self,
        *,
        market: DatabaseName | None = None,
        batch_id: BatchId | None = None,
    ) -> tuple[QuarantinedRecord, ...]:
        """Return quarantined immutable staging records in stable order."""
        sql = (
            "SELECT quarantine_id, batch_id, submitted_record_id, reason_code, "
            "canonical_payload_json, quarantined_at, disposition_group_id "
            "FROM quality.quarantined_records"
        )
        parameters: list[Any] = []
        if batch_id is not None:
            sql += " WHERE batch_id = ?"
            parameters.append(batch_id.value)
        connection = (
            self._connection()
            if market is None
            else self._market_database(name=market).connection
        )
        rows = connection.execute(
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
                None if row[6] is None else DispositionGroupId.parse(row[6]),
            )
            for row in rows
        )

    def findings(
        self,
        quarantine_id: QuarantineId,
        *,
        market: DatabaseName | None = None,
    ) -> tuple[ValidationFinding, ...]:
        """Return immutable validation findings for one quarantined record."""
        connection = (
            self._connection()
            if market is None
            else self._market_database(name=market).connection
        )
        rows = connection.execute(
            "SELECT f.finding_id, f.batch_id, f.validation_attempt_id, "
            "f.submitted_record_id, f.severity, f.action, f.reason_code, "
            "f.evidence_content_id, f.recorded_at, f.disposition_group_id "
            "FROM quality.findings f "
            "JOIN quality.quarantined_records q "
            "ON q.submitted_record_id = f.submitted_record_id "
            "WHERE q.quarantine_id = ? ORDER BY f.recorded_at, f.finding_id",
            [quarantine_id.value],
        ).fetchall()
        return tuple(
            ValidationFinding(
                FindingId.parse(row[0]),
                BatchId.parse(row[1]),
                ValidationAttemptId.parse(row[2]),
                None if row[3] is None else SubmittedRecordId.parse(row[3]),
                row[4],
                row[5],
                row[6],
                ContentId.parse(row[7]),
                row[8],
                None if row[9] is None else DispositionGroupId.parse(row[9]),
            )
            for row in rows
        )

    def remediate(
        self,
        quarantine_id: QuarantineId,
        *,
        header: BatchHeader,
        records: Iterable[IngestionRecord],
        relationship: str = "corrects",
    ) -> BatchResult:
        """Submit an immutable child batch and link it to quarantined parent evidence."""
        if relationship not in {"corrects", "replaces", "supplements"}:
            raise CatalogDefinitionError("remediation relationship is unsupported")
        parent = self._connection().execute(
            "SELECT q.batch_id, q.submitted_record_id, b.dataset_id "
            "FROM quality.quarantined_records q "
            "JOIN catalog.batches b ON b.batch_id = q.batch_id "
            "WHERE q.quarantine_id = ?",
            [quarantine_id.value],
        ).fetchone()
        if parent is None:
            raise CatalogReferenceError("quarantine record is unavailable")
        child_dataset = DatasetRegistry(self._project).resolve(header.dataset)
        if child_dataset.dataset_id.value != parent[2]:
            raise CatalogDefinitionError(
                "remediation child must use the quarantined parent dataset"
            )
        ingestion = IngestionService(self._project)
        attempts = self._connection().execute(
            "SELECT p.child_batch_id, b.current_status, b.submission_key, p.relationship, "
            "coalesce(sum(CASE WHEN d.disposition IN "
            "('accepted_new','accepted_revision','duplicate_ignored') THEN 1 ELSE 0 END), 0) "
            "FROM catalog.pending_remediations p "
            "JOIN catalog.batches b ON b.batch_id = p.child_batch_id "
            "LEFT JOIN catalog.record_dispositions d ON d.batch_id = b.batch_id "
            "WHERE p.parent_submitted_record_id = ? "
            "GROUP BY p.child_batch_id, b.current_status, b.submission_key, "
            "p.relationship, p.recorded_at "
            "ORDER BY p.recorded_at",
            [parent[1]],
        ).fetchall()
        if attempts:
            (
                _child_batch_id,
                status_text,
                submission_key,
                stored_relationship,
                accepted_count,
            ) = attempts[-1]
            status = BatchStatus(status_text)
            if status not in {
                BatchStatus.ABORTED,
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
                BatchStatus.QUARANTINED,
                BatchStatus.REJECTED,
            }:
                if submission_key != header.submission_key:
                    raise CatalogDefinitionError(
                        "pending remediation must resume with its original submission key"
                    )
                if stored_relationship != relationship:
                    raise CatalogDefinitionError(
                        "pending remediation must resume with its original relationship"
                    )
                return ingestion.submit(header, records)
            if int(accepted_count) > 0 and relationship != "supplements":
                raise CatalogDefinitionError("quarantined record already has a remediation")
        handle = ingestion.begin(
            header,
            parent_batch_id=BatchId.parse(parent[0]),
            parent_submitted_record_id=SubmittedRecordId.parse(parent[1]),
            remediation_relationship=relationship,
        )
        ingestion.stage(handle.batch_id, records)
        validation = ingestion.validate(handle.batch_id)
        return ingestion.commit(
            handle.batch_id,
            validation_token=validation.token,
        )

    def remediation_history(
        self,
        quarantine_id: QuarantineId,
        *,
        market: DatabaseName | None = None,
    ) -> RemediationHistory:
        connection = (
            self._connection()
            if market is None
            else self._market_database(name=market).connection
        )
        parent = connection.execute(
            "SELECT submitted_record_id FROM quality.quarantined_records "
            "WHERE quarantine_id = ?",
            [quarantine_id.value],
        ).fetchone()
        if parent is None:
            raise CatalogReferenceError("quarantine record is unavailable")
        rows = connection.execute(
            "SELECT p.child_batch_id, b.current_status, p.relationship, "
            "coalesce(sum(CASE WHEN d.disposition = 'accepted_new' THEN 1 ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN d.disposition = 'accepted_revision' THEN 1 ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN d.disposition = 'duplicate_ignored' THEN 1 ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN d.disposition = 'quarantined' THEN 1 ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN d.disposition = 'rejected' THEN 1 ELSE 0 END), 0) "
            "FROM catalog.pending_remediations p "
            "JOIN catalog.batches b ON b.batch_id = p.child_batch_id "
            "LEFT JOIN catalog.record_dispositions d ON d.batch_id = b.batch_id "
            "WHERE p.parent_submitted_record_id = ? "
            "GROUP BY p.child_batch_id, b.current_status, p.relationship, p.recorded_at "
            "ORDER BY p.recorded_at",
            [parent[0]],
        ).fetchall()
        attempts = tuple(
            RemediationAttempt(
                BatchId.parse(row[0]),
                BatchStatus(row[1]),
                row[2],
                int(row[3]),
                int(row[4]),
                int(row[5]),
                int(row[6]),
                int(row[7]),
            )
            for row in rows
        )
        if any(attempt.accepted_revision for attempt in attempts):
            state = "resolved_revision"
        elif any(attempt.accepted_new for attempt in attempts):
            state = "resolved_new"
        elif any(attempt.duplicate_ignored for attempt in attempts):
            state = "resolved_duplicate"
        elif len(attempts) > 1 and attempts[-1].relationship == "replaces":
            state = "superseded"
        elif attempts:
            state = "attempted"
        else:
            state = "open"
        return RemediationHistory(state, attempts)


def _record_material(record: IngestionRecord) -> tuple[ContentId, ContentId, bytes, bytes]:
    if not record.natural_key or len({item[0] for item in record.natural_key}) != len(
        record.natural_key
    ):
        raise CatalogDefinitionError("record natural key must have unique named fields")
    if record.revision_effect is RevisionEffect.UPSERT and not record.payload:
        raise CatalogDefinitionError("upsert record payload cannot be empty")
    retraction_fields = (
        record.retraction_target_revision_id,
        record.retraction_reason_code,
        record.retraction_evidence_content_id,
    )
    if record.revision_effect is RevisionEffect.RETRACT and any(
        value is None for value in retraction_fields
    ):
        raise CatalogDefinitionError(
            "retraction requires an exact target, reason, and evidence identity"
        )
    if record.revision_effect is RevisionEffect.UPSERT and any(
        value is not None for value in retraction_fields
    ):
        raise CatalogDefinitionError("upsert cannot carry retraction evidence")
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
            "retraction_evidence_content_id": record.retraction_evidence_content_id,
            "retraction_reason_code": record.retraction_reason_code,
            "retraction_target_revision_id": record.retraction_target_revision_id,
            "source_record_key": record.source_record_key,
            "source_revision_key": record.source_revision_key,
        }
    )
    return natural_id, source_id, natural, payload


def _revision_policy_reason(
    definition: DatasetDefinition, *, has_head: bool
) -> str | None:
    """Apply the registered initial linear-append revision policy."""
    policy_kind = str(definition.revision_policy).split(".")[-1]
    if policy_kind == "append_revision":
        return None
    return "ingestion.revision.policy_unsupported" if has_head else None


def _batch_digest_header(
    *,
    adapter: ComponentRef,
    source_id: SourceId,
    source_version: int,
    dataset_id: DatasetId,
    dataset_version: int,
) -> Any:
    digest = hashlib.sha256()
    digest.update(b"persistra.ingestion.batch@1\0")
    digest.update(
        canonical_bytes(
            {
                "adapter": adapter,
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "source_id": source_id,
                "source_version": source_version,
            }
        )
    )
    return digest


def _contextual_source_content_id(
    record: IngestionRecord,
    *,
    source_id: SourceId,
    source_version: int,
    dataset_id: DatasetId,
    dataset_version: int,
) -> ContentId:
    return scoped_content_id(
        {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "record_content_id": _record_material(record)[1],
            "source_id": source_id,
            "source_version": source_version,
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

    def begin(
        self,
        header: BatchHeader,
        *,
        parent_batch_id: BatchId | None = None,
        parent_submitted_record_id: SubmittedRecordId | None = None,
        remediation_relationship: str | None = None,
    ) -> BatchHandle:
        if not header.submission_key or len(header.submission_key.encode()) > 512:
            raise CatalogDefinitionError("submission key is required and bounded")
        source = SourceRegistry(self._project).resolve(header.source)
        dataset = DatasetRegistry(self._project).resolve(header.dataset)
        source_definition = SourceRegistry(self._project).get(source)
        dataset_definition = DatasetRegistry(self._project).get(dataset)
        if header.source not in dataset_definition.supported_sources:
            raise CatalogDefinitionError("source is not supported by the dataset version")
        if header.adapter != source_definition.adapter_contract:
            raise CatalogDefinitionError("batch adapter does not match the source contract")
        remediation_fields = (
            parent_batch_id,
            parent_submitted_record_id,
            remediation_relationship,
        )
        if any(value is not None for value in remediation_fields) and any(
            value is None for value in remediation_fields
        ):
            raise CatalogDefinitionError("remediation lineage must be declared completely")

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
                "submission_key, adapter_name, adapter_version, current_status, created_at, "
                "expected_batch_content_id, parent_batch_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    None
                    if header.expected_batch_content_id is None
                    else str(header.expected_batch_content_id),
                    None if parent_batch_id is None else parent_batch_id.value,
                ],
            )
            if parent_batch_id is not None:
                assert parent_submitted_record_id is not None
                assert remediation_relationship is not None
                connection.execute(
                    "INSERT INTO catalog.pending_remediations VALUES (?, ?, ?, ?, ?)",
                    [
                        batch_id.value,
                        parent_batch_id.value,
                        parent_submitted_record_id.value,
                        remediation_relationship,
                        now,
                    ],
                )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 1, NULL, ?, ?, ?)",
                [batch_id.value, BatchStatus.CREATED.value, "ingestion.batch.created", now],
            )
            _insert_event(
                connection,
                event_name="persistra.ingestion.batch_created",
                aggregate_kind="persistra.aggregate.batch",
                aggregate_id=batch_id,
                aggregate_sequence=1,
                recorded_at=now,
                payload={"status": BatchStatus.CREATED.value},
            )
            return BatchHandle(batch_id, BatchStatus.CREATED)

        return self._transaction("ingestion.batch.begin", operation)

    def stage(
        self, batch_id: BatchId, records: Iterable[IngestionRecord]
    ) -> BatchHandle:
        iterator = iter(records)
        try:
            first = next(iterator)
        except StopIteration as error:
            raise CatalogDefinitionError("a batch must contain at least one record") from error

        def start(connection: ManagedConnection, now: datetime) -> tuple[Any, ...]:
            batch = connection.execute(
                "SELECT current_status, source_id, source_version, dataset_id, dataset_version, "
                "adapter_name, adapter_version, batch_content_id, expected_batch_content_id "
                "FROM catalog.batches "
                "WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            status = BatchStatus(batch[0])
            permitted = {
                BatchStatus.CREATED,
                BatchStatus.STAGING,
                BatchStatus.STAGED,
                BatchStatus.VALIDATED,
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
                BatchStatus.QUARANTINED,
            }
            if status not in permitted:
                raise BatchStateError("batch cannot accept or verify staged records")
            if status is BatchStatus.CREATED:
                connection.execute(
                    "UPDATE catalog.batches SET current_status = ? WHERE batch_id = ?",
                    [BatchStatus.STAGING.value, batch_id.value],
                )
                connection.execute(
                    "INSERT INTO catalog.batch_transitions VALUES (?, 2, ?, ?, ?, ?)",
                    [
                        batch_id.value,
                        BatchStatus.CREATED.value,
                        BatchStatus.STAGING.value,
                        "ingestion.batch.staging_started",
                        now,
                    ],
                )
                _insert_event(
                    connection,
                    event_name="persistra.ingestion.batch_staging_started",
                    aggregate_kind="persistra.aggregate.batch",
                    aggregate_id=batch_id,
                    aggregate_sequence=2,
                    recorded_at=now,
                    payload={"status": BatchStatus.STAGING.value},
                )
                status = BatchStatus.STAGING
            definition_json = connection.execute(
                "SELECT definition_json FROM catalog.dataset_versions "
                "WHERE dataset_id = ? AND dataset_version = ?",
                [batch[3], batch[4]],
            ).fetchone()[0]
            definition = _dataset_definition(definition_json)
            return (*batch[1:], status, definition)

        metadata = self._transaction("ingestion.batch.start_staging", start)
        source_id = SourceId.parse(metadata[0])
        source_version = int(metadata[1])
        dataset_id = DatasetId.parse(metadata[2])
        dataset_version = int(metadata[3])
        adapter = ComponentRef(QualifiedName(metadata[4]), metadata[5])
        sealed_content_id = metadata[6]
        expected_content_id = metadata[7]
        initial_status = cast("BatchStatus", metadata[8])
        definition = cast("DatasetDefinition", metadata[9])
        mutable = initial_status is BatchStatus.STAGING
        digest = _batch_digest_header(
            adapter=adapter,
            source_id=source_id,
            source_version=source_version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
        input_count = 0
        chunk: list[IngestionRecord] = [first]
        exhausted = False
        while not exhausted:
            while len(chunk) < definition.staging_chunk_rows:
                try:
                    chunk.append(next(iterator))
                except StopIteration:
                    exhausted = True
                    break

            prepared: list[tuple[IngestionRecord, ContentId, bytes, bytes]] = []
            for record in chunk:
                if len(canonical_bytes(record)) > definition.maximum_record_bytes:
                    raise CatalogDefinitionError("record exceeds dataset maximum bytes")
                natural_id, _, natural, payload = _record_material(record)
                source_content_id = _contextual_source_content_id(
                    record,
                    source_id=source_id,
                    source_version=source_version,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                )
                prepared.append((record, natural_id, natural, payload))
                digest.update(source_content_id.digest)
                digest.update(canonical_bytes(record.disposition_group_id))

            start_number = input_count + 1
            input_count += len(prepared)

            def write_chunk(
                connection: ManagedConnection,
                now: datetime,
                *,
                prepared_rows: tuple[
                    tuple[IngestionRecord, ContentId, bytes, bytes], ...
                ] = tuple(prepared),
                first_number: int = start_number,
                final_count: int = input_count,
            ) -> None:
                current = connection.execute(
                    "SELECT current_status, submitted_count FROM catalog.batches "
                    "WHERE batch_id = ?",
                    [batch_id.value],
                ).fetchone()
                if current is None:
                    raise CatalogReferenceError("batch is not registered")
                status = BatchStatus(current[0])
                if mutable and status is not BatchStatus.STAGING:
                    raise BatchStateError("staging ownership changed before chunk commit")
                stored = {
                    int(number): str(content_id)
                    for number, content_id in connection.execute(
                        "SELECT record_number, source_content_id FROM catalog.batch_records "
                        "WHERE batch_id = ? AND record_number BETWEEN ? AND ?",
                        [batch_id.value, first_number, final_count],
                    ).fetchall()
                }
                for offset, (record, natural_id, natural, payload) in enumerate(
                    prepared_rows
                ):
                    number = first_number + offset
                    source_content_id = _contextual_source_content_id(
                        record,
                        source_id=source_id,
                        source_version=source_version,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                    )
                    existing_content = stored.get(number)
                    if existing_content is not None:
                        if existing_content != str(source_content_id):
                            raise BatchConflictError(
                                "staging retry does not match the stored content prefix"
                            )
                        continue
                    if not mutable:
                        raise BatchConflictError(
                            "staged batch retry contains additional records"
                        )
                    connection.execute(
                        "INSERT INTO catalog.batch_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                        "?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            SubmittedRecordId.new().value,
                            batch_id.value,
                            number,
                            record.source_record_key,
                            record.source_revision_key,
                            record.revision_effect.value,
                            None
                            if record.retraction_target_revision_id is None
                            else record.retraction_target_revision_id.value,
                            record.retraction_reason_code,
                            None
                            if record.retraction_evidence_content_id is None
                            else str(record.retraction_evidence_content_id),
                            str(natural_id),
                            natural.decode(),
                            str(ContentId.from_bytes(payload)),
                            str(source_content_id),
                            payload.decode(),
                            record.event_at,
                            record.available_at,
                            now,
                            None
                            if record.disposition_group_id is None
                            else record.disposition_group_id.value,
                        ],
                    )
                if mutable:
                    connection.execute(
                        "UPDATE catalog.batches SET submitted_count = greatest("
                        "submitted_count, ?) WHERE batch_id = ?",
                        [final_count, batch_id.value],
                    )

            self._transaction("ingestion.batch.stage_chunk", write_chunk)
            chunk = []

        digest.update(input_count.to_bytes(8, "big", signed=False))
        batch_content = ContentId("sha256", digest.digest())

        def seal(connection: ManagedConnection, now: datetime) -> BatchHandle:
            batch = connection.execute(
                "SELECT current_status, submitted_count, batch_content_id "
                "FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            status = BatchStatus(batch[0])
            if int(batch[1]) != input_count:
                raise BatchConflictError("staging retry ended before the stored content prefix")
            if expected_content_id is not None and expected_content_id != str(batch_content):
                raise BatchConflictError("sealed batch content does not match the expected ID")
            if status is not BatchStatus.STAGING:
                if batch[2] != str(batch_content) or sealed_content_id != batch[2]:
                    raise BatchConflictError("staged batch content does not match exact retry")
                return BatchHandle(batch_id, status)
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, staged_at = ?, "
                "batch_content_id = ? WHERE batch_id = ?",
                [BatchStatus.STAGED.value, now, str(batch_content), batch_id.value],
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, 3, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    BatchStatus.STAGING.value,
                    BatchStatus.STAGED.value,
                    "ingestion.batch.staged",
                    now,
                ],
            )
            _insert_event(
                connection,
                event_name="persistra.ingestion.batch_staged",
                aggregate_kind="persistra.aggregate.batch",
                aggregate_id=batch_id,
                aggregate_sequence=3,
                recorded_at=now,
                payload={"batch_content_id": batch_content, "record_count": input_count},
            )
            return BatchHandle(batch_id, BatchStatus.STAGED)

        return self._transaction("ingestion.batch.seal", seal)

    def resume_staging(
        self, batch_id: BatchId, records: Iterable[IngestionRecord]
    ) -> BatchHandle:
        """Verify a stored prefix, append its missing suffix, and seal the batch."""
        if self.get(batch_id).status is not BatchStatus.STAGING:
            raise BatchStateError("only a staging batch can be resumed")
        return self.stage(batch_id, records)

    def abort_batch(self, batch_id: BatchId) -> BatchResult:
        """Abort a nonterminal batch and reject every already-staged record."""

        def operation(connection: ManagedConnection, now: datetime) -> BatchResult:
            batch = connection.execute(
                "SELECT current_status, batch_content_id, catalog_sequence, "
                "source_id, source_version, dataset_id, dataset_version "
                "FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            status = BatchStatus(batch[0])
            if status is BatchStatus.ABORTED:
                return self._result(connection, batch_id, status, int(batch[2]))
            if status in {
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
                BatchStatus.QUARANTINED,
                BatchStatus.REJECTED,
            }:
                raise BatchStateError("terminal batch cannot be aborted")
            transition_sequence = int(
                connection.execute(
                    "SELECT coalesce(max(transition_sequence), 0) + 1 "
                    "FROM catalog.batch_transitions WHERE batch_id = ?",
                    [batch_id.value],
                ).fetchone()[0]
            )
            content = (
                ContentId.parse(batch[1])
                if batch[1] is not None
                else scoped_content_id({"aborted_batch_id": batch_id})
            )
            catalog_sequence = _advance_catalog(
                connection,
                change_kind="batch.aborted",
                entity_id=batch_id,
                change_content_id=content,
                recorded_at=now,
            )
            records = connection.execute(
                "SELECT submitted_record_id FROM catalog.batch_records "
                "WHERE batch_id = ? ORDER BY record_number",
                [batch_id.value],
            ).fetchall()
            for (submitted_record_id,) in records:
                connection.execute(
                    "INSERT INTO catalog.record_dispositions VALUES "
                    "(?, ?, ?, ?, NULL, ?, ?)",
                    [
                        submitted_record_id,
                        batch_id.value,
                        RecordDisposition.REJECTED.value,
                        "ingestion.batch.aborted",
                        now,
                        connection.execute(
                            "SELECT disposition_group_id FROM catalog.batch_records "
                            "WHERE submitted_record_id = ?",
                            [submitted_record_id],
                        ).fetchone()[0],
                    ],
                )
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, terminal_at = ?, "
                "catalog_sequence = ? WHERE batch_id = ?",
                [BatchStatus.ABORTED.value, now, catalog_sequence, batch_id.value],
            )
            _advance_registered_state(
                connection,
                dataset_id=batch[5],
                dataset_version=int(batch[6]),
                source_id=batch[3],
                source_version=int(batch[4]),
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    transition_sequence,
                    status.value,
                    BatchStatus.ABORTED.value,
                    "ingestion.batch.aborted",
                    now,
                ],
            )
            _insert_event(
                connection,
                event_name="persistra.ingestion.batch_aborted",
                aggregate_kind="persistra.aggregate.batch",
                aggregate_id=batch_id,
                aggregate_sequence=transition_sequence,
                recorded_at=now,
                payload={"rejected_count": len(records)},
            )
            return self._result(
                connection, batch_id, BatchStatus.ABORTED, catalog_sequence
            )

        return self._transaction("ingestion.batch.abort", operation)

    def validate(self, batch_id: BatchId) -> ValidationResult:
        def operation(connection: ManagedConnection, now: datetime) -> ValidationResult:
            batch = connection.execute(
                "SELECT current_status, batch_content_id, validation_attempt_id "
                ", source_id, dataset_id, dataset_version "
                "FROM catalog.batches WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None or BatchStatus(batch[0]) not in {
                BatchStatus.STAGED,
                BatchStatus.VALIDATED,
            }:
                raise BatchStateError("only staged or stale validated batches can be validated")
            prior_status = BatchStatus(batch[0])
            if prior_status is BatchStatus.VALIDATED and batch[2] is not None:
                prior_attempt_id = ValidationAttemptId.parse(batch[2])
                connection.execute(
                    "UPDATE catalog.validation_attempts SET current_status = 'stale' "
                    "WHERE validation_attempt_id = ?",
                    [batch[2]],
                )
                connection.execute(
                    "INSERT INTO catalog.validation_attempt_transitions "
                    "VALUES (?, 3, 'completed', 'stale', ?)",
                    [batch[2], now],
                )
                _insert_event(
                    connection,
                    event_name="persistra.ingestion.validation_attempt_stale",
                    aggregate_kind="persistra.aggregate.validation_attempt",
                    aggregate_id=prior_attempt_id,
                    aggregate_sequence=3,
                    recorded_at=now,
                    payload={"batch_id": batch_id},
                )
            dataset_definition = _dataset_definition(
                connection.execute(
                    "SELECT definition_json FROM catalog.dataset_versions "
                    "WHERE dataset_id = ? AND dataset_version = ?",
                    [batch[4], batch[5]],
                ).fetchone()[0]
            )
            validation_findings: list[tuple[SubmittedRecordId, str]] = []
            invalid_records: set[SubmittedRecordId] = set()
            validation_records = connection.execute(
                "SELECT submitted_record_id, revision_effect, "
                "retraction_target_revision_id, natural_key_content_id, "
                "source_revision_key, source_content_id, event_at, available_at, "
                "disposition_group_id, retraction_reason_code "
                "FROM catalog.batch_records WHERE batch_id = ? ORDER BY record_number",
                [batch_id.value],
            ).fetchall()
            revision_key_groups: dict[str, list[tuple[SubmittedRecordId, str]]] = {}
            disposition_groups: dict[str, list[tuple[Any, ...]]] = {}
            group_by_record: dict[SubmittedRecordId, str | None] = {}
            advanced_natural_keys: set[str] = set()
            seen_source_content: set[str] = set()
            for record in validation_records:
                submitted_record_id = SubmittedRecordId.parse(record[0])
                group_by_record[submitted_record_id] = (
                    None if record[8] is None else str(record[8])
                )
                if record[8] is not None:
                    disposition_groups.setdefault(str(record[8]), []).append(record)
                if record[4] is not None:
                    revision_key_groups.setdefault(record[4], []).append(
                        (submitted_record_id, record[5])
                    )
                if record[5] in seen_source_content:
                    continue
                seen_source_content.add(record[5])
                reason: str | None = None
                if record[6] is not None and record[7] < record[6]:
                    reason = "ingestion.availability.before_event"
                head = connection.execute(
                    "SELECT canonical_revision_id, revision_effect "
                    "FROM catalog.canonical_revisions "
                    "WHERE dataset_id = ? AND source_id = ? AND natural_key_content_id = ? "
                    "ORDER BY revision_ordinal DESC LIMIT 1",
                    [batch[4], batch[3], record[3]],
                ).fetchone()
                if record[1] == RevisionEffect.RETRACT.value:
                    if not dataset_definition.retractions_allowed:
                        reason = "ingestion.retraction.not_allowed"
                    elif head is None:
                        reason = "ingestion.retraction.target_not_found"
                    elif (
                        record[2] != head[0]
                        or head[1] == RevisionEffect.RETRACT.value
                        or record[3] in advanced_natural_keys
                    ):
                        reason = "ingestion.retraction.target_not_head"
                    elif (
                        str(record[9]).endswith(".natural_key_correction")
                        and record[8] is None
                    ):
                        reason = "ingestion.retraction.replacement_incomplete"
                if record[4] is not None:
                    revision_conflict = connection.execute(
                        "SELECT source_content_id FROM catalog.canonical_revisions "
                        "WHERE dataset_id = ? AND source_id = ? "
                        "AND source_revision_key = ? LIMIT 1",
                        [batch[4], batch[3], record[4]],
                    ).fetchone()
                    if revision_conflict is not None and revision_conflict[0] != record[5]:
                        reason = "ingestion.revision_key.conflict"
                if reason is None:
                    reason = _revision_policy_reason(
                        dataset_definition, has_head=head is not None
                    )
                if reason is not None:
                    validation_findings.append((submitted_record_id, reason))
                    invalid_records.add(submitted_record_id)
                else:
                    duplicate = connection.execute(
                        "SELECT 1 FROM catalog.canonical_revisions "
                        "WHERE source_content_id = ?",
                        [record[5]],
                    ).fetchone()
                    if duplicate is None:
                        advanced_natural_keys.add(record[3])
            for members in disposition_groups.values():
                correction_retractions = [
                    record
                    for record in members
                    if record[1] == RevisionEffect.RETRACT.value
                    and str(record[9]).endswith(".natural_key_correction")
                ]
                if correction_retractions:
                    upserts = [
                        record
                        for record in members
                        if record[1] == RevisionEffect.UPSERT.value
                    ]
                    complete = (
                        len(members) == 2
                        and len(correction_retractions) == 1
                        and len(upserts) == 1
                        and correction_retractions[0][3] != upserts[0][3]
                    )
                    if not complete:
                        for record in members:
                            submitted_record_id = SubmittedRecordId.parse(record[0])
                            finding = (
                                submitted_record_id,
                                "ingestion.retraction.replacement_incomplete",
                            )
                            if finding not in validation_findings:
                                validation_findings.append(finding)
                            invalid_records.add(submitted_record_id)
            for members in revision_key_groups.values():
                if len({content_id for _, content_id in members}) <= 1:
                    continue
                for submitted_record_id, _ in members:
                    finding = (
                        submitted_record_id,
                        "ingestion.revision_key.conflict",
                    )
                    if finding not in validation_findings:
                        validation_findings.append(finding)
                    invalid_records.add(submitted_record_id)
            for members in disposition_groups.values():
                if not any(
                    SubmittedRecordId.parse(record[0]) in invalid_records
                    for record in members
                ):
                    continue
                for record in members:
                    submitted_record_id = SubmittedRecordId.parse(record[0])
                    if submitted_record_id in invalid_records:
                        continue
                    validation_findings.append(
                        (
                            submitted_record_id,
                            "ingestion.disposition_group.atomic_quarantine",
                        )
                    )
                    invalid_records.add(submitted_record_id)
            validation_findings.sort(key=lambda finding: finding[0].value.int)
            invalid = len(invalid_records)
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
                    "findings": tuple(validation_findings),
                    "quarantined_count": invalid,
                    "validation_attempt_id": attempt,
                }
            )
            attempt_number = int(
                connection.execute(
                    "SELECT count(*) + 1 FROM catalog.validation_attempts WHERE batch_id = ?",
                    [batch_id.value],
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT INTO catalog.validation_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    attempt.value,
                    batch_id.value,
                    attempt_number,
                    catalog_sequence,
                    str(token),
                    "completed",
                    now,
                    now,
                ],
            )
            connection.execute(
                "INSERT INTO catalog.validation_attempt_transitions VALUES "
                "(?, 1, NULL, 'running', ?), (?, 2, 'running', 'completed', ?)",
                [attempt.value, now, attempt.value, now],
            )
            _insert_event(
                connection,
                event_name="persistra.ingestion.validation_attempt_started",
                aggregate_kind="persistra.aggregate.validation_attempt",
                aggregate_id=attempt,
                aggregate_sequence=1,
                recorded_at=now,
                payload={"attempt_number": attempt_number, "batch_id": batch_id},
            )
            _insert_event(
                connection,
                event_name="persistra.ingestion.validation_attempt_completed",
                aggregate_kind="persistra.aggregate.validation_attempt",
                aggregate_id=attempt,
                aggregate_sequence=2,
                recorded_at=now,
                payload={"token": token},
            )
            for submitted_record_id, reason in validation_findings:
                evidence = scoped_content_id(
                    {
                        "reason_code": reason,
                        "submitted_record_id": submitted_record_id,
                    }
                )
                connection.execute(
                    "INSERT INTO quality.findings VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        FindingId.new().value,
                        batch_id.value,
                        attempt.value,
                        submitted_record_id.value,
                        "error",
                        "quarantine_record",
                        reason,
                        str(evidence),
                        now,
                        group_by_record[submitted_record_id],
                    ],
                )
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, validated_at = ?, "
                "validation_token_content_id = ?, validation_input_catalog_sequence = ?, "
                "validation_attempt_id = ? WHERE batch_id = ?",
                [
                    BatchStatus.VALIDATED.value,
                    now,
                    str(token),
                    catalog_sequence,
                    attempt.value,
                    batch_id.value,
                ],
            )
            if prior_status is BatchStatus.STAGED:
                transition_sequence = int(
                    connection.execute(
                        "SELECT coalesce(max(transition_sequence), 0) + 1 "
                        "FROM catalog.batch_transitions WHERE batch_id = ?",
                        [batch_id.value],
                    ).fetchone()[0]
                )
                connection.execute(
                    "INSERT INTO catalog.batch_transitions VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        batch_id.value,
                        transition_sequence,
                        BatchStatus.STAGED.value,
                        BatchStatus.VALIDATED.value,
                        "ingestion.batch.validated",
                        now,
                    ],
                )
                _insert_event(
                    connection,
                    event_name="persistra.ingestion.batch_validated",
                    aggregate_kind="persistra.aggregate.batch",
                    aggregate_id=batch_id,
                    aggregate_sequence=transition_sequence,
                    recorded_at=now,
                    payload={"quarantined_count": invalid, "token": token},
                )
            proposed = (
                BatchStatus.QUARANTINED
                if invalid == len(validation_records)
                else BatchStatus.COMMITTED_WITH_QUARANTINE
                if invalid > 0
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
        def operation(
            connection: ManagedConnection, now: datetime
        ) -> BatchResult | None:
            batch = connection.execute(
                "SELECT current_status, validation_token_content_id, "
                "validation_input_catalog_sequence, batch_content_id, "
                "source_id, source_version, dataset_id, dataset_version, submitted_count, "
                "catalog_sequence, validation_attempt_id FROM catalog.batches "
                "WHERE batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if batch is None:
                raise CatalogReferenceError("batch is not registered")
            status = BatchStatus(batch[0])
            if status in {
                BatchStatus.COMMITTED,
                BatchStatus.COMMITTED_WITH_QUARANTINE,
                BatchStatus.QUARANTINED,
            }:
                return self._result(connection, batch_id, status, int(batch[9]))
            if status is not BatchStatus.VALIDATED:
                raise BatchStateError("only validated batches can be committed")
            if batch[1] != str(validation_token):
                raise ValidationTokenError("validation token does not match the batch")
            current_catalog_sequence = int(
                connection.execute(
                    "SELECT current_sequence FROM catalog.catalog_clock"
                ).fetchone()[0]
            )
            if current_catalog_sequence != int(batch[2]):
                attempt_id = ValidationAttemptId.parse(batch[10])
                transition_sequence = int(
                    connection.execute(
                        "SELECT coalesce(max(transition_sequence), 0) + 1 "
                        "FROM catalog.batch_transitions WHERE batch_id = ?",
                        [batch_id.value],
                    ).fetchone()[0]
                )
                connection.execute(
                    "UPDATE catalog.validation_attempts SET current_status = 'stale' "
                    "WHERE validation_attempt_id = ?",
                    [batch[10]],
                )
                connection.execute(
                    "INSERT INTO catalog.validation_attempt_transitions "
                    "VALUES (?, 3, 'completed', 'stale', ?)",
                    [batch[10], now],
                )
                connection.execute(
                    "UPDATE catalog.batches SET current_status = ?, validated_at = NULL, "
                    "validation_token_content_id = NULL, "
                    "validation_input_catalog_sequence = NULL, validation_attempt_id = NULL "
                    "WHERE batch_id = ?",
                    [BatchStatus.STAGED.value, batch_id.value],
                )
                connection.execute(
                    "INSERT INTO catalog.batch_transitions VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        batch_id.value,
                        transition_sequence,
                        BatchStatus.VALIDATED.value,
                        BatchStatus.STAGED.value,
                        "ingestion.validation.catalog_changed",
                        now,
                    ],
                )
                _insert_event(
                    connection,
                    event_name="persistra.ingestion.validation_attempt_stale",
                    aggregate_kind="persistra.aggregate.validation_attempt",
                    aggregate_id=attempt_id,
                    aggregate_sequence=3,
                    recorded_at=now,
                    payload={"batch_id": batch_id},
                )
                _insert_event(
                    connection,
                    event_name="persistra.ingestion.batch_validation_invalidated",
                    aggregate_kind="persistra.aggregate.batch",
                    aggregate_id=batch_id,
                    aggregate_sequence=transition_sequence,
                    recorded_at=now,
                    payload={"reason": "catalog_changed"},
                )
                return None
            sequence = _advance_catalog(
                connection,
                change_kind="batch.committed",
                entity_id=batch_id,
                change_content_id=ContentId.parse(batch[3]),
                recorded_at=now,
            )
            dataset_definition = _dataset_definition(
                connection.execute(
                    "SELECT definition_json FROM catalog.dataset_versions "
                    "WHERE dataset_id = ? AND dataset_version = ?",
                    [batch[6], batch[7]],
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
                "revision_effect, retraction_target_revision_id, retraction_reason_code, "
                "retraction_evidence_content_id, natural_key_content_id, natural_key_json, "
                "payload_content_id, source_content_id, canonical_payload_json, event_at, "
                "available_at, ingested_at, disposition_group_id "
                "FROM catalog.batch_records WHERE batch_id = ? ORDER BY record_number",
                [batch_id.value],
            ).fetchall()
            validation_reasons = {
                str(submitted_record_id): str(reason_code)
                for submitted_record_id, reason_code in connection.execute(
                    "SELECT submitted_record_id, reason_code FROM quality.findings "
                    "WHERE validation_attempt_id = ? AND action = 'quarantine_record' "
                    "ORDER BY submitted_record_id, finding_id",
                    [batch[10]],
                ).fetchall()
            }
            for record in records:
                disposition = RecordDisposition.REJECTED
                revision_id: CanonicalRevisionId | None = None
                reason = "ingestion.record.rejected"
                known_reason = validation_reasons.get(str(record[0]))
                duplicate: Any = None
                if known_reason is not None:
                    disposition = RecordDisposition.QUARANTINED
                    revision_id = None
                    reason = known_reason
                    connection.execute(
                        "INSERT INTO quality.quarantined_records VALUES "
                        "(?, ?, ?, ?, ?, ?, ?)",
                        [
                            QuarantineId.new().value,
                            record[0],
                            batch_id.value,
                            reason,
                            record[11],
                            now,
                            record[15],
                        ],
                    )
                else:
                    duplicate = connection.execute(
                        "SELECT canonical_revision_id FROM catalog.canonical_revisions "
                        "WHERE source_content_id = ?",
                        [record[10]],
                    ).fetchone()
                if known_reason is None and duplicate is not None:
                    disposition = RecordDisposition.DUPLICATE_IGNORED
                    revision_id = CanonicalRevisionId.parse(duplicate[0])
                    reason = "ingestion.record.duplicate"
                elif known_reason is None:
                    head = connection.execute(
                        "SELECT canonical_revision_id, revision_ordinal "
                        "FROM catalog.canonical_revisions WHERE dataset_id = ? "
                        "AND source_id = ? AND natural_key_content_id = ? "
                        "ORDER BY revision_ordinal DESC LIMIT 1",
                        [batch[6], batch[4], record[7]],
                    ).fetchone()
                    revision_key_conflict = None
                    if record[2] is not None:
                        revision_key_conflict = connection.execute(
                            "SELECT source_content_id FROM catalog.canonical_revisions "
                            "WHERE dataset_id = ? AND source_id = ? "
                            "AND source_revision_key = ? LIMIT 1",
                            [batch[6], batch[4], record[2]],
                        ).fetchone()
                    invalid_time = record[12] is not None and record[13] < record[12]
                    invalid_retraction = record[3] == RevisionEffect.RETRACT.value and (
                        not dataset_definition.retractions_allowed
                        or head is None
                        or record[4] != head[0]
                    )
                    invalid_revision_key = (
                        revision_key_conflict is not None
                        and revision_key_conflict[0] != record[10]
                    )
                    if invalid_time or invalid_retraction or invalid_revision_key:
                        disposition = RecordDisposition.QUARANTINED
                        revision_id = None
                        reason = (
                            "ingestion.availability.before_event"
                            if invalid_time
                            else (
                                "ingestion.retraction.target_not_head"
                                if invalid_retraction
                                else "ingestion.revision_key.conflict"
                            )
                        )
                        connection.execute(
                            "INSERT INTO quality.quarantined_records VALUES "
                            "(?, ?, ?, ?, ?, ?, ?)",
                            [
                                QuarantineId.new().value,
                                record[0],
                                batch_id.value,
                                reason,
                                record[11],
                                now,
                                record[15],
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
                                batch[6],
                                batch[7],
                                batch[4],
                                record[7],
                                record[8],
                                ordinal,
                                None if head is None else head[0],
                                record[1],
                                record[2],
                                record[3],
                                record[9],
                                record[10],
                                record[11],
                                batch_id.value,
                                record[0],
                                record[12],
                                record[13],
                                record[14],
                                sequence,
                            ],
                        )
                        if record[3] == RevisionEffect.RETRACT.value:
                            connection.execute(
                                "INSERT INTO catalog.canonical_retractions "
                                "VALUES (?, ?, ?, ?)",
                                [
                                    revision_id.value,
                                    record[4],
                                    record[5],
                                    record[6],
                                ],
                            )
                counts[disposition] += 1
                connection.execute(
                    "INSERT INTO catalog.record_dispositions VALUES "
                    "(?, ?, ?, ?, ?, ?, ?)",
                    [
                        record[0],
                        batch_id.value,
                        disposition.value,
                        reason,
                        None if revision_id is None else revision_id.value,
                        now,
                        record[15],
                    ],
                )
            pending_remediation = connection.execute(
                "SELECT parent_batch_id, parent_submitted_record_id, relationship "
                "FROM catalog.pending_remediations WHERE child_batch_id = ?",
                [batch_id.value],
            ).fetchone()
            if pending_remediation is not None:
                for record in records:
                    remediation_id = RemediationId.new()
                    connection.execute(
                        "INSERT INTO quality.remediation_links VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            remediation_id.value,
                            pending_remediation[0],
                            pending_remediation[1],
                            batch_id.value,
                            record[0],
                            pending_remediation[2],
                            now,
                        ],
                    )
                    _insert_event(
                        connection,
                        event_name="persistra.ingestion.remediation_linked",
                        aggregate_kind="persistra.aggregate.remediation",
                        aggregate_id=remediation_id,
                        aggregate_sequence=1,
                        recorded_at=now,
                        payload={
                            "child_batch_id": batch_id,
                            "parent_batch_id": BatchId.parse(pending_remediation[0]),
                            "relationship": pending_remediation[2],
                        },
                    )
            accepted_count = sum(
                counts[item]
                for item in (
                    RecordDisposition.ACCEPTED_NEW,
                    RecordDisposition.ACCEPTED_REVISION,
                    RecordDisposition.DUPLICATE_IGNORED,
                )
            )
            if counts[RecordDisposition.QUARANTINED] and accepted_count == 0:
                final_status = BatchStatus.QUARANTINED
            elif counts[RecordDisposition.QUARANTINED]:
                final_status = BatchStatus.COMMITTED_WITH_QUARANTINE
            else:
                final_status = BatchStatus.COMMITTED
            connection.execute(
                "UPDATE catalog.batches SET current_status = ?, terminal_at = ?, "
                "catalog_sequence = ? WHERE batch_id = ?",
                [final_status.value, now, sequence, batch_id.value],
            )
            _advance_registered_state(
                connection,
                dataset_id=batch[6],
                dataset_version=int(batch[7]),
                source_id=batch[4],
                source_version=int(batch[5]),
            )
            transition_sequence = int(
                connection.execute(
                    "SELECT coalesce(max(transition_sequence), 0) + 1 "
                    "FROM catalog.batch_transitions WHERE batch_id = ?",
                    [batch_id.value],
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT INTO catalog.batch_transitions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    batch_id.value,
                    transition_sequence,
                    BatchStatus.VALIDATED.value,
                    final_status.value,
                    "ingestion.batch.committed",
                    now,
                ],
            )
            _insert_event(
                connection,
                event_name=(
                    "persistra.ingestion.batch_quarantined"
                    if final_status is BatchStatus.QUARANTINED
                    else "persistra.ingestion.batch_committed"
                ),
                aggregate_kind="persistra.aggregate.batch",
                aggregate_id=batch_id,
                aggregate_sequence=transition_sequence,
                recorded_at=now,
                payload={"catalog_sequence": sequence, "status": final_status.value},
            )
            return BatchResult(
                batch_id,
                final_status,
                sequence,
                BatchCounts(
                    int(batch[8]),
                    counts[RecordDisposition.ACCEPTED_NEW],
                    counts[RecordDisposition.ACCEPTED_REVISION],
                    counts[RecordDisposition.DUPLICATE_IGNORED],
                    counts[RecordDisposition.QUARANTINED],
                    0,
                ),
            )

        result = self._transaction("ingestion.batch.commit", operation)
        if result is None:
            raise ValidationTokenError(
                "catalog changed after validation; validate the batch again"
            )
        if create_snapshot:
            try:
                snapshot = SnapshotService(self._project).create()
            except Exception as error:
                return BatchResult(
                    result.batch_id,
                    result.status,
                    result.catalog_sequence,
                    result.counts,
                    snapshot_failure=SnapshotFailure(
                        "snapshot.create_failed",
                        type(error).__name__,
                        str(error),
                    ),
                )
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
        source = SourceRegistry(self._project).resolve(header.source)
        dataset = DatasetRegistry(self._project).resolve(header.dataset)
        existing = self._connection().execute(
            "SELECT batch_id, current_status, catalog_sequence, batch_content_id "
            "FROM catalog.batches WHERE source_id = ? AND dataset_id = ? AND submission_key = ?",
            [source.source_id.value, dataset.dataset_id.value, header.submission_key],
        ).fetchone()
        handle = (
            self.begin(header)
            if existing is None
            else BatchHandle(BatchId.parse(existing[0]), BatchStatus(existing[1]))
        )
        if (
            existing is not None
            and header.expected_batch_content_id is not None
            and existing[3] != str(header.expected_batch_content_id)
        ):
            raise BatchConflictError("submission retry content expectation does not match")
        staged = self.stage(handle.batch_id, records)
        if staged.status in {
            BatchStatus.COMMITTED,
            BatchStatus.COMMITTED_WITH_QUARANTINE,
            BatchStatus.QUARANTINED,
        }:
            assert existing is not None
            return self._result(
                self._connection(), handle.batch_id, staged.status, int(existing[2])
            )
        if staged.status is BatchStatus.VALIDATED:
            token_row = self._connection().execute(
                "SELECT validation_token_content_id FROM catalog.batches WHERE batch_id = ?",
                [handle.batch_id.value],
            ).fetchone()
            if token_row is None or token_row[0] is None:
                raise BatchStateError("validated batch has no validation token")
            token = ContentId.parse(token_row[0])
        else:
            validation = self.validate(handle.batch_id)
            token = validation.token
        return self.commit(
            handle.batch_id,
            validation_token=token,
            create_snapshot=create_snapshot,
        )


def _query_root(
    connection: ManagedConnection,
    schema: str,
    sql: str,
    parameters: list[Any],
) -> ContentId:
    digest = hashlib.sha256()
    digest.update(schema.encode("ascii"))
    cursor = connection.execute(sql, parameters)
    count = 0
    while rows := cursor.fetchmany(1_000):
        for row in rows:
            normalized = tuple(str(value) if isinstance(value, UUID) else value for value in row)
            encoded = canonical_bytes(normalized)
            digest.update(len(encoded).to_bytes(8, "big", signed=False))
            digest.update(encoded)
            count += 1
    digest.update(count.to_bytes(8, "big", signed=False))
    return ContentId("sha256", digest.digest())


def _catalog_chain_at(connection: ManagedConnection, sequence: int) -> str:
    from persistra.market import BarSpecId, CorporateActionId
    from persistra.reference import (
        CalendarId,
        ClassificationAssignmentId,
        ClassificationNodeId,
        ClassificationSchemeId,
        IdentifierAssignmentId,
        IdentifierNamespaceId,
        InstrumentId,
    )

    prior = str(scoped_content_id({"schema": "persistra.catalog.genesis", "version": 1}))
    rows = connection.execute(
        "SELECT catalog_sequence, change_kind, change_entity_id, change_content_id, "
        "prior_chain_content_id, chain_content_id FROM catalog.changes "
        "WHERE catalog_sequence <= ? ORDER BY catalog_sequence",
        [sequence],
    ).fetchall()
    if [int(row[0]) for row in rows] != list(range(1, sequence + 1)):
        raise CatalogDefinitionError("catalog change history is not gap-free")
    identity_types = {
        "batch.aborted": BatchId,
        "batch.committed": BatchId,
        "dataset.registered": DatasetId,
        "source.registered": SourceId,
        "reference.instrument_registered": InstrumentId,
        "reference.identifier_namespace_registered": IdentifierNamespaceId,
        "reference.identifier_assigned": IdentifierAssignmentId,
        "reference.calendar_registered": CalendarId,
        "reference.classification_scheme_registered": ClassificationSchemeId,
        "reference.classification_node_added": ClassificationNodeId,
        "reference.classification_assigned": ClassificationAssignmentId,
        "reference.universe_membership_ingested": InstrumentId,
        "market.bar_spec_registered": BarSpecId,
        "market.bar_ingested": InstrumentId,
        "market.trading_status_ingested": InstrumentId,
        "market.corporate_action_ingested": CorporateActionId,
    }
    for number, kind, entity_value, content_value, stored_prior, stored_chain in rows:
        identity_type = identity_types.get(str(kind))
        if identity_type is None:
            raise CatalogDefinitionError("catalog change kind is unsupported")
        expected = scoped_content_id(
            {
                "schema": "persistra.catalog.change_chain",
                "version": 1,
                "catalog_sequence": int(number),
                "change_content_id": ContentId.parse(content_value),
                "change_entity_id": identity_type.parse(entity_value),
                "change_kind": str(kind),
                "prior_chain_content_id": prior,
            }
        )
        if stored_prior != prior or stored_chain != str(expected):
            raise CatalogDefinitionError("catalog change chain does not rebuild")
        prior = str(expected)
    return prior


def _snapshot_material(
    connection: ManagedConnection,
    *,
    snapshot_id: MarketSnapshotId,
    database_id: EntityId,
    sequence: int,
    chain: str,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    dataset_definitions = connection.execute(
        "SELECT dataset_id, dataset_version, definition_content_id, definition_json "
        "FROM catalog.dataset_versions WHERE catalog_sequence <= ? "
        "ORDER BY dataset_id, dataset_version",
        [sequence],
    ).fetchall()
    source_definitions = connection.execute(
        "SELECT source_id, source_version, definition_content_id, definition_json "
        "FROM catalog.source_versions WHERE catalog_sequence <= ? "
        "ORDER BY source_id, source_version",
        [sequence],
    ).fetchall()
    dataset_states: list[dict[str, Any]] = []
    for dataset_id, dataset_version, definition_content_id, definition_json in dataset_definitions:
        if str(scoped_content_id(_dataset_definition(definition_json))) != definition_content_id:
            raise CatalogDefinitionError("dataset definition content does not rebuild")
        revision_count, latest_revision = connection.execute(
            "SELECT count(*), coalesce(max(catalog_sequence), 0) "
            "FROM catalog.canonical_revisions WHERE dataset_id = ? "
            "AND dataset_version = ? AND catalog_sequence <= ?",
            [dataset_id, dataset_version, sequence],
        ).fetchone()
        terminal_count = connection.execute(
            "SELECT count(*) FROM catalog.batches WHERE dataset_id = ? "
            "AND dataset_version = ? AND catalog_sequence <= ?",
            [dataset_id, dataset_version, sequence],
        ).fetchone()[0]
        state: dict[str, Any] = {
            "dataset_id": DatasetId.parse(dataset_id),
            "dataset_version": int(dataset_version),
            "latest_catalog_sequence": int(latest_revision),
            "revision_count": int(revision_count),
            "terminal_batch_count": int(terminal_count),
        }
        evidence_roots = {
            "batch_root": _query_root(
                connection,
                "persistra.snapshot.dataset_batches@1",
                "SELECT batch_id, batch_content_id, current_status, submitted_count, "
                "catalog_sequence FROM catalog.batches WHERE dataset_id = ? "
                "AND dataset_version = ? AND catalog_sequence <= ? ORDER BY catalog_sequence",
                [dataset_id, dataset_version, sequence],
            ),
            "disposition_root": _query_root(
                connection,
                "persistra.snapshot.dataset_dispositions@1",
                "SELECT d.submitted_record_id, d.disposition, d.primary_reason_code, "
                "d.canonical_revision_id, d.disposition_group_id "
                "FROM catalog.record_dispositions d "
                "JOIN catalog.batches b ON b.batch_id = d.batch_id WHERE b.dataset_id = ? "
                "AND b.dataset_version = ? AND b.catalog_sequence <= ? "
                "ORDER BY b.catalog_sequence, d.submitted_record_id",
                [dataset_id, dataset_version, sequence],
            ),
            "finding_root": _query_root(
                connection,
                "persistra.snapshot.dataset_findings@1",
                "SELECT f.finding_id, f.submitted_record_id, f.severity, f.action, "
                "f.reason_code, f.evidence_content_id, f.disposition_group_id "
                "FROM quality.findings f "
                "JOIN catalog.batches b ON b.batch_id = f.batch_id WHERE b.dataset_id = ? "
                "AND b.dataset_version = ? AND b.catalog_sequence <= ? "
                "ORDER BY b.catalog_sequence, f.finding_id",
                [dataset_id, dataset_version, sequence],
            ),
            "revision_root": _query_root(
                connection,
                "persistra.snapshot.dataset_revisions@1",
                "SELECT canonical_revision_id, source_id, natural_key_content_id, "
                "natural_key_json, revision_ordinal, supersedes_revision_id, revision_effect, "
                "payload_content_id, source_content_id, canonical_payload_json, event_at, "
                "available_at, ingested_at, catalog_sequence "
                "FROM catalog.canonical_revisions WHERE dataset_id = ? "
                "AND dataset_version = ? AND catalog_sequence <= ? "
                "ORDER BY catalog_sequence, canonical_revision_id",
                [dataset_id, dataset_version, sequence],
            ),
            "retraction_root": _query_root(
                connection,
                "persistra.snapshot.dataset_retractions@1",
                "SELECT r.canonical_revision_id, r.retracted_revision_id, "
                "r.retraction_reason_code, r.evidence_content_id "
                "FROM catalog.canonical_retractions r "
                "JOIN catalog.canonical_revisions v "
                "ON v.canonical_revision_id = r.canonical_revision_id "
                "WHERE v.dataset_id = ? AND v.dataset_version = ? "
                "AND v.catalog_sequence <= ? ORDER BY r.canonical_revision_id",
                [dataset_id, dataset_version, sequence],
            ),
            "validation_root": _query_root(
                connection,
                "persistra.snapshot.dataset_validation@1",
                "SELECT a.validation_attempt_id, a.attempt_number, "
                "a.input_catalog_sequence, a.validation_token_content_id, "
                "a.current_status FROM catalog.validation_attempts a "
                "JOIN catalog.batches b ON b.batch_id = a.batch_id "
                "WHERE b.dataset_id = ? AND b.dataset_version = ? "
                "AND b.catalog_sequence <= ? "
                "ORDER BY b.catalog_sequence, a.attempt_number",
                [dataset_id, dataset_version, sequence],
            ),
        }
        state["state_content_id"] = scoped_content_id(
            {
                "schema": "persistra.snapshot.dataset_state",
                "version": 1,
                **state,
                **evidence_roots,
            }
        )
        dataset_states.append(state)
    source_states: list[dict[str, Any]] = []
    for source_id, source_version, definition_content_id, definition_json in source_definitions:
        if str(scoped_content_id(_source_definition(definition_json))) != definition_content_id:
            raise CatalogDefinitionError("source definition content does not rebuild")
        terminal_count, latest = connection.execute(
            "SELECT count(*), coalesce(max(catalog_sequence), 0) FROM catalog.batches "
            "WHERE source_id = ? AND source_version = ? AND catalog_sequence <= ?",
            [source_id, source_version, sequence],
        ).fetchone()
        state = cast("dict[str, Any]", {
            "latest_catalog_sequence": int(latest),
            "source_id": SourceId.parse(source_id),
            "source_version": int(source_version),
            "terminal_batch_count": int(terminal_count),
        })
        evidence_roots = {
            "batch_root": _query_root(
                connection,
                "persistra.snapshot.source_batches@1",
                "SELECT batch_id, batch_content_id, current_status, submitted_count, "
                "catalog_sequence FROM catalog.batches WHERE source_id = ? "
                "AND source_version = ? AND catalog_sequence <= ? ORDER BY catalog_sequence",
                [source_id, source_version, sequence],
            ),
            "revision_root": _query_root(
                connection,
                "persistra.snapshot.source_revisions@1",
                "SELECT r.canonical_revision_id, r.dataset_id, r.dataset_version, "
                "r.natural_key_content_id, r.revision_ordinal, r.revision_effect, "
                "r.payload_content_id, r.source_content_id, r.canonical_payload_json, "
                "r.available_at, r.ingested_at, r.catalog_sequence "
                "FROM catalog.canonical_revisions r JOIN catalog.batches b "
                "ON b.batch_id = r.batch_id WHERE b.source_id = ? "
                "AND b.source_version = ? AND r.catalog_sequence <= ? "
                "ORDER BY r.catalog_sequence, r.canonical_revision_id",
                [source_id, source_version, sequence],
            ),
        }
        state["state_content_id"] = scoped_content_id(
            {
                "schema": "persistra.snapshot.source_state",
                "version": 1,
                **state,
                **evidence_roots,
            }
        )
        source_states.append(state)
    created_by_version, database_schema_version = connection.execute(
        "SELECT created_by_version, schema_version FROM _persistra.database_info"
    ).fetchone()
    manifest = {
        "catalog_chain_content_id": chain,
        "catalog_sequence": sequence,
        "created_by_version": created_by_version,
        "database_id": database_id,
        "database_schema_version": int(database_schema_version),
        "dataset_definitions": tuple(
            {
                "dataset_id": DatasetId.parse(item[0]),
                "dataset_version": int(item[1]),
                "definition_content_id": ContentId.parse(item[2]),
            }
            for item in dataset_definitions
        ),
        "dataset_states": tuple(dataset_states),
        "manifest_schema": "persistra.snapshot.market_manifest@1",
        "snapshot_id": snapshot_id,
        "source_definitions": tuple(
            {
                "source_id": SourceId.parse(item[0]),
                "source_version": int(item[1]),
                "definition_content_id": ContentId.parse(item[2]),
            }
            for item in source_definitions
        ),
        "source_states": tuple(source_states),
    }
    return manifest, tuple(dataset_states), tuple(source_states)


def verify_snapshot_integrity(
    connection: ManagedConnection, snapshot: SnapshotRef
) -> None:
    """Rebuild and verify one snapshot manifest and every normalized state row."""
    verify_registered_state(connection)
    row = connection.execute(
        "SELECT catalog_chain_content_id, manifest_content_id, manifest_json "
        "FROM snapshots.market_snapshots WHERE market_snapshot_id = ? "
        "AND database_id = ? AND catalog_sequence = ?",
        [
            snapshot.snapshot_id.value,
            snapshot.database_id.value,
            snapshot.catalog_sequence,
        ],
    ).fetchone()
    if row is None or row[1] != str(snapshot.manifest_content_id):
        raise CatalogReferenceError("snapshot reference is not committed")
    rebuilt_chain = _catalog_chain_at(connection, snapshot.catalog_sequence)
    if row[0] != rebuilt_chain:
        raise CatalogDefinitionError("snapshot catalog chain does not rebuild")
    manifest, dataset_states, source_states = _snapshot_material(
        connection,
        snapshot_id=snapshot.snapshot_id,
        database_id=snapshot.database_id,
        sequence=snapshot.catalog_sequence,
        chain=rebuilt_chain,
    )
    encoded = canonical_bytes(manifest)
    if row[1] != str(ContentId.from_bytes(encoded)) or row[2] != encoded.decode():
        raise CatalogDefinitionError("stored market snapshot manifest does not rebuild")
    stored_dataset_states = connection.execute(
        "SELECT dataset_id, dataset_version, revision_count, terminal_batch_count, "
        "latest_catalog_sequence, state_content_id FROM snapshots.snapshot_dataset_state "
        "WHERE market_snapshot_id = ? ORDER BY dataset_id, dataset_version",
        [snapshot.snapshot_id.value],
    ).fetchall()
    expected_dataset_states = [
        (
            state["dataset_id"].value,
            state["dataset_version"],
            state["revision_count"],
            state["terminal_batch_count"],
            state["latest_catalog_sequence"],
            str(state["state_content_id"]),
        )
        for state in dataset_states
    ]
    stored_source_states = connection.execute(
        "SELECT source_id, source_version, terminal_batch_count, "
        "latest_catalog_sequence, state_content_id FROM snapshots.snapshot_source_state "
        "WHERE market_snapshot_id = ? ORDER BY source_id, source_version",
        [snapshot.snapshot_id.value],
    ).fetchall()
    expected_source_states = [
        (
            state["source_id"].value,
            state["source_version"],
            state["terminal_batch_count"],
            state["latest_catalog_sequence"],
            str(state["state_content_id"]),
        )
        for state in source_states
    ]
    states_match = (
        stored_dataset_states == expected_dataset_states
        and stored_source_states == expected_source_states
    )
    if not states_match:
        raise CatalogDefinitionError("stored market snapshot state does not rebuild")


class SnapshotService(_OwnedService):
    def create(self) -> SnapshotRef:
        def operation(connection: ManagedConnection, now: datetime) -> SnapshotRef:
            sequence, chain = connection.execute(
                "SELECT current_sequence, chain_content_id FROM catalog.catalog_clock"
            ).fetchone()
            if chain != _catalog_chain_at(connection, int(sequence)):
                raise CatalogDefinitionError("catalog clock chain does not rebuild")
            opened = self._market_database()
            existing = connection.execute(
                "SELECT market_snapshot_id, manifest_content_id, manifest_json "
                "FROM snapshots.market_snapshots "
                "WHERE database_id = ? AND catalog_sequence = ?",
                [opened.metadata.database_id.value, sequence],
            ).fetchone()
            if existing is not None:
                existing_id = MarketSnapshotId.parse(existing[0])
                manifest, _, _ = _snapshot_material(
                    connection,
                    snapshot_id=existing_id,
                    database_id=opened.metadata.database_id,
                    sequence=int(sequence),
                    chain=chain,
                )
                encoded = canonical_bytes(manifest)
                if (
                    existing[1] != str(ContentId.from_bytes(encoded))
                    or existing[2] != encoded.decode()
                ):
                    raise CatalogDefinitionError(
                        "stored market snapshot manifest does not rebuild"
                    )
                reference = SnapshotRef(
                    opened.metadata.database_id,
                    existing_id,
                    int(sequence),
                    ContentId.parse(existing[1]),
                )
                verify_snapshot_integrity(connection, reference)
                return reference
            snapshot_id = MarketSnapshotId.new()
            manifest, dataset_states, source_states = _snapshot_material(
                connection,
                snapshot_id=snapshot_id,
                database_id=opened.metadata.database_id,
                sequence=int(sequence),
                chain=chain,
            )
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
            for state in dataset_states:
                connection.execute(
                    "INSERT INTO snapshots.snapshot_dataset_state VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        snapshot_id.value,
                        state["dataset_id"].value,
                        state["dataset_version"],
                        state["revision_count"],
                        state["terminal_batch_count"],
                        state["latest_catalog_sequence"],
                        str(state["state_content_id"]),
                    ],
                )
            for state in source_states:
                connection.execute(
                    "INSERT INTO snapshots.snapshot_source_state VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        snapshot_id.value,
                        state["source_id"].value,
                        state["source_version"],
                        state["terminal_batch_count"],
                        state["latest_catalog_sequence"],
                        str(state["state_content_id"]),
                    ],
                )
            _insert_event(
                connection,
                event_name="persistra.snapshot.market_created",
                aggregate_kind="persistra.aggregate.market_snapshot",
                aggregate_id=snapshot_id,
                aggregate_sequence=1,
                recorded_at=now,
                payload={
                    "catalog_sequence": int(sequence),
                    "manifest_content_id": content_id,
                },
            )
            return SnapshotRef(
                opened.metadata.database_id, snapshot_id, int(sequence), content_id
            )

        return self._transaction("catalog.snapshot.create", operation)

    def latest(self, *, market: DatabaseName | None = None) -> SnapshotRef | None:
        opened = self._market_database(name=market)
        connection = opened.connection
        row = connection.execute(
            "SELECT market_snapshot_id, catalog_sequence, manifest_content_id "
            "FROM snapshots.market_snapshots WHERE database_id = ? "
            "ORDER BY catalog_sequence DESC LIMIT 1",
            [opened.metadata.database_id.value],
        ).fetchone()
        if row is None:
            return None
        reference = SnapshotRef(
            opened.metadata.database_id,
            MarketSnapshotId.parse(row[0]),
            int(row[1]),
            ContentId.parse(row[2]),
        )
        verify_snapshot_integrity(connection, reference)
        current_sequence = int(
            connection.execute(
                "SELECT current_sequence FROM catalog.catalog_clock"
            ).fetchone()[0]
        )
        if current_sequence > reference.catalog_sequence:
            return SnapshotRef(
                reference.database_id,
                reference.snapshot_id,
                reference.catalog_sequence,
                reference.manifest_content_id,
                ("snapshot.catalog_unpinned",),
            )
        return reference

    def get(
        self, snapshot_id: MarketSnapshotId, *, market: DatabaseName | None = None
    ) -> SnapshotRef:
        opened = self._market_database(name=market)
        connection = opened.connection
        row = connection.execute(
            "SELECT catalog_sequence, manifest_content_id FROM snapshots.market_snapshots "
            "WHERE database_id = ? AND market_snapshot_id = ?",
            [opened.metadata.database_id.value, snapshot_id.value],
        ).fetchone()
        if row is None:
            raise CatalogReferenceError("market snapshot is not committed")
        reference = SnapshotRef(
            opened.metadata.database_id,
            snapshot_id,
            int(row[0]),
            ContentId.parse(row[1]),
        )
        verify_snapshot_integrity(connection, reference)
        return reference

    def list(
        self, *, market: DatabaseName | None = None, limit: int = 100
    ) -> tuple[SnapshotRef, ...]:
        if not 1 <= limit <= 10_000:
            raise CatalogDefinitionError("snapshot list limit is invalid")
        opened = self._market_database(name=market)
        connection = opened.connection
        rows = connection.execute(
            "SELECT market_snapshot_id, catalog_sequence, manifest_content_id "
            "FROM snapshots.market_snapshots WHERE database_id = ? "
            "ORDER BY catalog_sequence DESC LIMIT ?",
            [opened.metadata.database_id.value, limit],
        ).fetchall()
        references = tuple(
            SnapshotRef(
                opened.metadata.database_id,
                MarketSnapshotId.parse(row[0]),
                int(row[1]),
                ContentId.parse(row[2]),
            )
            for row in rows
        )
        for reference in references:
            verify_snapshot_integrity(connection, reference)
        return references

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
            committed = opened.connection.execute(
                "SELECT 1 FROM snapshots.market_snapshots WHERE market_snapshot_id = ? "
                "AND database_id = ? AND catalog_sequence = ? AND manifest_content_id = ?",
                [
                    snapshot.snapshot_id.value,
                    snapshot.database_id.value,
                    snapshot.catalog_sequence,
                    str(snapshot.manifest_content_id),
                ],
            ).fetchone()
            if committed is None:
                raise CatalogReferenceError(
                    "composite snapshot member is not committed in its market database"
                )
            verify_snapshot_integrity(opened.connection, snapshot)
            normalized.append(
                CompositeSnapshotMember(
                    name,
                    snapshot.database_id,
                    snapshot.snapshot_id,
                    snapshot.manifest_content_id,
                    None
                    if opened.copy_verification is None
                    else opened.copy_verification.copy_id,
                    snapshot.warnings,
                )
            )
        immutable_members = tuple(normalized)
        manifest = {
            "manifest_schema": "persistra.snapshot.composite_manifest@1",
            "members": immutable_members,
            "project_id": self._project._config.project_id,  # pyright: ignore[reportPrivateUsage]
        }
        encoded = canonical_bytes(manifest)
        content_id = ContentId.from_bytes(encoded)

        def operation(_context: object) -> CompositeSnapshotRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
            qualified = f'"{database_name.replace(chr(34), chr(34) * 2)}"."research"'
            existing = connection.execute(
                f"SELECT composite_snapshot_id, manifest_json FROM "
                f"{qualified}.composite_snapshots "
                "WHERE manifest_content_id = ?",
                [str(content_id)],
            ).fetchone()
            if existing is not None:
                stored_members = connection.execute(
                    f"SELECT database_name, database_id, market_snapshot_id, "
                    f"market_manifest_content_id, verified_copy_id FROM "
                    f"{qualified}.composite_snapshot_members "
                    "WHERE composite_snapshot_id = ? ORDER BY database_name",
                    [existing[0]],
                ).fetchall()
                expected_members = [
                    (
                        member.database_name.value,
                        member.database_id.value,
                        member.market_snapshot_id.value,
                        str(member.market_manifest_content_id),
                        None
                        if member.verified_copy_id is None
                        else member.verified_copy_id.value,
                    )
                    for member in immutable_members
                ]
                if existing[1] != encoded.decode() or stored_members != expected_members:
                    raise CatalogDefinitionError(
                        "stored composite snapshot manifest does not rebuild"
                    )
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
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        snapshot_id.value,
                        member.database_name.value,
                        member.database_id.value,
                        member.market_snapshot_id.value,
                        str(member.market_manifest_content_id),
                        None
                        if member.verified_copy_id is None
                        else member.verified_copy_id.value,
                    ],
                )
            _insert_event(
                connection,
                event_name="persistra.snapshot.composite_created",
                aggregate_kind="persistra.aggregate.composite_snapshot",
                aggregate_id=snapshot_id,
                aggregate_sequence=1,
                recorded_at=now,
                payload={"manifest_content_id": content_id},
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
    ) -> SnapshotSelection:
        public_cutoff = validate_instant(public_cutoff)
        project_cutoff = validate_instant(project_cutoff)
        opened = self._market_database(database_id=snapshot.database_id)
        connection = opened.connection
        if opened.metadata.database_id != snapshot.database_id:
            raise CatalogReferenceError("snapshot belongs to a different market database")
        verify_snapshot_integrity(connection, snapshot)
        datasets = DatasetRegistry(self._project, connection=connection)
        sources = SourceRegistry(self._project, connection=connection)
        resolved = datasets.resolve(dataset)
        definition = datasets.get(resolved)
        source_priority = {
            sources.resolve(reference).source_id: number
            for number, reference in enumerate(definition.supported_sources)
        }
        rows = connection.execute(
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
        observations = tuple(
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
            if RevisionEffect(row[4]) is not RevisionEffect.RETRACT
        )
        audits = tuple(
            SelectionAudit(
                _fields(json.loads(row[2])),
                (
                    "retracted"
                    if RevisionEffect(row[4]) is RevisionEffect.RETRACT
                    else "available"
                ),
                CanonicalRevisionId.parse(row[0]),
                SourceId.parse(row[1]),
            )
            for _, row in sorted(winners.items())
        )
        return SnapshotSelection(observations, audits)
