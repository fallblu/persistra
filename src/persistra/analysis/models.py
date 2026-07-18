"""Initial structured performance metric contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from persistra.domain import ContentId, EntityId


class AnalysisArtifactId(EntityId):
    KIND: ClassVar[str] = "analysis_artifact"


class MetricState(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    INVALID_BASE = "invalid_base"
    UNDEFINED = "undefined"


@dataclass(frozen=True, slots=True)
class MetricResult:
    metric_name: str
    state: MetricState
    estimate: float | None
    unit: str
    observation_count: int
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class MetricsRef:
    analysis_artifact_id: AnalysisArtifactId
    execution_content_id: ContentId
    output_content_id: ContentId


@dataclass(frozen=True, slots=True)
class TabularAnalysisRef:
    analysis_artifact_id: AnalysisArtifactId
    analysis_kind: str
    execution_content_id: ContentId
    output_content_id: ContentId
    compatibility_state: str | None = None
