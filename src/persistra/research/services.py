"""Research-owned immutable daily decision-dataset builder."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, Duration, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    ResearchDatasetBuildError,
    ResearchDatasetDefinitionError,
    ResearchResultLimitError,
)
from persistra.market import (
    AdjustmentPriceMode,
    AdjustmentViewRequest,
    BarQuery,
    BarSpecRef,
    BarState,
)
from persistra.reference import (
    AsOfContext,
    CalendarRef,
    CutoffMode,
    PublicCutoffPolicy,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
    UniverseEvaluationId,
    UniverseRef,
)
from persistra.reference.models import InstrumentId
from persistra.research.models import (
    DailyBarInput,
    MissingInputAction,
    ResearchCutoffSpec,
    ResearchDatasetBuildId,
    ResearchDatasetBuildRef,
    ResearchDatasetDefinition,
    ResearchDatasetId,
    ResearchDatasetRef,
    ResearchDatasetRole,
    ResolvedResearchDatasetRef,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from persistra.catalog import CompositeSnapshotRef
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.reference.universes import UniverseService


def _decode_definition(text: str) -> ResearchDatasetDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    schedule_value = cast("dict[str, Any]", value["decisions"])
    calendar_value = cast("dict[str, Any]", schedule_value["calendar"])
    cutoff_value = cast("dict[str, Any]", value["cutoff"])
    policy_value = cast("dict[str, Any]", cutoff_value["public_policy"])
    inputs = tuple(
        DailyBarInput(
            name=item["name"],
            spec=BarSpecRef(
                QualifiedName(item["spec"]["name"]), int(item["spec"]["version"])
            ),
            adjustment_mode=AdjustmentPriceMode(item["adjustment_mode"]),
            max_age=Duration.parse(item["max_age"]),
            missing_action=MissingInputAction(item["missing_action"]),
        )
        for item in value["inputs"]
    )
    return ResearchDatasetDefinition(
        name=QualifiedName(value["name"]),
        version=int(value["version"]),
        universe=UniverseRef(
            QualifiedName(value["universe"]["name"]), int(value["universe"]["version"])
        ),
        decisions=SessionDecisionSchedule(
            calendar=CalendarRef(
                QualifiedName(calendar_value["name"]), int(calendar_value["version"])
            ),
            anchor=SessionDecisionAnchor(schedule_value["anchor"]),
            selection=SessionSelection(schedule_value["selection"]),
            delay=Duration.parse(schedule_value["delay"]),
        ),
        cutoff=ResearchCutoffSpec(
            CutoffMode(cutoff_value["mode"]),
            PublicCutoffPolicy(
                Duration.parse(policy_value["lag"]),
            ),
        ),
        inputs=inputs,
        role=ResearchDatasetRole(value["role"]),
    )


def _identity_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float):
        return format(value, ".17g")
    if isinstance(value, tuple | list):
        sequence = cast("tuple[Any, ...] | list[Any]", value)
        return tuple(_identity_value(item) for item in sequence)
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        return {str(key): _identity_value(item) for key, item in mapping.items()}
    return value


class ResearchService:
    """Research capability group."""

    __slots__ = ("datasets", "features", "sql", "workspace")

    def __init__(self, project: Project, universes: UniverseService) -> None:
        from persistra.research.feature_services import FeatureService
        from persistra.research.sql_services import SqlReadService, WorkspaceService

        self.datasets = ResearchDatasetService(project, universes)
        self.features = FeatureService(project)
        self.sql = SqlReadService(project)
        self.workspace = WorkspaceService(project, self.sql)


class ResearchDatasetService:
    """Versioned daily decision-dataset registry and builder."""

    __slots__ = ("_project", "_universes")

    def __init__(self, project: Project, universes: UniverseService) -> None:
        self._project = project
        self._universes = universes

    def register(
        self, definition: ResearchDatasetDefinition
    ) -> ResolvedResearchDatasetRef:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "research dataset registration requires research_write mode"
            )
        self._universes.resolve(definition.universe)
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.research.dataset_definition", "definition": definition}
        )

        def operation(context: TransactionContext) -> ResolvedResearchDatasetRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.research_dataset_id, v.definition_content_id, v.definition_json "
                "FROM research.research_datasets d JOIN "
                "research.research_dataset_versions v USING (research_dataset_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise ResearchDatasetDefinitionError(
                        "research dataset version conflicts"
                    )
                return ResolvedResearchDatasetRef(
                    ResearchDatasetId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            prior = connection.execute(
                "SELECT d.research_dataset_id, max(v.definition_version) "
                "FROM research.research_datasets d LEFT JOIN "
                "research.research_dataset_versions v USING (research_dataset_id) "
                "WHERE d.qualified_name = ? GROUP BY d.research_dataset_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise ResearchDatasetDefinitionError(
                        "first research dataset version must be one"
                    )
                dataset_id = ResearchDatasetId.new()
                connection.execute(
                    "INSERT INTO research.research_datasets VALUES (?, ?, ?)",
                    [
                        dataset_id.value,
                        str(definition.name),
                        context.recorded_at,  # type: ignore[attr-defined]
                    ],
                )
            else:
                dataset_id = ResearchDatasetId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise ResearchDatasetDefinitionError(
                        "research dataset versions must be contiguous"
                    )
            connection.execute(
                "INSERT INTO research.research_dataset_versions VALUES (?, ?, ?, ?, ?)",
                [
                    dataset_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,  # type: ignore[attr-defined]
                ],
            )
            insert_event(
                connection,
                event_name="persistra.research.dataset_registered",
                aggregate_kind="persistra.aggregate.research_dataset",
                aggregate_id=dataset_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,  # type: ignore[attr-defined]
                payload={
                    "definition_content_id": content_id,
                    "research_dataset_id": dataset_id,
                },
            )
            return ResolvedResearchDatasetRef(
                dataset_id, definition.version, content_id
            )

        return self._project.services.transactions.run("research_dataset_register", operation)

    def resolve(self, reference: ResearchDatasetRef) -> ResolvedResearchDatasetRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.research_dataset_id, v.definition_content_id "
            "FROM research.research_datasets d JOIN "
            "research.research_dataset_versions v USING (research_dataset_id) "
            "WHERE d.qualified_name = ? AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise ResearchDatasetDefinitionError("research dataset is not registered")
        return ResolvedResearchDatasetRef(
            ResearchDatasetId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def get_definition(
        self, reference: ResearchDatasetRef
    ) -> ResearchDatasetDefinition:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT v.definition_json FROM research.research_datasets d JOIN "
            "research.research_dataset_versions v USING (research_dataset_id) "
            "WHERE d.qualified_name = ? AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise ResearchDatasetDefinitionError("research dataset is not registered")
        return _decode_definition(row[0])

    def build(
        self,
        *,
        definition: ResearchDatasetRef,
        composite_snapshot: CompositeSnapshotRef,
        start_at: datetime,
        end_at: datetime,
        market_database: str,
        project_cutoff_at: datetime | None = None,
        universe_evaluation: UniverseEvaluationId | None = None,
    ) -> ResearchDatasetBuild:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "research dataset build requires research_write mode"
            )
        resolved = self.resolve(definition)
        stored = self.get_definition(definition)
        if stored.cutoff.mode is CutoffMode.PUBLIC_AND_PROJECT and project_cutoff_at is None:
            raise ResearchDatasetBuildError("dataset build requires project_cutoff_at")
        if stored.cutoff.mode is CutoffMode.PUBLIC and project_cutoff_at is not None:
            raise ResearchDatasetBuildError("public-only dataset forbids project_cutoff_at")
        if universe_evaluation is None:
            evaluated = self._universes.evaluate(
                definition=stored.universe,
                composite_snapshot=composite_snapshot,
                decisions=stored.decisions,
                start_at=start_at,
                end_at=end_at,
                cutoff_mode=stored.cutoff.mode,
                public_cutoff_policy=stored.cutoff.public_policy,
                project_cutoff_at=project_cutoff_at,
                market_database=market_database,
            )
            universe_evaluation = evaluated.universe_evaluation_id
        self._verify_evaluation(
            universe_evaluation,
            stored,
            composite_snapshot,
            start_at,
            end_at,
            project_cutoff_at,
        )
        eligibility = self._universes.eligibility(universe_evaluation)
        output_rows, audit_rows, outcome_rows = self._assemble(
            stored,
            composite_snapshot,
            eligibility,
            market_database,
            project_cutoff_at,
        )
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.research.dataset_execution",
                "definition": resolved,
                "composite_snapshot": composite_snapshot,
                "universe_evaluation_id": universe_evaluation,
                "start_at": start_at,
                "end_at": end_at,
                "project_cutoff_at": project_cutoff_at,
                "output_rows": _identity_value(output_rows),
                "audit_rows": _identity_value(audit_rows),
                "outcome_rows": _identity_value(outcome_rows),
            }
        )
        output_manifest_content_id = scoped_content_id(
            {
                "schema": "persistra.research.dataset_output_manifest",
                "execution_content_id": execution_content_id,
                "row_count": len(output_rows),
                "rows": _identity_value(output_rows),
            }
        )

        def operation(context: TransactionContext) -> ResearchDatasetBuild:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT research_dataset_build_id FROM "
                "research.research_dataset_builds WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(ResearchDatasetBuildId.parse(existing[0]))
            build_id = ResearchDatasetBuildId.new()
            relation = f"dataset_{build_id.value.hex}"
            dynamic_columns = ", ".join(
                f'"{item.name}_close" DOUBLE, "{item.name}_state" VARCHAR NOT NULL, '
                f'"{item.name}_reason" VARCHAR NOT NULL'
                for item in stored.inputs
            )
            connection.execute(
                f'CREATE TABLE research_data."{relation}" ('
                "research_dataset_build_id UUID NOT NULL, "
                "decision_at TIMESTAMPTZ NOT NULL, session_date DATE, "
                "instrument_id UUID NOT NULL, research_row_usable BOOLEAN NOT NULL, "
                "research_primary_reason_code VARCHAR NOT NULL, "
                "research_reason_codes_json JSON NOT NULL, "
                "research_row_lineage_content_id VARCHAR NOT NULL, "
                f"{dynamic_columns}, PRIMARY KEY (decision_at, instrument_id))"
            )
            value_columns = [
                "research_dataset_build_id",
                "decision_at",
                "session_date",
                "instrument_id",
                "research_row_usable",
                "research_primary_reason_code",
                "research_reason_codes_json",
                "research_row_lineage_content_id",
            ]
            for item in stored.inputs:
                value_columns.extend(
                    [f"{item.name}_close", f"{item.name}_state", f"{item.name}_reason"]
                )
            quoted = ", ".join(f'"{item}"' for item in value_columns)
            placeholders = ", ".join("?" for _ in value_columns)
            for row in output_rows:
                connection.execute(
                    f'INSERT INTO research_data."{relation}" ({quoted}) VALUES ({placeholders})',
                    [build_id.value, *(row[column] for column in value_columns[1:])],
                )
            for row in audit_rows:
                connection.execute(
                    "INSERT INTO research.research_dataset_row_audit VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [build_id.value, *row],
                )
            for row in outcome_rows:
                connection.execute(
                    "INSERT INTO research.research_dataset_input_outcomes VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [build_id.value, *row],
                )
            usable_count = sum(bool(row["research_row_usable"]) for row in output_rows)
            connection.execute(
                "INSERT INTO research.research_dataset_builds VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    build_id.value,
                    resolved.research_dataset_id.value,
                    resolved.version,
                    composite_snapshot.composite_snapshot_id.value,
                    universe_evaluation.value,
                    str(execution_content_id),
                    relation,
                    str(output_manifest_content_id),
                    len(output_rows),
                    usable_count,
                    context.recorded_at,  # type: ignore[attr-defined]
                ],
            )
            insert_event(
                connection,
                event_name="persistra.research.dataset_build_completed",
                aggregate_kind="persistra.aggregate.research_dataset_build",
                aggregate_id=build_id,
                aggregate_sequence=1,
                recorded_at=context.recorded_at,  # type: ignore[attr-defined]
                payload={
                    "execution_content_id": execution_content_id,
                    "output_manifest_content_id": output_manifest_content_id,
                    "research_dataset_build_id": build_id,
                },
            )
            reference = ResearchDatasetBuildRef(
                build_id,
                resolved.research_dataset_id,
                resolved.version,
                universe_evaluation,
                execution_content_id,
                output_manifest_content_id,
                len(output_rows),
                usable_count,
            )
            return ResearchDatasetBuild(self._project, reference, relation)

        return self._project.services.transactions.run("research_dataset_build", operation)

    def get(self, build_id: ResearchDatasetBuildId) -> ResearchDatasetBuild:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT research_dataset_id, definition_version, universe_evaluation_id, "
            "execution_content_id, output_relation_name, output_manifest_content_id, "
            "row_count, usable_count FROM research.research_dataset_builds "
            "WHERE research_dataset_build_id = ?",
            [build_id.value],
        ).fetchone()
        if row is None:
            raise ResearchDatasetBuildError("research dataset build is not found")
        reference = ResearchDatasetBuildRef(
            build_id,
            ResearchDatasetId.parse(row[0]),
            int(row[1]),
            UniverseEvaluationId.parse(row[2]),
            ContentId.parse(row[3]),
            ContentId.parse(row[5]),
            int(row[6]),
            int(row[7]),
        )
        return ResearchDatasetBuild(self._project, reference, row[4])

    def _verify_evaluation(
        self,
        evaluation_id: UniverseEvaluationId,
        definition: ResearchDatasetDefinition,
        composite_snapshot: CompositeSnapshotRef,
        start_at: datetime,
        end_at: datetime,
        project_cutoff_at: datetime | None,
    ) -> None:
        universe = self._universes.resolve(definition.universe)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT universe_definition_id, definition_version, composite_snapshot_id, "
            "start_at, end_at, cutoff_mode, public_cutoff_policy_content_id, "
            "project_cutoff_at FROM research.universe_evaluations "
            "WHERE universe_evaluation_id = ?",
            [evaluation_id.value],
        ).fetchone()
        expected = (
            universe.universe_definition_id.value,
            universe.version,
            composite_snapshot.composite_snapshot_id.value,
            start_at,
            end_at,
            definition.cutoff.mode.value,
            str(scoped_content_id(definition.cutoff.public_policy)),
            project_cutoff_at,
        )
        if row != expected:
            raise ResearchDatasetBuildError(
                "universe evaluation is incompatible with the dataset build"
            )

    def _assemble(
        self,
        definition: ResearchDatasetDefinition,
        composite_snapshot: CompositeSnapshotRef,
        eligibility: pd.DataFrame,
        market_database: str,
        project_cutoff_at: datetime | None,
    ) -> tuple[list[dict[str, Any]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        output: list[dict[str, Any]] = []
        audit: list[tuple[Any, ...]] = []
        outcomes: list[tuple[Any, ...]] = []
        for eligibility_row in eligibility.to_dict("records"):
            decision_at = eligibility_row["decision_at"].to_pydatetime()
            instrument = InstrumentId.parse(eligibility_row["instrument_id"])
            if not eligibility_row["eligible"]:
                audit.append(
                    (
                        decision_at,
                        eligibility_row["session_date"],
                        instrument.value,
                        False,
                        False,
                        False,
                        eligibility_row["primary_reason_code"],
                        json.dumps(eligibility_row["reason_codes"], separators=(",", ":")),
                        None,
                    )
                )
                continue
            context = AsOfContext(
                composite_snapshot,
                decision_at,
                definition.cutoff.public_policy.resolve(decision_at),
                definition.cutoff.mode,
                project_cutoff_at,
                market_database=market_database,
            )
            row: dict[str, Any] = {
                "decision_at": decision_at,
                "session_date": eligibility_row["session_date"],
                "instrument_id": instrument.value,
                "research_row_usable": True,
                "research_primary_reason_code": "research.row.usable",
                "research_reason_codes_json": "[]",
            }
            reasons: list[str] = []
            included = True
            usable = True
            row_outcomes: list[tuple[Any, ...]] = []
            for ordinal, item in enumerate(definition.inputs, start=1):
                if not included:
                    row_outcomes.append(
                        (
                            ordinal,
                            decision_at,
                            instrument.value,
                            "not_evaluated",
                            None,
                            None,
                            '["research.input.not_evaluated"]',
                            None,
                        )
                    )
                    continue
                selected = self._select_bar(item, instrument, decision_at, context)
                if selected is None:
                    reason = "research.input.not_available"
                    row[f"{item.name}_close"] = None
                    row[f"{item.name}_state"] = "not_available"
                    row[f"{item.name}_reason"] = reason
                    if item.missing_action is MissingInputAction.FAIL_BUILD:
                        raise ResearchDatasetBuildError(
                            f"required input {item.name} is unavailable"
                        )
                    if item.missing_action is MissingInputAction.DROP_WITH_AUDIT:
                        included = False
                        usable = False
                    elif item.missing_action is MissingInputAction.MARK_UNUSABLE:
                        usable = False
                    reasons.append(reason)
                    row_outcomes.append(
                        (
                            ordinal,
                            decision_at,
                            instrument.value,
                            "not_available",
                            None,
                            None,
                            json.dumps([reason]),
                            None,
                        )
                    )
                else:
                    state, close, selected_id, selected_at, evidence_id, reason = selected
                    row[f"{item.name}_close"] = close
                    row[f"{item.name}_state"] = state
                    row[f"{item.name}_reason"] = reason
                    if state in {"unavailable", "no_trade", "partial"}:
                        usable = False
                        reasons.append(reason)
                    row_outcomes.append(
                        (
                            ordinal,
                            decision_at,
                            instrument.value,
                            "selected" if state == "selected" else state,
                            selected_id,
                            selected_at,
                            json.dumps([] if state == "selected" else [reason]),
                            evidence_id,
                        )
                    )
            lineage = scoped_content_id(
                {
                    "schema": "persistra.research.dataset_row_lineage",
                    "decision_at": decision_at,
                    "instrument_id": instrument,
                    "outcomes": _identity_value(row_outcomes),
                }
            )
            row["research_row_usable"] = usable
            row["research_primary_reason_code"] = (
                "research.row.usable" if usable else reasons[0]
            )
            row["research_reason_codes_json"] = json.dumps(reasons, separators=(",", ":"))
            row["research_row_lineage_content_id"] = str(lineage)
            audit.append(
                (
                    decision_at,
                    eligibility_row["session_date"],
                    instrument.value,
                    True,
                    included,
                    usable,
                    row["research_primary_reason_code"],
                    row["research_reason_codes_json"],
                    str(lineage),
                )
            )
            outcomes.extend(row_outcomes)
            if included:
                output.append(row)
        return output, audit, outcomes

    def _select_bar(
        self,
        item: DailyBarInput,
        instrument: InstrumentId,
        decision_at: datetime,
        context: AsOfContext,
    ) -> tuple[str, float | None, Any, Any, str, str] | None:
        start = decision_at - item.max_age.to_timedelta()
        query = BarQuery(
            (instrument,),
            item.spec,
            start,
            decision_at,
            context,
            include_partial=False,
            include_no_trade=True,
            max_rows=10_000,
        )
        if item.adjustment_mode is AdjustmentPriceMode.RAW:
            frame = self._project.services.market.bars.query(query)
            close_column = "close"
            status_column = "bar_state"
        else:
            frame = self._project.services.market.adjustments.view(
                AdjustmentViewRequest(query, item.adjustment_mode, decision_at)
            ).bars()
            close_column = "adjusted_close"
            status_column = "adjustment_status"
        if frame.empty:
            return None
        selected = frame.iloc[-1]
        raw_state = selected["bar_state"]
        if raw_state == BarState.NO_TRADE.value:
            state = "no_trade"
            reason = "market.price.no_trade"
        elif item.adjustment_mode is not AdjustmentPriceMode.RAW and selected[
            status_column
        ] == "unavailable":
            state = "unavailable"
            reason = "adjustment.unavailable"
        else:
            state = "selected"
            reason = "market.price.selected"
        evidence = scoped_content_id(
            {
                "schema": "persistra.research.input_outcome",
                "canonical_revision_id": selected["canonical_revision_id"],
                "decision_at": decision_at,
                "mode": item.adjustment_mode,
            }
        )
        close = selected[close_column]
        return (
            state,
            None if pd.isna(close) else float(close),
            selected["canonical_revision_id"],
            selected["interval_end"].to_pydatetime(),
            str(evidence),
            reason,
        )


@dataclass(frozen=True, slots=True)
class ResearchDatasetBuild:
    """Project-bound immutable handle for one completed dataset build."""

    _project: Project
    reference: ResearchDatasetBuildRef
    _relation: str

    def rows(self, *, include_unusable: bool = True, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        filter_sql = "" if include_unusable else " AND research_row_usable"
        rows = connection.execute(
            f'SELECT * FROM research_data."{self._relation}" '
            f"WHERE research_dataset_build_id = ?{filter_sql} "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            [self.reference.research_dataset_build_id.value, max_rows + 1],
        ).fetchdf()
        if len(rows) > max_rows:
            raise ResearchResultLimitError("dataset rows exceed max_rows")
        return _normalize_frame(rows)

    def decision_rows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self.rows(include_unusable=False, max_rows=max_rows)

    def eligibility_audit(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT * FROM research.research_dataset_row_audit "
            "WHERE research_dataset_build_id = ? "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            [self.reference.research_dataset_build_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("dataset audit exceeds max_rows")
        return _normalize_frame(frame)

    def input_outcomes(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT * FROM research.research_dataset_input_outcomes "
            "WHERE research_dataset_build_id = ? "
            "ORDER BY decision_at, instrument_id, input_ordinal LIMIT ?",
            [self.reference.research_dataset_build_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("dataset input outcomes exceed max_rows")
        return _normalize_frame(frame)

    def iter_rows(self, *, chunk_rows: int = 100_000) -> Iterator[pd.DataFrame]:
        if chunk_rows < 1:
            raise ResearchResultLimitError("chunk_rows must be positive")
        frame = self.rows(max_rows=max(self.reference.row_count, 1))
        for start in range(0, len(frame), chunk_rows):
            yield frame.iloc[start : start + chunk_rows].reset_index(drop=True)


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column.endswith("_id") or column.endswith("_content_id"):
            frame[column] = frame[column].astype("string")
        if column.endswith("_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame
