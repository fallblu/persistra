"""Normalized run result value contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persistra.domain import ContentId
    from persistra.simulation import RunRecordId, VectorizedSimulationId


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_record_id: RunRecordId
    vectorized_simulation_id: VectorizedSimulationId
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    decision_count: int
    fill_count: int
    fidelity_findings: tuple[str, ...]
