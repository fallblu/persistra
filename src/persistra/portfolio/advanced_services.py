"""Immutable direct forecasts, point-in-time risk, and verified optimization."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd

from persistra.db import ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    ForecastDefinitionError,
    ForecastMaterializationError,
    OptimizationError,
    ResearchResultLimitError,
    RiskModelError,
)
from persistra.portfolio.advanced_models import (
    DirectForecastDefinition,
    ForecastDefinitionId,
    ForecastMaterializationId,
    ForecastMaterializationRef,
    ForecastRef,
    ForecastTargetKind,
    OptimizationAttemptStatus,
    OptimizationRequest,
    OptimizationResultRef,
    PredictionState,
    PsdPolicy,
    RiskEstimateState,
    RiskMaterializationId,
    RiskMaterializationRef,
    RiskModelDefinition,
    RiskModelDefinitionId,
    RiskModelKind,
    RiskModelRef,
)
from persistra.portfolio.models import PortfolioConstructionResultId
from persistra.research.models import ResearchDatasetBuildId

if TYPE_CHECKING:

    from persistra.db.services import TransactionContext
    from persistra.portfolio.safety_models import UnsafeDecisionInputOverride
    from persistra.project import Project


class ForecastService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: DirectForecastDefinition) -> ForecastDefinitionId:
        _require_write(self._project)
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.portfolio.forecast_definition", "value": definition}
        )

        def operation(context: TransactionContext) -> ForecastDefinitionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.forecast_definition_id, v.definition_content_id, "
                "v.definition_json FROM portfolio.forecast_definitions d JOIN "
                "portfolio.forecast_versions v USING (forecast_definition_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise ForecastDefinitionError("forecast version conflicts")
                return ForecastDefinitionId.parse(existing[0])
            prior = connection.execute(
                "SELECT d.forecast_definition_id, max(v.definition_version) FROM "
                "portfolio.forecast_definitions d LEFT JOIN "
                "portfolio.forecast_versions v USING (forecast_definition_id) "
                "WHERE d.qualified_name = ? GROUP BY d.forecast_definition_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise ForecastDefinitionError(
                        "first forecast version must be one"
                    )
                definition_id = ForecastDefinitionId.new()
                connection.execute(
                    "INSERT INTO portfolio.forecast_definitions VALUES (?, ?, ?)",
                    [definition_id.value, str(definition.name), context.recorded_at],
                )
            else:
                definition_id = ForecastDefinitionId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise ForecastDefinitionError(
                        "forecast versions must be contiguous"
                    )
            connection.execute(
                "INSERT INTO portfolio.forecast_versions VALUES (?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            return definition_id

        return self._project.services.transactions.run(
            "forecast_register", operation
        )

    def materialize(
        self,
        reference: ForecastRef,
        *,
        unsafe_override: UnsafeDecisionInputOverride | None = None,
    ) -> ForecastMaterialization:
        _require_write(self._project)
        definition_id, definition, content_id = self._resolve(reference)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        build = _decision_build(
            connection, definition.research_dataset_build_id
        )
        safety = self._project.services.portfolio.decision_inputs.for_dataset(
            definition.research_dataset_build_id
        )
        self._project.services.portfolio.decision_inputs.validate(
            safety, unsafe_override
        )
        relation = str(build[0]).replace('"', '""')
        required = (
            "decision_at",
            "instrument_id",
            definition.feature_output,
            f"{definition.feature_output}_state",
            f"{definition.feature_output}_available_at",
            f"{definition.feature_output}_lineage_content_id",
        )
        quoted = ", ".join(f'"{item}"' for item in required)
        try:
            frame = cast(
                "pd.DataFrame",
                connection.execute(
                    f'SELECT {quoted} FROM research_data."{relation}" '
                    "ORDER BY decision_at, instrument_id"
                ).fetchdf(),
            )
        except Exception as error:
            raise ForecastMaterializationError(
                "forecast feature output is unavailable"
            ) from error
        multiplier, intercept = float(definition.multiplier), float(definition.intercept)
        rows: list[tuple[object, ...]] = []
        for item in frame.to_dict("records"):
            state = PredictionState.COMPUTED
            value: float | None = None
            reason: str | None = None
            if item[f"{definition.feature_output}_state"] != "computed":
                state = PredictionState.INPUT_MISSING
                reason = "forecast.input.noncomputed"
            else:
                value = float(item[definition.feature_output]) * multiplier + intercept
                if not math.isfinite(value):
                    value = None
                    state = PredictionState.INVALID_NUMERIC
                    reason = "forecast.numeric.invalid"
            lineage = scoped_content_id(
                {
                    "schema": "persistra.portfolio.forecast_row",
                    "definition_content_id": content_id,
                    "source_lineage": item[
                        f"{definition.feature_output}_lineage_content_id"
                    ],
                    "value": None if value is None else value.hex(),
                }
            )
            rows.append(
                (
                    item["decision_at"],
                    item["instrument_id"],
                    value,
                    state.value,
                    reason,
                    (
                        item[f"{definition.feature_output}_available_at"]
                        if state is PredictionState.COMPUTED
                        else None
                    ),
                    str(lineage),
                )
            )
        output_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.forecast_output",
                "rows": tuple(
                    (
                        row[0],
                        str(row[1]),
                        None
                        if row[2] is None
                        else cast("float", row[2]).hex(),
                        *row[3:],
                    )
                    for row in rows
                ),
            }
        )
        execution_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.forecast_execution",
                "definition_content_id": content_id,
                "dataset_manifest": ContentId.parse(build[1]),
                "decision_input_manifest": safety.manifest_content_id,
                "unsafe_override": unsafe_override,
                "output": output_id,
            }
        )

        def operation(context: TransactionContext) -> ForecastMaterialization:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT forecast_materialization_id FROM "
                "portfolio.forecast_materializations WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            if existing is not None:
                return self.get(ForecastMaterializationId.parse(existing[0]))
            materialization_id = ForecastMaterializationId.new()
            computed = sum(row[3] == PredictionState.COMPUTED.value for row in rows)
            active.execute(
                "INSERT INTO portfolio.forecast_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    definition_id.value,
                    definition.version,
                    definition.research_dataset_build_id.value,
                    str(execution_id),
                    str(output_id),
                    len(rows),
                    computed,
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO portfolio.forecast_values VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                [(materialization_id.value, *row) for row in rows],
            )
            self._project.services.portfolio.decision_inputs.bind(
                artifact_kind="forecast_materialization",
                artifact_id=materialization_id,
                manifest=safety,
                override=unsafe_override,
                created_at=context.recorded_at,
            )
            return self.get(materialization_id)

        return self._project.services.transactions.run(
            "forecast_materialize", operation
        )

    def get(self, materialization_id: ForecastMaterializationId) -> ForecastMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT forecast_definition_id, research_dataset_build_id, "
            "execution_content_id, output_content_id, row_count, computed_count "
            "FROM portfolio.forecast_materializations "
            "WHERE forecast_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise ForecastMaterializationError("forecast materialization is unavailable")
        return ForecastMaterialization(
            self._project,
            ForecastMaterializationRef(
                materialization_id,
                ForecastDefinitionId.parse(row[0]),
                ResearchDatasetBuildId.parse(row[1]),
                ContentId.parse(row[2]),
                ContentId.parse(row[3]),
                int(row[4]),
                int(row[5]),
            ),
        )

    def _resolve(
        self, reference: ForecastRef
    ) -> tuple[ForecastDefinitionId, DirectForecastDefinition, ContentId]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.forecast_definition_id, v.definition_content_id, "
            "v.definition_json FROM portfolio.forecast_definitions d JOIN "
            "portfolio.forecast_versions v USING (forecast_definition_id) "
            "WHERE d.qualified_name = ? AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise ForecastDefinitionError("forecast definition is unavailable")
        value = cast("dict[str, Any]", json.loads(row[2]))
        definition = DirectForecastDefinition(
            QualifiedName(value["name"]),
            int(value["version"]),
            ResearchDatasetBuildId.parse(value["research_dataset_build_id"]),
            str(value["feature_output"]),
            ForecastTargetKind(value["target_kind"]),
            int(value["horizon_decisions"]),
            str(value["multiplier"]),
            str(value["intercept"]),
        )
        return (
            ForecastDefinitionId.parse(row[0]),
            definition,
            ContentId.parse(row[1]),
        )


@dataclass(frozen=True, slots=True)
class ForecastMaterialization:
    _project: Project
    reference: ForecastMaterializationRef

    def rows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return _bounded_rows(
            self._project,
            "SELECT * FROM portfolio.forecast_values "
            "WHERE forecast_materialization_id = ? "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            self.reference.forecast_materialization_id.value,
            max_rows,
        )


class RiskService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: RiskModelDefinition) -> RiskModelDefinitionId:
        _require_write(self._project)
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.portfolio.risk_definition", "value": definition}
        )

        def operation(context: TransactionContext) -> RiskModelDefinitionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.risk_model_definition_id, v.definition_content_id, "
                "v.definition_json FROM portfolio.risk_model_definitions d JOIN "
                "portfolio.risk_model_versions v USING (risk_model_definition_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise RiskModelError("risk model version conflicts")
                return RiskModelDefinitionId.parse(existing[0])
            prior = connection.execute(
                "SELECT d.risk_model_definition_id, max(v.definition_version) "
                "FROM portfolio.risk_model_definitions d LEFT JOIN "
                "portfolio.risk_model_versions v USING (risk_model_definition_id) "
                "WHERE d.qualified_name = ? GROUP BY d.risk_model_definition_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise RiskModelError("first risk model version must be one")
                definition_id = RiskModelDefinitionId.new()
                connection.execute(
                    "INSERT INTO portfolio.risk_model_definitions VALUES (?, ?, ?)",
                    [definition_id.value, str(definition.name), context.recorded_at],
                )
            else:
                definition_id = RiskModelDefinitionId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise RiskModelError("risk model versions must be contiguous")
            connection.execute(
                "INSERT INTO portfolio.risk_model_versions VALUES (?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            return definition_id

        return self._project.services.transactions.run("risk_register", operation)

    def materialize(
        self,
        reference: RiskModelRef,
        *,
        unsafe_override: UnsafeDecisionInputOverride | None = None,
    ) -> RiskMaterialization:
        _require_write(self._project)
        definition_id, definition, content_id = self._resolve(reference)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        build = _decision_build(connection, definition.research_dataset_build_id)
        safety = self._project.services.portfolio.decision_inputs.for_dataset(
            definition.research_dataset_build_id
        )
        self._project.services.portfolio.decision_inputs.validate(
            safety, unsafe_override
        )
        relation = str(build[0]).replace('"', '""')
        output = definition.return_output
        try:
            frame = cast(
                "pd.DataFrame",
                connection.execute(
                    f'SELECT decision_at, instrument_id, "{output}", '
                    f'"{output}_state" FROM research_data."{relation}" '
                    "ORDER BY decision_at, instrument_id"
                ).fetchdf(),
            )
        except Exception as error:
            raise RiskModelError("risk return output is unavailable") from error
        rows = _risk_rows(definition, frame)
        output_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.risk_output",
                "rows": tuple(
                    (
                        row[0],
                        str(row[1]),
                        str(row[2]),
                        None if row[3] is None else cast("float", row[3]).hex(),
                        *row[4:],
                    )
                    for row in rows
                ),
            }
        )
        execution_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.risk_execution",
                "definition_content_id": content_id,
                "dataset_manifest": ContentId.parse(build[1]),
                "decision_input_manifest": safety.manifest_content_id,
                "unsafe_override": unsafe_override,
                "output": output_id,
            }
        )

        def operation(context: TransactionContext) -> RiskMaterialization:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT risk_materialization_id FROM "
                "portfolio.risk_materializations WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            if existing is not None:
                return self.get(RiskMaterializationId.parse(existing[0]))
            materialization_id = RiskMaterializationId.new()
            active.execute(
                "INSERT INTO portfolio.risk_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    definition_id.value,
                    definition.version,
                    definition.research_dataset_build_id.value,
                    str(execution_id),
                    str(output_id),
                    len(rows),
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO portfolio.risk_covariances VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                [(materialization_id.value, *row) for row in rows],
            )
            self._project.services.portfolio.decision_inputs.bind(
                artifact_kind="risk_materialization",
                artifact_id=materialization_id,
                manifest=safety,
                override=unsafe_override,
                created_at=context.recorded_at,
            )
            return self.get(materialization_id)

        return self._project.services.transactions.run(
            "risk_materialize", operation
        )

    def get(self, materialization_id: RiskMaterializationId) -> RiskMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT risk_model_definition_id, research_dataset_build_id, "
            "execution_content_id, output_content_id, estimate_count FROM "
            "portfolio.risk_materializations WHERE risk_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise RiskModelError("risk materialization is unavailable")
        return RiskMaterialization(
            self._project,
            RiskMaterializationRef(
                materialization_id,
                RiskModelDefinitionId.parse(row[0]),
                ResearchDatasetBuildId.parse(row[1]),
                ContentId.parse(row[2]),
                ContentId.parse(row[3]),
                int(row[4]),
            ),
        )

    def _resolve(
        self, reference: RiskModelRef
    ) -> tuple[RiskModelDefinitionId, RiskModelDefinition, ContentId]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.risk_model_definition_id, v.definition_content_id, "
            "v.definition_json FROM portfolio.risk_model_definitions d JOIN "
            "portfolio.risk_model_versions v USING (risk_model_definition_id) "
            "WHERE d.qualified_name = ? AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise RiskModelError("risk model definition is unavailable")
        value = cast("dict[str, Any]", json.loads(row[2]))
        definition = RiskModelDefinition(
            QualifiedName(value["name"]),
            int(value["version"]),
            ResearchDatasetBuildId.parse(value["research_dataset_build_id"]),
            str(value["return_output"]),
            RiskModelKind(value["kind"]),
            int(value["lookback_decisions"]),
            int(value["minimum_observations"]),
            str(value["ewma_decay"]),
            str(value["shrinkage"]),
            PsdPolicy(value["psd_policy"]),
        )
        return (
            RiskModelDefinitionId.parse(row[0]),
            definition,
            ContentId.parse(row[1]),
        )


@dataclass(frozen=True, slots=True)
class RiskMaterialization:
    _project: Project
    reference: RiskMaterializationRef

    def covariances(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return _bounded_rows(
            self._project,
            "SELECT * FROM portfolio.risk_covariances "
            "WHERE risk_materialization_id = ? "
            "ORDER BY decision_at, row_instrument_id, column_instrument_id LIMIT ?",
            self.reference.risk_materialization_id.value,
            max_rows,
        )


class OptimizationService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def construct(self, request: OptimizationRequest) -> OptimizationResult:
        _require_write(self._project)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        forecast_meta = connection.execute(
            "SELECT research_dataset_build_id, output_content_id FROM "
            "portfolio.forecast_materializations WHERE forecast_materialization_id = ?",
            [request.forecast_materialization_id.value],
        ).fetchone()
        risk_meta = connection.execute(
            "SELECT research_dataset_build_id, output_content_id FROM "
            "portfolio.risk_materializations WHERE risk_materialization_id = ?",
            [request.risk_materialization_id.value],
        ).fetchone()
        if (
            forecast_meta is None
            or risk_meta is None
            or forecast_meta[0] != risk_meta[0]
        ):
            raise OptimizationError(
                "forecast and risk inputs must share one exact base dataset"
            )
        forecast_safety = self._project.services.portfolio.decision_inputs.for_artifact(
            "forecast_materialization", request.forecast_materialization_id
        )
        risk_safety = self._project.services.portfolio.decision_inputs.for_artifact(
            "risk_materialization", request.risk_materialization_id
        )
        if forecast_safety.manifest_content_id != risk_safety.manifest_content_id:
            raise OptimizationError(
                "forecast and risk inputs have different safety manifests"
            )
        self._project.services.portfolio.decision_inputs.validate(
            forecast_safety, request.unsafe_override
        )
        forecast = cast(
            "pd.DataFrame",
            connection.execute(
                "SELECT instrument_id, expected_return FROM "
                "portfolio.forecast_values WHERE forecast_materialization_id = ? "
                "AND decision_at = ? AND prediction_state = 'computed' "
                "ORDER BY instrument_id",
                [request.forecast_materialization_id.value, request.decision_at],
            ).fetchdf(),
        )
        covariance_rows = cast(
            "pd.DataFrame",
            connection.execute(
                "SELECT row_instrument_id, column_instrument_id, covariance FROM "
                "portfolio.risk_covariances WHERE risk_materialization_id = ? "
                "AND decision_at = ? AND estimate_state = 'computed' "
                "ORDER BY row_instrument_id, column_instrument_id",
                [request.risk_materialization_id.value, request.decision_at],
            ).fetchdf(),
        )
        if forecast.empty or covariance_rows.empty:
            raise OptimizationError(
                "forecast or risk estimate is unavailable at the decision"
            )
        assets = [str(item) for item in forecast["instrument_id"]]
        covariance = (
            covariance_rows.assign(
                row_instrument_id=covariance_rows["row_instrument_id"].astype(str),
                column_instrument_id=covariance_rows[
                    "column_instrument_id"
                ].astype(str),
            )
            .pivot(
                index="row_instrument_id",
                columns="column_instrument_id",
                values="covariance",
            )
            .reindex(index=assets, columns=assets)
        )
        if covariance.isna().any().any():
            raise OptimizationError("risk covariance does not cover forecast assets")
        matrix = covariance.to_numpy(dtype="float64")
        matrix = (matrix + matrix.T) / 2
        if float(np.linalg.eigvalsh(matrix).min()) < -1e-10:
            raise OptimizationError("optimization covariance is not positive semidefinite")
        expected = forecast["expected_return"].to_numpy(dtype="float64")
        current_by_id = dict(request.current_weights)
        current = np.asarray(
            [float(current_by_id.get(asset, "0")) for asset in assets],
            dtype="float64",
        )
        cp = _cvxpy()
        weights = cp.Variable(len(assets))
        risk_aversion = float(request.risk_aversion)
        turnover_penalty = float(request.turnover_penalty)
        objective = cp.Maximize(
            expected @ weights
            - risk_aversion * cp.quad_form(weights, cp.psd_wrap(matrix))
            - turnover_penalty * cp.norm1(weights - current)
        )
        maximum = float(request.maximum_weight)
        gross = float(request.gross_limit)
        net = float(request.net_target)
        constraints = [
            weights >= 0,
            weights <= maximum,
            cp.sum(weights) == net,
            cp.norm1(weights) <= gross,
        ]
        problem = cp.Problem(objective, constraints)
        installed = set(cp.installed_solvers())
        solver = next(
            (name for name in ("CLARABEL", "OSQP", "SCS") if name in installed),
            None,
        )
        if solver is None:
            raise OptimizationError("no supported convex solver is installed")
        try:
            problem.solve(solver=solver, warm_start=False, verbose=False)
        except Exception as error:
            raise OptimizationError("convex solver failed") from error
        if problem.status != cp.OPTIMAL or weights.value is None:
            raise OptimizationError(
                f"optimization did not produce an optimal result: {problem.status}"
            )
        target = np.asarray(weights.value, dtype="float64").reshape(-1)
        violations = (
            max(0.0, float(-target.min())),
            max(0.0, float(target.max() - maximum)),
            abs(float(target.sum() - net)),
            max(0.0, float(np.abs(target).sum() - gross)),
        )
        maximum_violation = max(violations)
        if (
            not np.isfinite(target).all()
            or maximum_violation > 1e-6
            or problem.value is None
            or not math.isfinite(float(problem.value))
        ):
            raise OptimizationError(
                "independent post-solve verification rejected the result"
            )
        output_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.optimization_output",
                "weights": tuple(
                    (asset, float(value).hex())
                    for asset, value in zip(assets, target, strict=True)
                ),
                "maximum_violation": maximum_violation.hex(),
            }
        )
        execution_id = scoped_content_id(
            {
                "schema": "persistra.portfolio.optimization_execution",
                "request": request,
                "forecast_output": ContentId.parse(forecast_meta[1]),
                "risk_output": ContentId.parse(risk_meta[1]),
                "decision_input_manifest": forecast_safety.manifest_content_id,
                "solver": solver,
                "output": output_id,
            }
        )

        def operation(context: TransactionContext) -> OptimizationResult:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT portfolio_construction_result_id FROM "
                "portfolio.optimization_results WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            if existing is not None:
                return self.get(PortfolioConstructionResultId.parse(existing[0]))
            result_id = PortfolioConstructionResultId.new()
            active.execute(
                "INSERT INTO portfolio.optimization_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    result_id.value,
                    request.forecast_materialization_id.value,
                    request.risk_materialization_id.value,
                    request.decision_at,
                    str(execution_id),
                    str(output_id),
                    OptimizationAttemptStatus.OPTIMAL.value,
                    solver,
                    float(problem.value),
                    maximum_violation,
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO portfolio.optimization_weights VALUES "
                "(?, ?, ?, ?, ?)",
                [
                    (
                        result_id.value,
                        asset,
                        float(expected[index]),
                        float(target[index]),
                        float(current[index]),
                    )
                    for index, asset in enumerate(assets)
                ],
            )
            self._project.services.portfolio.decision_inputs.bind(
                artifact_kind="portfolio_construction_result",
                artifact_id=result_id,
                manifest=forecast_safety,
                override=request.unsafe_override,
                created_at=context.recorded_at,
            )
            return self.get(result_id)

        return self._project.services.transactions.run(
            "portfolio_optimize", operation
        )

    def get(self, result_id: PortfolioConstructionResultId) -> OptimizationResult:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT forecast_materialization_id, risk_materialization_id, "
            "decision_at, execution_content_id, output_content_id, attempt_status, "
            "solver_name, objective_value, maximum_violation FROM "
            "portfolio.optimization_results WHERE portfolio_construction_result_id = ?",
            [result_id.value],
        ).fetchone()
        if row is None:
            raise OptimizationError("optimization result is unavailable")
        return OptimizationResult(
            self._project,
            OptimizationResultRef(
                result_id,
                ForecastMaterializationId.parse(row[0]),
                RiskMaterializationId.parse(row[1]),
                row[2],
                ContentId.parse(row[3]),
                ContentId.parse(row[4]),
                OptimizationAttemptStatus(row[5]),
                str(row[6]),
                None if row[7] is None else float(row[7]),
                float(row[8]),
            ),
        )


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    _project: Project
    reference: OptimizationResultRef

    def weights(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        return _bounded_rows(
            self._project,
            "SELECT * FROM portfolio.optimization_weights "
            "WHERE portfolio_construction_result_id = ? ORDER BY instrument_id LIMIT ?",
            self.reference.portfolio_construction_result_id.value,
            max_rows,
        )


def _risk_rows(
    definition: RiskModelDefinition, frame: pd.DataFrame
) -> list[tuple[object, ...]]:
    output = definition.return_output
    valid = frame[frame[f"{output}_state"] == "computed"].copy()
    valid[output] = pd.to_numeric(valid[output], errors="coerce")
    pivot = valid.pivot(
        index="decision_at", columns="instrument_id", values=output
    ).sort_index()
    rows: list[tuple[object, ...]] = []
    decisions = list(pivot.index)
    for index, decision in enumerate(decisions):
        start = max(0, index - definition.lookback_decisions + 1)
        window = pivot.iloc[start : index + 1]
        assets = sorted(pivot.columns, key=str)
        if len(window) < definition.minimum_observations:
            for row_asset in assets:
                for column_asset in assets:
                    rows.append(
                        (
                            pd.Timestamp(decision).to_pydatetime(),
                            row_asset,
                            column_asset,
                            None,
                            RiskEstimateState.INSUFFICIENT_OBSERVATIONS.value,
                            len(window),
                            "risk.observations.insufficient",
                        )
                    )
            continue
        if definition.kind is RiskModelKind.EWMA_COVARIANCE:
            decay = float(definition.ewma_decay)
            weights = np.asarray(
                [decay ** (len(window) - offset - 1) for offset in range(len(window))],
                dtype="float64",
            )
            weights /= weights.sum()
            values = window.to_numpy(dtype="float64")
            means = np.nansum(values * weights[:, None], axis=0)
            centered = values - means
            covariance = np.nan_to_num(
                (centered * weights[:, None]).T @ centered,
                nan=0.0,
            )
        else:
            covariance = window.cov(min_periods=definition.minimum_observations).to_numpy(
                dtype="float64"
            )
        if definition.kind is RiskModelKind.FIXED_SHRINKAGE:
            shrinkage = float(definition.shrinkage)
            diagonal = np.diag(np.diag(covariance))
            covariance = (1 - shrinkage) * covariance + shrinkage * diagonal
        covariance = (covariance + covariance.T) / 2
        if not np.isfinite(covariance).all():
            state = RiskEstimateState.INVALID_NUMERIC
            reason = "risk.numeric.invalid"
        else:
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            if eigenvalues.min() < -1e-12:
                if definition.psd_policy is PsdPolicy.FAIL:
                    state = RiskEstimateState.NON_PSD
                    reason = "risk.covariance.non_psd"
                else:
                    covariance = (
                        eigenvectors
                        @ np.diag(np.maximum(eigenvalues, 0.0))
                        @ eigenvectors.T
                    )
                    state = RiskEstimateState.COMPUTED
                    reason = None
            else:
                state = RiskEstimateState.COMPUTED
                reason = None
        for row_index, row_asset in enumerate(assets):
            for column_index, column_asset in enumerate(assets):
                value = (
                    float(covariance[row_index, column_index])
                    if state is RiskEstimateState.COMPUTED
                    else None
                )
                rows.append(
                    (
                        pd.Timestamp(decision).to_pydatetime(),
                        row_asset,
                        column_asset,
                        value,
                        state.value,
                        len(window),
                        reason,
                    )
                )
    return rows


def _decision_build(connection: Any, build_id: ResearchDatasetBuildId) -> tuple[Any, ...]:
    row = connection.execute(
        "SELECT b.output_relation_name, b.output_manifest_content_id, "
        "coalesce(e.dataset_role, 'decision'), "
        "coalesce(e.information_class, 'causal'), "
        "coalesce(e.structurally_decision_eligible, true) FROM "
        "research.research_dataset_builds b LEFT JOIN "
        "research.research_dataset_enrichments e USING (research_dataset_build_id) "
        "WHERE research_dataset_build_id = ?",
        [build_id.value],
    ).fetchone()
    if (
        row is None
        or row[2] != "decision"
        or row[3] in {"label", "retrospective"}
        or not bool(row[4])
    ):
        raise ForecastMaterializationError(
            "portfolio inputs require a structurally decision-eligible dataset"
        )
    return tuple(row)


def _bounded_rows(
    project: Project,
    query: str,
    identifier: object,
    max_rows: int,
) -> pd.DataFrame:
    if max_rows < 1:
        raise ResearchResultLimitError("max_rows must be positive")
    connection = project._primary_connection()  # pyright: ignore[reportPrivateUsage]
    frame = cast(
        "pd.DataFrame",
        connection.execute(query, [identifier, max_rows + 1]).fetchdf(),
    )
    if len(frame) > max_rows:
        raise ResearchResultLimitError("portfolio result exceeds max_rows")
    return frame


def _require_write(project: Project) -> None:
    if project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
        raise CapabilityUnavailableError(
            "portfolio artifact mutation requires research_write mode"
        )


def _cvxpy() -> Any:
    try:
        return cast("Any", import_module("cvxpy"))
    except ModuleNotFoundError as error:
        raise CapabilityUnavailableError(
            "convex optimization requires the 'optimize' extra"
        ) from error
