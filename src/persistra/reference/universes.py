"""This module contains the immutable point-in-time universe definitions and evaluation."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    ResearchResultLimitError,
    UniverseDefinitionError,
    UniverseEvaluationError,
)
from persistra.reference.models import (
    ActiveListings,
    AsOfContext,
    CutoffMode,
    ExplicitInstrument,
    ExplicitInstruments,
    ExplicitMembership,
    InstrumentId,
    ListingStatus,
    MembershipRole,
    PublicCutoffPolicy,
    ResolvedUniverseRef,
    SecurityKind,
    SessionDecisionSchedule,
    UniverseDefinition,
    UniverseDefinitionId,
    UniverseEvaluationId,
    UniverseEvaluationRef,
    UniverseRef,
    VenueId,
)
from persistra.reference.services import ReferenceService, market_for_context

if TYPE_CHECKING:
    from persistra.catalog import CompositeSnapshotRef
    from persistra.db.services import TransactionContext
    from persistra.project import Project


def _decode_definition(text: str) -> UniverseDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    candidate_value = cast("dict[str, Any]", value["candidate_expression"])
    if "source_universe_key" in candidate_value:
        candidate = ExplicitMembership(
            cast("str", candidate_value["source_universe_key"]),
            tuple(MembershipRole(item) for item in candidate_value["roles"]),
        )
    elif "venues" in candidate_value:
        candidate = ActiveListings(
            tuple(VenueId.parse(item) for item in candidate_value["venues"]),
            tuple(SecurityKind(item) for item in candidate_value["security_kinds"]),
        )
    else:
        candidate = ExplicitInstruments(
            tuple(
                ExplicitInstrument(
                    InstrumentId.parse(item["instrument_id"]),
                    datetime.fromisoformat(item["valid_from"].replace("Z", "+00:00")),
                    (
                        None
                        if item["valid_to"] is None
                        else datetime.fromisoformat(
                            item["valid_to"].replace("Z", "+00:00")
                        )
                    ),
                )
                for item in candidate_value["instruments"]
            )
        )
    return UniverseDefinition(
        name=QualifiedName(value["name"]),
        version=int(value["version"]),
        candidate_expression=candidate,
        require_active_listing=bool(value["require_active_listing"]),
        allowed_security_kinds=tuple(
            SecurityKind(item) for item in value["allowed_security_kinds"]
        ),
        required_identifier_namespace=(
            None
            if value["required_identifier_namespace"] is None
            else QualifiedName(value["required_identifier_namespace"])
        ),
    )


class UniverseService:
    """This class represents the research-owned universe registry and complete eligibility audit."""

    __slots__ = ("_project", "_reference")

    def __init__(self, project: Project, reference: ReferenceService) -> None:
        self._project = project
        self._reference = reference

    def register(self, definition: UniverseDefinition) -> ResolvedUniverseRef:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "universe registration requires research_write mode"
            )
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.universe.definition", "definition": definition}
        )

        def operation(context: TransactionContext) -> ResolvedUniverseRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT universe_definition_id, definition_content_id, definition_json "
                "FROM research.universe_definitions WHERE qualified_name = ? "
                "AND definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise UniverseDefinitionError("universe definition version conflicts")
                return ResolvedUniverseRef(
                    UniverseDefinitionId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            prior = connection.execute(
                "SELECT max(definition_version), min(universe_definition_id) "
                "FROM research.universe_definitions WHERE qualified_name = ?",
                [str(definition.name)],
            ).fetchone()
            prior_version = None if prior is None else prior[0]
            if prior_version is not None and definition.version != int(prior_version) + 1:
                raise UniverseDefinitionError("universe versions must be contiguous")
            if prior_version is None and definition.version != 1:
                raise UniverseDefinitionError("first universe version must be one")
            definition_id = (
                UniverseDefinitionId.new()
                if prior_version is None
                else UniverseDefinitionId.parse(cast("Any", prior)[1])
            )
            connection.execute(
                "INSERT INTO research.universe_definitions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(definition.name),
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,  # type: ignore[attr-defined]
                ],
            )
            insert_event(
                connection,
                event_name="persistra.universe.definition_registered",
                aggregate_kind="persistra.aggregate.universe_definition",
                aggregate_id=definition_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,  # type: ignore[attr-defined]
                payload={
                    "universe_definition_id": definition_id,
                    "definition_content_id": content_id,
                },
            )
            return ResolvedUniverseRef(definition_id, definition.version, content_id)

        return self._project.services.transactions.run("universe_register", operation)

    def resolve(self, reference: UniverseRef) -> ResolvedUniverseRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT universe_definition_id, definition_content_id "
            "FROM research.universe_definitions WHERE qualified_name = ? "
            "AND definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise UniverseDefinitionError("universe definition is not registered")
        return ResolvedUniverseRef(
            UniverseDefinitionId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def get_definition(self, reference: UniverseRef) -> UniverseDefinition:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT definition_json FROM research.universe_definitions "
            "WHERE qualified_name = ? AND definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise UniverseDefinitionError("universe definition is not registered")
        return _decode_definition(row[0])

    def evaluate(
        self,
        *,
        definition: UniverseRef,
        composite_snapshot: CompositeSnapshotRef,
        decisions: SessionDecisionSchedule,
        start_at: datetime,
        end_at: datetime,
        cutoff_mode: CutoffMode = CutoffMode.PUBLIC,
        public_cutoff_policy: PublicCutoffPolicy | None = None,
        project_cutoff_at: datetime | None = None,
        market_database: str,
    ) -> UniverseEvaluationRef:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "universe evaluation requires research_write mode"
            )
        if start_at >= end_at:
            raise UniverseEvaluationError("universe interval must be nonempty")
        if cutoff_mode is CutoffMode.PUBLIC_AND_PROJECT and project_cutoff_at is None:
            raise UniverseEvaluationError("project cutoff is required")
        if cutoff_mode is CutoffMode.PUBLIC and project_cutoff_at is not None:
            raise UniverseEvaluationError("public mode forbids project cutoff")
        public_cutoff_policy = public_cutoff_policy or PublicCutoffPolicy.at_decision()
        resolved = self.resolve(definition)
        stored = self.get_definition(definition)
        initial_context = AsOfContext(
            composite_snapshot,
            start_at,
            public_cutoff_policy.resolve(start_at),
            cutoff_mode,
            project_cutoff_at,
            market_database=market_database,
        )
        decision_rows, schedule_content_id = self._reference.calendars.decisions(
            decisions,
            start_at=start_at,
            end_at=end_at,
            context=initial_context,
        )
        if not decision_rows:
            raise UniverseEvaluationError("decision schedule is empty")
        envelope = self._candidate_envelope(stored, initial_context, start_at, end_at)
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.universe.evaluation",
                "definition": resolved,
                "composite_snapshot": composite_snapshot,
                "decisions": decision_rows,
                "schedule_content_id": schedule_content_id,
                "cutoff_mode": cutoff_mode,
                "public_cutoff_policy": public_cutoff_policy,
                "project_cutoff_at": project_cutoff_at,
                "candidate_envelope": envelope,
            }
        )

        def operation(context: TransactionContext) -> UniverseEvaluationRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT universe_evaluation_id FROM research.universe_evaluations "
                "WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return UniverseEvaluationRef(
                    UniverseEvaluationId.parse(existing[0]),
                    resolved.universe_definition_id,
                    resolved.version,
                    composite_snapshot.composite_snapshot_id,
                    execution_content_id,
                    schedule_content_id,
                )
            evaluation_id = UniverseEvaluationId.new()
            connection.execute(
                "INSERT INTO research.universe_evaluations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    evaluation_id.value,
                    resolved.universe_definition_id.value,
                    resolved.version,
                    composite_snapshot.composite_snapshot_id.value,
                    str(execution_content_id),
                    start_at,
                    end_at,
                    cutoff_mode.value,
                    str(scoped_content_id(public_cutoff_policy)),
                    project_cutoff_at,
                    str(schedule_content_id),
                    context.recorded_at,  # type: ignore[attr-defined]
                ],
            )
            for decision in decision_rows:
                decision_context = replace(
                    initial_context,
                    effective_at=decision.decision_at,
                    public_cutoff_at=public_cutoff_policy.resolve(decision.decision_at),
                )
                for instrument_id in envelope:
                    eligible, reasons, outcomes = self._evaluate_candidate(
                        stored, instrument_id, decision_context
                    )
                    primary = "universe.eligible" if eligible else reasons[0]
                    lineage = scoped_content_id(
                        {
                            "schema": "persistra.universe.eligibility_lineage",
                            "instrument_id": instrument_id,
                            "decision": decision,
                            "outcomes": outcomes,
                        }
                    )
                    connection.execute(
                        "INSERT INTO research.universe_eligibility VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            evaluation_id.value,
                            decision.decision_at,
                            decision.session_date,
                            instrument_id.value,
                            eligible,
                            primary,
                            json.dumps(reasons, separators=(",", ":")),
                            "[]",
                            str(lineage),
                        ],
                    )
                    for ordinal, outcome in enumerate(outcomes, start=1):
                        evidence = scoped_content_id(
                            {
                                "schema": "persistra.universe.rule_outcome",
                                "decision_at": decision.decision_at,
                                "instrument_id": instrument_id,
                                "outcome": outcome,
                            }
                        )
                        connection.execute(
                            "INSERT INTO research.universe_rule_outcomes VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                evaluation_id.value,
                                decision.decision_at,
                                instrument_id.value,
                                ordinal,
                                outcome["rule"],
                                outcome["outcome"],
                                outcome["reason"],
                                str(evidence),
                            ],
                        )
            insert_event(
                connection,
                event_name="persistra.universe.evaluation_completed",
                aggregate_kind="persistra.aggregate.universe_evaluation",
                aggregate_id=evaluation_id,
                aggregate_sequence=1,
                recorded_at=context.recorded_at,  # type: ignore[attr-defined]
                payload={
                    "execution_content_id": execution_content_id,
                    "universe_evaluation_id": evaluation_id,
                },
            )
            return UniverseEvaluationRef(
                evaluation_id,
                resolved.universe_definition_id,
                resolved.version,
                composite_snapshot.composite_snapshot_id,
                execution_content_id,
                schedule_content_id,
            )

        return self._project.services.transactions.run("universe_evaluate", operation)

    def eligibility(
        self, evaluation_id: UniverseEvaluationId, *, max_rows: int = 2_000_000
    ) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT universe_evaluation_id, decision_at, session_date, instrument_id, "
            "eligible, primary_reason_code, reason_codes_json, warning_codes_json, "
            "lineage_content_id FROM research.universe_eligibility "
            "WHERE universe_evaluation_id = ? ORDER BY decision_at, instrument_id LIMIT ?",
            [evaluation_id.value, max_rows + 1],
        ).fetchall()
        if len(rows) > max_rows:
            raise ResearchResultLimitError("universe eligibility exceeds max_rows")
        columns = [
            "universe_evaluation_id",
            "decision_at",
            "session_date",
            "instrument_id",
            "eligible",
            "primary_reason_code",
            "reason_codes",
            "warning_codes",
            "lineage_content_id",
        ]
        frame = pd.DataFrame(rows, columns=columns)
        for column in (
            "universe_evaluation_id",
            "instrument_id",
            "lineage_content_id",
        ):
            frame[column] = frame[column].astype("string")
        frame["decision_at"] = pd.to_datetime(frame["decision_at"], utc=True)
        frame["reason_codes"] = frame["reason_codes"].map(json.loads)
        frame["warning_codes"] = frame["warning_codes"].map(json.loads)
        return frame

    def _candidate_envelope(
        self,
        definition: UniverseDefinition,
        context: AsOfContext,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[InstrumentId, ...]:
        opened, sequence = market_for_context(self._project, context)
        expression = definition.candidate_expression
        if isinstance(expression, ExplicitInstruments):
            return tuple(
                sorted(
                    (
                        item.instrument_id
                        for item in expression.instruments
                        if item.valid_from < end_at
                        and (item.valid_to is None or start_at < item.valid_to)
                    ),
                    key=lambda item: item.value.bytes,
                )
            )
        if isinstance(expression, ActiveListings):
            rows = opened.connection.execute(
                "SELECT DISTINCT o.instrument_id FROM canonical.instrument_observations o "
                "JOIN canonical.instruments i USING (instrument_id) "
                "JOIN canonical.listings l USING (listing_id) "
                "WHERE l.venue_id IN (SELECT unnest(?)) "
                "AND o.security_kind IN (SELECT unnest(?)) AND o.catalog_sequence <= ? "
                "ORDER BY o.instrument_id",
                [
                    [item.value for item in expression.venues],
                    [item.value for item in expression.security_kinds],
                    sequence,
                ],
            ).fetchall()
        else:
            rows = opened.connection.execute(
                "SELECT DISTINCT instrument_id FROM canonical.universe_memberships "
                "WHERE source_universe_key = ? "
                "AND membership_role IN (SELECT unnest(?)) "
                "AND valid_from < ? AND (valid_to IS NULL OR ? < valid_to) "
                "AND catalog_sequence <= ? ORDER BY instrument_id",
                [
                    expression.source_universe_key,
                    [item.value for item in expression.roles],
                    end_at,
                    start_at,
                    sequence,
                ],
            ).fetchall()
        return tuple(InstrumentId.parse(row[0]) for row in rows)

    def _evaluate_candidate(
        self,
        definition: UniverseDefinition,
        instrument_id: InstrumentId,
        context: AsOfContext,
    ) -> tuple[bool, list[str], list[dict[str, str]]]:
        frame = self._reference.instruments(
            context=context, instrument_ids=(instrument_id,), max_rows=1
        )
        reasons: list[str] = []
        outcomes: list[dict[str, str]] = []
        if frame.empty:
            reason = "universe.candidate.not_available"
            reasons.append(reason)
            outcomes.append(
                {"rule": "candidate", "outcome": "unavailable", "reason": reason}
            )
            return False, reasons, outcomes
        row = frame.iloc[0]
        expression = definition.candidate_expression
        candidate_pass = True
        if isinstance(expression, ActiveListings):
            candidate_pass = (
                row["venue_id"] in {str(item.value) for item in expression.venues}
                and row["security_kind"]
                in {item.value for item in expression.security_kinds}
            )
        elif isinstance(expression, ExplicitMembership):
            candidate_pass = self._membership_passes(
                expression, instrument_id, context
            )
        else:
            candidate_pass = any(
                item.instrument_id == instrument_id
                and item.valid_from <= context.effective_at
                and (item.valid_to is None or context.effective_at < item.valid_to)
                for item in expression.instruments
            )
        candidate_reason = (
            "universe.candidate.selected"
            if candidate_pass
            else "universe.candidate.not_effective"
        )
        outcomes.append(
            {
                "rule": "candidate",
                "outcome": "pass" if candidate_pass else "fail",
                "reason": candidate_reason,
            }
        )
        if not candidate_pass:
            reasons.append(candidate_reason)
        active = not definition.require_active_listing or (
            row["listing_status"] == ListingStatus.ACTIVE.value
        )
        outcomes.append(
            {
                "rule": "listing_active",
                "outcome": "pass" if active else "fail",
                "reason": (
                    "universe.listing.active"
                    if active
                    else "universe.listing.inactive"
                ),
            }
        )
        if not active:
            reasons.append("universe.listing.inactive")
        kind_ok = row["security_kind"] in {
            item.value for item in definition.allowed_security_kinds
        }
        outcomes.append(
            {
                "rule": "security_kind",
                "outcome": "pass" if kind_ok else "fail",
                "reason": (
                    "universe.security.supported_kind"
                    if kind_ok
                    else "universe.security.unsupported_kind"
                ),
            }
        )
        if not kind_ok:
            reasons.append("universe.security.unsupported_kind")
        if definition.required_identifier_namespace is not None:
            identifier_state = self._identifier_state(
                definition.required_identifier_namespace,
                instrument_id,
                context,
            )
            identifier_ok = identifier_state == "resolved"
            identifier_reason = {
                "resolved": "universe.identifier.resolved",
                "not_found": "universe.identifier.not_found",
                "ambiguous": "universe.identifier.ambiguous",
            }[identifier_state]
            outcomes.append(
                {
                    "rule": "required_identifier",
                    "outcome": "pass" if identifier_ok else "fail",
                    "reason": identifier_reason,
                }
            )
            if not identifier_ok:
                reasons.append(identifier_reason)
        return not reasons, reasons or ["universe.eligible"], outcomes

    def _membership_passes(
        self,
        expression: ExplicitMembership,
        instrument_id: InstrumentId,
        context: AsOfContext,
    ) -> bool:
        opened, sequence = market_for_context(self._project, context)
        parameters: list[Any] = [
            expression.source_universe_key,
            instrument_id.value,
            [item.value for item in expression.roles],
            context.effective_at,
            context.effective_at,
            context.public_cutoff_at,
            sequence,
        ]
        project_sql = ""
        if context.project_cutoff_at is not None:
            project_sql = " AND ingested_at <= ?"
            parameters.insert(-1, context.project_cutoff_at)
        row = opened.connection.execute(
            "SELECT 1 FROM canonical.universe_memberships "
            "WHERE source_universe_key = ? AND instrument_id = ? "
            "AND membership_role IN (SELECT unnest(?)) AND valid_from <= ? "
            "AND (valid_to IS NULL OR ? < valid_to) AND available_at <= ? "
            f"{project_sql} AND catalog_sequence <= ? LIMIT 1",
            parameters,
        ).fetchone()
        return row is not None

    def _identifier_state(
        self,
        namespace_name: QualifiedName,
        instrument_id: InstrumentId,
        context: AsOfContext,
    ) -> str:
        opened, sequence = market_for_context(self._project, context)
        namespace = opened.connection.execute(
            "SELECT identifier_namespace_id, namespace_version "
            "FROM canonical.identifier_namespaces WHERE qualified_name = ? "
            "AND created_catalog_sequence <= ? ORDER BY namespace_version DESC LIMIT 1",
            [str(namespace_name), sequence],
        ).fetchone()
        if namespace is None:
            return "not_found"
        parameters: list[Any] = [
            namespace[0],
            namespace[1],
            instrument_id.value,
            context.effective_at,
            context.effective_at,
            context.public_cutoff_at,
            sequence,
        ]
        project_sql = ""
        if context.project_cutoff_at is not None:
            project_sql = " AND ingested_at <= ?"
            parameters.insert(-1, context.project_cutoff_at)
        rows = opened.connection.execute(
            "SELECT normalized_value FROM canonical.identifier_assignments "
            "WHERE namespace_id = ? AND namespace_version = ? AND entity_id = ? "
            "AND valid_from <= ? AND (valid_to IS NULL OR ? < valid_to) "
            f"AND available_at <= ?{project_sql} AND catalog_sequence <= ? "
            "ORDER BY normalized_value",
            parameters,
        ).fetchall()
        values = {row[0] for row in rows}
        if not values:
            return "not_found"
        return "resolved" if len(values) == 1 else "ambiguous"
