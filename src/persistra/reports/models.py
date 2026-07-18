"""Immutable HTML report planning and output contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId

if TYPE_CHECKING:
    from persistra.analysis import AnalysisArtifactId
    from persistra.simulation import RunRecordId


class ReportPlanId(EntityId):
    KIND: ClassVar[str] = "report_plan"


class ReportOutputId(EntityId):
    KIND: ClassVar[str] = "report_output"


class ReportOutputMode(StrEnum):
    SELF_CONTAINED_HTML = "self_contained_html"
    DIRECTORY_BUNDLE = "directory_bundle"


@dataclass(frozen=True, slots=True)
class ReportLimits:
    max_metric_rows: int = 10_000
    max_report_bytes: int = 500_000_000
    max_bundle_files: int = 32

    def __post_init__(self) -> None:
        if min(self.max_metric_rows, self.max_report_bytes, self.max_bundle_files) < 1:
            raise ValueError("report limits must be positive")


@dataclass(frozen=True, slots=True)
class ReportSectionSpec:
    name: str
    title: str
    failure: str = "render_unavailable"

    def __post_init__(self) -> None:
        if not self.name or not self.title:
            raise ValueError("report section name and title are required")
        if self.failure not in {
            "fail_report",
            "render_unavailable",
            "omit_with_reason",
        }:
            raise ValueError("report section failure policy is invalid")


@dataclass(frozen=True, slots=True)
class ReportRequest:
    run_record_id: RunRecordId
    metrics_artifact_id: AnalysisArtifactId
    title: str = "Persistra momentum strategy report"
    output_mode: ReportOutputMode = ReportOutputMode.SELF_CONTAINED_HTML
    sections: tuple[str, ...] | None = None
    limits: ReportLimits = ReportLimits()


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


@dataclass(frozen=True, slots=True)
class ReportBundleRef:
    path: str
    manifest_content_id: ContentId
    file_count: int
    byte_count: int
