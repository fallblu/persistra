"""Online and batch feature transformers for price and return series."""

from persistra.features.online import EWMA, EWVolatility
from persistra.features.returns import CumReturn, LogReturn, SimpleReturn, VolScaledReturn
from persistra.features.stats import (
    RollingKurt,
    RollingMean,
    RollingQuantile,
    RollingSkew,
    RollingStd,
    RollingZScore,
)
from persistra.features.structural import (
    CointegrationCoefficients,
    KalmanHedgeRatio,
    RollingPCA,
)

__all__ = [
    "CointegrationCoefficients",
    "CumReturn",
    "EWMA",
    "EWVolatility",
    "KalmanHedgeRatio",
    "LogReturn",
    "RollingKurt",
    "RollingMean",
    "RollingPCA",
    "RollingQuantile",
    "RollingSkew",
    "RollingStd",
    "RollingZScore",
    "SimpleReturn",
    "VolScaledReturn",
]
