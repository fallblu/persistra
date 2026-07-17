"""Minimal vectorized-simulation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId
from persistra.errors import VectorizedSimulationRequestError

if TYPE_CHECKING:
    from persistra.accounting import AccountingOpening
    from persistra.market import BarSpecRef
    from persistra.portfolio import PortfolioConstructionResultId
    from persistra.reference import AsOfContext


class VectorizedSimulationId(EntityId):
    KIND: ClassVar[str] = "vectorized_simulation"


class RunRecordId(EntityId):
    KIND: ClassVar[str] = "run_record"


@dataclass(frozen=True, slots=True)
class VectorizedExecutionPolicy:
    commission_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("5")
    fractional_quantum: Decimal = Decimal("0.000000000001")
    insufficient_cash: str = "pro_rata"

    def __post_init__(self) -> None:
        if (
            self.commission_bps < 0
            or self.slippage_bps < 0
            or self.fractional_quantum <= 0
            or self.insufficient_cash not in {"pro_rata", "fail"}
        ):
            raise VectorizedSimulationRequestError("execution policy is invalid")


@dataclass(frozen=True, slots=True)
class VectorizedSimulationRequest:
    market_context: AsOfContext
    market_database: str
    bar_spec: BarSpecRef
    construction_result_id: PortfolioConstructionResultId
    opening: AccountingOpening
    execution: VectorizedExecutionPolicy = VectorizedExecutionPolicy()

    def __post_init__(self) -> None:
        if not self.market_database:
            raise VectorizedSimulationRequestError("market database is required")


@dataclass(frozen=True, slots=True)
class VectorizedSimulationPlan:
    request: VectorizedSimulationRequest
    execution_content_id: ContentId


@dataclass(frozen=True, slots=True)
class VectorizedRunRef:
    vectorized_simulation_id: VectorizedSimulationId
    run_record_id: RunRecordId
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    decision_count: int
    fill_count: int
