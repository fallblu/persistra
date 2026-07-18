"""Initial structured performance metric contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from persistra.domain import ContentId, EntityId
from persistra.errors import AnalysisUnavailableError


class AnalysisArtifactId(EntityId):
    KIND: ClassVar[str] = "analysis_artifact"


class MetricState(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    MISSING_INPUT = "missing_input"
    INVALID_BASE = "invalid_base"
    UNDEFINED = "undefined"
    NONUNIQUE_SOLUTION = "nonunique_solution"
    INVALID_NUMERIC = "invalid_numeric"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class MetricResult:
    metric_name: str
    state: MetricState
    estimate: float | None
    unit: str
    observation_count: int
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class MetricInputs:
    """Exact optional aligned series required by versioned metrics."""

    risk_free_returns: tuple[float, ...] | None = None
    benchmark_returns: tuple[float, ...] | None = None
    eligible_volume_by_fill: tuple[float, ...] | None = None
    closed_lot_holding_periods: tuple[tuple[float, float], ...] | None = None

    def __post_init__(self) -> None:
        for values in (
            self.risk_free_returns,
            self.benchmark_returns,
            self.eligible_volume_by_fill,
        ):
            if values is not None and any(not math.isfinite(value) for value in values):
                raise AnalysisUnavailableError(
                    "metric input series must contain only finite values"
                )
        if (
            self.eligible_volume_by_fill is not None
            and any(value <= 0 for value in self.eligible_volume_by_fill)
        ):
            raise AnalysisUnavailableError(
                "eligible fill volumes must be positive"
            )
        if self.closed_lot_holding_periods is not None and any(
            not math.isfinite(days)
            or not math.isfinite(notional)
            or days < 0
            or notional <= 0
            for days, notional in self.closed_lot_holding_periods
        ):
            raise AnalysisUnavailableError(
                "closed-lot holding-period inputs are invalid"
            )


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
