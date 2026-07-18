"""Finance-aware temporal validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.errors import ValidationSchemeError

if TYPE_CHECKING:
    from persistra.research.models import ResearchDatasetBuildId


class ValidationSchemeId(EntityId):
    KIND: ClassVar[str] = "validation_scheme"


class ValidationPlanId(EntityId):
    KIND: ClassVar[str] = "validation_plan"


class FinalHoldoutUseId(EntityId):
    KIND: ClassVar[str] = "final_holdout_use"


class ValidationSchemeKind(StrEnum):
    EXPANDING = "expanding"
    ROLLING = "rolling"
    COMBINATORIAL_PURGED = "combinatorial_purged"
    NESTED = "nested"


class LeakageScope(StrEnum):
    ENTITY = "entity"
    GROUP = "group"
    PANEL = "panel"


class ValidationRole(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    FINAL_HOLDOUT = "final_holdout"
    EXCLUDED = "excluded"


class EligibilityPolicy(StrEnum):
    COMPLETE_CASE = "complete_case"
    LABEL_COMPLETE = "label_complete"


class ValidationSampleState(StrEnum):
    ELIGIBLE = "eligible"
    DATASET_UNUSABLE = "dataset_unusable"
    FEATURE_NONCOMPUTED = "feature_noncomputed"
    LABEL_NONCOMPUTED = "label_noncomputed"
    INTERVAL_MISSING = "interval_missing"
    INTERVAL_INVALID = "interval_invalid"


@dataclass(frozen=True, slots=True)
class DecisionWidth:
    decisions: int

    def __post_init__(self) -> None:
        if self.decisions < 1:
            raise ValidationSchemeError("decision width must be positive")


@dataclass(frozen=True, slots=True)
class ValidationInputSpec:
    research_dataset_build_id: ResearchDatasetBuildId
    feature_outputs: tuple[str, ...]
    label_output: str
    leakage_scope: LeakageScope = LeakageScope.ENTITY
    eligibility_policy: EligibilityPolicy = EligibilityPolicy.COMPLETE_CASE

    def __post_init__(self) -> None:
        if (
            not self.feature_outputs
            or len(set(self.feature_outputs)) != len(self.feature_outputs)
            or not self.label_output
        ):
            raise ValidationSchemeError(
                "validation requires unique features and one label"
            )


@dataclass(frozen=True, slots=True)
class ValidationSchemeDefinition:
    name: QualifiedName
    version: int
    kind: ValidationSchemeKind
    minimum_train: DecisionWidth
    test_width: DecisionWidth
    step_width: DecisionWidth
    rolling_train_width: DecisionWidth | None = None
    embargo: DecisionWidth | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValidationSchemeError("validation scheme version must be positive")
        if self.kind is ValidationSchemeKind.ROLLING and self.rolling_train_width is None:
            raise ValidationSchemeError("rolling validation requires a train width")
        if (
            self.kind is ValidationSchemeKind.EXPANDING
            and self.rolling_train_width is not None
        ):
            raise ValidationSchemeError(
                "expanding validation cannot declare a rolling width"
            )
        if self.kind not in {
            ValidationSchemeKind.EXPANDING,
            ValidationSchemeKind.ROLLING,
        }:
            raise ValidationSchemeError(
                "this validation executor supports expanding and rolling schemes"
            )


@dataclass(frozen=True, slots=True)
class ValidationSchemeRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedValidationSchemeRef:
    validation_scheme_id: ValidationSchemeId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ValidationPlanRef:
    validation_plan_id: ValidationPlanId
    validation_scheme_id: ValidationSchemeId
    definition_version: int
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    membership_content_id: ContentId
    fold_count: int
    sample_count: int
    purged_count: int
    embargoed_count: int
