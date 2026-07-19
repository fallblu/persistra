"""Project-owned reference and calendar services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog import CompositeSnapshotRef, SnapshotRef
from persistra.catalog.services import advance_catalog, insert_event
from persistra.db import DatabaseRole, ProjectMode
from persistra.domain import ContentId, EntityId
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CalendarCoverageError,
    CalendarReferenceError,
    CapabilityUnavailableError,
    ReferenceDefinitionError,
    ReferenceResolutionError,
)
from persistra.reference.models import (
    AsOfContext,
    CalendarDay,
    CalendarDefinition,
    CalendarId,
    CalendarRef,
    ClassificationAssignment,
    ClassificationAssignmentId,
    ClassificationNode,
    ClassificationNodeId,
    ClassificationSchemeDefinition,
    ClassificationSchemeId,
    DecisionInstant,
    EntityKind,
    IdentifierAssignment,
    IdentifierAssignmentId,
    IdentifierNamespaceDefinition,
    IdentifierNamespaceId,
    IdentifierResolution,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    NonSession,
    ResolvedCalendarRef,
    ResolvedClassificationScheme,
    ResolvedIdentifierNamespace,
    SecurityId,
    Session,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
    UniverseMembership,
    VenueId,
)

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


def market_for_context(
    project: Project, context: AsOfContext
) -> tuple[Any, int]:
    project._guard()  # pyright: ignore[reportPrivateUsage]
    markets = [
        item
        for item in project._databases  # pyright: ignore[reportPrivateUsage]
        if item.metadata.role is DatabaseRole.MARKET
    ]
    if isinstance(context.snapshot, SnapshotRef):
        matches = [
            item
            for item in markets
            if item.metadata.database_id == context.snapshot.database_id
        ]
        snapshot_id = context.snapshot.snapshot_id
        sequence = context.snapshot.catalog_sequence
    else:
        assert isinstance(context.snapshot, CompositeSnapshotRef)
        members = [
            member
            for member in context.snapshot.members
            if member.database_name.value == context.market_database
        ]
        if len(members) != 1:
            raise ReferenceResolutionError(
                "composite snapshot has no matching market member"
            )
        matches = [
            item
            for item in markets
            if item.metadata.database_id == members[0].database_id
        ]
        snapshot_id = members[0].market_snapshot_id
        sequence = -1
    if len(matches) != 1:
        raise ReferenceResolutionError("snapshot database is not open in this project")
    opened = matches[0]
    row = opened.connection.execute(
        "SELECT catalog_sequence FROM snapshots.market_snapshots "
        "WHERE market_snapshot_id = ? AND database_id = ?",
        [snapshot_id.value, opened.metadata.database_id.value],
    ).fetchone()
    if row is None or (sequence >= 0 and int(row[0]) != sequence):
        raise ReferenceResolutionError("snapshot is not committed or does not match")
    return opened, int(row[0])


def cutoff_sql(context: AsOfContext) -> tuple[str, list[Any]]:
    sql = "available_at <= ?"
    parameters: list[Any] = [context.public_cutoff_at]
    if context.project_cutoff_at is not None:
        sql += " AND ingested_at <= ?"
        parameters.append(context.project_cutoff_at)
    return sql, parameters


class ReferenceService:
    """Reference identity and point-in-time query entry point."""

    __slots__ = ("_project", "calendars", "classifications", "identifiers", "memberships")

    def __init__(self, project: Project) -> None:
        self._project = project
        self.calendars = CalendarService(project)
        self.classifications = ClassificationService(project)
        self.identifiers = IdentifierService(project)
        self.memberships = MembershipService(project)

    def register_instrument(self, definition: InstrumentDefinition) -> InstrumentId:
        """Atomically allocate an immutable issuer-to-instrument identity chain."""
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "instrument registration requires market_write mode"
            )
        material = canonical_bytes(definition)
        content_id = ContentId.from_bytes(material)

        def operation(context: TransactionContext) -> InstrumentId:
            recorded_at = context.recorded_at
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT content_id FROM canonical.instrument_observations "
                "WHERE instrument_id = ?",
                [definition.instrument_id.value],
            ).fetchone()
            if existing is not None:
                if existing[0] != str(content_id):
                    raise ReferenceDefinitionError(
                        "instrument identity already has different terms"
                    )
                return definition.instrument_id
            sequence = advance_catalog(
                connection,
                change_kind="reference.instrument_registered",
                entity_id=definition.instrument_id,
                change_content_id=content_id,
                recorded_at=recorded_at,
            )
            rows: tuple[tuple[str, str, str, list[Any]], ...] = (
                (
                    "canonical.issuers",
                    "issuer_id",
                    "INSERT INTO canonical.issuers VALUES (?, ?, ?)",
                    [definition.issuer_id.value, sequence, recorded_at],
                ),
                (
                    "canonical.securities",
                    "security_id",
                    "INSERT INTO canonical.securities VALUES (?, ?, ?, ?)",
                    [
                        definition.security_id.value,
                        definition.issuer_id.value,
                        sequence,
                        recorded_at,
                    ],
                ),
                (
                    "canonical.venues",
                    "venue_id",
                    "INSERT INTO canonical.venues VALUES (?, ?, ?, ?, ?)",
                    [
                        definition.venue_id.value,
                        definition.mic,
                        definition.timezone_name,
                        sequence,
                        recorded_at,
                    ],
                ),
                (
                    "canonical.listings",
                    "listing_id",
                    "INSERT INTO canonical.listings VALUES (?, ?, ?, ?, ?)",
                    [
                        definition.listing_id.value,
                        definition.security_id.value,
                        definition.venue_id.value,
                        sequence,
                        recorded_at,
                    ],
                ),
                (
                    "canonical.instruments",
                    "instrument_id",
                    "INSERT INTO canonical.instruments VALUES (?, ?, ?, ?)",
                    [
                        definition.instrument_id.value,
                        definition.listing_id.value,
                        sequence,
                        recorded_at,
                    ],
                ),
            )
            for table, id_column, statement, parameters in rows:
                key = parameters[0]
                present = connection.execute(
                    f"SELECT 1 FROM {table} WHERE {id_column} = ?",
                    [key],
                ).fetchone()
                if present is None:
                    connection.execute(statement, parameters)
            connection.execute(
                "INSERT INTO canonical.instrument_observations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    UUID(bytes=content_id.digest[:16]),
                    definition.instrument_id.value,
                    definition.security_kind.value,
                    definition.security_status.value,
                    definition.listing_status.value,
                    definition.currency,
                    definition.valid_from,
                    definition.valid_to,
                    definition.available_at or recorded_at,
                    recorded_at,
                    sequence,
                    str(content_id),
                    None if definition.asset_class is None else definition.asset_class.value,
                    definition.base_currency,
                    definition.quote_currency,
                ],
            )
            insert_event(
                connection,
                event_name="persistra.reference.instrument_registered",
                aggregate_kind="persistra.aggregate.instrument",
                aggregate_id=definition.instrument_id,
                aggregate_sequence=1,
                recorded_at=recorded_at,
                payload={"content_id": content_id, "instrument_id": definition.instrument_id},
            )
            return definition.instrument_id

        return self._project.services.transactions.run("reference_register_instrument", operation)

    def instruments(
        self,
        *,
        context: AsOfContext,
        instrument_ids: tuple[InstrumentId, ...] = (),
        max_rows: int = 1_000_000,
    ) -> pd.DataFrame:
        """Return one selected effective row per instrument under exact cutoffs."""
        if max_rows < 1:
            raise ReferenceDefinitionError("max_rows must be positive")
        opened, sequence = market_for_context(self._project, context)
        cutoff_clause, parameters = cutoff_sql(context)
        identifiers = [item.value for item in instrument_ids]
        id_sql = ""
        if identifiers:
            id_sql = " AND i.instrument_id IN (SELECT unnest(?))"
            parameters.append(identifiers)
        parameters.extend(
            [
                context.effective_at,
                context.effective_at,
                sequence,
                max_rows + 1,
            ]
        )
        rows = opened.connection.execute(
            "SELECT i.instrument_id, l.listing_id, s.security_id, s.issuer_id, "
            "v.venue_id, v.mic, o.security_kind, o.security_status, o.listing_status, "
            "o.currency, o.asset_class, o.base_currency, o.quote_currency, "
            "o.valid_from, o.valid_to, o.available_at, o.catalog_sequence "
            "FROM canonical.instruments i "
            "JOIN canonical.listings l ON l.listing_id = i.listing_id "
            "JOIN canonical.securities s ON s.security_id = l.security_id "
            "JOIN canonical.venues v ON v.venue_id = l.venue_id "
            "JOIN canonical.instrument_observations o ON o.instrument_id = i.instrument_id "
            f"WHERE {cutoff_clause}{id_sql} AND o.valid_from <= ? "
            "AND (o.valid_to IS NULL OR ? < o.valid_to) AND o.catalog_sequence <= ? "
            "QUALIFY row_number() OVER (PARTITION BY i.instrument_id "
            "ORDER BY o.catalog_sequence DESC) = 1 ORDER BY i.instrument_id LIMIT ?",
            parameters,
        ).fetchall()
        if len(rows) > max_rows:
            raise ReferenceDefinitionError("instrument query exceeds max_rows")
        columns = [
            "instrument_id",
            "listing_id",
            "security_id",
            "issuer_id",
            "venue_id",
            "mic",
            "security_kind",
            "security_status",
            "listing_status",
            "currency",
            "asset_class",
            "base_currency",
            "quote_currency",
            "valid_from",
            "valid_to",
            "available_at",
            "catalog_sequence",
        ]
        frame = pd.DataFrame(rows, columns=columns)
        for column in columns[:5]:
            frame[column] = frame[column].astype("string")
        for column in ("valid_from", "valid_to", "available_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        return frame


class IdentifierService:
    """Versioned identifier namespace, assignment, and resolution service."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: IdentifierNamespaceDefinition
    ) -> ResolvedIdentifierNamespace:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "identifier registration requires market_write mode"
            )
        content_id = scoped_content_id(
            {"schema": "persistra.reference.identifier_namespace", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedIdentifierNamespace:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT identifier_namespace_id, definition_content_id "
                "FROM canonical.identifier_namespaces "
                "WHERE qualified_name = ? AND namespace_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id):
                    raise ReferenceDefinitionError(
                        "identifier namespace version conflicts"
                    )
                return ResolvedIdentifierNamespace(
                    IdentifierNamespaceId.parse(existing[0]), definition.version, content_id
                )
            namespace_id = IdentifierNamespaceId.new()
            sequence = advance_catalog(
                connection,
                change_kind="reference.identifier_namespace_registered",
                entity_id=namespace_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.identifier_namespaces VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    namespace_id.value,
                    definition.version,
                    str(definition.name),
                    definition.kind.value,
                    definition.entity_kind.value,
                    definition.case_sensitive,
                    definition.venue_scoped,
                    str(content_id),
                    sequence,
                ],
            )
            return ResolvedIdentifierNamespace(namespace_id, definition.version, content_id)

        return self._project.services.transactions.run(
            "identifier_namespace_register", operation
        )

    def assign(self, assignment: IdentifierAssignment) -> IdentifierAssignmentId:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "identifier assignment requires market_write mode"
            )
        material = {
            "schema": "persistra.reference.identifier_assignment",
            "value": assignment,
        }
        content_id = scoped_content_id(material)

        def operation(context: TransactionContext) -> IdentifierAssignmentId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT identifier_assignment_id FROM canonical.identifier_assignments "
                "WHERE content_id = ?",
                [str(content_id)],
            ).fetchone()
            if existing is not None:
                return IdentifierAssignmentId.parse(existing[0])
            namespace = connection.execute(
                "SELECT case_sensitive, venue_scoped, entity_kind "
                "FROM canonical.identifier_namespaces "
                "WHERE identifier_namespace_id = ? AND namespace_version = ?",
                [assignment.namespace.namespace_id.value, assignment.namespace.version],
            ).fetchone()
            if namespace is None or namespace[2] != assignment.entity_kind.value:
                raise ReferenceDefinitionError("identifier namespace does not match assignment")
            if bool(namespace[1]) != (assignment.venue_id is not None):
                raise ReferenceDefinitionError("identifier venue scope does not match namespace")
            normalized = (
                assignment.raw_value
                if bool(namespace[0])
                else assignment.raw_value.upper()
            )
            assignment_id = IdentifierAssignmentId.new()
            sequence = advance_catalog(
                connection,
                change_kind="reference.identifier_assigned",
                entity_id=assignment_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.identifier_assignments VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    assignment_id.value,
                    assignment.namespace.namespace_id.value,
                    assignment.namespace.version,
                    assignment.raw_value,
                    normalized,
                    assignment.entity_kind.value,
                    assignment.entity_id.value,
                    None if assignment.venue_id is None else assignment.venue_id.value,
                    assignment.is_primary,
                    assignment.valid_from,
                    assignment.valid_to,
                    assignment.available_at or context.recorded_at,
                    context.recorded_at,
                    sequence,
                    str(content_id),
                ],
            )
            return assignment_id

        return self._project.services.transactions.run("identifier_assign", operation)

    def resolve(
        self,
        namespace: ResolvedIdentifierNamespace,
        value: str,
        *,
        entity_kind: EntityKind,
        context: AsOfContext,
        venue_id: Any | None = None,
    ) -> IdentifierResolution:
        opened, sequence = market_for_context(self._project, context)
        namespace_row = opened.connection.execute(
            "SELECT case_sensitive, venue_scoped FROM canonical.identifier_namespaces "
            "WHERE identifier_namespace_id = ? AND namespace_version = ? "
            "AND created_catalog_sequence <= ?",
            [namespace.namespace_id.value, namespace.version, sequence],
        ).fetchone()
        if namespace_row is None:
            raise ReferenceResolutionError("identifier namespace is not in the snapshot")
        normalized = value if bool(namespace_row[0]) else value.upper()
        cutoff_clause, parameters = cutoff_sql(context)
        parameters = [
            namespace.namespace_id.value,
            namespace.version,
            normalized,
            entity_kind.value,
            *parameters,
            context.effective_at,
            context.effective_at,
            sequence,
        ]
        venue_sql = " AND venue_id IS NULL"
        if venue_id is not None:
            venue_sql = " AND venue_id = ?"
            parameters.insert(4, venue_id.value)
        rows = opened.connection.execute(
            "SELECT identifier_assignment_id, entity_id FROM "
            "canonical.identifier_assignments WHERE namespace_id = ? "
            "AND namespace_version = ? AND normalized_value = ? AND entity_kind = ? "
            f"{venue_sql} AND {cutoff_clause} AND valid_from <= ? "
            "AND (valid_to IS NULL OR ? < valid_to) AND catalog_sequence <= ? "
            "ORDER BY entity_id, identifier_assignment_id",
            parameters,
        ).fetchall()
        entity_ids = sorted({row[1] for row in rows}, key=str)
        if not rows:
            return IdentifierResolution("not_found", None, None)
        assignments = tuple(IdentifierAssignmentId.parse(row[0]) for row in rows)
        if len(entity_ids) != 1:
            return IdentifierResolution("ambiguous", None, None, assignments)
        concrete = {
            EntityKind.ISSUER: IssuerId,
            EntityKind.SECURITY: SecurityId,
            EntityKind.VENUE: VenueId,
            EntityKind.LISTING: ListingId,
            EntityKind.INSTRUMENT: InstrumentId,
        }.get(entity_kind)
        assert concrete is not None
        return IdentifierResolution(
            "resolved", entity_kind, concrete.parse(entity_ids[0]), assignments
        )


class ClassificationService:
    """Versioned classification hierarchy and effective assignments."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: ClassificationSchemeDefinition
    ) -> ResolvedClassificationScheme:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "classification registration requires market_write mode"
            )
        content_id = scoped_content_id(
            {"schema": "persistra.reference.classification_scheme", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedClassificationScheme:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT classification_scheme_id, definition_content_id "
                "FROM canonical.classification_schemes WHERE qualified_name = ? "
                "AND scheme_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id):
                    raise ReferenceDefinitionError(
                        "classification scheme version conflicts"
                    )
                return ResolvedClassificationScheme(
                    ClassificationSchemeId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            scheme_id = ClassificationSchemeId.new()
            sequence = advance_catalog(
                connection,
                change_kind="reference.classification_scheme_registered",
                entity_id=scheme_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.classification_schemes VALUES "
                "(?, ?, ?, ?, ?, ?)",
                [
                    scheme_id.value,
                    definition.version,
                    str(definition.name),
                    definition.allows_multiple,
                    str(content_id),
                    sequence,
                ],
            )
            return ResolvedClassificationScheme(
                scheme_id, definition.version, content_id
            )

        return self._project.services.transactions.run(
            "classification_scheme_register", operation
        )

    def add_node(self, node: ClassificationNode) -> ClassificationNodeId:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "classification mutation requires market_write mode"
            )
        content_id = scoped_content_id(
            {"schema": "persistra.reference.classification_node", "value": node}
        )

        def operation(context: TransactionContext) -> ClassificationNodeId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT content_id FROM canonical.classification_nodes "
                "WHERE classification_node_id = ?",
                [node.classification_node_id.value],
            ).fetchone()
            if existing is not None:
                if existing[0] != str(content_id):
                    raise ReferenceDefinitionError("classification node identity conflicts")
                return node.classification_node_id
            scheme = connection.execute(
                "SELECT 1 FROM canonical.classification_schemes "
                "WHERE classification_scheme_id = ? AND scheme_version = ? "
                "AND definition_content_id = ?",
                [
                    node.scheme.classification_scheme_id.value,
                    node.scheme.version,
                    str(node.scheme.definition_content_id),
                ],
            ).fetchone()
            if scheme is None:
                raise ReferenceDefinitionError("classification scheme is not registered")
            if node.parent_node_id is not None:
                parent = connection.execute(
                    "SELECT 1 FROM canonical.classification_nodes "
                    "WHERE classification_node_id = ? AND classification_scheme_id = ?",
                    [
                        node.parent_node_id.value,
                        node.scheme.classification_scheme_id.value,
                    ],
                ).fetchone()
                if parent is None:
                    raise ReferenceDefinitionError("classification parent is not registered")
            sequence = advance_catalog(
                connection,
                change_kind="reference.classification_node_added",
                entity_id=node.classification_node_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.classification_nodes VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    node.classification_node_id.value,
                    node.scheme.classification_scheme_id.value,
                    node.scheme.version,
                    node.code,
                    node.display_name,
                    None if node.parent_node_id is None else node.parent_node_id.value,
                    node.valid_from,
                    node.valid_to,
                    node.available_at or context.recorded_at,
                    sequence,
                    str(content_id),
                ],
            )
            return node.classification_node_id

        return self._project.services.transactions.run("classification_node_add", operation)

    def assign(
        self, assignment: ClassificationAssignment
    ) -> ClassificationAssignmentId:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "classification mutation requires market_write mode"
            )
        content_id = scoped_content_id(
            {"schema": "persistra.reference.classification_assignment", "value": assignment}
        )

        def operation(context: TransactionContext) -> ClassificationAssignmentId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT content_id FROM canonical.classification_assignments "
                "WHERE classification_assignment_id = ?",
                [assignment.classification_assignment_id.value],
            ).fetchone()
            if existing is not None:
                if existing[0] != str(content_id):
                    raise ReferenceDefinitionError(
                        "classification assignment identity conflicts"
                    )
                return assignment.classification_assignment_id
            node = connection.execute(
                "SELECT 1 FROM canonical.classification_nodes "
                "WHERE classification_node_id = ? AND classification_scheme_id = ? "
                "AND scheme_version = ?",
                [
                    assignment.classification_node_id.value,
                    assignment.scheme.classification_scheme_id.value,
                    assignment.scheme.version,
                ],
            ).fetchone()
            if node is None:
                raise ReferenceDefinitionError("classification node is not registered")
            sequence = advance_catalog(
                connection,
                change_kind="reference.classification_assigned",
                entity_id=assignment.classification_assignment_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.classification_assignments VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    assignment.classification_assignment_id.value,
                    assignment.scheme.classification_scheme_id.value,
                    assignment.scheme.version,
                    assignment.entity_kind.value,
                    assignment.entity_id.value,
                    assignment.classification_node_id.value,
                    assignment.valid_from,
                    assignment.valid_to,
                    assignment.available_at or context.recorded_at,
                    sequence,
                    str(content_id),
                ],
            )
            return assignment.classification_assignment_id

        return self._project.services.transactions.run("classification_assign", operation)

    def query(self, *, context: AsOfContext, entity_id: EntityId) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, context)
        rows = opened.connection.execute(
            "SELECT a.classification_assignment_id, s.qualified_name, s.scheme_version, "
            "a.entity_kind, a.entity_id, n.classification_node_id, n.code, "
            "n.display_name, n.parent_node_id, a.valid_from, a.valid_to, a.available_at "
            "FROM canonical.classification_assignments a "
            "JOIN canonical.classification_schemes s USING "
            "(classification_scheme_id, scheme_version) "
            "JOIN canonical.classification_nodes n USING (classification_node_id) "
            "WHERE a.entity_id = ? AND a.valid_from <= ? "
            "AND (a.valid_to IS NULL OR ? < a.valid_to) AND a.available_at <= ? "
            "AND a.catalog_sequence <= ? ORDER BY s.qualified_name, n.code",
            [
                entity_id.value,
                context.effective_at,
                context.effective_at,
                context.public_cutoff_at,
                sequence,
            ],
        ).fetchall()
        columns = [
            "classification_assignment_id",
            "scheme_name",
            "scheme_version",
            "entity_kind",
            "entity_id",
            "classification_node_id",
            "code",
            "display_name",
            "parent_node_id",
            "valid_from",
            "valid_to",
            "available_at",
        ]
        frame = pd.DataFrame(rows, columns=columns)
        for column in (
            "classification_assignment_id",
            "entity_id",
            "classification_node_id",
            "parent_node_id",
        ):
            frame[column] = frame[column].astype("string")
        return frame


class MembershipService:
    """Effective source-universe membership ingestion."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, memberships: tuple[UniverseMembership, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "universe membership ingestion requires market_write mode"
            )
        if not memberships:
            raise ReferenceDefinitionError("membership ingestion requires rows")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            for membership in memberships:
                content_id = scoped_content_id(
                    {"schema": "persistra.reference.universe_membership", "value": membership}
                )
                existing = connection.execute(
                    "SELECT membership_id FROM canonical.universe_memberships "
                    "WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    result.append(existing[0])
                    continue
                membership_id = UUID(bytes=content_id.digest[:16])
                sequence = advance_catalog(
                    connection,
                    change_kind="reference.universe_membership_ingested",
                    entity_id=membership.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.universe_memberships VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        membership_id,
                        membership.source_universe_key,
                        membership.instrument_id.value,
                        membership.role.value,
                        membership.weight,
                        membership.valid_from,
                        membership.valid_to,
                        membership.available_at or context.recorded_at,
                        context.recorded_at,
                        sequence,
                        str(content_id),
                    ],
                )
                result.append(membership_id)
            return tuple(result)

        return self._project.services.transactions.run("universe_membership_ingest", operation)


class CalendarService:
    """Reviewed materialized calendar registry and resolver."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: CalendarDefinition) -> ResolvedCalendarRef:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("calendar registration requires market_write mode")
        import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

        calendar = xcals.get_calendar(
            definition.exchange_calendar_name,
            start=definition.coverage_start.isoformat(),
            end=(definition.coverage_end - timedelta(days=1)).isoformat(),
        )
        if str(calendar.tz) != definition.timezone_name:
            raise ReferenceDefinitionError("calendar timezone does not match generator")
        schedule = calendar.schedule
        session_dates = {item.date(): item for item in schedule.index}
        early_closes = {item.date() for item in calendar.early_closes}
        rows: list[dict[str, Any]] = []
        current = definition.coverage_start
        while current < definition.coverage_end:
            label = session_dates.get(current)
            if label is None:
                rows.append(
                    {
                        "calendar_date": current,
                        "is_session": False,
                        "open_at": None,
                        "break_start_at": None,
                        "break_end_at": None,
                        "close_at": None,
                        "is_early_close": False,
                        "closure_reason": (
                            "weekend" if current.weekday() >= 5 else "scheduled_holiday"
                        ),
                    }
                )
            else:
                record = cast("pd.Series[Any]", schedule.loc[label])
                open_at = cast("pd.Timestamp", record["open"])
                close_at = cast("pd.Timestamp", record["close"])
                break_start = record["break_start"]
                break_end = record["break_end"]
                rows.append(
                    {
                        "calendar_date": current,
                        "is_session": True,
                        "open_at": open_at.to_pydatetime(),
                        "break_start_at": (
                            None
                            if pd.isna(break_start)
                            else cast("pd.Timestamp", break_start).to_pydatetime()
                        ),
                        "break_end_at": (
                            None
                            if pd.isna(break_end)
                            else cast("pd.Timestamp", break_end).to_pydatetime()
                        ),
                        "close_at": close_at.to_pydatetime(),
                        "is_early_close": current in early_closes,
                        "closure_reason": None,
                    }
                )
            current += timedelta(days=1)
        schedule_root = scoped_content_id(
            {"schema": "persistra.calendar.schedule", "rows": rows}
        )
        definition_content = scoped_content_id(
            {
                "schema": "persistra.calendar.definition",
                "definition": definition,
                "schedule_root": schedule_root,
            }
        )

        def operation(context: TransactionContext) -> ResolvedCalendarRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT calendar_id, definition_content_id, schedule_root_content_id "
                "FROM canonical.calendar_definitions "
                "WHERE qualified_name = ? AND calendar_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(definition_content):
                    raise ReferenceDefinitionError("calendar version conflicts")
                return ResolvedCalendarRef(
                    CalendarId.parse(existing[0]),
                    definition.version,
                    ContentId.parse(existing[1]),
                    ContentId.parse(existing[2]),
                )
            calendar_id = CalendarId.new()
            sequence = advance_catalog(
                connection,
                change_kind="reference.calendar_registered",
                entity_id=calendar_id,
                change_content_id=definition_content,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.calendar_definitions VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    calendar_id.value,
                    definition.version,
                    str(definition.name),
                    definition.venue_id.value,
                    definition.timezone_name,
                    definition.coverage_start,
                    definition.coverage_end,
                    str(definition_content),
                    str(schedule_root),
                    sequence,
                ],
            )
            for row in rows:
                row_content = scoped_content_id(
                    {
                        "schema": "persistra.calendar.date",
                        "calendar_id": calendar_id,
                        "version": definition.version,
                        "row": row,
                    }
                )
                connection.execute(
                    "INSERT INTO canonical.calendar_dates VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        calendar_id.value,
                        definition.version,
                        row["calendar_date"],
                        row["is_session"],
                        row["open_at"],
                        row["break_start_at"],
                        row["break_end_at"],
                        row["close_at"],
                        row["is_early_close"],
                        row["closure_reason"],
                        definition.available_at,
                        sequence,
                        str(row_content),
                    ],
                )
            insert_event(
                connection,
                event_name="persistra.calendar.registered",
                aggregate_kind="persistra.aggregate.calendar",
                aggregate_id=calendar_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,
                payload={
                    "calendar_id": calendar_id,
                    "definition_content_id": definition_content,
                    "schedule_root_content_id": schedule_root,
                },
            )
            return ResolvedCalendarRef(
                calendar_id,
                definition.version,
                definition_content,
                schedule_root,
            )

        return self._project.services.transactions.run("calendar_register", operation)

    def resolve(self, reference: CalendarRef, *, context: AsOfContext) -> ResolvedCalendarRef:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT calendar_id, calendar_version, definition_content_id, "
            "schedule_root_content_id FROM canonical.calendar_definitions "
            "WHERE qualified_name = ? AND calendar_version = ? "
            "AND created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise CalendarReferenceError("calendar reference is not in the snapshot")
        return ResolvedCalendarRef(
            CalendarId.parse(row[0]), int(row[1]), ContentId.parse(row[2]), ContentId.parse(row[3])
        )

    def get(self, reference: CalendarRef, *, context: AsOfContext) -> CalendarHandle:
        return CalendarHandle(self._project, context, self.resolve(reference, context=context))

    def decisions(
        self,
        schedule: SessionDecisionSchedule,
        *,
        start_at: datetime,
        end_at: datetime,
        context: AsOfContext,
    ) -> tuple[tuple[DecisionInstant, ...], ContentId]:
        handle = self.get(schedule.calendar, context=context)
        days = handle.schedule(start_at.date(), end_at.date() + timedelta(days=1))
        sessions = [item for item in days if isinstance(item, Session)]
        selected: list[Session] = []
        for index, session in enumerate(sessions):
            keep = schedule.selection is SessionSelection.EVERY_SESSION
            next_date = (
                sessions[index + 1].calendar_date
                if index + 1 < len(sessions)
                else (
                    None
                    if schedule.selection is SessionSelection.EVERY_SESSION
                    else handle.next_session(session.calendar_date).calendar_date
                )
            )
            if schedule.selection is SessionSelection.WEEK_END:
                keep = (
                    next_date is None
                    or next_date.isocalendar()[:2]
                    != session.calendar_date.isocalendar()[:2]
                )
            elif schedule.selection is SessionSelection.MONTH_END:
                keep = next_date is None or (next_date.year, next_date.month) != (
                    session.calendar_date.year,
                    session.calendar_date.month,
                )
            elif schedule.selection is SessionSelection.QUARTER_END:
                keep = next_date is None or (
                    next_date.year,
                    (next_date.month - 1) // 3,
                ) != (
                    session.calendar_date.year,
                    (session.calendar_date.month - 1) // 3,
                )
            if keep:
                selected.append(session)
        decisions = tuple(
            DecisionInstant(
                (
                    item.open_at
                    if schedule.anchor is SessionDecisionAnchor.OPEN
                    else item.close_at
                )
                + schedule.delay.to_timedelta(),
                item.calendar_date,
            )
            for item in selected
            if start_at
            <= (
                item.open_at
                if schedule.anchor is SessionDecisionAnchor.OPEN
                else item.close_at
            )
            + schedule.delay.to_timedelta()
            < end_at
        )
        content_id = scoped_content_id(
            {
                "schema": "persistra.calendar.decision_schedule",
                "schedule": schedule,
                "resolved_calendar": handle.reference,
                "decisions": decisions,
            }
        )
        return decisions, content_id


@dataclass(frozen=True, slots=True)
class CalendarHandle:
    _project: Project
    context: AsOfContext
    reference: ResolvedCalendarRef

    def schedule(self, start: date, end: date) -> tuple[CalendarDay, ...]:
        if start >= end:
            raise CalendarCoverageError("calendar range must be nonempty")
        opened, sequence = market_for_context(self._project, self.context)
        rows = opened.connection.execute(
            "SELECT calendar_date, is_session, open_at, break_start_at, break_end_at, "
            "close_at, is_early_close, closure_reason FROM canonical.calendar_dates "
            "WHERE calendar_id = ? AND calendar_version = ? "
            "AND calendar_date >= ? AND calendar_date < ? "
            "AND available_at <= ? AND catalog_sequence <= ? ORDER BY calendar_date",
            [
                self.reference.calendar_id.value,
                self.reference.version,
                start,
                end,
                self.context.public_cutoff_at,
                sequence,
            ],
        ).fetchall()
        expected = (end - start).days
        if len(rows) != expected:
            raise CalendarCoverageError("calendar lacks eligible coverage for the range")
        return tuple(
            (
                Session(row[0], row[2], row[5], row[3], row[4], bool(row[6]))
                if row[1]
                else NonSession(row[0], row[7])
            )
            for row in rows
        )

    def session(self, value: date) -> CalendarDay:
        return self.schedule(value, value + timedelta(days=1))[0]

    def next_session(self, value: date, count: int = 1) -> Session:
        if count < 1:
            raise CalendarCoverageError("session count must be positive")
        rows = self._session_rows(value, count, ascending=True)
        if len(rows) < count:
            raise CalendarCoverageError("calendar lacks next-session coverage")
        return self._session_from_row(rows[count - 1])

    def previous_session(self, value: date, count: int = 1) -> Session:
        if count < 1:
            raise CalendarCoverageError("session count must be positive")
        rows = self._session_rows(value, count, ascending=False)
        if len(rows) < count:
            raise CalendarCoverageError("calendar lacks previous-session coverage")
        return self._session_from_row(rows[count - 1])

    def _session_rows(
        self, value: date, count: int, *, ascending: bool
    ) -> list[tuple[Any, ...]]:
        opened, sequence = market_for_context(self._project, self.context)
        operator = ">" if ascending else "<"
        direction = "ASC" if ascending else "DESC"
        return opened.connection.execute(
            "SELECT calendar_date, open_at, break_start_at, break_end_at, close_at, "
            "is_early_close FROM canonical.calendar_dates "
            "WHERE calendar_id = ? AND calendar_version = ? AND is_session "
            f"AND calendar_date {operator} ? AND available_at <= ? "
            f"AND catalog_sequence <= ? ORDER BY calendar_date {direction} LIMIT ?",
            [
                self.reference.calendar_id.value,
                self.reference.version,
                value,
                self.context.public_cutoff_at,
                sequence,
                count,
            ],
        ).fetchall()

    @staticmethod
    def _session_from_row(row: tuple[Any, ...]) -> Session:
        return Session(row[0], row[1], row[4], row[2], row[3], bool(row[5]))
