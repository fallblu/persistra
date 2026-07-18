from __future__ import annotations

from typing import TYPE_CHECKING

from test_research_components import (
    NOW,
    VERSION,
    _feature_definition,  # pyright: ignore[reportPrivateUsage]
    _seed_build,  # pyright: ignore[reportPrivateUsage]
)

from persistra import Project, ProjectMode
from persistra.domain import FixedClock, QualifiedName
from persistra.research import (
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
