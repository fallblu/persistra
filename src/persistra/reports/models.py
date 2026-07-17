"""Self-contained phase-4 report contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId

if TYPE_CHECKING:
    from persistra.analysis import AnalysisArtifactId
    from persistra.simulation import RunRecordId


class ReportPlanId(EntityId):
    KIND: ClassVar[str] = "report_plan"


class ReportOutputId(EntityId):
    KIND: ClassVar[str] = "report_output"


@dataclass(frozen=True, slots=True)
class ReportRequest:
    run_record_id: RunRecordId
    metrics_artifact_id: AnalysisArtifactId
    title: str = "Persistra momentum strategy report"


@dataclass(frozen=True, slots=True)
class ReportPlan:
    report_plan_id: ReportPlanId
    request: ReportRequest
    execution_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ReportRef:
    report_output_id: ReportOutputId
    report_plan_id: ReportPlanId
    analysis_artifact_id: AnalysisArtifactId
    output_content_id: ContentId
    byte_count: int
