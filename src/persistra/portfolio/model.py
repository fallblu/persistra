"""Typed policies and results for portfolio research."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.portfolio._validation import finite_scalar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.portfolio.solver import PortfolioSolverStatus
    from persistra.research import FactorRiskModel

type WeightingMethod = Literal["equal", "signal_proportional"]
type PortfolioConfiguration = Literal["long_only", "long_short"]
type MissingReturnPolicy = Literal["error", "zero"]
type NontradeablePolicy = Literal["error", "hold"]
type OptimizationFailurePolicy = Literal["raise", "hold_previous"]
type MissingMembershipPolicy = Literal["error", "zero"]
type OverlappingMembershipPolicy = Literal["error", "allow"]
type MissingCostPolicy = Literal["error", "zero"]
type UnavailableShortPolicy = Literal["error", "cover"]
type MissingFxPolicy = Literal["error", "ffill"]
type PortfolioObjective = (
    MinimumVarianceObjective
    | MeanVarianceObjective
    | MinimumTrackingErrorObjective
    | ActiveMeanVarianceObjective
    | RiskParityObjective
    | ConditionalValueAtRiskObjective
    | RobustMeanVarianceObjective
)
type PortfolioConstraint = (
    WeightBounds
    | GrossExposureConstraint
    | NetExposureConstraint
    | TurnoverConstraint
    | FactorExposureConstraint
    | LinearExposureConstraint
    | GroupedExposureConstraint
    | RiskBudgetConstraint
    | ConditionalValueAtRiskConstraint
    | TrackingErrorConstraint
)
type PortfolioPenalty = (
    LinearTransactionCostPenalty
    | AsymmetricTransactionCostPenalty
    | QuadraticTransactionCostPenalty
)


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
class MinimumVarianceObjective:
    """Minimize total portfolio variance."""


@dataclass(frozen=True, slots=True)
class MeanVarianceObjective:
    """Maximize expected return against an explicit variance penalty."""

    risk_aversion: float = 1.0

    def __post_init__(self) -> None:
        finite_scalar(self.risk_aversion, name="risk_aversion", minimum=0.0)
        if self.risk_aversion == 0.0:
            raise ValueError("risk_aversion must be positive")


@dataclass(frozen=True, slots=True)
class MinimumTrackingErrorObjective:
    """Minimize variance relative to supplied benchmark weights."""


@dataclass(frozen=True, slots=True)
class ActiveMeanVarianceObjective:
    """Maximize expected active return against tracking-error variance."""

    risk_aversion: float = 1.0

    def __post_init__(self) -> None:
        finite_scalar(self.risk_aversion, name="risk_aversion", minimum=0.0)
        if self.risk_aversion == 0.0:
            raise ValueError("risk_aversion must be positive")


@dataclass(frozen=True, slots=True)
class RiskParityObjective:
    """Minimize squared differences between realized and requested risk budgets."""

    budgets: pd.Series | None = None

    def __post_init__(self) -> None:
        if self.budgets is not None:
            object.__setattr__(self, "budgets", self.budgets.copy(deep=True))


@dataclass(frozen=True, slots=True)
class ConditionalValueAtRiskObjective:
    """Minimize empirical loss CVaR at the requested confidence level."""

    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        finite_scalar(self.confidence_level, name="confidence_level", minimum=0.0)
        if self.confidence_level <= 0.0 or self.confidence_level >= 1.0:
            raise ValueError("confidence_level must be strictly between zero and one")


@dataclass(frozen=True, slots=True)
class EllipsoidalExpectedReturnUncertainty:
    """Ellipsoidal expected-return uncertainty matrix and radius."""

    matrix: pd.DataFrame
    radius: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "matrix", self.matrix.copy(deep=True))
        finite_scalar(self.radius, name="uncertainty radius", minimum=0.0)


@dataclass(frozen=True, slots=True)
class RobustMeanVarianceObjective:
    """Mean variance with an ellipsoidal worst-case expected-return penalty."""

    uncertainty: EllipsoidalExpectedReturnUncertainty
    risk_aversion: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(
            cast("object", self.uncertainty), EllipsoidalExpectedReturnUncertainty
        ):
            raise TypeError("uncertainty must be EllipsoidalExpectedReturnUncertainty")
        finite_scalar(self.risk_aversion, name="risk_aversion", minimum=0.0)
        if self.risk_aversion == 0.0:
            raise ValueError("risk_aversion must be positive")


@dataclass(frozen=True, slots=True)
class WeightBounds:
    """Per-asset lower and upper portfolio-weight bounds."""

    lower: float | pd.Series = -1.0
    upper: float | pd.Series = 1.0

    def __post_init__(self) -> None:
        for name in ("lower", "upper"):
            value = getattr(self, name)
            if isinstance(value, pd.Series):
                object.__setattr__(self, name, value.copy(deep=True))
            else:
                finite_scalar(value, name=name)


@dataclass(frozen=True, slots=True)
class GrossExposureConstraint:
    """Upper bound on total absolute risky-asset weight."""

    maximum: float

    def __post_init__(self) -> None:
        finite_scalar(self.maximum, name="gross exposure maximum", minimum=0.0)


@dataclass(frozen=True, slots=True)
class NetExposureConstraint:
    """Lower and upper bounds on signed risky-asset weight."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        finite_scalar(self.minimum, name="net exposure minimum")
        finite_scalar(self.maximum, name="net exposure maximum")
        if self.minimum > self.maximum:
            raise ValueError("net exposure minimum must not exceed maximum")


@dataclass(frozen=True, slots=True)
class TurnoverConstraint:
    """Upper bound on one-way turnover from current risky and residual-cash weights."""

    maximum: float

    def __post_init__(self) -> None:
        finite_scalar(self.maximum, name="turnover maximum", minimum=0.0)


@dataclass(frozen=True, slots=True)
class FactorExposureConstraint:
    """Lower and upper bounds for every supplied factor exposure."""

    lower: pd.Series
    upper: pd.Series

    def __post_init__(self) -> None:
        object.__setattr__(self, "lower", self.lower.copy(deep=True))
        object.__setattr__(self, "upper", self.upper.copy(deep=True))


@dataclass(frozen=True, slots=True)
class LinearExposureConstraint:
    """Bound caller-defined linear loadings without assigning column semantics."""

    name: str
    loadings: pd.DataFrame
    lower: pd.Series
    upper: pd.Series

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("linear exposure constraint name must not be empty")
        object.__setattr__(self, "loadings", self.loadings.copy(deep=True))
        object.__setattr__(self, "lower", self.lower.copy(deep=True))
        object.__setattr__(self, "upper", self.upper.copy(deep=True))


@dataclass(frozen=True, slots=True)
class GroupedExposureConstraint:
    """Bounds for stable or dated caller-defined asset groups."""

    name: str
    memberships: pd.Series | pd.DataFrame
    lower: float | pd.Series = -1.0
    upper: float | pd.Series = 1.0
    neutrality_target: float | pd.Series | None = None
    missing: MissingMembershipPolicy = "error"
    overlapping: OverlappingMembershipPolicy = "error"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("grouped exposure constraint name must not be empty")
        object.__setattr__(self, "memberships", self.memberships.copy(deep=True))
        for name in ("lower", "upper", "neutrality_target"):
            value = getattr(self, name)
            if isinstance(value, pd.Series):
                object.__setattr__(self, name, value.copy(deep=True))
            elif value is not None:
                finite_scalar(value, name=name)
        if self.missing not in {"error", "zero"}:
            raise ValueError("unsupported missing membership policy")
        if self.overlapping not in {"error", "allow"}:
            raise ValueError("unsupported overlapping membership policy")


@dataclass(frozen=True, slots=True)
class RiskBudgetConstraint:
    """Target or cap asset and grouped fractional contributions to variance."""

    targets: pd.Series | None = None
    upper: pd.Series | None = None
    group_loadings: pd.DataFrame | None = None
    group_targets: pd.Series | None = None
    group_upper: pd.Series | None = None

    def __post_init__(self) -> None:
        for name in ("targets", "upper", "group_loadings", "group_targets", "group_upper"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, value.copy(deep=True))
        if all(
            value is None
            for value in (self.targets, self.upper, self.group_targets, self.group_upper)
        ):
            raise ValueError("risk budget constraint requires at least one target or upper bound")
        if (
            self.group_targets is not None or self.group_upper is not None
        ) and self.group_loadings is None:
            raise ValueError("group risk budgets require group_loadings")


@dataclass(frozen=True, slots=True)
class ConditionalValueAtRiskConstraint:
    """Maximum empirical loss CVaR at the requested confidence level."""

    maximum: float
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        finite_scalar(self.maximum, name="CVaR maximum")
        finite_scalar(self.confidence_level, name="confidence_level", minimum=0.0)
        if self.confidence_level <= 0.0 or self.confidence_level >= 1.0:
            raise ValueError("confidence_level must be strictly between zero and one")


@dataclass(frozen=True, slots=True)
class TrackingErrorConstraint:
    """Upper bound on portfolio volatility relative to a benchmark."""

    maximum: float

    def __post_init__(self) -> None:
        finite_scalar(self.maximum, name="tracking error maximum", minimum=0.0)


@dataclass(frozen=True, slots=True)
class LinearTransactionCostPenalty:
    """Linear risky-asset trading-cost rates and objective multiplier."""

    rates: float | pd.Series
    multiplier: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.rates, pd.Series):
            object.__setattr__(self, "rates", self.rates.copy(deep=True))
        else:
            finite_scalar(self.rates, name="transaction cost rate", minimum=0.0)
        finite_scalar(self.multiplier, name="transaction cost multiplier", minimum=0.0)


@dataclass(frozen=True, slots=True)
class AsymmetricTransactionCostPenalty:
    """Separate linear buy and sell cost rates with one objective multiplier."""

    buy_rates: float | pd.Series
    sell_rates: float | pd.Series
    multiplier: float = 1.0

    def __post_init__(self) -> None:
        for name in ("buy_rates", "sell_rates"):
            value = getattr(self, name)
            if isinstance(value, pd.Series):
                object.__setattr__(self, name, value.copy(deep=True))
            else:
                finite_scalar(value, name=name, minimum=0.0)
        finite_scalar(self.multiplier, name="transaction cost multiplier", minimum=0.0)


@dataclass(frozen=True, slots=True)
class QuadraticTransactionCostPenalty:
    """Asset-specific quadratic market-impact rates and objective multiplier."""

    rates: float | pd.Series
    multiplier: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.rates, pd.Series):
            object.__setattr__(self, "rates", self.rates.copy(deep=True))
        else:
            finite_scalar(self.rates, name="quadratic cost rate", minimum=0.0)
        finite_scalar(self.multiplier, name="quadratic cost multiplier", minimum=0.0)


@dataclass(frozen=True, slots=True)
class CovariancePolicy:
    """Explicit diagonal shrinkage and eigenvalue-floor conditioning policy."""

    diagonal_shrinkage: float = 0.0
    minimum_eigenvalue: float | None = None

    def __post_init__(self) -> None:
        finite_scalar(
            self.diagonal_shrinkage,
            name="diagonal_shrinkage",
            minimum=0.0,
        )
        if self.diagonal_shrinkage > 1.0:
            raise ValueError("diagonal_shrinkage must not exceed one")
        if self.minimum_eigenvalue is not None:
            finite_scalar(
                self.minimum_eigenvalue,
                name="minimum_eigenvalue",
                minimum=0.0,
            )


@dataclass(frozen=True, slots=True)
class PortfolioProblem:
    """One solver-independent continuous portfolio optimization problem."""

    covariance: pd.DataFrame | FactorRiskModel
    objective: PortfolioObjective
    expected_returns: pd.Series | None = None
    current_weights: pd.Series | None = None
    benchmark_weights: pd.Series | None = None
    factor_exposures: pd.DataFrame | None = None
    scenario_returns: pd.DataFrame | None = None
    constraints: tuple[PortfolioConstraint, ...] = ()
    penalties: tuple[PortfolioPenalty, ...] = ()
    covariance_policy: CovariancePolicy = CovariancePolicy()
    as_of: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        for name in (
            "expected_returns",
            "current_weights",
            "benchmark_weights",
            "factor_exposures",
            "scenario_returns",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, value.copy(deep=True))
        if isinstance(self.covariance, pd.DataFrame):
            object.__setattr__(self, "covariance", self.covariance.copy(deep=True))
        if not isinstance(cast("object", self.constraints), tuple):
            raise TypeError("constraints must be a tuple")
        if not isinstance(cast("object", self.penalties), tuple):
            raise TypeError("penalties must be a tuple")
        if not isinstance(cast("object", self.covariance_policy), CovariancePolicy):
            raise TypeError("covariance_policy must be CovariancePolicy")


@dataclass(frozen=True, slots=True)
class DiscretePortfolioProblem:
    """Long-only portfolio problem expressed in integer trade lots."""

    covariance: pd.DataFrame
    prices: pd.Series
    capital: float
    objective: MinimumVarianceObjective | MeanVarianceObjective
    expected_returns: pd.Series | None = None
    maximum_positions: int | None = None
    minimum_position_weight: float = 0.0
    maximum_position_weight: float | pd.Series = 1.0
    lot_sizes: int | pd.Series = 1
    minimum_invested_weight: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "covariance", self.covariance.copy(deep=True))
        object.__setattr__(self, "prices", self.prices.copy(deep=True))
        if self.expected_returns is not None:
            object.__setattr__(self, "expected_returns", self.expected_returns.copy(deep=True))
        for name in ("maximum_position_weight", "lot_sizes"):
            value = getattr(self, name)
            if isinstance(value, pd.Series):
                object.__setattr__(self, name, value.copy(deep=True))
        if not isinstance(self.maximum_position_weight, pd.Series):
            finite_scalar(
                self.maximum_position_weight,
                name="maximum_position_weight",
                minimum=0.0,
            )
            if self.maximum_position_weight > 1.0:
                raise ValueError("maximum_position_weight must not exceed one")
        if isinstance(self.lot_sizes, pd.Series):
            if pd.api.types.is_bool_dtype(self.lot_sizes.dtype):
                raise TypeError("lot_sizes must contain integers")
        else:
            object.__setattr__(
                self,
                "lot_sizes",
                require_integer(self.lot_sizes, name="lot_sizes", minimum=1),
            )
        finite_scalar(self.capital, name="capital", minimum=0.0)
        if self.capital == 0.0:
            raise ValueError("capital must be positive")
        if self.maximum_positions is not None:
            object.__setattr__(
                self,
                "maximum_positions",
                require_integer(
                    self.maximum_positions,
                    name="maximum_positions",
                    minimum=1,
                ),
            )
        finite_scalar(
            self.minimum_position_weight,
            name="minimum_position_weight",
            minimum=0.0,
        )
        if self.minimum_position_weight > 1.0:
            raise ValueError("minimum_position_weight must not exceed one")
        finite_scalar(
            self.minimum_invested_weight,
            name="minimum_invested_weight",
            minimum=0.0,
        )
        if self.minimum_invested_weight > 1.0:
            raise ValueError("minimum_invested_weight must not exceed one")


@dataclass(frozen=True, slots=True)
class DiscretePortfolioResult:
    """Discrete holdings, bounds, and normalized mixed-integer diagnostics."""

    holdings: pd.Series
    lots: pd.Series
    weights: pd.Series
    cash: float
    objective_value: float
    status: PortfolioSolverStatus
    lower_bound: float | None
    upper_bound: float | None
    solver: str
    solver_message: str
    iterations: int
    solver_statistics: Mapping[str, float | int | str]
    problem: DiscretePortfolioProblem

    def __post_init__(self) -> None:
        for name in ("holdings", "lots", "weights"):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        if not self.holdings.index.equals(self.weights.index) or not self.lots.index.equals(
            self.weights.index
        ):
            raise ValueError("discrete portfolio outputs must use one asset index")
        object.__setattr__(
            self,
            "iterations",
            require_integer(self.iterations, name="iterations", minimum=0),
        )
        object.__setattr__(
            self,
            "solver_statistics",
            MappingProxyType(dict(self.solver_statistics)),
        )


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationResult:
    """Optimal weights with objective, risk, exposure, and constraint diagnostics."""

    weights: pd.Series
    cash: float
    expected_return: float
    variance: float
    tracking_error: float | None
    turnover: float
    exposures: pd.Series
    factor_exposures: pd.Series
    linear_exposures: pd.Series
    risk_contributions: pd.Series
    risk_budget_diagnostics: pd.DataFrame
    downside_risk: pd.Series
    downside_diagnostics: pd.DataFrame
    covariance_diagnostics: pd.Series
    objective_breakdown: pd.Series
    constraint_diagnostics: pd.DataFrame
    solver: str
    solver_message: str
    iterations: int
    solver_statistics: Mapping[str, float | int | str]
    problem: PortfolioProblem

    def __post_init__(self) -> None:
        for name in (
            "weights",
            "exposures",
            "factor_exposures",
            "linear_exposures",
            "risk_contributions",
            "risk_budget_diagnostics",
            "downside_risk",
            "downside_diagnostics",
            "covariance_diagnostics",
            "objective_breakdown",
            "constraint_diagnostics",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        if not np.isclose(self.weights.sum() + self.cash, 1.0, atol=1e-10, rtol=0.0):
            raise ValueError("optimized risky and cash weights must sum to one")
        object.__setattr__(
            self,
            "iterations",
            require_integer(self.iterations, name="iterations", minimum=0),
        )
        object.__setattr__(
            self,
            "solver_statistics",
            MappingProxyType(dict(self.solver_statistics)),
        )


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationStep:
    """One dated optimized or explicitly held portfolio in a path."""

    as_of: pd.Timestamp
    problem: PortfolioProblem
    weights: pd.Series
    cash: float
    result: PortfolioOptimizationResult | None
    status: Literal["optimized", "held"]
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", pd.Timestamp(self.as_of))
        object.__setattr__(self, "weights", self.weights.copy(deep=True))
        if self.status not in {"optimized", "held"}:
            raise ValueError("optimization step status must be optimized or held")


@dataclass(frozen=True, slots=True)
class PortfolioOptimizationPathResult:
    """Ordered point-in-time portfolio optimization steps and aligned targets."""

    steps: tuple[PortfolioOptimizationStep, ...]
    weights: pd.DataFrame
    cash: pd.Series
    failure_policy: OptimizationFailurePolicy

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "weights", self.weights.copy(deep=True))
        object.__setattr__(self, "cash", self.cash.copy(deep=True))
        expected_index = pd.DatetimeIndex([step.as_of for step in self.steps], name="as_of")
        if not self.weights.index.equals(expected_index) or not self.cash.index.equals(
            expected_index
        ):
            raise ValueError("optimization path outputs must use the step as_of index")
        if self.failure_policy not in {"raise", "hold_previous"}:
            raise ValueError("unsupported optimization failure policy")


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
        object.__setattr__(
            self,
            "decision_lag",
            require_integer(self.decision_lag, name="decision_lag", minimum=0),
        )
        object.__setattr__(
            self,
            "execution_lag",
            require_integer(self.execution_lag, name="execution_lag", minimum=0),
        )
        if self.holding_period is not None:
            object.__setattr__(
                self,
                "holding_period",
                require_integer(self.holding_period, name="holding_period", minimum=1),
            )


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
class MarketImpactModel:
    """Nonlinear participation impact calibrated in basis points."""

    coefficient_bps: float
    exponent: float = 0.5

    def __post_init__(self) -> None:
        finite_scalar(self.coefficient_bps, name="impact coefficient", minimum=0.0)
        finite_scalar(self.exponent, name="impact exponent", minimum=0.0)
        if self.exponent == 0.0:
            raise ValueError("impact exponent must be positive")


@dataclass(frozen=True, slots=True)
class BorrowPolicy:
    """Missing-rate and unavailable-short behavior for portfolio backtests."""

    unavailable: UnavailableShortPolicy = "error"
    missing_rate: MissingCostPolicy = "error"

    def __post_init__(self) -> None:
        if self.unavailable not in {"error", "cover"}:
            raise ValueError("unsupported unavailable-short policy")
        if self.missing_rate not in {"error", "zero"}:
            raise ValueError("unsupported missing borrow-rate policy")


@dataclass(frozen=True, slots=True)
class MultiCurrencyPolicy:
    """Base currency, asset currencies, and bounded missing-FX behavior."""

    base_currency: str
    asset_currencies: pd.Series
    missing_fx: MissingFxPolicy = "error"
    maximum_staleness: int = 0

    def __post_init__(self) -> None:
        if not self.base_currency:
            raise ValueError("base_currency must not be empty")
        object.__setattr__(self, "asset_currencies", self.asset_currencies.copy(deep=True))
        if self.missing_fx not in {"error", "ffill"}:
            raise ValueError("unsupported missing-FX policy")
        object.__setattr__(
            self,
            "maximum_staleness",
            require_integer(
                self.maximum_staleness,
                name="maximum_staleness",
                minimum=0,
            ),
        )


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
    local_return_attribution: pd.DataFrame
    fx_return_attribution: pd.DataFrame
    cash_return_attribution: pd.Series
    currency_cash: pd.DataFrame
    ending_currency_cash: pd.DataFrame
    fx_rates: pd.DataFrame
    fx_staleness: pd.DataFrame
    cost_attribution: pd.DataFrame
    trade_cost_attribution: pd.DataFrame
    impact_cost_attribution: pd.DataFrame
    borrow_cost_attribution: pd.DataFrame
    costs: pd.Series
    trade_costs: pd.Series
    impact_costs: pd.Series
    borrow_costs: pd.Series
    cost_input_coverage: pd.DataFrame
    borrow_events: pd.DataFrame
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
            "local_return_attribution": self.local_return_attribution,
            "fx_return_attribution": self.fx_return_attribution,
            "cost_attribution": self.cost_attribution,
            "trade_cost_attribution": self.trade_cost_attribution,
            "impact_cost_attribution": self.impact_cost_attribution,
            "borrow_cost_attribution": self.borrow_cost_attribution,
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
            "trade_costs": self.trade_costs,
            "impact_costs": self.impact_costs,
            "borrow_costs": self.borrow_costs,
        }
        for name, values in series.items():
            if not values.index.equals(weights.index):
                raise ValueError(f"{name} must use the realized-weight index")
            object.__setattr__(self, name, values.copy(deep=True))
        if not self.exposures.index.equals(weights.index):
            raise ValueError("exposures must use the realized-weight index")
        object.__setattr__(self, "exposures", self.exposures.copy(deep=True))
        for name, panel in {
            "currency_cash": self.currency_cash,
            "ending_currency_cash": self.ending_currency_cash,
            "fx_rates": self.fx_rates,
            "fx_staleness": self.fx_staleness,
        }.items():
            if not panel.index.equals(weights.index):
                raise ValueError(f"{name} must use the realized-weight index")
            object.__setattr__(self, name, panel.copy(deep=True))
        if not self.cost_input_coverage.index.equals(weights.index):
            raise ValueError("cost_input_coverage must use the realized-weight index")
        object.__setattr__(
            self,
            "cost_input_coverage",
            self.cost_input_coverage.copy(deep=True),
        )
        object.__setattr__(self, "borrow_events", self.borrow_events.copy(deep=True))
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
            self.local_return_attribution.add(self.fx_return_attribution),
            self.asset_return_attribution,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("local and FX attribution do not reconcile to asset returns")
        if not np.allclose(
            self.currency_cash.sum(axis="columns"),
            self.cash,
            atol=tolerance,
            rtol=0.0,
        ) or not np.allclose(
            self.ending_currency_cash.sum(axis="columns"),
            self.ending_cash,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("currency cash does not reconcile to base cash")
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
        for name, attribution, totals in (
            ("trade", self.trade_cost_attribution, self.trade_costs),
            ("impact", self.impact_cost_attribution, self.impact_costs),
            ("borrow", self.borrow_cost_attribution, self.borrow_costs),
        ):
            if not np.allclose(
                attribution.sum(axis="columns"),
                totals,
                atol=tolerance,
                rtol=0.0,
            ):
                raise ValueError(f"{name} cost attribution does not reconcile")
        if not np.allclose(
            self.trade_costs.add(self.impact_costs).add(self.borrow_costs),
            self.costs,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("cost components do not reconcile to total costs")
        expected_equity = self.returns.add(1.0).cumprod().mul(self.initial_equity)
        if not np.allclose(expected_equity, self.equity, atol=tolerance, rtol=1e-12):
            raise ValueError("returns do not reconcile to equity")
        object.__setattr__(self, "realized_weights", weights)
