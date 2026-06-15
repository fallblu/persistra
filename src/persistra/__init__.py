"""persistra: event-driven backtesting framework.

Provider adapters write canonical market data for ``ParquetMarketData``.
Construct an Engine in Python and call ``.run()``::

    from persistra import Engine, ParquetMarketData, Portfolio, Strategy

    class BuyAndHold(Strategy):
        def on_bar(self, ctx):
            ctx.signal({sym: 1.0 / len(ctx.universe) for sym in ctx.universe})

    result = Engine(
        data=ParquetMarketData("data/market"),
        strategy=BuyAndHold(),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2020-01-02",
        end="2023-12-29",
    ).run()
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from persistra.core.engine import Engine
from persistra.core.execution import (
    ExecutionModel,
    ExecutionTiming,
    FixedCommission,
    IdealFill,
    ProportionalSlippage,
    VolumeImpact,
)
from persistra.core.portfolio import FillDecision, Portfolio, PortfolioConstraint, PortfolioPolicy
from persistra.core.result import Result
from persistra.data.store import (
    ActionQuery,
    AdjustmentPolicy,
    BarQuery,
    MarketData,
    MarketDataWriter,
    ParquetMarketData,
    StreamingMarketData,
    UniverseMembership,
    UniverseQuery,
    coerce_adjustment_policy,
)
from persistra.features import (
    EWMA,
    CointegrationCoefficients,
    CumReturn,
    EWVolatility,
    KalmanHedgeRatio,
    LogReturn,
    RollingKurt,
    RollingMean,
    RollingPCA,
    RollingQuantile,
    RollingSkew,
    RollingStd,
    RollingZScore,
    SimpleReturn,
    VolScaledReturn,
)
from persistra.metrics import (
    alpha,
    annualized_return,
    annualized_volatility,
    benchmark_summary,
    beta,
    calmar_ratio,
    hit_rate,
    information_ratio,
    max_drawdown,
    realized_pnl,
    sharpe_ratio,
    sortino_ratio,
    tracking_error,
    turnover,
)
from persistra.pipeline import (
    AllocationRule,
    CashFloor,
    Decile,
    Direct,
    EqualWeight,
    FixedDollar,
    LinearSignal,
    MaxGrossExposure,
    MaxNetExposure,
    MaxPositionSize,
    RankWeighted,
    RiskConstraint,
    SignalCombiner,
    Sizer,
    TopN,
    VolTarget,
)
from persistra.strategies import (
    BuyAndHold,
    CrossSectionalMomentum,
    EqualWeightRebalance,
    MeanReversion,
    SMACrossover,
    VolTargetedEqualWeight,
)
from persistra.strategy import (
    CompositeStrategy,
    FactorStrategy,
    StrategyContext,
)
from persistra.strategy.base import Strategy

try:
    __version__ = version("persistra")
except PackageNotFoundError:  # pragma: no cover - editable installs provide metadata
    __version__ = "0+unknown"

__all__ = [
    "AllocationRule",
    "BuyAndHold",
    "CashFloor",
    "CointegrationCoefficients",
    "CompositeStrategy",
    "CrossSectionalMomentum",
    "CumReturn",
    "ActionQuery",
    "AdjustmentPolicy",
    "BarQuery",
    "Decile",
    "Direct",
    "EWMA",
    "EWVolatility",
    "Engine",
    "EqualWeight",
    "EqualWeightRebalance",
    "ExecutionModel",
    "ExecutionTiming",
    "FactorStrategy",
    "FillDecision",
    "FixedCommission",
    "FixedDollar",
    "IdealFill",
    "KalmanHedgeRatio",
    "LinearSignal",
    "LogReturn",
    "MarketData",
    "MarketDataWriter",
    "MaxGrossExposure",
    "MaxNetExposure",
    "MaxPositionSize",
    "MeanReversion",
    "ParquetMarketData",
    "Portfolio",
    "PortfolioConstraint",
    "PortfolioPolicy",
    "ProportionalSlippage",
    "RankWeighted",
    "Result",
    "RiskConstraint",
    "RollingKurt",
    "RollingMean",
    "RollingPCA",
    "RollingQuantile",
    "RollingSkew",
    "RollingStd",
    "RollingZScore",
    "SMACrossover",
    "SignalCombiner",
    "SimpleReturn",
    "Sizer",
    "Strategy",
    "StrategyContext",
    "StreamingMarketData",
    "TopN",
    "UniverseMembership",
    "UniverseQuery",
    "VolScaledReturn",
    "VolTarget",
    "VolTargetedEqualWeight",
    "VolumeImpact",
    "__version__",
    "alpha",
    "annualized_return",
    "annualized_volatility",
    "benchmark_summary",
    "beta",
    "calmar_ratio",
    "coerce_adjustment_policy",
    "hit_rate",
    "information_ratio",
    "max_drawdown",
    "realized_pnl",
    "sharpe_ratio",
    "sortino_ratio",
    "tracking_error",
    "turnover",
]
