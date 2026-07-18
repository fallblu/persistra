"""Typed alpha-diagnostic definitions and immutable result references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.errors import AlphaAnalysisDefinitionError

if TYPE_CHECKING:
    from persistra.research.models import ResearchDatasetBuildId


class AlphaAnalysisDefinitionId(EntityId):
    KIND: ClassVar[str] = "alpha_analysis_definition"


class AlphaAnalysisResultId(EntityId):
    KIND: ClassVar[str] = "alpha_analysis_result"


class AnalysisIntent(StrEnum):
    EXPLORATORY = "exploratory"
    VALIDATION = "validation"
    CONFIRMATORY_HOLDOUT = "confirmatory_holdout"


class AlphaMetricKind(StrEnum):
    PEARSON_IC = "pearson_ic"
    SPEARMAN_IC = "spearman_ic"
    QUANTILE_LABELS = "quantile_labels"
    COVERAGE = "coverage"
    MONOTONICITY = "monotonicity"
    TURNOVER = "turnover"
    PERSISTENCE = "persistence"
    DECAY = "decay"
    AUTOCORRELATION = "autocorrelation"
    CATEGORICAL_EXPOSURE = "categorical_exposure"
    NUMERIC_EXPOSURE = "numeric_exposure"
    JOINT_EXPOSURE = "joint_exposure"


class MetricValueState(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    ZERO_DISPERSION = "zero_dispersion"
    RANK_DEFICIENT = "rank_deficient"
    INVALID_NUMERIC = "invalid_numeric"
    EMPTY_MEMBERSHIP = "empty_membership"


class InferenceKind(StrEnum):
    NONE = "none"
    HAC = "hac"
    MOVING_BLOCK_BOOTSTRAP = "moving_block_bootstrap"


class PValueAdjustment(StrEnum):
    NONE = "none"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"


@dataclass(frozen=True, slots=True)
class AlphaAnalysisDefinition:
    name: QualifiedName
    version: int
    research_dataset_build_id: ResearchDatasetBuildId
    feature_outputs: tuple[str, ...]
    label_outputs: tuple[str, ...]
    metrics: tuple[AlphaMetricKind, ...]
    intent: AnalysisIntent = AnalysisIntent.EXPLORATORY
    quantiles: int = 5
    inference: InferenceKind = InferenceKind.HAC
    p_value_adjustment: PValueAdjustment = PValueAdjustment.BENJAMINI_HOCHBERG

    def __post_init__(self) -> None:
        if self.version < 1:
            raise AlphaAnalysisDefinitionError("alpha definition version must be positive")
        if (
            not self.feature_outputs
            or not self.label_outputs
            or len(set(self.feature_outputs)) != len(self.feature_outputs)
            or len(set(self.label_outputs)) != len(self.label_outputs)
            or not self.metrics
            or len(set(self.metrics)) != len(self.metrics)
        ):
            raise AlphaAnalysisDefinitionError(
                "alpha inputs and metrics must be nonempty and unique"
            )
        if not 2 <= self.quantiles <= 100:
            raise AlphaAnalysisDefinitionError("alpha quantile count is out of range")
        if self.intent is AnalysisIntent.CONFIRMATORY_HOLDOUT:
            raise AlphaAnalysisDefinitionError(
                "confirmatory analysis requires a sealed holdout capability"
            )


@dataclass(frozen=True, slots=True)
class AlphaAnalysisRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedAlphaAnalysisRef:
    alpha_analysis_definition_id: AlphaAnalysisDefinitionId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class AlphaAnalysisResultRef:
    alpha_analysis_result_id: AlphaAnalysisResultId
    alpha_analysis_definition_id: AlphaAnalysisDefinitionId
    definition_version: int
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    output_content_id: ContentId


@dataclass(frozen=True, slots=True)
class AlphaMetricResult:
    feature_name: str
    label_name: str
    metric_kind: str
    state: MetricValueState
    estimate: float | None
    observation_count: int
    reason_code: str | None
