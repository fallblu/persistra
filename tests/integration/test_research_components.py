from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from persistra import Project, ProjectMode
from persistra.catalog.models import CompositeSnapshotId
from persistra.db.connection import ManagedConnection
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.errors import FeatureDefinitionError
from persistra.reference import InstrumentId, UniverseEvaluationId
from persistra.research import (
    BoundedPythonImplementation,
    BoundedSqlImplementation,
    ComponentImplementationKind,
    ComponentInputKind,
    ComponentInputSpec,
    ComponentOutput,
    ComponentValueState,
    FeatureDefinitionRef,
    FeaturePartition,
    LabelDefinitionRef,
    LabelPartition,
    ManagedComponentDefinition,
    ManagedOperator,
    ParameterValues,
    ResearchComponentKind,
    ResearchComponentVersion,
    ResearchDatasetBuildId,
    ResearchDatasetId,
)

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 2, 2, 12, tzinfo=UTC)
VERSION = ResearchComponentVersion(1, 0, 0)


def _seed_build(tmp_path: Path) -> tuple[Path, ResearchDatasetBuildId]:
    layout = Project.init(tmp_path / "project")
    build_id = ResearchDatasetBuildId.new()
    instrument_id = InstrumentId.new()
    relation = f"dataset_{build_id.value.hex}"
    assert layout.research_database_path is not None
    connection = ManagedConnection(layout.research_database_path, read_only=False)
    try:
        connection.execute(
            f'CREATE TABLE research_data."{relation}" ('
            "decision_at TIMESTAMPTZ NOT NULL, session_date DATE NOT NULL, "
            "instrument_id UUID NOT NULL, close DOUBLE NOT NULL)"
        )
        connection.executemany(
            f'INSERT INTO research_data."{relation}" VALUES (?, ?, ?, ?)',
            [
                (
                    datetime(2026, 1, 2, 21, tzinfo=UTC),
                    date(2026, 1, 2),
                    instrument_id.value,
                    100.0,
                ),
                (
                    datetime(2026, 1, 5, 21, tzinfo=UTC),
                    date(2026, 1, 5),
                    instrument_id.value,
                    110.0,
                ),
                (
                    datetime(2026, 1, 6, 21, tzinfo=UTC),
                    date(2026, 1, 6),
                    instrument_id.value,
                    121.0,
                ),
            ],
        )
        connection.execute(
            "INSERT INTO research.research_dataset_builds VALUES "
            "(?, ?, 1, ?, ?, ?, ?, ?, 3, 3, ?)",
            [
                build_id.value,
                ResearchDatasetId.new().value,
                CompositeSnapshotId.new().value,
                UniverseEvaluationId.new().value,
                str(ContentId.from_bytes(b"component-fixture-execution")),
                relation,
                str(ContentId.from_bytes(b"component-fixture-output")),
                NOW,
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return layout.root, build_id


def _feature_definition() -> ManagedComponentDefinition:
    return ManagedComponentDefinition(
        name=QualifiedName("feature.simple_return"),
        version=VERSION,
        kind=ResearchComponentKind.FEATURE,
        operator=ManagedOperator.SIMPLE_RETURN,
        inputs=(
            ComponentInputSpec(
                "close",
                1,
                ComponentInputKind.DATASET_FIELD,
                field_name="close",
            ),
        ),
        output_name="simple_return",
        assumptions_and_limitations="Requires positive consecutive close observations.",
        lookback=1,
    )


def test_unified_feature_label_graph_materializes_exact_outputs(tmp_path: Path) -> None:
    root, build_id = _seed_build(tmp_path)
    feature_ref = FeatureDefinitionRef(
        QualifiedName("feature.simple_return"), VERSION
    )
    derived_ref = FeatureDefinitionRef(
        QualifiedName("feature.derived_return"), VERSION
    )
    label_ref = LabelDefinitionRef(QualifiedName("label.forward_return"), VERSION)
    derived = ManagedComponentDefinition(
        name=derived_ref.name,
        version=VERSION,
        kind=ResearchComponentKind.FEATURE,
        operator=ManagedOperator.PRICE,
        inputs=(
            ComponentInputSpec(
                "return_input",
                1,
                ComponentInputKind.FEATURE_OUTPUT,
                dependency=feature_ref,
                dependency_output="simple_return",
            ),
        ),
        output_name="derived_return",
        assumptions_and_limitations="Passes through the pinned causal return feature.",
        lookback=0,
    )
    label = ManagedComponentDefinition(
        name=label_ref.name,
        version=VERSION,
        kind=ResearchComponentKind.LABEL,
        operator=ManagedOperator.FORWARD_RETURN,
        inputs=(
            ComponentInputSpec(
                "close",
                1,
                ComponentInputKind.DATASET_FIELD,
                field_name="close",
            ),
        ),
        output_name="forward_return",
        assumptions_and_limitations="Censors rows without a complete forward horizon.",
        horizon=1,
    )

    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        registered = project.services.research.features.register(
            _feature_definition()
        )
        assert registered.version == VERSION
        project.services.research.features.register(derived)
        project.services.research.labels.register(label)

        result = project.services.research.features.materialize(
            definition=derived_ref,
            primary_dataset=build_id,
        )
        retry = project.services.research.features.materialize(
            definition=derived_ref,
            primary_dataset=build_id,
        )
        assert retry.reference == result.reference
        rows = result.rows()
        assert rows["derived_return_state"].tolist() == [
            ComponentValueState.INPUT_MISSING.value,
            ComponentValueState.COMPUTED.value,
            ComponentValueState.COMPUTED.value,
        ]
        assert rows["derived_return"].iloc[1:].tolist() == pytest.approx([0.1, 0.1])

        label_result = project.services.research.labels.materialize(
            definition=label_ref,
            primary_dataset=build_id,
        )
        label_rows = label_result.rows()
        assert label_rows["forward_return"].iloc[:2].tolist() == pytest.approx(
            [0.1, 0.1]
        )
        assert label_rows["forward_return_state"].iloc[2] == (
            ComponentValueState.CENSORED.value
        )
        assert not label_result.reference.structurally_decision_eligible


def test_feature_definition_rejects_label_dependency() -> None:
    with pytest.raises(FeatureDefinitionError):
        ManagedComponentDefinition(
            name=QualifiedName("feature.invalid"),
            version=VERSION,
            kind=ResearchComponentKind.FEATURE,
            operator=ManagedOperator.PRICE,
            inputs=(
                ComponentInputSpec(
                    "future",
                    1,
                    ComponentInputKind.LABEL_OUTPUT,
                    dependency=LabelDefinitionRef(
                        QualifiedName("label.forward_return"), VERSION
                    ),
                    dependency_output="forward_return",
                ),
            ),
            output_name="invalid",
            assumptions_and_limitations="Invalid by construction.",
        )


def _bounded_return(
    partition: FeaturePartition | LabelPartition, parameters: ParameterValues
) -> ComponentOutput:
    assert isinstance(partition, FeaturePartition)
    assert parameters.get("scale", "1") == "1"
    history = partition.history_rows()
    if len(history) < 2:
        return ComponentOutput(
            (None,),
            (ComponentValueState.INSUFFICIENT_HISTORY,),
            ("feature.history.insufficient",),
            ((),),
        )
    value = float(history["close"].iloc[-1] / history["close"].iloc[-2] - 1)
    return ComponentOutput(
        (value,),
        (ComponentValueState.COMPUTED,),
        ("component.computed",),
        ((len(history) - 2, len(history) - 1),),
    )


def test_bounded_python_requires_exact_passing_conformance(tmp_path: Path) -> None:
    root, build_id = _seed_build(tmp_path)
    implementation_id = ContentId.from_bytes(b"bounded-return@1")
    reference = FeatureDefinitionRef(QualifiedName("feature.bounded_return"), VERSION)
    definition = ManagedComponentDefinition(
        name=reference.name,
        version=VERSION,
        kind=ResearchComponentKind.FEATURE,
        operator=ManagedOperator.SIMPLE_RETURN,
        inputs=(
            ComponentInputSpec(
                "close",
                1,
                ComponentInputKind.DATASET_FIELD,
                field_name="close",
            ),
        ),
        output_name="bounded_return",
        assumptions_and_limitations="Uses only one declared prior observation.",
        lookback=1,
        implementation_kind=ComponentImplementationKind.BOUNDED_PYTHON,
        implementation_content_id=implementation_id,
    )
    implementation = BoundedPythonImplementation(
        "bounded-return@1", implementation_id, _bounded_return
    )

    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        project.services.research.features.install_bounded_python(
            definition, implementation
        )
        conformance = project.services.research.features.conform(reference)
        assert conformance.passed
        result = project.services.research.features.materialize(
            definition=reference,
            primary_dataset=build_id,
        )
        rows = result.rows()
        assert rows["bounded_return_state"].tolist() == [
            ComponentValueState.INSUFFICIENT_HISTORY.value,
            ComponentValueState.COMPUTED.value,
            ComponentValueState.COMPUTED.value,
        ]
        assert rows["bounded_return"].iloc[1:].tolist() == pytest.approx([0.1, 0.1])


def test_bounded_sql_is_parsed_and_future_blind(tmp_path: Path) -> None:
    pytest.importorskip("sqlglot")
    root, build_id = _seed_build(tmp_path)
    reference = FeatureDefinitionRef(QualifiedName("feature.sql_return"), VERSION)
    implementation = BoundedSqlImplementation.create(
        "sql-return@1",
        "SELECT close / lag(close) OVER (ORDER BY decision_at "
        "ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) - 1 AS sql_return "
        "FROM ctx.partition",
    )
    definition = ManagedComponentDefinition(
        name=reference.name,
        version=VERSION,
        kind=ResearchComponentKind.FEATURE,
        operator=ManagedOperator.SIMPLE_RETURN,
        inputs=(
            ComponentInputSpec(
                "close",
                1,
                ComponentInputKind.DATASET_FIELD,
                field_name="close",
            ),
        ),
        output_name="sql_return",
        assumptions_and_limitations="Uses a parsed one-row preceding window.",
        lookback=1,
        implementation_kind=ComponentImplementationKind.BOUNDED_SQL,
        implementation_content_id=implementation.content_id,
    )

    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        project.services.research.features.install_bounded_sql(
            definition, implementation
        )
        assert project.services.research.features.conform(reference).passed
        result = project.services.research.features.materialize(
            definition=reference,
            primary_dataset=build_id,
        )
        assert result.rows()["sql_return"].iloc[1:].tolist() == pytest.approx(
            [0.1, 0.1]
        )
