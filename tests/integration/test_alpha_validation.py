from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest
from test_research_components import (
    NOW,
    VERSION,
    _feature_definition,  # pyright: ignore[reportPrivateUsage]
    _seed_build,  # pyright: ignore[reportPrivateUsage]
)

from persistra import Project, ProjectMode
from persistra.catalog.models import CompositeSnapshotId
from persistra.db.connection import ManagedConnection
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.reference import InstrumentId, UniverseEvaluationId
from persistra.research import (
    AlphaAnalysisDefinition,
    AlphaAnalysisRef,
    AlphaMetricKind,
    ComponentInputKind,
    ComponentInputSpec,
    DecisionWidth,
    FeatureDefinitionRef,
    FeatureInputRef,
    LabelDefinitionRef,
    LabelInputRef,
    LeakageScope,
    ManagedComponentDefinition,
    ManagedOperator,
    ResearchComponentKind,
    ResearchDatasetBuildId,
    ResearchDatasetId,
    ResearchDatasetRole,
    ValidationInputSpec,
    ValidationRole,
    ValidationSchemeDefinition,
    ValidationSchemeKind,
    ValidationSchemeRef,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_expanding_validation_purges_closed_label_overlap(tmp_path: Path) -> None:
    root, build_id = _seed_build(tmp_path)
    feature_ref = FeatureDefinitionRef(
        QualifiedName("feature.simple_return"), VERSION
    )
    label_ref = LabelDefinitionRef(QualifiedName("label.forward_return"), VERSION)
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
        assumptions_and_limitations="One exact decision-step horizon.",
        horizon=1,
    )
    scheme = ValidationSchemeDefinition(
        QualifiedName("validation.expanding"),
        1,
        ValidationSchemeKind.EXPANDING,
        DecisionWidth(1),
        DecisionWidth(1),
        DecisionWidth(1),
    )

    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        project.services.research.features.register(_feature_definition())
        project.services.research.labels.register(label)
        feature = project.services.research.features.materialize(
            definition=feature_ref, primary_dataset=build_id
        )
        label_result = project.services.research.labels.materialize(
            definition=label_ref, primary_dataset=build_id
        )
        analysis = project.services.research.datasets.enrich(
            base_build=build_id,
            inputs=(
                FeatureInputRef.from_reference(
                    feature.reference, ("simple_return",)
                ),
                LabelInputRef.from_reference(
                    label_result.reference, ("forward_return",)
                ),
            ),
            role=ResearchDatasetRole.ANALYSIS,
        )
        project.services.research.validation.register(scheme)
        plan = project.services.research.validation.create_plan(
            scheme=ValidationSchemeRef(scheme.name, scheme.version),
            input_spec=ValidationInputSpec(
                analysis.reference.research_dataset_build_id,
                ("simple_return",),
                "forward_return",
                LeakageScope.ENTITY,
            ),
        )
        retry = project.services.research.validation.create_plan(
            scheme=ValidationSchemeRef(scheme.name, scheme.version),
            input_spec=ValidationInputSpec(
                analysis.reference.research_dataset_build_id,
                ("simple_return",),
                "forward_return",
                LeakageScope.ENTITY,
            ),
        )
        assert retry.reference == plan.reference
        membership = plan.membership()
        assert ValidationRole.TEST.value in set(membership["validation_role"])
        assert "validation.purged.overlap" in set(membership["reason_code"])


def _seed_alpha_build(tmp_path: Path) -> tuple[Path, ResearchDatasetBuildId]:
    layout = Project.init(tmp_path / "alpha-project")
    build_id = ResearchDatasetBuildId.new()
    relation = f"dataset_{build_id.value.hex}"
    assert layout.research_database_path is not None
    connection = ManagedConnection(layout.research_database_path, read_only=False)
    try:
        connection.execute(
            f'CREATE TABLE research_data."{relation}" ('
            "research_dataset_build_id UUID NOT NULL, "
            "decision_at TIMESTAMPTZ NOT NULL, session_date DATE NOT NULL, "
            "instrument_id UUID NOT NULL, research_row_usable BOOLEAN NOT NULL, "
            "signal DOUBLE, signal_state VARCHAR NOT NULL, "
            "outcome DOUBLE, outcome_state VARCHAR NOT NULL, "
            "outcome_label_start_at TIMESTAMPTZ, "
            "outcome_label_end_at TIMESTAMPTZ)"
        )
        instruments = [InstrumentId.new() for _ in range(3)]
        rows: list[tuple[object, ...]] = []
        for decision_index in range(3):
            decision = datetime(2026, 1, 2 + decision_index, 21, tzinfo=UTC)
            end = datetime(2026, 1, 3 + decision_index, 21, tzinfo=UTC)
            for rank, instrument in enumerate(instruments, 1):
                rows.append(
                    (
                        build_id.value,
                        decision,
                        date(2026, 1, 2 + decision_index),
                        instrument.value,
                        True,
                        float(rank),
                        "computed",
                        float(rank * 2 + decision_index),
                        "computed",
                        decision,
                        end,
                    )
                )
        connection.executemany(
            f'INSERT INTO research_data."{relation}" VALUES '
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.execute(
            "INSERT INTO research.research_dataset_builds VALUES "
            "(?, ?, 1, ?, ?, ?, ?, ?, 9, 9, ?)",
            [
                build_id.value,
                ResearchDatasetId.new().value,
                CompositeSnapshotId.new().value,
                UniverseEvaluationId.new().value,
                str(ContentId.from_bytes(b"alpha-execution")),
                relation,
                str(ContentId.from_bytes(b"alpha-output")),
                NOW,
            ],
        )
        connection.execute(
            "INSERT INTO research.research_dataset_enrichments VALUES "
            "(?, ?, 'analysis', 'label', 'opaque', 'complete', 'safe', false)",
            [build_id.value, build_id.value],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return layout.root, build_id


def test_alpha_diagnostics_compute_cross_sectional_series(tmp_path: Path) -> None:
    root, build_id = _seed_alpha_build(tmp_path)
    definition = AlphaAnalysisDefinition(
        QualifiedName("alpha.signal_quality"),
        1,
        build_id,
        ("signal",),
        ("outcome",),
        (
            AlphaMetricKind.PEARSON_IC,
            AlphaMetricKind.SPEARMAN_IC,
            AlphaMetricKind.COVERAGE,
            AlphaMetricKind.QUANTILE_LABELS,
            AlphaMetricKind.MONOTONICITY,
        ),
        quantiles=3,
    )
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        project.services.research.alpha.register(definition)
        result = project.services.research.alpha.execute(
            AlphaAnalysisRef(definition.name, definition.version)
        )
        retry = project.services.research.alpha.execute(
            AlphaAnalysisRef(definition.name, definition.version)
        )
        assert retry.reference == result.reference
        summaries = {item.metric_kind: item for item in result.summaries()}
        assert summaries[AlphaMetricKind.PEARSON_IC.value].estimate == pytest.approx(
            1.0
        )
        assert summaries[AlphaMetricKind.SPEARMAN_IC.value].estimate == pytest.approx(
            1.0
        )
        assert summaries[AlphaMetricKind.COVERAGE.value].estimate == pytest.approx(1.0)
        assert len(result.series()) == 15
