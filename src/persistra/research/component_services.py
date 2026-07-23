"""This module contains the unified managed feature and label registration and materialization."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    FeatureDefinitionError,
    FeatureMaterializationError,
    LabelDefinitionError,
    LabelMaterializationError,
    ResearchResultLimitError,
    TemporalConformanceError,
)
from persistra.research.components import (
    BoundedPythonImplementation,
    BoundedSqlImplementation,
    ComponentDefinitionRef,
    ComponentDependencyScope,
    ComponentImplementationKind,
    ComponentInputKind,
    ComponentInputSpec,
    ComponentMaterializationLimits,
    ComponentMaterializationRef,
    ComponentOutput,
    ComponentValueState,
    FeatureDefinitionRef,
    FeaturePartition,
    LabelDefinitionId,
    LabelDefinitionRef,
    LabelMaterializationId,
    LabelPartition,
    ManagedComponentDefinition,
    ManagedOperator,
    ParameterValues,
    PartitionShape,
    ResearchComponentKind,
    ResearchComponentVersion,
    ResolvedComponentDefinition,
    TemporalConformanceResult,
    TemporalConformanceResultId,
)
from persistra.research.features import FeatureDefinitionId, FeatureMaterializationId
from persistra.research.models import ResearchDatasetBuildId
from persistra.research.sql_models import (
    InformationClass,
    LineageCompleteness,
    SafetyStatus,
    TemporalContractKind,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project


_EXECUTABLE_MANAGED_OPERATORS = frozenset(
    {
        ManagedOperator.PRICE,
        ManagedOperator.SIMPLE_RETURN,
        ManagedOperator.LOG_RETURN,
        ManagedOperator.MOMENTUM,
        ManagedOperator.REVERSAL,
        ManagedOperator.REALIZED_VOLATILITY,
        ManagedOperator.MAX_DRAWDOWN,
        ManagedOperator.QUOTED_SPREAD_BPS,
        ManagedOperator.FUNDAMENTAL_RATIO,
        ManagedOperator.FUNDAMENTAL_GROWTH,
        ManagedOperator.ESTIMATE_REVISION,
        ManagedOperator.MACRO_LEVEL,
        ManagedOperator.MACRO_CHANGE,
        ManagedOperator.CROSS_SECTIONAL_RANK,
        ManagedOperator.CROSS_SECTIONAL_WINSORIZE,
        ManagedOperator.CROSS_SECTIONAL_ZSCORE,
        ManagedOperator.FORWARD_RETURN,
        ManagedOperator.FUTURE_VOLATILITY,
        ManagedOperator.FUTURE_DRAWDOWN,
    }
)


@dataclass(slots=True)
class _ComputedNode:
    definition: ManagedComponentDefinition
    resolved: ResolvedComponentDefinition
    frame: pd.DataFrame
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    dependency_nodes: tuple[_ComputedNode, ...]
    existing_id: EntityId | None = None


class ComponentService:
    """This class owns the unified managed feature and label definition DAG."""

    __slots__ = ("_implementations", "_kind", "_project")

    def __init__(self, project: Project, kind: ResearchComponentKind) -> None:
        self._project = project
        self._kind = kind
        self._implementations: dict[
            tuple[str, str], BoundedPythonImplementation
        ] = {}

    def install_bounded_python(
        self,
        definition: ManagedComponentDefinition,
        implementation: BoundedPythonImplementation,
    ) -> ResolvedComponentDefinition:
        """Register and attach one explicitly captured bounded callback."""
        if (
            definition.implementation_kind
            is not ComponentImplementationKind.BOUNDED_PYTHON
        ):
            raise self._definition_error(
                "bounded Python installation requires a bounded_python definition"
            )
        if definition.implementation_content_id != implementation.content_id:
            raise self._definition_error(
                "bounded callback identity does not match the definition"
            )
        resolved = self.register(definition)
        key = (str(definition.name), str(definition.version))
        existing = self._implementations.get(key)
        if existing is not None and existing.content_id != implementation.content_id:
            raise self._definition_error("bounded callback installation conflicts")
        self._implementations[key] = implementation
        return resolved

    def install_bounded_sql(
        self,
        definition: ManagedComponentDefinition,
        implementation: BoundedSqlImplementation,
    ) -> ResolvedComponentDefinition:
        """Register parsed component SQL behind the same bounded protocol."""
        if (
            definition.implementation_kind
            is not ComponentImplementationKind.BOUNDED_SQL
        ):
            raise self._definition_error(
                "bounded SQL installation requires a bounded_sql definition"
            )
        if definition.implementation_content_id != implementation.content_id:
            raise self._definition_error(
                "bounded SQL identity does not match the definition"
            )
        callback = _bounded_sql_callback(definition, implementation)
        installed = BoundedPythonImplementation(
            implementation.version,
            implementation.content_id,
            callback,
        )
        resolved = self.register(definition)
        key = (str(definition.name), str(definition.version))
        existing = self._implementations.get(key)
        if existing is not None and existing.content_id != implementation.content_id:
            raise self._definition_error("bounded SQL installation conflicts")
        self._implementations[key] = installed
        return resolved

    def conform(
        self, reference: ComponentDefinitionRef
    ) -> TemporalConformanceResult:
        """Run deterministic boundary sentinels for an installed callback."""
        self._require_write()
        resolved = self.resolve(reference)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        definition = self._get_definition(connection, resolved)
        key = (str(definition.name), str(definition.version))
        implementation = self._implementations.get(key)
        if definition.implementation_kind not in {
            ComponentImplementationKind.BOUNDED_PYTHON,
            ComponentImplementationKind.BOUNDED_SQL,
        } or implementation is None:
            raise TemporalConformanceError(
                "an exact bounded Python implementation must be installed"
            )
        suite_content_id = scoped_content_id(
            {
                "schema": "persistra.research.temporal_conformance_suite",
                "version": 1,
                "kind": definition.kind,
                "lookback": definition.lookback,
                "horizon": definition.horizon,
            }
        )
        existing = connection.execute(
            "SELECT temporal_conformance_result_id, status, evidence_content_id "
            "FROM research.temporal_conformance_results "
            "WHERE component_definition_id = ? AND component_version = ? "
            "AND suite_content_id = ? AND implementation_content_id = ?",
            [
                resolved.component_definition_id.value,
                str(resolved.version),
                str(suite_content_id),
                str(implementation.content_id),
            ],
        ).fetchone()
        if existing is not None:
            return TemporalConformanceResult(
                TemporalConformanceResultId.parse(existing[0]),
                resolved.component_definition_id,
                resolved.version,
                existing[1] == "passed",
                ContentId.parse(existing[2]),
            )
        passed, evidence_content_id = _run_conformance(
            definition, implementation
        )

        def operation(context: TransactionContext) -> TemporalConformanceResult:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result_id = TemporalConformanceResultId.new()
            active.execute(
                "INSERT INTO research.temporal_conformance_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    result_id.value,
                    resolved.component_definition_id.value,
                    str(resolved.version),
                    str(suite_content_id),
                    str(implementation.content_id),
                    "passed" if passed else "failed",
                    str(evidence_content_id),
                    context.recorded_at,
                ],
            )
            insert_event(
                active,
                event_name="persistra.research.temporal_conformance_completed",
                aggregate_kind="persistra.aggregate.temporal_conformance_result",
                aggregate_id=result_id,
                aggregate_sequence=1,
                recorded_at=context.recorded_at,
                payload={
                    "component_definition_id": resolved.component_definition_id,
                    "evidence_content_id": evidence_content_id,
                    "passed": passed,
                },
            )
            return TemporalConformanceResult(
                result_id,
                resolved.component_definition_id,
                resolved.version,
                passed,
                evidence_content_id,
            )

        return self._project.services.transactions.run(
            "temporal_conformance_publish", operation
        )

    def register(
        self, definition: ManagedComponentDefinition
    ) -> ResolvedComponentDefinition:
        self._require_write()
        if definition.kind is not self._kind:
            raise self._definition_error("component registered through the wrong service")
        if (
            definition.implementation_kind
            is ComponentImplementationKind.MANAGED_OPERATOR
            and definition.operator not in _EXECUTABLE_MANAGED_OPERATORS
        ):
            raise self._definition_error(
                "managed operator is not executable in this version: "
                f"{definition.operator.value}"
            )
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.research.component_definition", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedComponentDefinition:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.component_definition_id, d.component_kind, "
                "v.registration_sequence, v.definition_content_id, v.definition_json "
                "FROM research.component_definitions d JOIN research.component_versions v "
                "USING (component_definition_id) WHERE d.qualified_name = ? "
                "AND v.component_version = ?",
                [str(definition.name), str(definition.version)],
            ).fetchone()
            if existing is not None:
                if (
                    existing[1] != definition.kind.value
                    or existing[3] != str(content_id)
                    or existing[4] != encoded.decode()
                ):
                    raise self._definition_error("component version conflicts")
                return ResolvedComponentDefinition(
                    self._definition_id(existing[0]),
                    self._kind,
                    definition.version,
                    int(existing[2]),
                    content_id,
                )
            master = connection.execute(
                "SELECT component_definition_id, component_kind FROM "
                "research.component_definitions WHERE qualified_name = ?",
                [str(definition.name)],
            ).fetchone()
            if master is None:
                definition_id = self._new_definition_id()
                sequence = 1
                connection.execute(
                    "INSERT INTO research.component_definitions VALUES (?, ?, ?, ?)",
                    [
                        definition_id.value,
                        definition.kind.value,
                        str(definition.name),
                        context.recorded_at,
                    ],
                )
            else:
                if master[1] != self._kind.value:
                    raise self._definition_error(
                        "component name is owned by the other component kind"
                    )
                definition_id = self._definition_id(master[0])
                versions = [
                    ResearchComponentVersion.parse(row[0])
                    for row in connection.execute(
                        "SELECT component_version FROM research.component_versions "
                        "WHERE component_definition_id = ?",
                        [definition_id.value],
                    ).fetchall()
                ]
                if definition.version <= max(versions):
                    raise self._definition_error(
                        "component versions must increase monotonically"
                    )
                sequence = len(versions) + 1
            dependency_rows: list[
                tuple[EntityId, ResearchComponentVersion, ComponentInputSpec]
            ] = []
            for item in definition.inputs:
                if item.kind is ComponentInputKind.DATASET_FIELD:
                    continue
                assert item.dependency is not None
                dependency = self._resolve(connection, item.dependency)
                if (
                    definition.kind is ResearchComponentKind.FEATURE
                    and dependency.kind is ResearchComponentKind.LABEL
                ):
                    raise FeatureDefinitionError(
                        "feature definitions cannot depend on label outputs"
                    )
                dependency_rows.append(
                    (dependency.component_definition_id, dependency.version, item)
                )
            connection.execute(
                "INSERT INTO research.component_versions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    str(definition.version),
                    sequence,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            for dependency_id, dependency_version, item in dependency_rows:
                assert item.dependency_output is not None
                connection.execute(
                    "INSERT INTO research.component_definition_dependencies VALUES "
                    "(?, ?, ?, ?, ?, ?, ?)",
                    [
                        definition_id.value,
                        str(definition.version),
                        item.ordinal,
                        dependency_id.value,
                        str(dependency_version),
                        item.kind.value,
                        item.dependency_output,
                    ],
                )
            insert_event(
                connection,
                event_name=f"persistra.research.{self._kind.value}_registered",
                aggregate_kind=f"persistra.aggregate.{self._kind.value}_definition",
                aggregate_id=definition_id,
                aggregate_sequence=sequence,
                recorded_at=context.recorded_at,
                payload={"definition_content_id": content_id},
            )
            return ResolvedComponentDefinition(
                definition_id, self._kind, definition.version, sequence, content_id
            )

        return self._project.services.transactions.run(
            f"{self._kind.value}_component_register", operation
        )

    def resolve(self, reference: ComponentDefinitionRef) -> ResolvedComponentDefinition:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        resolved = self._resolve(connection, reference)
        if resolved.kind is not self._kind:
            raise self._definition_error("component reference uses the wrong service")
        return resolved

    def materialize(
        self,
        *,
        definition: ComponentDefinitionRef,
        primary_dataset: ResearchDatasetBuildId,
        parameters: tuple[tuple[str, str], ...] = (),
        limits: ComponentMaterializationLimits | None = None,
    ) -> ComponentMaterialization:
        self._require_write()
        self.resolve(definition)
        active_limits = limits or ComponentMaterializationLimits()
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        build = connection.execute(
            "SELECT output_relation_name, output_manifest_content_id, row_count FROM "
            "research.research_dataset_builds WHERE research_dataset_build_id = ?",
            [primary_dataset.value],
        ).fetchone()
        if build is None:
            raise self._materialization_error("primary dataset build is unavailable")
        if int(build[2]) > active_limits.max_base_rows:
            raise ResearchResultLimitError("component base rows exceed limits")
        relation = str(build[0]).replace('"', '""')
        base = cast(
            "pd.DataFrame",
            connection.execute(
                f'SELECT * FROM research_data."{relation}" '
                "ORDER BY instrument_id, decision_at"
            ).fetchdf(),
        )
        if len(base) > active_limits.direct_pandas_rows:
            raise ResearchResultLimitError(
                "component direct dataframe path exceeds its row ceiling"
            )
        expanded_parameters = tuple(sorted(parameters))
        computed: dict[tuple[str, str], _ComputedNode] = {}
        visiting: set[tuple[str, str]] = set()

        def visit(reference: ComponentDefinitionRef) -> _ComputedNode:
            key = (str(reference.name), str(reference.version))
            if key in visiting:
                raise self._definition_error("component dependency graph contains a cycle")
            if key in computed:
                return computed[key]
            visiting.add(key)
            node_resolved = self._resolve(connection, reference)
            node_definition = self._get_definition(connection, node_resolved)
            dependencies: list[_ComputedNode] = []
            working = base.copy()
            for item in node_definition.inputs:
                if item.kind is ComponentInputKind.DATASET_FIELD:
                    assert item.field_name is not None
                    if item.field_name not in working:
                        raise self._materialization_error(
                            f"dataset field {item.field_name!r} is unavailable"
                        )
                    if item.name != item.field_name:
                        working[item.name] = working[item.field_name]
                    continue
                assert item.dependency is not None
                dependency = visit(item.dependency)
                if (
                    item.dependency_output
                    != dependency.definition.output_name
                ):
                    raise self._definition_error(
                        "component dependency output does not match its definition"
                    )
                expected_kind = (
                    ResearchComponentKind.FEATURE
                    if item.kind is ComponentInputKind.FEATURE_OUTPUT
                    else ResearchComponentKind.LABEL
                )
                if dependency.definition.kind is not expected_kind:
                    raise self._definition_error(
                        "component input kind does not match its dependency"
                    )
                dependencies.append(dependency)
                output = dependency.definition.output_name
                selected = dependency.frame[
                    [
                        "decision_at",
                        "instrument_id",
                        output,
                        f"{output}_state",
                        f"{output}_available_at",
                    ]
                ].rename(
                    columns={
                        output: item.name,
                        f"{output}_state": f"{item.name}_state",
                        f"{output}_available_at": f"{item.name}_available_at",
                    }
                )
                working = working.merge(
                    selected,
                    on=["decision_at", "instrument_id"],
                    how="left",
                    validate="one_to_one",
                )
            node_parameters = dict(node_definition.parameters)
            node_parameters.update(dict(expanded_parameters))
            if (
                node_definition.implementation_kind
                is ComponentImplementationKind.MANAGED_OPERATOR
            ):
                output_frame = _calculate(
                    node_definition, working, node_parameters
                )
            else:
                implementation_key = (
                    str(node_definition.name),
                    str(node_definition.version),
                )
                implementation = self._implementations.get(implementation_key)
                if implementation is None:
                    raise TemporalConformanceError(
                        "bounded implementation is not installed"
                    )
                if not self._conformance_passed(
                    connection, node_resolved, implementation
                ):
                    raise TemporalConformanceError(
                        "bounded implementation has no exact passing conformance result"
                    )
                output_frame = _calculate_bounded_python(
                    node_definition,
                    working,
                    node_parameters,
                    implementation,
                )
            execution_id = scoped_content_id(
                {
                    "schema": "persistra.research.component_execution",
                    "definition": node_resolved,
                    "primary_dataset": primary_dataset,
                    "dataset_manifest": build[1],
                    "parameters": tuple(sorted(node_parameters.items())),
                    "dependencies": tuple(
                        dependency.output_manifest_content_id
                        for dependency in dependencies
                    ),
                    "limits": active_limits,
                }
            )
            output_manifest = _frame_manifest(
                output_frame, node_definition.output_name, execution_id
            )
            existing = connection.execute(
                "SELECT component_materialization_id, output_relation_name FROM "
                "research.component_materializations WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            existing_id = (
                None
                if existing is None
                else self._materialization_id(node_definition.kind, existing[0])
            )
            if existing is not None:
                stored = self._read_relation(
                    connection, node_definition.kind, str(existing[1])
                )
                if _frame_manifest(
                    stored, node_definition.output_name, execution_id
                ) != output_manifest:
                    raise self._materialization_error(
                        "stored component output does not reproduce"
                    )
                output_frame = stored
            node = _ComputedNode(
                node_definition,
                node_resolved,
                output_frame,
                execution_id,
                output_manifest,
                tuple(dependencies),
                existing_id,
            )
            visiting.remove(key)
            computed[key] = node
            return node

        root = visit(definition)
        ordered = tuple(computed.values())

        def operation(context: TransactionContext) -> ComponentMaterialization:
            published: dict[tuple[str, str], EntityId] = {}
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            for node in ordered:
                key = (
                    str(node.definition.name),
                    str(node.definition.version),
                )
                if node.existing_id is not None:
                    published[key] = node.existing_id
                    continue
                materialization_id = self._new_materialization_id(node.definition.kind)
                relation_name = f"materialization_{materialization_id.value.hex}"
                _publish_relation(
                    active,
                    node.definition.kind,
                    relation_name,
                    node.definition.output_name,
                    node.frame,
                )
                computed_count = int(
                    (
                        node.frame[f"{node.definition.output_name}_state"]
                        == ComponentValueState.COMPUTED.value
                    ).sum()
                )
                information = (
                    InformationClass.LABEL
                    if node.definition.kind is ResearchComponentKind.LABEL
                    else InformationClass.CAUSAL
                )
                active.execute(
                    "INSERT INTO research.component_materializations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        materialization_id.value,
                        node.resolved.component_definition_id.value,
                        str(node.resolved.version),
                        node.definition.kind.value,
                        primary_dataset.value,
                        str(scoped_content_id(expanded_parameters)),
                        str(node.execution_content_id),
                        str(_output_schema_id(node.definition.output_name)),
                        str(node.output_manifest_content_id),
                        relation_name,
                        information.value,
                        TemporalContractKind.DECISION_PANEL.value,
                        LineageCompleteness.COMPLETE.value,
                        SafetyStatus.SAFE.value,
                        node.definition.kind is ResearchComponentKind.FEATURE,
                        len(node.frame),
                        computed_count,
                        context.recorded_at,
                    ],
                )
                for ordinal, dependency in enumerate(node.dependency_nodes, 1):
                    dependency_key = (
                        str(dependency.definition.name),
                        str(dependency.definition.version),
                    )
                    dependency_id = published.get(dependency_key) or dependency.existing_id
                    assert dependency_id is not None
                    active.execute(
                        "INSERT INTO research.component_materialization_dependencies "
                        "VALUES (?, ?, ?, ?)",
                        [
                            materialization_id.value,
                            ordinal,
                            dependency_id.value,
                            str(dependency.output_manifest_content_id),
                        ],
                    )
                insert_event(
                    active,
                    event_name=(
                        f"persistra.research.{node.definition.kind.value}_materialized"
                    ),
                    aggregate_kind=(
                        f"persistra.aggregate.{node.definition.kind.value}_materialization"
                    ),
                    aggregate_id=materialization_id,
                    aggregate_sequence=1,
                    recorded_at=context.recorded_at,
                    payload={"execution_content_id": node.execution_content_id},
                )
                published[key] = materialization_id
            root_key = (str(root.definition.name), str(root.definition.version))
            root_id = published.get(root_key) or root.existing_id
            assert root_id is not None
            return self.get(root_id)

        return self._project.services.transactions.run(
            f"{self._kind.value}_component_materialize", operation
        )

    def get(self, materialization_id: EntityId) -> ComponentMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT component_definition_id, component_version, component_kind, "
            "research_dataset_build_id, execution_content_id, output_manifest_content_id, "
            "information_class, temporal_contract_kind, lineage_completeness, "
            "safety_status, structurally_decision_eligible, row_count, computed_count, "
            "output_relation_name FROM "
            "research.component_materializations WHERE component_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise self._materialization_error("component materialization is unavailable")
        kind = ResearchComponentKind(row[2])
        reference = ComponentMaterializationRef(
            self._materialization_id(kind, materialization_id.value),
            self._definition_id_for_kind(kind, row[0]),
            ResearchComponentVersion.parse(row[1]),
            kind,
            ResearchDatasetBuildId.parse(row[3]),
            ContentId.parse(row[4]),
            ContentId.parse(row[5]),
            InformationClass(row[6]),
            TemporalContractKind(row[7]),
            LineageCompleteness(row[8]),
            SafetyStatus(row[9]),
            bool(row[10]),
            int(row[11]),
            int(row[12]),
        )
        return ComponentMaterialization(self._project, reference, str(row[13]), kind)

    def _resolve(
        self, connection: ManagedConnection, reference: ComponentDefinitionRef
    ) -> ResolvedComponentDefinition:
        row = connection.execute(
            "SELECT d.component_definition_id, d.component_kind, "
            "v.registration_sequence, v.definition_content_id "
            "FROM research.component_definitions d JOIN research.component_versions v "
            "USING (component_definition_id) WHERE d.qualified_name = ? "
            "AND v.component_version = ?",
            [str(reference.name), str(reference.version)],
        ).fetchone()
        if row is None:
            raise self._definition_error("component definition is unavailable")
        kind = ResearchComponentKind(row[1])
        return ResolvedComponentDefinition(
            self._definition_id_for_kind(kind, row[0]),
            kind,
            reference.version,
            int(row[2]),
            ContentId.parse(row[3]),
        )

    def _get_definition(
        self, connection: ManagedConnection, resolved: ResolvedComponentDefinition
    ) -> ManagedComponentDefinition:
        row = connection.execute(
            "SELECT definition_json FROM research.component_versions "
            "WHERE component_definition_id = ? AND component_version = ?",
            [resolved.component_definition_id.value, str(resolved.version)],
        ).fetchone()
        if row is None:
            raise self._definition_error("component definition payload is unavailable")
        return _decode_definition(row[0])

    def _new_definition_id(self) -> EntityId:
        return (
            FeatureDefinitionId.new()
            if self._kind is ResearchComponentKind.FEATURE
            else LabelDefinitionId.new()
        )

    @staticmethod
    def _conformance_passed(
        connection: ManagedConnection,
        resolved: ResolvedComponentDefinition,
        implementation: BoundedPythonImplementation,
    ) -> bool:
        row = connection.execute(
            "SELECT count(*) FROM research.temporal_conformance_results "
            "WHERE component_definition_id = ? AND component_version = ? "
            "AND implementation_content_id = ? AND status = 'passed'",
            [
                resolved.component_definition_id.value,
                str(resolved.version),
                str(implementation.content_id),
            ],
        ).fetchone()
        return row is not None and int(row[0]) == 1

    def _definition_id(self, value: object) -> EntityId:
        return self._definition_id_for_kind(self._kind, value)

    @staticmethod
    def _definition_id_for_kind(
        kind: ResearchComponentKind, value: object
    ) -> EntityId:
        return (
            FeatureDefinitionId.parse(value)
            if kind is ResearchComponentKind.FEATURE
            else LabelDefinitionId.parse(value)
        )

    @staticmethod
    def _new_materialization_id(kind: ResearchComponentKind) -> EntityId:
        return (
            FeatureMaterializationId.new()
            if kind is ResearchComponentKind.FEATURE
            else LabelMaterializationId.new()
        )

    @staticmethod
    def _materialization_id(kind: ResearchComponentKind, value: object) -> EntityId:
        return (
            FeatureMaterializationId.parse(value)
            if kind is ResearchComponentKind.FEATURE
            else LabelMaterializationId.parse(value)
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                f"{self._kind.value} component writes require research_write mode"
            )

    def _definition_error(self, message: str) -> Exception:
        return (
            FeatureDefinitionError(message)
            if self._kind is ResearchComponentKind.FEATURE
            else LabelDefinitionError(message)
        )

    def _materialization_error(self, message: str) -> Exception:
        return (
            FeatureMaterializationError(message)
            if self._kind is ResearchComponentKind.FEATURE
            else LabelMaterializationError(message)
        )

    @staticmethod
    def _read_relation(
        connection: ManagedConnection, kind: ResearchComponentKind, relation: str
    ) -> pd.DataFrame:
        schema = "feature_data" if kind is ResearchComponentKind.FEATURE else "label_data"
        escaped = relation.replace('"', '""')
        return cast(
            "pd.DataFrame",
            connection.execute(
                f'SELECT * FROM {schema}."{escaped}" '
                "ORDER BY instrument_id, decision_at"
            ).fetchdf(),
        )


@dataclass(frozen=True, slots=True)
class ComponentMaterialization:
    """This class represents the immutable project-owned managed component result."""

    _project: Project
    reference: ComponentMaterializationRef
    _relation: str
    _kind: ResearchComponentKind

    def rows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        if max_rows < 1:
            raise ResearchResultLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = ComponentService._read_relation(  # pyright: ignore[reportPrivateUsage]
            connection, self._kind, self._relation
        )
        if len(frame) > max_rows:
            raise ResearchResultLimitError("component rows exceed max_rows")
        return frame

    def iter_rows(self, *, chunk_rows: int = 100_000) -> Iterator[pd.DataFrame]:
        if chunk_rows < 1:
            raise ResearchResultLimitError("chunk_rows must be positive")
        frame = self.rows(max_rows=max(self.reference.row_count, 1))
        for start in range(0, len(frame), chunk_rows):
            yield frame.iloc[start : start + chunk_rows].reset_index(drop=True)


def _decode_definition(text: str) -> ManagedComponentDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    inputs: list[ComponentInputSpec] = []
    for raw in value["inputs"]:
        dependency_value = raw["dependency"]
        dependency = None
        if dependency_value is not None:
            reference_type = (
                FeatureDefinitionRef
                if raw["kind"] == ComponentInputKind.FEATURE_OUTPUT.value
                else LabelDefinitionRef
            )
            dependency = reference_type(
                QualifiedName(dependency_value["name"]),
                _decode_version(dependency_value["version"]),
            )
        inputs.append(
            ComponentInputSpec(
                raw["name"],
                int(raw["ordinal"]),
                ComponentInputKind(raw["kind"]),
                raw["field_name"],
                dependency,
                raw["dependency_output"],
            )
        )
    return ManagedComponentDefinition(
        QualifiedName(value["name"]),
        _decode_version(value["version"]),
        ResearchComponentKind(value["kind"]),
        ManagedOperator(value["operator"]),
        tuple(inputs),
        value["output_name"],
        value["assumptions_and_limitations"],
        tuple((str(key), str(item)) for key, item in value["parameters"]),
        int(value["lookback"]),
        int(value["horizon"]),
        PartitionShape(value["partition_shape"]),
        ComponentDependencyScope(value["dependency_scope"]),
        ComponentImplementationKind(value["implementation_kind"]),
        ContentId.parse(value["implementation_content_id"]),
    )


def _bounded_sql_callback(
    definition: ManagedComponentDefinition,
    implementation: BoundedSqlImplementation,
) -> Any:
    sqlglot = cast("Any", import_module("sqlglot"))
    exp = cast("Any", import_module("sqlglot.expressions"))
    try:
        statements = sqlglot.parse(implementation.query, read="duckdb")
    except Exception as error:
        raise FeatureDefinitionError("bounded component SQL cannot be parsed") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise FeatureDefinitionError("bounded component SQL must be one SELECT")
    expression = statements[0]
    forbidden = (
        exp.Join,
        exp.Subquery,
        exp.Union,
        exp.Intersect,
        exp.Except,
        exp.Limit,
        exp.Offset,
    )
    if any(expression.find(node_type) is not None for node_type in forbidden):
        raise FeatureDefinitionError("bounded component SQL uses a forbidden construct")
    tables = tuple(expression.find_all(exp.Table))
    if (
        len(tables) != 1
        or tables[0].db != "ctx"
        or tables[0].name != "partition"
    ):
        raise FeatureDefinitionError(
            "bounded component SQL may read only ctx.partition"
        )
    projections = tuple(expression.expressions)
    if len(projections) != 1 or projections[0].alias_or_name != definition.output_name:
        raise FeatureDefinitionError(
            "bounded component SQL must emit exactly its declared output"
        )
    normalized = expression.sql(dialect="duckdb").upper()
    if "UNBOUNDED" in normalized:
        raise FeatureDefinitionError("bounded component SQL forbids unbounded windows")
    if (
        definition.kind is ResearchComponentKind.FEATURE
        and " FOLLOWING" in normalized
    ):
        raise FeatureDefinitionError("bounded feature SQL cannot use following rows")
    if (
        definition.kind is ResearchComponentKind.LABEL
        and " PRECEDING" in normalized
    ):
        raise FeatureDefinitionError("bounded label SQL cannot use preceding rows")
    table = tables[0]
    table.set("db", None)
    table.set("this", exp.to_identifier("partition", quoted=True))
    executable = expression.sql(dialect="duckdb")

    def callback(
        partition: FeaturePartition | LabelPartition,
        parameters: ParameterValues,
    ) -> ComponentOutput:
        del parameters
        source = (
            partition.history_rows()
            if isinstance(partition, FeaturePartition)
            else partition.window_rows()
        )
        duckdb = cast("Any", import_module("duckdb"))
        connection = duckdb.connect(":memory:")
        try:
            connection.execute("SET enable_external_access = false")
            connection.register("partition", source)
            result = cast("pd.DataFrame", connection.execute(executable).fetchdf())
        finally:
            connection.close()
        if definition.output_name not in result or result.empty:
            raise TemporalConformanceError(
                "bounded SQL did not emit its declared output rows"
            )
        selected = result[definition.output_name].iloc[-1]
        if pd.isna(selected):
            state = (
                ComponentValueState.INSUFFICIENT_HISTORY
                if definition.kind is ResearchComponentKind.FEATURE
                else ComponentValueState.CENSORED
            )
            return ComponentOutput(
                (None,),
                (state,),
                (
                    "feature.history.insufficient"
                    if definition.kind is ResearchComponentKind.FEATURE
                    else "label.horizon.censored",
                ),
                ((),),
            )
        return ComponentOutput(
            (float(selected),),
            (ComponentValueState.COMPUTED,),
            ("component.computed",),
            (tuple(range(len(source))),),
        )

    return callback


def _run_conformance(
    definition: ManagedComponentDefinition,
    implementation: BoundedPythonImplementation,
) -> tuple[bool, ContentId]:
    decisions = [
        datetime(2025, 1, 2, 21, tzinfo=UTC) + timedelta(days=index)
        for index in range(5)
    ]
    frame = pd.DataFrame(
        {
            "decision_at": decisions,
            "session_date": [item.date() for item in decisions],
            "instrument_id": [UUID(int=1)] * len(decisions),
            **{
                item.name: [float(index + 1) for index in range(len(decisions))]
                for item in definition.inputs
            },
            **{
                f"{item.name}_available_at": decisions
                for item in definition.inputs
            },
        }
    )
    cases: list[tuple[str, bool]] = []
    try:
        first = _calculate_bounded_python(
            definition, frame, dict(definition.parameters), implementation
        )
        repeated = _calculate_bounded_python(
            definition, frame.copy(deep=True), dict(definition.parameters), implementation
        )
        cases.append(("repeat_determinism", first.equals(repeated)))
        changed = frame.copy(deep=True)
        for item in definition.inputs:
            changed.loc[len(changed) - 1, item.name] = 9_999_991.0
        sentinel = _calculate_bounded_python(
            definition, changed, dict(definition.parameters), implementation
        )
        if definition.kind is ResearchComponentKind.FEATURE:
            comparable = first.iloc[:-1].reset_index(drop=True)
            observed = sentinel.iloc[:-1].reset_index(drop=True)
            cases.append(("future_sentinel", comparable.equals(observed)))
        else:
            unaffected = max(0, len(first) - definition.horizon - 1)
            cases.append(
                (
                    "horizon_sentinel",
                    first.iloc[:unaffected].reset_index(drop=True).equals(
                        sentinel.iloc[:unaffected].reset_index(drop=True)
                    ),
                )
            )
        cases.append(
            (
                "schema_and_keys",
                len(first) == len(frame)
                and not first[["decision_at", "instrument_id"]].duplicated().any(),
            )
        )
        passed = all(result for _, result in cases)
    except Exception:
        cases.append(("bounded_protocol", False))
        passed = False
    evidence = scoped_content_id(
        {
            "schema": "persistra.research.temporal_conformance_evidence",
            "definition_content": scoped_content_id(definition),
            "implementation_content_id": implementation.content_id,
            "cases": tuple(cases),
            "passed": passed,
        }
    )
    return passed, evidence


def _calculate_bounded_python(
    definition: ManagedComponentDefinition,
    frame: pd.DataFrame,
    parameters: dict[str, str],
    implementation: BoundedPythonImplementation,
) -> pd.DataFrame:
    required = {"decision_at", "instrument_id", *(item.name for item in definition.inputs)}
    if not required.issubset(frame.columns):
        raise TemporalConformanceError("bounded partition inputs are incomplete")
    ordered = frame.sort_values(["instrument_id", "decision_at"]).reset_index(drop=True)
    output = definition.output_name
    rows: list[dict[str, object]] = []
    for _, group in ordered.groupby("instrument_id", sort=True):
        group = group.reset_index(drop=True)
        for local in range(len(group)):
            callback_output: ComponentOutput | None = None
            if definition.kind is ResearchComponentKind.FEATURE:
                start = max(0, local - definition.lookback)
                window = group.iloc[start : local + 1].reset_index(drop=True)
                partition: FeaturePartition | LabelPartition = FeaturePartition(
                    group.iloc[[local]].reset_index(drop=True).copy(deep=True),
                    window.copy(deep=True),
                )
            else:
                end = local + definition.horizon
                window = group.iloc[local : min(end + 1, len(group))].reset_index(
                    drop=True
                )
                if end >= len(group):
                    callback_output = ComponentOutput(
                        (None,),
                        (ComponentValueState.CENSORED,),
                        ("label.horizon.censored",),
                        ((),),
                    )
                    partition = LabelPartition(
                        group.iloc[[local]].reset_index(drop=True).copy(deep=True),
                        window.copy(deep=True),
                        definition.horizon,
                    )
                else:
                    partition = LabelPartition(
                        group.iloc[[local]].reset_index(drop=True).copy(deep=True),
                        window.copy(deep=True),
                        definition.horizon,
                    )
                    callback_output = implementation.callback(
                        partition, ParameterValues(parameters)
                    )
            if definition.kind is ResearchComponentKind.FEATURE:
                callback_output = implementation.callback(
                    partition, ParameterValues(parameters)
                )
            if callback_output is None:
                raise TemporalConformanceError(
                    "bounded callback produced no output"
                )
            _validate_callback_output(callback_output, len(window))
            value = callback_output.values[0]
            state = callback_output.states[0]
            reason = callback_output.reason_codes[0]
            if state is ComponentValueState.COMPUTED:
                if value is None or not math.isfinite(value):
                    raise TemporalConformanceError(
                        "computed bounded output must be finite"
                    )
            elif value is not None:
                raise TemporalConformanceError(
                    "noncomputed bounded output must be null"
                )
            used = callback_output.used_input_rows[0]
            availabilities: list[pd.Timestamp] = []
            for position in used:
                for item in definition.inputs:
                    column = f"{item.name}_available_at"
                    candidate = (
                        window.loc[position, column]
                        if column in window
                        else window.loc[position, "decision_at"]
                    )
                    if not pd.isna(candidate):
                        availabilities.append(pd.Timestamp(cast("Any", candidate)))
            available_at = max(availabilities) if availabilities else None
            if (
                state is ComponentValueState.COMPUTED
                and available_at is None
            ):
                raise TemporalConformanceError(
                    "computed bounded output requires used-input availability"
                )
            core = group.iloc[local]
            label_end = (
                window.iloc[-1]["decision_at"]
                if definition.kind is ResearchComponentKind.LABEL
                else None
            )
            if definition.kind is ResearchComponentKind.LABEL and available_at is not None:
                available_at = max(
                    available_at, pd.Timestamp(cast("Any", label_end))
                )
            row: dict[str, object] = {
                "decision_at": core["decision_at"],
                "session_date": core.get("session_date"),
                "instrument_id": core["instrument_id"],
                output: value,
                f"{output}_state": state.value,
                f"{output}_reason_code": reason,
                f"{output}_available_at": available_at,
                f"{output}_lineage_content_id": str(
                    scoped_content_id(
                        {
                            "schema": "persistra.research.bounded_component_row",
                            "definition": definition.name,
                            "version": definition.version,
                            "decision_at": core["decision_at"],
                            "instrument_id": str(core["instrument_id"]),
                            "used_input_rows": used,
                            "state": state,
                            "value": (
                                None if value is None else float(value).hex()
                            ),
                        }
                    )
                ),
            }
            if definition.kind is ResearchComponentKind.LABEL:
                row["label_start_at"] = core["decision_at"]
                row["label_end_at"] = label_end
            rows.append(row)
    return pd.DataFrame(rows)


def _validate_callback_output(output: ComponentOutput, window_size: int) -> None:
    if len(output.values) != 1:
        raise TemporalConformanceError(
            "bounded callback must return exactly one core row"
        )
    used = output.used_input_rows[0]
    if len(set(used)) != len(used) or any(
        position < 0 or position >= window_size for position in used
    ):
        raise TemporalConformanceError("bounded callback used-input mask is invalid")
    if output.states[0] is ComponentValueState.COMPUTED and not used:
        raise TemporalConformanceError(
            "computed bounded callback output requires used inputs"
        )


def _calculate(
    definition: ManagedComponentDefinition,
    frame: pd.DataFrame,
    parameters: dict[str, str],
) -> pd.DataFrame:
    required = {"decision_at", "instrument_id"}
    if not required.issubset(frame.columns):
        raise FeatureMaterializationError(
            "component base dataset lacks decision_at/instrument_id"
        )
    ordered = frame.sort_values(["instrument_id", "decision_at"]).reset_index(drop=True)
    output = definition.output_name
    values = pd.Series(float("nan"), index=ordered.index, dtype="float64")
    states = pd.Series(
        ComponentValueState.INPUT_MISSING.value, index=ordered.index, dtype="string"
    )
    reasons = pd.Series(
        "component.input.missing", index=ordered.index, dtype="string"
    )
    available = pd.Series(pd.NaT, index=ordered.index, dtype="datetime64[us, UTC]")
    label_end = pd.Series(pd.NaT, index=ordered.index, dtype="datetime64[us, UTC]")
    inputs = [item.name for item in definition.inputs]
    for _, group in ordered.groupby("instrument_id", sort=True):
        index = list(group.index)
        for local, position in enumerate(index):
            value: float | None = None
            state = ComponentValueState.COMPUTED
            reason = "component.computed"
            used_positions: list[int] = [position]
            try:
                value, used_positions = _operator_value(
                    definition, parameters, ordered, index, local, inputs
                )
            except _Insufficient:
                state = (
                    ComponentValueState.CENSORED
                    if definition.kind is ResearchComponentKind.LABEL
                    else ComponentValueState.INSUFFICIENT_HISTORY
                )
                reason = (
                    "label.horizon.censored"
                    if definition.kind is ResearchComponentKind.LABEL
                    else "feature.history.insufficient"
                )
            except (_Missing, KeyError):
                state = ComponentValueState.INPUT_MISSING
                reason = "component.input.missing"
            except (ArithmeticError, ValueError, TypeError):
                state = ComponentValueState.INVALID_NUMERIC
                reason = "component.numeric.invalid"
            if value is None or not math.isfinite(value):
                if state is ComponentValueState.COMPUTED:
                    state = ComponentValueState.INVALID_NUMERIC
                    reason = "component.numeric.invalid"
                value = None
            else:
                values.loc[position] = value
                availabilities: list[pd.Timestamp] = []
                for used in used_positions:
                    for item in definition.inputs:
                        column = f"{item.name}_available_at"
                        candidate = (
                            ordered.loc[used, column]
                            if column in ordered
                            else ordered.loc[used, "decision_at"]
                        )
                        if not pd.isna(candidate):
                            availabilities.append(
                                pd.Timestamp(cast("Any", candidate))
                            )
                if availabilities:
                    available.loc[position] = max(availabilities)
            states.loc[position] = state.value
            reasons.loc[position] = reason
            if definition.kind is ResearchComponentKind.LABEL and used_positions:
                label_end.loc[position] = ordered.loc[
                    max(used_positions), "decision_at"
                ]
    result = ordered[["decision_at", "instrument_id"]].copy()
    if "session_date" in ordered:
        result.insert(1, "session_date", ordered["session_date"])
    result[output] = values
    result[f"{output}_state"] = states
    result[f"{output}_reason_code"] = reasons
    result[f"{output}_available_at"] = available
    result[f"{output}_lineage_content_id"] = [
        str(
            scoped_content_id(
                {
                    "schema": "persistra.research.component_row",
                    "definition": definition.name,
                    "version": definition.version,
                    "decision_at": row.decision_at,
                    "instrument_id": str(row.instrument_id),
                    "state": states.iloc[index],
                    "value": (
                        None if pd.isna(values.iloc[index]) else values.iloc[index].hex()
                    ),
                }
            )
        )
        for index, row in enumerate(result.itertuples(index=False))
    ]
    if definition.kind is ResearchComponentKind.LABEL:
        result["label_start_at"] = result["decision_at"]
        result["label_end_at"] = label_end
    return result


class _Missing(Exception):
    pass


class _Insufficient(Exception):
    pass


def _decode_version(value: object) -> ResearchComponentVersion:
    if isinstance(value, str):
        return ResearchComponentVersion.parse(value)
    if not isinstance(value, dict):
        raise FeatureDefinitionError("stored component version is invalid")
    mapping = cast("dict[str, Any]", value)
    return ResearchComponentVersion(
        int(mapping["major"]),
        int(mapping["minor"]),
        int(mapping["patch"]),
    )


def _operator_value(
    definition: ManagedComponentDefinition,
    parameters: dict[str, str],
    frame: pd.DataFrame,
    group_index: list[int],
    local: int,
    inputs: list[str],
) -> tuple[float, list[int]]:
    operator = definition.operator
    position = group_index[local]

    def number(at: int, input_index: int = 0) -> float:
        if at < 0 or at >= len(group_index):
            raise _Insufficient
        value = frame.loc[group_index[at], inputs[input_index]]
        if pd.isna(value):
            raise _Missing
        return float(cast("Any", value))

    if operator in {ManagedOperator.PRICE, ManagedOperator.MACRO_LEVEL}:
        return number(local), [position]
    if operator is ManagedOperator.FUNDAMENTAL_RATIO:
        denominator = number(local, 1)
        if denominator == 0:
            raise ArithmeticError
        return number(local) / denominator, [position]
    if operator is ManagedOperator.QUOTED_SPREAD_BPS:
        bid, ask = number(local), number(local, 1)
        if bid <= 0 or ask < bid:
            raise ArithmeticError
        return 10_000 * (ask - bid) / ((ask + bid) / 2), [position]
    if operator is ManagedOperator.CROSS_SECTIONAL_RANK:
        decision = frame.loc[position, "decision_at"]
        panel = pd.to_numeric(
            frame.loc[frame["decision_at"] == decision, inputs[0]], errors="coerce"
        )
        rank = panel.rank(method="average", pct=True)
        return float(rank.loc[position]), [position]
    if operator in {
        ManagedOperator.CROSS_SECTIONAL_ZSCORE,
        ManagedOperator.CROSS_SECTIONAL_WINSORIZE,
    }:
        decision = frame.loc[position, "decision_at"]
        panel = pd.to_numeric(
            frame.loc[frame["decision_at"] == decision, inputs[0]], errors="coerce"
        ).dropna()
        current = number(local)
        if operator is ManagedOperator.CROSS_SECTIONAL_ZSCORE:
            standard = float(panel.std(ddof=0))
            if standard <= 0:
                raise ArithmeticError
            return (current - float(panel.mean())) / standard, [position]
        lower = float(parameters.get("lower", "0.01"))
        upper = float(parameters.get("upper", "0.99"))
        return max(float(panel.quantile(lower)), min(float(panel.quantile(upper)), current)), [
            position
        ]
    if operator in {
        ManagedOperator.FORWARD_RETURN,
        ManagedOperator.FUTURE_VOLATILITY,
        ManagedOperator.FUTURE_DRAWDOWN,
    }:
        end = local + definition.horizon
        if end >= len(group_index):
            raise _Insufficient
        used = list(range(local, end + 1))
        prices = [number(item) for item in used]
        if any(value <= 0 for value in prices):
            raise ArithmeticError
        if operator is ManagedOperator.FORWARD_RETURN:
            return prices[-1] / prices[0] - 1, [group_index[item] for item in used]
        if operator is ManagedOperator.FUTURE_VOLATILITY:
            returns = [
                math.log(prices[index] / prices[index - 1])
                for index in range(1, len(prices))
            ]
            if len(returns) < 2:
                raise _Insufficient
            mean = sum(returns) / len(returns)
            variance = sum((item - mean) ** 2 for item in returns) / (
                len(returns) - 1
            )
            return math.sqrt(variance), [group_index[item] for item in used]
        peak = prices[0]
        drawdown = 0.0
        for price in prices:
            peak = max(peak, price)
            drawdown = max(drawdown, 1 - price / peak)
        return drawdown, [group_index[item] for item in used]
    lookback = definition.lookback or int(parameters.get("lookback", "1"))
    left = local - lookback
    right = local - int(parameters.get("skip", "0"))
    if left < 0:
        raise _Insufficient
    left_value, right_value = number(left), number(right)
    if left_value <= 0 or right_value <= 0:
        raise ArithmeticError
    used = [group_index[left], group_index[right]]
    if operator in {
        ManagedOperator.SIMPLE_RETURN,
        ManagedOperator.MOMENTUM,
        ManagedOperator.REVERSAL,
        ManagedOperator.FUNDAMENTAL_GROWTH,
        ManagedOperator.MACRO_CHANGE,
        ManagedOperator.ESTIMATE_REVISION,
    }:
        result = right_value / left_value - 1
        return (-result if operator is ManagedOperator.REVERSAL else result), used
    if operator is ManagedOperator.LOG_RETURN:
        return math.log(right_value / left_value), used
    window_positions = list(range(left, local + 1))
    prices = [number(item) for item in window_positions]
    if operator is ManagedOperator.MAX_DRAWDOWN:
        peak = prices[0]
        drawdown = 0.0
        for price in prices:
            peak = max(peak, price)
            drawdown = max(drawdown, 1 - price / peak)
        return drawdown, [group_index[item] for item in window_positions]
    returns = [
        math.log(prices[index] / prices[index - 1])
        for index in range(1, len(prices))
    ]
    if operator is ManagedOperator.REALIZED_VOLATILITY:
        if len(returns) < 2:
            raise _Insufficient
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
        annualization = float(parameters.get("annualization_factor", "1"))
        return math.sqrt(variance * annualization), [
            group_index[item] for item in window_positions
        ]
    raise FeatureMaterializationError(
        "managed operator is registered but not executable in this version"
    )


def _publish_relation(
    connection: ManagedConnection,
    kind: ResearchComponentKind,
    relation: str,
    output: str,
    frame: pd.DataFrame,
) -> None:
    schema = "feature_data" if kind is ResearchComponentKind.FEATURE else "label_data"
    label_columns = (
        ", label_start_at TIMESTAMPTZ, label_end_at TIMESTAMPTZ"
        if kind is ResearchComponentKind.LABEL
        else ""
    )
    connection.execute(
        f'CREATE TABLE {schema}."{relation}" ('
        "decision_at TIMESTAMPTZ NOT NULL, session_date DATE, instrument_id UUID NOT NULL, "
        f'"{output}" DOUBLE, "{output}_state" VARCHAR NOT NULL, '
        f'"{output}_reason_code" VARCHAR NOT NULL, '
        f'"{output}_available_at" TIMESTAMPTZ, '
        f'"{output}_lineage_content_id" VARCHAR NOT NULL{label_columns}, '
        "PRIMARY KEY (decision_at, instrument_id))"
    )
    columns = [
        "decision_at",
        "session_date",
        "instrument_id",
        output,
        f"{output}_state",
        f"{output}_reason_code",
        f"{output}_available_at",
        f"{output}_lineage_content_id",
    ]
    if kind is ResearchComponentKind.LABEL:
        columns.extend(["label_start_at", "label_end_at"])
    records = [
        tuple(
            None if pd.isna(value) else value
            for value in row
        )
        for row in frame.reindex(columns=columns).itertuples(index=False, name=None)
    ]
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f'INSERT INTO {schema}."{relation}" VALUES ({placeholders})', records
    )


def _frame_manifest(
    frame: pd.DataFrame, output: str, execution: ContentId
) -> ContentId:
    rows = tuple(
        {
            "available_at": (
                None
                if pd.isna(row[4])
                else pd.Timestamp(row[4]).to_pydatetime()
            ),
            "decision_at": pd.Timestamp(row[0]).to_pydatetime(),
            "instrument_id": str(row[1]),
            "state": str(row[3]),
            "value": None if pd.isna(row[2]) else float(row[2]).hex(),
        }
        for row in frame[
            [
                "decision_at",
                "instrument_id",
                output,
                f"{output}_state",
                f"{output}_available_at",
            ]
        ].itertuples(index=False, name=None)
    )
    return scoped_content_id(
        {
            "schema": "persistra.research.component_output",
            "execution": execution,
            "rows": rows,
        }
    )


def _output_schema_id(output: str) -> ContentId:
    return scoped_content_id(
        {
            "schema": "persistra.research.component_output_schema",
            "output": output,
            "columns": (
                output,
                f"{output}_state",
                f"{output}_reason_code",
                f"{output}_available_at",
                f"{output}_lineage_content_id",
            ),
        }
    )
