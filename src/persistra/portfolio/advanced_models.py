"""Direct forecast, point-in-time risk, and optimization contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.errors import ForecastDefinitionError, OptimizationError, RiskModelError

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.portfolio.models import PortfolioConstructionResultId
    from persistra.portfolio.safety_models import UnsafeDecisionInputOverride
    from persistra.research.models import ResearchDatasetBuildId


class ForecastDefinitionId(EntityId):
    KIND: ClassVar[str] = "forecast_definition"


class ForecastMaterializationId(EntityId):
    KIND: ClassVar[str] = "forecast_materialization"


class RiskModelDefinitionId(EntityId):
    KIND: ClassVar[str] = "risk_model_definition"


class RiskMaterializationId(EntityId):
    KIND: ClassVar[str] = "risk_materialization"


class ForecastTargetKind(StrEnum):
    SIMPLE_RETURN = "simple_return"
    LOG_RETURN = "log_return"
    EXCESS_RETURN = "excess_return"
    PROBABILITY = "probability"
    VOLATILITY = "volatility"


class PredictionState(StrEnum):
    COMPUTED = "computed"
    INPUT_MISSING = "input_missing"
    FIT_UNAVAILABLE = "fit_unavailable"
    INVALID_NUMERIC = "invalid_numeric"


class RiskModelKind(StrEnum):
    SAMPLE_COVARIANCE = "sample_covariance"
    EWMA_COVARIANCE = "ewma_covariance"
    FIXED_SHRINKAGE = "fixed_shrinkage"


class PsdPolicy(StrEnum):
    FAIL = "fail"
    EIGENVALUE_CLIP = "eigenvalue_clip"


class RiskEstimateState(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
    NON_PSD = "non_psd"
    INVALID_NUMERIC = "invalid_numeric"


class OptimizationAttemptStatus(StrEnum):
    OPTIMAL = "optimal"
    INFEASIBLE = "infeasible"
    SOLVER_ERROR = "solver_error"
    INVALID_RESULT = "invalid_result"


@dataclass(frozen=True, slots=True)
class DirectForecastDefinition:
    name: QualifiedName
    version: int
    research_dataset_build_id: ResearchDatasetBuildId
    feature_output: str
    target_kind: ForecastTargetKind
    horizon_decisions: int
    multiplier: str = "1"
    intercept: str = "0"

    def __post_init__(self) -> None:
        if self.version < 1 or self.horizon_decisions < 1 or not self.feature_output:
            raise ForecastDefinitionError("direct forecast definition is invalid")
        try:
            multiplier = float(self.multiplier)
            intercept = float(self.intercept)
        except ValueError as error:
            raise ForecastDefinitionError(
                "forecast transform parameters must be finite numbers"
            ) from error
        if not all(map(_finite, (multiplier, intercept))):
            raise ForecastDefinitionError(
                "forecast transform parameters must be finite numbers"
            )


@dataclass(frozen=True, slots=True)
class ForecastRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ForecastMaterializationRef:
    forecast_materialization_id: ForecastMaterializationId
    forecast_definition_id: ForecastDefinitionId
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    output_content_id: ContentId
    row_count: int
    computed_count: int


@dataclass(frozen=True, slots=True)
class RiskModelDefinition:
    name: QualifiedName
    version: int
    research_dataset_build_id: ResearchDatasetBuildId
    return_output: str
    kind: RiskModelKind
    lookback_decisions: int
    minimum_observations: int
    ewma_decay: str = "0.94"
    shrinkage: str = "0.1"
    psd_policy: PsdPolicy = PsdPolicy.FAIL

    def __post_init__(self) -> None:
        if (
            self.version < 1
            or self.lookback_decisions < 2
            or not 2 <= self.minimum_observations <= self.lookback_decisions
            or not self.return_output
        ):
            raise RiskModelError("risk model definition is invalid")
        decay, shrinkage = float(self.ewma_decay), float(self.shrinkage)
        if not 0 < decay < 1 or not 0 <= shrinkage <= 1:
            raise RiskModelError("risk model parameters are out of range")


@dataclass(frozen=True, slots=True)
class RiskModelRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class RiskMaterializationRef:
    risk_materialization_id: RiskMaterializationId
    risk_model_definition_id: RiskModelDefinitionId
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    output_content_id: ContentId
    estimate_count: int


@dataclass(frozen=True, slots=True)
class OptimizationRequest:
    forecast_materialization_id: ForecastMaterializationId
    risk_materialization_id: RiskMaterializationId
    decision_at: datetime
    risk_aversion: str = "5"
    maximum_weight: str = "0.1"
    gross_limit: str = "1"
    net_target: str = "1"
    turnover_penalty: str = "0"
    current_weights: tuple[tuple[str, str], ...] = ()
    unsafe_override: UnsafeDecisionInputOverride | None = None

    def __post_init__(self) -> None:
        if self.decision_at.tzinfo is None:
            raise OptimizationError("optimization decision must be timezone-aware")
        risk_aversion = float(self.risk_aversion)
        maximum = float(self.maximum_weight)
        gross = float(self.gross_limit)
        net = float(self.net_target)
        penalty = float(self.turnover_penalty)
        if (
            risk_aversion < 0
            or maximum <= 0
            or gross <= 0
            or abs(net) > gross
            or penalty < 0
            or not all(map(_finite, (risk_aversion, maximum, gross, net, penalty)))
        ):
            raise OptimizationError("optimization request bounds are invalid")
        if len({item[0] for item in self.current_weights}) != len(
            self.current_weights
        ):
            raise OptimizationError("current weights contain duplicate instruments")


@dataclass(frozen=True, slots=True)
class OptimizationResultRef:
    portfolio_construction_result_id: PortfolioConstructionResultId
    forecast_materialization_id: ForecastMaterializationId
    risk_materialization_id: RiskMaterializationId
    decision_at: datetime
    execution_content_id: ContentId
    output_content_id: ContentId
    status: OptimizationAttemptStatus
    solver_name: str
    objective_value: float | None
    maximum_violation: float


def _finite(value: float) -> bool:
    return value == value and value not in {float("inf"), float("-inf")}
