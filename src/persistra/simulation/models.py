"""Minimal vectorized-simulation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
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


class FidelityProfileId(EntityId):
    KIND: ClassVar[str] = "fidelity_profile"


class CapacityAction(StrEnum):
    IGNORE_WITH_WARNING = "ignore_with_fidelity_warning"
    CLIP = "clip"
    FAIL = "fail"


class QuantityPolicy(StrEnum):
    FRACTIONAL = "fractional"
    WHOLE_SHARE_DOWN = "whole_share_down"


@dataclass(frozen=True, slots=True)
class VectorizedExecutionPolicy:
    commission_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("5")
    fractional_quantum: Decimal = Decimal("0.000000000001")
    insufficient_cash: str = "pro_rata"
    quantity_policy: QuantityPolicy = QuantityPolicy.FRACTIONAL
    rebalance_threshold_bps: Decimal = Decimal(0)
    capacity_action: CapacityAction = CapacityAction.IGNORE_WITH_WARNING
    participation_limit: Decimal | None = None
    target_failure: str = "fail_run"
    checkpoint_every: int = 1
    max_decisions: int = 100_000

    def __post_init__(self) -> None:
        if (
            self.commission_bps < 0
            or self.slippage_bps < 0
            or self.fractional_quantum <= 0
            or self.insufficient_cash not in {"pro_rata", "fail"}
            or self.rebalance_threshold_bps < 0
            or self.rebalance_threshold_bps > 10_000
            or (
                self.participation_limit is not None
                and not Decimal(0) < self.participation_limit <= 1
            )
            or (
                self.capacity_action is not CapacityAction.IGNORE_WITH_WARNING
                and self.participation_limit is None
            )
            or self.target_failure not in {"fail_run", "skip_decision"}
            or self.checkpoint_every <= 0
            or self.max_decisions <= 0
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
