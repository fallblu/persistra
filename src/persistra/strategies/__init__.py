"""Ready-to-use builtin strategies (buy-and-hold, momentum, mean-reversion, ...)."""

from persistra.strategies.baseline import BuyAndHold, EqualWeightRebalance
from persistra.strategies.cross_sectional import CrossSectionalMomentum, MeanReversion
from persistra.strategies.risk_based import VolTargetedEqualWeight
from persistra.strategies.trend import SMACrossover

__all__ = [
    "BuyAndHold",
    "CrossSectionalMomentum",
    "EqualWeightRebalance",
    "MeanReversion",
    "SMACrossover",
    "VolTargetedEqualWeight",
]
