"""Typed policies and results for portfolio research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from persistra.portfolio._validation import finite_scalar

if TYPE_CHECKING:
    import pandas as pd

type WeightingMethod = Literal["equal", "signal_proportional"]
type PortfolioConfiguration = Literal["long_only", "long_short"]
type MissingReturnPolicy = Literal["error", "zero"]
type NontradeablePolicy = Literal["error", "hold"]


@dataclass(frozen=True, slots=True)
class PortfolioConstraints:
    """Hard exposure, position, and one-way turnover limits."""

    gross_limit: float = 1.0
    net_minimum: float = -1.0
    net_maximum: float = 1.0
    position_limit: float = 1.0
    turnover_limit: float | None = None
    tolerance: float = 1e-10

    def __post_init__(self) -> None:
        finite_scalar(self.gross_limit, name="gross_limit", minimum=0.0)
        finite_scalar(self.net_minimum, name="net_minimum")
        finite_scalar(self.net_maximum, name="net_maximum")
        finite_scalar(self.position_limit, name="position_limit", minimum=0.0)
        finite_scalar(self.tolerance, name="tolerance", minimum=0.0)
        if self.net_minimum > self.net_maximum:
            raise ValueError("net_minimum must not exceed net_maximum")
        if self.turnover_limit is not None:
            finite_scalar(self.turnover_limit, name="turnover_limit", minimum=0.0)


@dataclass(frozen=True, slots=True)
class PortfolioRiskControl:
    """Annualized volatility target and ceiling based on supplied covariance."""

    target_volatility: float | None = None
    volatility_limit: float | None = None
    periods_per_year: float = 252.0
    covariance_tolerance: float = 1e-10

    def __post_init__(self) -> None:
        finite_scalar(self.periods_per_year, name="periods_per_year", minimum=0.0)
        finite_scalar(
            self.covariance_tolerance,
            name="covariance_tolerance",
            minimum=0.0,
        )
        if self.periods_per_year == 0:
            raise ValueError("periods_per_year must be positive")
        if self.target_volatility is not None:
            finite_scalar(self.target_volatility, name="target_volatility", minimum=0.0)
        if self.volatility_limit is not None:
            finite_scalar(self.volatility_limit, name="volatility_limit", minimum=0.0)
        if (
            self.target_volatility is not None
            and self.volatility_limit is not None
            and self.target_volatility > self.volatility_limit
        ):
            raise ValueError("target_volatility must not exceed volatility_limit")


@dataclass(frozen=True, slots=True)
class PortfolioConstructionResult:
    """Transparent unconstrained and final target portfolio weights."""

    weights: pd.DataFrame
    unconstrained_weights: pd.DataFrame
    cash: pd.Series
    exposures: pd.DataFrame
    turnover: pd.Series
    predicted_volatility: pd.Series
    risk_contributions: pd.DataFrame
    constraint_utilization: pd.DataFrame
    weighting: WeightingMethod
    configuration: PortfolioConfiguration
    gross_target: float
    net_target: float
    constraints: PortfolioConstraints
    risk_control: PortfolioRiskControl | None

    def __post_init__(self) -> None:
        weights = self.weights.copy(deep=True)
        panels = {
            "unconstrained_weights": self.unconstrained_weights,
            "risk_contributions": self.risk_contributions,
        }
        for name, panel in panels.items():
            if not panel.index.equals(weights.index) or not panel.columns.equals(weights.columns):
                raise ValueError(f"{name} must use the target-weight axes")
            object.__setattr__(self, name, panel.copy(deep=True))
        series = {
            "cash": self.cash,
            "turnover": self.turnover,
            "predicted_volatility": self.predicted_volatility,
        }
        for name, values in series.items():
            if not values.index.equals(weights.index):
                raise ValueError(f"{name} must use the target-weight index")
            object.__setattr__(self, name, values.copy(deep=True))
        for name, panel in {
            "exposures": self.exposures,
            "constraint_utilization": self.constraint_utilization,
        }.items():
            if not panel.index.equals(weights.index):
                raise ValueError(f"{name} must use the target-weight index")
            object.__setattr__(self, name, panel.copy(deep=True))
        if not np.allclose(
            weights.sum(axis="columns").add(self.cash).to_numpy(dtype=float),
            1.0,
            atol=self.constraints.tolerance,
            rtol=0.0,
        ):
            raise ValueError("target asset and cash weights must sum to one")
        object.__setattr__(self, "weights", weights)


@dataclass(frozen=True, slots=True)
class BacktestTiming:
    """Signal-to-decision and decision-to-holding timing policy."""

    decision_lag: int = 0
    execution_lag: int = 1
    holding_period: int | None = None
    signal_available_before_trade: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.decision_lag, bool) or self.decision_lag < 0:
            raise ValueError("decision_lag must be a nonnegative integer")
        if isinstance(self.execution_lag, bool) or self.execution_lag < 0:
            raise ValueError("execution_lag must be a nonnegative integer")
        if self.holding_period is not None:
            if isinstance(self.holding_period, bool):
                raise ValueError("holding_period must be a positive integer")
            if self.holding_period <= 0:
                raise ValueError("holding_period must be positive")


@dataclass(frozen=True, slots=True)
class BacktestPolicies:
    """Explicit missing-return and nontradeable-asset behavior."""

    missing_return: MissingReturnPolicy = "error"
    nontradeable: NontradeablePolicy = "error"

    def __post_init__(self) -> None:
        if self.missing_return not in {"error", "zero"}:
            raise ValueError("unsupported missing-return policy")
        if self.nontradeable not in {"error", "hold"}:
            raise ValueError("unsupported nontradeable policy")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Reconciled portfolio-level backtest paths and benchmark comparisons."""

    target_weights: pd.DataFrame
    realized_weights: pd.DataFrame
    ending_weights: pd.DataFrame
    cash: pd.Series
    ending_cash: pd.Series
    returns: pd.Series
    gross_returns: pd.Series
    equity: pd.Series
    drawdown: pd.Series
    exposures: pd.DataFrame
    turnover: pd.Series
    trades: pd.DataFrame
    asset_return_attribution: pd.DataFrame
    cash_return_attribution: pd.Series
    cost_attribution: pd.DataFrame
    costs: pd.Series
    rebalance_log: pd.DataFrame
    benchmark_returns: pd.DataFrame
    benchmark_equity: pd.DataFrame
    benchmark_comparison: pd.DataFrame
    initial_equity: float
    timing: BacktestTiming
    policies: BacktestPolicies
    tolerance: float = 1e-10

    def __post_init__(self) -> None:
        weights = self.realized_weights.copy(deep=True)
        panels = {
            "ending_weights": self.ending_weights,
            "trades": self.trades,
            "asset_return_attribution": self.asset_return_attribution,
            "cost_attribution": self.cost_attribution,
        }
        for name, panel in panels.items():
            if not panel.index.equals(weights.index) or not panel.columns.equals(weights.columns):
                raise ValueError(f"{name} must use the realized-weight axes")
            object.__setattr__(self, name, panel.copy(deep=True))
        series = {
            "cash": self.cash,
            "ending_cash": self.ending_cash,
            "returns": self.returns,
            "gross_returns": self.gross_returns,
            "equity": self.equity,
            "drawdown": self.drawdown,
            "turnover": self.turnover,
            "cash_return_attribution": self.cash_return_attribution,
            "costs": self.costs,
        }
        for name, values in series.items():
            if not values.index.equals(weights.index):
                raise ValueError(f"{name} must use the realized-weight index")
            object.__setattr__(self, name, values.copy(deep=True))
        if not self.exposures.index.equals(weights.index):
            raise ValueError("exposures must use the realized-weight index")
        object.__setattr__(self, "exposures", self.exposures.copy(deep=True))
        for name, panel in {
            "benchmark_returns": self.benchmark_returns,
            "benchmark_equity": self.benchmark_equity,
        }.items():
            if not panel.index.equals(weights.index):
                raise ValueError(f"{name} must use the realized-weight index")
            object.__setattr__(self, name, panel.copy(deep=True))
        object.__setattr__(self, "target_weights", self.target_weights.copy(deep=True))
        object.__setattr__(self, "rebalance_log", self.rebalance_log.copy(deep=True))
        object.__setattr__(
            self,
            "benchmark_comparison",
            self.benchmark_comparison.copy(deep=True),
        )
        tolerance = finite_scalar(self.tolerance, name="tolerance", minimum=0.0)
        finite_scalar(self.initial_equity, name="initial_equity", minimum=0.0)
        if self.initial_equity == 0:
            raise ValueError("initial_equity must be positive")
        start_total = weights.sum(axis="columns").add(self.cash)
        end_total = self.ending_weights.sum(axis="columns").add(self.ending_cash)
        if not np.allclose(start_total, 1.0, atol=tolerance, rtol=0.0):
            raise ValueError("realized asset and cash weights must sum to one")
        if not np.allclose(end_total, 1.0, atol=tolerance, rtol=0.0):
            raise ValueError("ending asset and cash weights must sum to one")
        attributed_gross = self.asset_return_attribution.sum(axis="columns").add(
            self.cash_return_attribution
        )
        if not np.allclose(
            attributed_gross,
            self.gross_returns,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("asset and cash returns do not reconcile to gross returns")
        if not np.allclose(
            self.gross_returns.sub(self.costs),
            self.returns,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("gross returns and costs do not reconcile to net returns")
        if not np.allclose(
            self.cost_attribution.sum(axis="columns"),
            self.costs,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("asset costs do not reconcile to total costs")
        expected_equity = self.returns.add(1.0).cumprod().mul(self.initial_equity)
        if not np.allclose(expected_equity, self.equity, atol=tolerance, rtol=1e-12):
            raise ValueError("returns do not reconcile to equity")
        object.__setattr__(self, "realized_weights", weights)
