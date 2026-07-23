"""This module contains the normalized run result value contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import EntityId

if TYPE_CHECKING:
    from persistra.domain import ContentId
    from persistra.simulation import RunRecordId


class AnnotationId(EntityId):
    KIND: ClassVar[str] = "annotation"


class ExportAttemptId(EntityId):
    KIND: ClassVar[str] = "export_attempt"


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_record_id: RunRecordId
    simulation_kind: str
    simulation_id: str
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    decision_count: int
    fill_count: int
    fidelity_findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportRef:
    export_attempt_id: ExportAttemptId
    run_record_id: RunRecordId
    export_format: str
    manifest_content_id: ContentId
    output_sha256: str
    byte_count: int
