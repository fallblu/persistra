"""This module contains the minimal signal and target-portfolio contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.errors import PortfolioConstructionError, SignalDefinitionError

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.portfolio.safety_models import UnsafeDecisionInputOverride
    from persistra.research.features import FeatureMaterializationId


class SignalDefinitionId(EntityId):
    KIND: ClassVar[str] = "signal_definition"


class SignalMaterializationId(EntityId):
    KIND: ClassVar[str] = "signal_materialization"


class PortfolioConstructorId(EntityId):
    KIND: ClassVar[str] = "portfolio_constructor"


class PortfolioConstructionResultId(EntityId):
    KIND: ClassVar[str] = "portfolio_construction_result"


class SignalMeaning(StrEnum):
    RANK = "rank"


class SignalValueState(StrEnum):
    COMPUTED = "computed"
    INPUT_MISSING = "input_missing"
    UPSTREAM_NONCOMPUTED = "upstream_noncomputed"


class ConstructionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RankSignalDefinition:
    name: QualifiedName
    version: int
    ascending: bool = True
    meaning: SignalMeaning = SignalMeaning.RANK

    def __post_init__(self) -> None:
        if self.version < 1:
            raise SignalDefinitionError("signal version must be positive")


@dataclass(frozen=True, slots=True)
class SignalRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedSignalRef:
    signal_definition_id: SignalDefinitionId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class SignalMaterializationRef:
    signal_materialization_id: SignalMaterializationId
    signal_definition_id: SignalDefinitionId
    feature_materialization_id: FeatureMaterializationId
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    row_count: int
    computed_count: int


@dataclass(frozen=True, slots=True)
class EqualWeightConstructorDefinition:
    name: QualifiedName
    version: int
    minimum_rank: float = 0.5

    def __post_init__(self) -> None:
        if self.version < 1 or not 0 <= self.minimum_rank <= 1:
            raise PortfolioConstructionError("equal-weight constructor is invalid")


@dataclass(frozen=True, slots=True)
class ConstructorRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedConstructorRef:
    portfolio_constructor_id: PortfolioConstructorId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ConstructionRequest:
    constructor: ConstructorRef
    signal_materialization_id: SignalMaterializationId
    start_at: datetime | None = None
    end_at: datetime | None = None
    unsafe_override: UnsafeDecisionInputOverride | None = None

    def __post_init__(self) -> None:
        for value in (self.start_at, self.end_at):
            if value is not None and value.tzinfo is None:
                raise PortfolioConstructionError(
                    "construction interval instants must be timezone-aware"
                )
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.start_at >= self.end_at
        ):
            raise PortfolioConstructionError("construction interval is invalid")


@dataclass(frozen=True, slots=True)
class PortfolioConstructionResultRef:
    portfolio_construction_result_id: PortfolioConstructionResultId
    portfolio_constructor_id: PortfolioConstructorId
    signal_materialization_id: SignalMaterializationId
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    decision_count: int
    target_row_count: int
