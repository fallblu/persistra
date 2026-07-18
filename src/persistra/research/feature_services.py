"""Managed return and momentum feature service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast, overload

import pandas as pd

from persistra._identity import (
    identity_bytes,
)
from persistra._identity import (
    scoped_identity_content_id as scoped_content_id,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.errors import (
    CapabilityUnavailableError,
    FeatureDefinitionError,
    FeatureMaterializationError,
    ResearchResultLimitError,
)
from persistra.research.components import (
    BoundedPythonImplementation,
    BoundedSqlImplementation,
    ComponentMaterializationLimits,
    FeatureDefinitionRef,
    ManagedComponentDefinition,
    ResolvedComponentDefinition,
    TemporalConformanceResult,
)
from persistra.research.features import (
    FeatureDefinition,
    FeatureDefinitionId,
    FeatureKind,
    FeatureMaterializationId,
    FeatureMaterializationRef,
    FeatureRef,
    FeatureValueState,
    ResolvedFeatureRef,
)
from persistra.research.models import ResearchDatasetBuildId

if TYPE_CHECKING:
    from collections.abc import Iterator

    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.research.component_services import (
        ComponentMaterialization,
        ComponentService,
    )


def _decode_definition(text: str) -> FeatureDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    return FeatureDefinition(
        QualifiedName(value["name"]),
        int(value["version"]),
        FeatureKind(value["kind"]),
        str(value["input_name"]),
        int(value["lookback"]),
        int(value["skip"]),
    )


class FeatureService:
    """Versioned managed feature registry and materializer."""

    __slots__ = ("_components", "_project")

    def __init__(
        self, project: Project, components: ComponentService | None = None
    ) -> None:
        self._project = project
        self._components = components

    @overload
    def register(
        self, definition: FeatureDefinition
    ) -> ResolvedFeatureRef: ...

    @overload
    def register(
        self, definition: ManagedComponentDefinition
    ) -> ResolvedComponentDefinition: ...

    def register(
        self, definition: FeatureDefinition | ManagedComponentDefinition
    ) -> ResolvedFeatureRef | ResolvedComponentDefinition:
        if isinstance(definition, ManagedComponentDefinition):
            if self._components is None:
                raise FeatureDefinitionError("managed component service is unavailable")
            return self._components.register(definition)
        self._require_write()
        encoded = identity_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.research.feature_definition@1", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedFeatureRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.feature_definition_id, v.definition_content_id, "
                "v.definition_json FROM research.feature_definitions d JOIN "
                "research.feature_versions v USING (feature_definition_id) "
                "WHERE d.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise FeatureDefinitionError("feature version conflicts")
                return ResolvedFeatureRef(
                    FeatureDefinitionId.parse(existing[0]), definition.version, content_id
                )
            prior = connection.execute(
                "SELECT d.feature_definition_id, max(v.definition_version) "
                "FROM research.feature_definitions d LEFT JOIN "
                "research.feature_versions v USING (feature_definition_id) "
                "WHERE d.qualified_name = ? GROUP BY d.feature_definition_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise FeatureDefinitionError("first feature version must be one")
                definition_id = FeatureDefinitionId.new()
                connection.execute(
                    "INSERT INTO research.feature_definitions VALUES (?, ?, ?)",
                    [definition_id.value, str(definition.name), context.recorded_at],
                )
            else:
                definition_id = FeatureDefinitionId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise FeatureDefinitionError("feature versions must be contiguous")
            connection.execute(
                "INSERT INTO research.feature_versions VALUES (?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            return ResolvedFeatureRef(definition_id, definition.version, content_id)

        return self._project.services.transactions.run("feature_register", operation)

    def install_bounded_python(
        self,
        definition: ManagedComponentDefinition,
        implementation: BoundedPythonImplementation,
    ) -> ResolvedComponentDefinition:
        if self._components is None:
            raise FeatureDefinitionError("managed component service is unavailable")
        return self._components.install_bounded_python(definition, implementation)

    def conform(
        self, reference: FeatureDefinitionRef
    ) -> TemporalConformanceResult:
        if self._components is None:
            raise FeatureDefinitionError("managed component service is unavailable")
        return self._components.conform(reference)

    def install_bounded_sql(
        self,
        definition: ManagedComponentDefinition,
        implementation: BoundedSqlImplementation,
    ) -> ResolvedComponentDefinition:
        if self._components is None:
            raise FeatureDefinitionError("managed component service is unavailable")
        return self._components.install_bounded_sql(definition, implementation)

    def resolve(self, reference: FeatureRef) -> ResolvedFeatureRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.feature_definition_id, v.definition_content_id FROM "
            "research.feature_definitions d JOIN research.feature_versions v "
            "USING (feature_definition_id) WHERE d.qualified_name = ? "
            "AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise FeatureDefinitionError("feature is not registered")
        return ResolvedFeatureRef(
            FeatureDefinitionId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    @overload
    def materialize(
        self,
        *,
        definition: FeatureRef,
        primary_dataset: ResearchDatasetBuildId,
        parameters: tuple[tuple[str, str], ...] = (),
        limits: ComponentMaterializationLimits | None = None,
    ) -> FeatureMaterialization: ...

    @overload
    def materialize(
        self,
        *,
        definition: FeatureDefinitionRef,
        primary_dataset: ResearchDatasetBuildId,
        parameters: tuple[tuple[str, str], ...] = (),
        limits: ComponentMaterializationLimits | None = None,
    ) -> ComponentMaterialization: ...

    def materialize(
        self,
        *,
        definition: FeatureRef | FeatureDefinitionRef,
        primary_dataset: ResearchDatasetBuildId,
        parameters: tuple[tuple[str, str], ...] = (),
        limits: ComponentMaterializationLimits | None = None,
    ) -> FeatureMaterialization | ComponentMaterialization:
        if isinstance(definition, FeatureDefinitionRef):
            if self._components is None:
                raise FeatureMaterializationError(
                    "managed component service is unavailable"
                )
            return self._components.materialize(
                definition=definition,
                primary_dataset=primary_dataset,
                parameters=parameters,
                limits=limits,
            )
        self._require_write()
        resolved = self.resolve(definition)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        definition_row = connection.execute(
            "SELECT definition_json FROM research.feature_versions WHERE "
            "feature_definition_id = ? AND definition_version = ?",
            [resolved.feature_definition_id.value, resolved.version],
        ).fetchone()
        build_row = connection.execute(
            "SELECT output_relation_name, output_manifest_content_id FROM "
            "research.research_dataset_builds WHERE research_dataset_build_id = ?",
            [primary_dataset.value],
        ).fetchone()
        if definition_row is None or build_row is None:
            raise FeatureMaterializationError("feature definition or dataset build is missing")
        stored = _decode_definition(definition_row[0])
        column = f"{stored.input_name}_close"
        relation = str(build_row[0]).replace('"', '""')
        try:
            frame = connection.execute(
                f'SELECT decision_at, session_date, instrument_id, "{column}" AS price, '
                f'research_row_usable FROM research_data."{relation}" '
                "ORDER BY instrument_id, decision_at"
            ).fetchdf()
        except Exception as error:
            raise FeatureMaterializationError(
                f"dataset input {stored.input_name!r} is unavailable"
            ) from error
        output = _calculate_values(frame, stored)
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.research.feature_execution@1",
                "definition": resolved,
                "primary_dataset": primary_dataset,
                "dataset_manifest": build_row[1],
            }
        )
        output_manifest_content_id = scoped_content_id(
            {
                "schema": "persistra.research.feature_output@1",
                "execution": execution_content_id,
                "rows": output,
            }
        )

        def operation(context: TransactionContext) -> FeatureMaterialization:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT feature_materialization_id FROM "
                "research.feature_materializations WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(FeatureMaterializationId.parse(existing[0]))
            materialization_id = FeatureMaterializationId.new()
            computed_count = sum(row[4] == FeatureValueState.COMPUTED.value for row in output)
            active.execute(
                "INSERT INTO research.feature_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    resolved.feature_definition_id.value,
                    resolved.version,
                    primary_dataset.value,
                    str(execution_content_id),
                    str(output_manifest_content_id),
                    len(output),
                    computed_count,
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO research_data.feature_values VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(materialization_id.value, *row) for row in output],
            )
            return self.get(materialization_id)

        return self._project.services.transactions.run("feature_materialize", operation)

    def get(self, materialization_id: FeatureMaterializationId) -> FeatureMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT feature_definition_id, definition_version, "
            "research_dataset_build_id, execution_content_id, "
            "output_manifest_content_id, row_count, computed_count FROM "
            "research.feature_materializations WHERE feature_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise FeatureMaterializationError("feature materialization is missing")
        reference = FeatureMaterializationRef(
            materialization_id,
            FeatureDefinitionId.parse(row[0]),
            int(row[1]),
            ResearchDatasetBuildId.parse(row[2]),
            ContentId.parse(row[3]),
            ContentId.parse(row[4]),
            int(row[5]),
            int(row[6]),
        )
        return FeatureMaterialization(self._project, reference)

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("feature writes require research_write mode")


def _calculate_values(
    frame: pd.DataFrame, definition: FeatureDefinition
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for _, group in frame.groupby("instrument_id", sort=True):
        ordered = group.sort_values("decision_at").reset_index(drop=True)
        records = cast("list[dict[str, Any]]", ordered.to_dict("records"))
        for position, item in enumerate(records):
            left_index = position - definition.lookback
            right_index = position - definition.skip
            state = FeatureValueState.COMPUTED
            reason: str | None = None
            value: float | None = None
            used: tuple[Any, Any] | None = None
            if left_index < 0:
                state = FeatureValueState.INSUFFICIENT_HISTORY
                reason = "feature.history.insufficient"
            else:
                left = records[left_index]
                right = records[right_index]
                if (
                    not bool(left["research_row_usable"])
                    or not bool(right["research_row_usable"])
                    or pd.isna(left["price"])
                    or pd.isna(right["price"])
                ):
                    state = FeatureValueState.INPUT_MISSING
                    reason = "feature.input.missing"
                elif float(left["price"]) <= 0 or float(right["price"]) <= 0:
                    state = FeatureValueState.INVALID_NUMERIC
                    reason = "feature.price.nonpositive"
                else:
                    value = float(right["price"]) / float(left["price"]) - 1.0
                    used = (left["decision_at"], right["decision_at"])
            lineage = scoped_content_id(
                {
                    "schema": "persistra.research.feature_row@1",
                    "definition": definition,
                    "instrument_id": str(item["instrument_id"]),
                    "decision_at": cast("pd.Timestamp", item["decision_at"]).isoformat(),
                    "used": used,
                    "state": state.value,
                    "value": value,
                }
            )
            rows.append(
                (
                    cast("pd.Timestamp", item["decision_at"]).to_pydatetime(),
                    pd.Timestamp(item["session_date"]).date(),
                    item["instrument_id"],
                    value,
                    state.value,
                    reason,
                    cast("pd.Timestamp", item["decision_at"]).to_pydatetime(),
                    str(lineage),
                )
            )
    rows.sort(key=lambda row: (row[0], str(row[2])))
    return rows


@dataclass(frozen=True, slots=True)
class FeatureMaterialization:
    """Project-bound immutable feature result."""

    _project: Project
    reference: FeatureMaterializationRef

    def rows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT decision_at, session_date, instrument_id, value, state, "
            "reason_code, logical_available_at, lineage_content_id FROM "
            "research_data.feature_values WHERE feature_materialization_id = ? "
            "ORDER BY decision_at, instrument_id LIMIT ?",
            [self.reference.feature_materialization_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("feature rows exceed max_rows")
        for column in ("decision_at", "logical_available_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        for column in ("instrument_id", "lineage_content_id"):
            frame[column] = frame[column].astype("string")
        return frame

    def iter_rows(self, *, chunk_rows: int = 100_000) -> Iterator[pd.DataFrame]:
        if chunk_rows < 1:
            raise ResearchResultLimitError("chunk_rows must be positive")
        frame = self.rows(max_rows=max(self.reference.row_count, 1))
        for start in range(0, len(frame), chunk_rows):
            yield frame.iloc[start : start + chunk_rows].reset_index(drop=True)
