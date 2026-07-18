"""Managed rank signals and equal-weight construction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import (
    identity_bytes,
)
from persistra._identity import (
    scoped_identity_content_id as scoped_content_id,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    PortfolioConstructionError,
    ResearchResultLimitError,
    SignalDefinitionError,
)
from persistra.portfolio.models import (
    ConstructionRequest,
    ConstructionStatus,
    ConstructorRef,
    EqualWeightConstructorDefinition,
    PortfolioConstructionResultId,
    PortfolioConstructionResultRef,
    PortfolioConstructorId,
    RankSignalDefinition,
    ResolvedConstructorRef,
    ResolvedSignalRef,
    SignalDefinitionId,
    SignalMaterializationId,
    SignalMaterializationRef,
    SignalRef,
    SignalValueState,
)
from persistra.research.features import FeatureMaterializationId, FeatureValueState

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


class SignalService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: RankSignalDefinition) -> ResolvedSignalRef:
        self._require_write()
        encoded = identity_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.portfolio.signal_definition@1", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedSignalRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.signal_definition_id, v.definition_content_id, "
                "v.definition_json FROM portfolio.signal_definitions d JOIN "
                "portfolio.signal_versions v USING (signal_definition_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise SignalDefinitionError("signal version conflicts")
                return ResolvedSignalRef(
                    SignalDefinitionId.parse(existing[0]), definition.version, content_id
                )
            prior = connection.execute(
                "SELECT d.signal_definition_id, max(v.definition_version) FROM "
                "portfolio.signal_definitions d LEFT JOIN portfolio.signal_versions v "
                "USING (signal_definition_id) WHERE d.qualified_name = ? "
                "GROUP BY d.signal_definition_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise SignalDefinitionError("first signal version must be one")
                definition_id = SignalDefinitionId.new()
                connection.execute(
                    "INSERT INTO portfolio.signal_definitions VALUES (?, ?, ?)",
                    [definition_id.value, str(definition.name), context.recorded_at],
                )
            else:
                definition_id = SignalDefinitionId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise SignalDefinitionError("signal versions must be contiguous")
            connection.execute(
                "INSERT INTO portfolio.signal_versions VALUES (?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            return ResolvedSignalRef(definition_id, definition.version, content_id)

        return self._project.services.transactions.run("signal_register", operation)

    def resolve(self, reference: SignalRef) -> ResolvedSignalRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.signal_definition_id, v.definition_content_id FROM "
            "portfolio.signal_definitions d JOIN portfolio.signal_versions v "
            "USING (signal_definition_id) WHERE d.qualified_name = ? "
            "AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise SignalDefinitionError("signal is not registered")
        return ResolvedSignalRef(
            SignalDefinitionId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def materialize(
        self, *, definition: SignalRef, feature: FeatureMaterializationId
    ) -> SignalMaterialization:
        self._require_write()
        resolved = self.resolve(definition)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        definition_row = connection.execute(
            "SELECT definition_json FROM portfolio.signal_versions WHERE "
            "signal_definition_id = ? AND definition_version = ?",
            [resolved.signal_definition_id.value, resolved.version],
        ).fetchone()
        feature_row = connection.execute(
            "SELECT output_manifest_content_id FROM research.feature_materializations "
            "WHERE feature_materialization_id = ?",
            [feature.value],
        ).fetchone()
        if definition_row is None or feature_row is None:
            raise SignalDefinitionError("signal definition or feature is missing")
        value = cast("dict[str, Any]", json.loads(definition_row[0]))
        ascending = bool(value["ascending"])
        frame = connection.execute(
            "SELECT decision_at, session_date, instrument_id, value, state, "
            "logical_available_at, lineage_content_id FROM research_data.feature_values "
            "WHERE feature_materialization_id = ? ORDER BY decision_at, instrument_id",
            [feature.value],
        ).fetchdf()
        output = _rank_values(frame, ascending=ascending)
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.signal_execution@1",
                "definition": resolved,
                "feature": feature,
                "feature_manifest": feature_row[0],
            }
        )
        output_content_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.signal_output@1",
                "execution": execution_content_id,
                "rows": output,
            }
        )

        def operation(context: TransactionContext) -> SignalMaterialization:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT signal_materialization_id FROM "
                "portfolio.signal_materializations WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(SignalMaterializationId.parse(existing[0]))
            materialization_id = SignalMaterializationId.new()
            computed_count = sum(row[4] == SignalValueState.COMPUTED.value for row in output)
            active.execute(
                "INSERT INTO portfolio.signal_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    resolved.signal_definition_id.value,
                    resolved.version,
                    feature.value,
                    str(execution_content_id),
                    str(output_content_id),
                    len(output),
                    computed_count,
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO portfolio.signal_values VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(materialization_id.value, *row) for row in output],
            )
            return self.get(materialization_id)

        return self._project.services.transactions.run("signal_materialize", operation)

    def get(self, materialization_id: SignalMaterializationId) -> SignalMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT signal_definition_id, feature_materialization_id, "
            "execution_content_id, output_manifest_content_id, row_count, computed_count "
            "FROM portfolio.signal_materializations WHERE signal_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise SignalDefinitionError("signal materialization is missing")
        return SignalMaterialization(
            self._project,
            SignalMaterializationRef(
                materialization_id,
                SignalDefinitionId.parse(row[0]),
                FeatureMaterializationId.parse(row[1]),
                ContentId.parse(row[2]),
                ContentId.parse(row[3]),
                int(row[4]),
                int(row[5]),
            ),
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("signal writes require research_write mode")


def _rank_values(frame: pd.DataFrame, *, ascending: bool) -> list[tuple[Any, ...]]:
    output: list[tuple[Any, ...]] = []
    for _, group in frame.groupby("decision_at", sort=True):
        computed = group[
            (group["state"] == FeatureValueState.COMPUTED.value) & group["value"].notna()
        ].copy()
        count = len(computed)
        rank_map: dict[str, float] = {}
        if count:
            ranks = computed["value"].rank(method="average", ascending=ascending)
            normalized = (
                pd.Series([0.5] * count, index=computed.index)
                if count == 1
                else (ranks - 1.0) / (count - 1.0)
            )
            rank_map = {
                str(computed.loc[index, "instrument_id"]): float(
                    cast("Any", normalized.loc[index])
                )
                for index in computed.index
            }
        for _, item in group.sort_values("instrument_id").iterrows():
            instrument = str(item["instrument_id"])
            if instrument in rank_map:
                state = SignalValueState.COMPUTED
                signal_value: float | None = rank_map[instrument]
                reason = None
            else:
                state = SignalValueState.UPSTREAM_NONCOMPUTED
                signal_value = None
                reason = "signal.upstream.noncomputed"
            lineage = scoped_content_id(
                {
                    "schema": "persistra.portfolio.signal_row@1",
                    "feature_lineage": item["lineage_content_id"],
                    "decision_at": item["decision_at"].isoformat(),
                    "instrument_id": instrument,
                    "cross_section_count": count,
                    "value": signal_value,
                }
            )
            output.append(
                (
                    item["decision_at"].to_pydatetime(),
                    pd.Timestamp(item["session_date"]).date(),
                    item["instrument_id"],
                    signal_value,
                    state.value,
                    reason,
                    item["logical_available_at"].to_pydatetime(),
                    str(lineage),
                )
            )
    output.sort(key=lambda row: (row[0], str(row[2])))
    return output


@dataclass(frozen=True, slots=True)
class SignalMaterialization:
    _project: Project
    reference: SignalMaterializationRef

    def rows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT decision_at, session_date, instrument_id, value, state, "
            "reason_code, logical_available_at, lineage_content_id FROM "
            "portfolio.signal_values WHERE signal_materialization_id = ? "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            [self.reference.signal_materialization_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("signal rows exceed max_rows")
        return _normalize(frame)


class ConstructorService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: EqualWeightConstructorDefinition
    ) -> ResolvedConstructorRef:
        self._require_write()
        encoded = identity_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.portfolio.constructor_definition@1", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedConstructorRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.portfolio_constructor_id, v.definition_content_id, "
                "v.definition_json FROM portfolio.constructor_definitions d JOIN "
                "portfolio.constructor_versions v USING (portfolio_constructor_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise PortfolioConstructionError("constructor version conflicts")
                return ResolvedConstructorRef(
                    PortfolioConstructorId.parse(existing[0]), definition.version, content_id
                )
            prior = connection.execute(
                "SELECT d.portfolio_constructor_id, max(v.definition_version) FROM "
                "portfolio.constructor_definitions d LEFT JOIN "
                "portfolio.constructor_versions v USING (portfolio_constructor_id) "
                "WHERE d.qualified_name = ? GROUP BY d.portfolio_constructor_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise PortfolioConstructionError(
                        "first constructor version must be one"
                    )
                constructor_id = PortfolioConstructorId.new()
                connection.execute(
                    "INSERT INTO portfolio.constructor_definitions VALUES (?, ?, ?)",
                    [constructor_id.value, str(definition.name), context.recorded_at],
                )
            else:
                constructor_id = PortfolioConstructorId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise PortfolioConstructionError(
                        "constructor versions must be contiguous"
                    )
            connection.execute(
                "INSERT INTO portfolio.constructor_versions VALUES (?, ?, ?, ?, ?)",
                [
                    constructor_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            return ResolvedConstructorRef(constructor_id, definition.version, content_id)

        return self._project.services.transactions.run("constructor_register", operation)

    def resolve(self, reference: ConstructorRef) -> ResolvedConstructorRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.portfolio_constructor_id, v.definition_content_id FROM "
            "portfolio.constructor_definitions d JOIN portfolio.constructor_versions v "
            "USING (portfolio_constructor_id) WHERE d.qualified_name = ? "
            "AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise PortfolioConstructionError("constructor is not registered")
        return ResolvedConstructorRef(
            PortfolioConstructorId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def construct(self, request: ConstructionRequest) -> PortfolioConstructionResult:
        self._require_write()
        resolved = self.resolve(request.constructor)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        definition_row = connection.execute(
            "SELECT definition_json FROM portfolio.constructor_versions WHERE "
            "portfolio_constructor_id = ? AND definition_version = ?",
            [resolved.portfolio_constructor_id.value, resolved.version],
        ).fetchone()
        signal_row = connection.execute(
            "SELECT output_manifest_content_id FROM portfolio.signal_materializations "
            "WHERE signal_materialization_id = ?",
            [request.signal_materialization_id.value],
        ).fetchone()
        if definition_row is None or signal_row is None:
            raise PortfolioConstructionError("constructor or signal is missing")
        definition_value = cast("dict[str, Any]", json.loads(definition_row[0]))
        minimum_rank = float(definition_value["minimum_rank"])
        frame = connection.execute(
            "SELECT decision_at, session_date, instrument_id, value, state FROM "
            "portfolio.signal_values WHERE signal_materialization_id = ? "
            "ORDER BY decision_at, instrument_id",
            [request.signal_materialization_id.value],
        ).fetchdf()
        if request.start_at is not None:
            frame = frame[frame["decision_at"] >= request.start_at]
        if request.end_at is not None:
            frame = frame[frame["decision_at"] < request.end_at]
        decisions, weights = _construct_monthly(frame, minimum_rank)
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.construction_execution@1",
                "constructor": resolved,
                "signal": request.signal_materialization_id,
                "signal_manifest": signal_row[0],
                "start_at": request.start_at,
                "end_at": request.end_at,
            }
        )
        output_content_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.construction_output@1",
                "execution": execution_content_id,
                "decisions": decisions,
                "weights": weights,
            }
        )

        def operation(context: TransactionContext) -> PortfolioConstructionResult:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT portfolio_construction_result_id FROM "
                "portfolio.construction_results WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(PortfolioConstructionResultId.parse(existing[0]))
            result_id = PortfolioConstructionResultId.new()
            active.execute(
                "INSERT INTO portfolio.construction_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    result_id.value,
                    resolved.portfolio_constructor_id.value,
                    resolved.version,
                    request.signal_materialization_id.value,
                    str(execution_content_id),
                    str(output_content_id),
                    len(decisions),
                    len(weights),
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO portfolio.target_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(result_id.value, *row) for row in decisions],
            )
            active.executemany(
                "INSERT INTO portfolio.target_weights VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(result_id.value, *row) for row in weights],
            )
            return self.get(result_id)

        return self._project.services.transactions.run("portfolio_construct", operation)

    def get(self, result_id: PortfolioConstructionResultId) -> PortfolioConstructionResult:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT portfolio_constructor_id, signal_materialization_id, "
            "execution_content_id, output_manifest_content_id, decision_count, "
            "target_row_count FROM portfolio.construction_results WHERE "
            "portfolio_construction_result_id = ?",
            [result_id.value],
        ).fetchone()
        if row is None:
            raise PortfolioConstructionError("construction result is missing")
        return PortfolioConstructionResult(
            self._project,
            PortfolioConstructionResultRef(
                result_id,
                PortfolioConstructorId.parse(row[0]),
                SignalMaterializationId.parse(row[1]),
                ContentId.parse(row[2]),
                ContentId.parse(row[3]),
                int(row[4]),
                int(row[5]),
            ),
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "portfolio construction requires research_write mode"
            )


def _construct_monthly(
    frame: pd.DataFrame, minimum_rank: float
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    if frame.empty:
        return [], []
    frame = frame.copy()
    session_dates = pd.to_datetime(frame["session_date"])
    frame["_month"] = session_dates.dt.to_period("M").astype(str)
    frame["_session_text"] = session_dates.dt.strftime("%Y-%m-%d")
    monthly_frames: list[pd.DataFrame] = []
    for _, month_group in frame.groupby("_month", sort=True):
        last_date = max(str(value) for value in month_group["_session_text"])
        monthly_frames.append(month_group[month_group["_session_text"] == last_date])
    selected_frame = pd.concat(monthly_frames, ignore_index=True)
    decisions: list[tuple[Any, ...]] = []
    weights: list[tuple[Any, ...]] = []
    for decision_at, group in selected_frame.groupby("decision_at", sort=True):
        decision_timestamp = cast("pd.Timestamp", decision_at)
        eligible = group[
            (group["state"] == SignalValueState.COMPUTED.value)
            & group["value"].notna()
            & (group["value"] >= minimum_rank)
        ]
        status = (
            ConstructionStatus.COMPLETED if not eligible.empty else ConstructionStatus.FAILED
        )
        target_weight = 1.0 / len(eligible) if not eligible.empty else 0.0
        target_root = scoped_content_id(
            {
                "schema": "persistra.portfolio.target_decision@1",
                "decision_at": decision_timestamp.isoformat(),
                "selected": sorted(str(item) for item in eligible["instrument_id"]),
                "minimum_rank": minimum_rank,
            }
        )
        first = group.iloc[0]
        decisions.append(
            (
                decision_timestamp.to_pydatetime(),
                pd.Timestamp(first["session_date"]).date(),
                status.value,
                0.0 if status is ConstructionStatus.COMPLETED else None,
                None if status is ConstructionStatus.COMPLETED else "portfolio.empty_selection",
                str(target_root),
            )
        )
        eligible_ids = {str(item) for item in eligible["instrument_id"]}
        for _, item in group.sort_values("instrument_id").iterrows():
            chosen = str(item["instrument_id"]) in eligible_ids
            weights.append(
                (
                    decision_timestamp.to_pydatetime(),
                    item["instrument_id"],
                    None if pd.isna(item["value"]) else float(item["value"]),
                    chosen,
                    target_weight if chosen else 0.0,
                    "targeted" if chosen else "fixed_zero",
                    None if chosen else "portfolio.signal.below_threshold",
                )
            )
    return decisions, weights


@dataclass(frozen=True, slots=True)
class PortfolioConstructionResult:
    _project: Project
    reference: PortfolioConstructionResultRef

    def decisions(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT decision_at, session_date, status, cash_weight, reason_code, "
            "target_content_id FROM portfolio.target_decisions WHERE "
            "portfolio_construction_result_id = ? ORDER BY decision_at LIMIT ?",
            [self.reference.portfolio_construction_result_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("target decisions exceed max_rows")
        return _normalize(frame)

    def weights(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT decision_at, instrument_id, signal_value, selected, target_weight, "
            "state, reason_code FROM portfolio.target_weights WHERE "
            "portfolio_construction_result_id = ? "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            [self.reference.portfolio_construction_result_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("target weights exceed max_rows")
        return _normalize(frame)


class PortfolioService:
    __slots__ = ("constructors", "forecasts", "optimization", "risk", "signals")

    def __init__(self, project: Project) -> None:
        from persistra.portfolio.advanced_services import (
            ForecastService,
            OptimizationService,
            RiskService,
        )

        self.signals = SignalService(project)
        self.constructors = ConstructorService(project)
        self.forecasts = ForecastService(project)
        self.risk = RiskService(project)
        self.optimization = OptimizationService(project)

    def construct(self, request: ConstructionRequest) -> PortfolioConstructionResult:
        return self.constructors.construct(request)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column.endswith("_id"):
            frame[column] = frame[column].astype("string")
        if column.endswith("_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame
