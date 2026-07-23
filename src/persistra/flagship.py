"""This module contains the versioned assumptions for the v3 momentum flagship."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from persistra.domain import QualifiedName
from persistra.portfolio import EqualWeightConstructorDefinition, RankSignalDefinition
from persistra.research import FeatureDefinition, FeatureKind
from persistra.simulation import VectorizedExecutionPolicy


@dataclass(frozen=True, slots=True)
class FlagshipMomentumProfile:
    """This class contains all numerical and semantic assumptions for the v3 flagship."""

    name: QualifiedName
    version: int
    opening_cash_usd: Decimal
    momentum: FeatureDefinition
    signal: RankSignalDefinition
    constructor: EqualWeightConstructorDefinition
    execution: VectorizedExecutionPolicy


FLAGSHIP_MOMENTUM_V1 = FlagshipMomentumProfile(
    name=QualifiedName("persistra.flagship_momentum"),
    version=1,
    opening_cash_usd=Decimal("1000000"),
    momentum=FeatureDefinition(
        QualifiedName("persistra.feature.momentum_12_1"),
        1,
        FeatureKind.MOMENTUM,
        "daily",
        lookback=252,
        skip=21,
    ),
    signal=RankSignalDefinition(
        QualifiedName("persistra.signal.momentum_rank"),
        1,
        ascending=True,
    ),
    constructor=EqualWeightConstructorDefinition(
        QualifiedName("persistra.constructor.momentum_top_half_equal_weight"),
        1,
        minimum_rank=0.5,
    ),
    execution=VectorizedExecutionPolicy(
        commission_bps=Decimal("1"),
        slippage_bps=Decimal("5"),
        fractional_quantum=Decimal("0.000000000001"),
        insufficient_cash="pro_rata",
    ),
)

__all__ = ["FLAGSHIP_MOMENTUM_V1", "FlagshipMomentumProfile"]
