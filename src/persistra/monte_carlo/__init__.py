"""Deterministic, pluggable, multi-path Monte Carlo research."""

from persistra.monte_carlo.calibration import fit_geometric_brownian_motion
from persistra.monte_carlo.contracts import (
    Distribution,
    MonteCarloExecution,
    MonteCarloExperiment,
    MonteCarloModel,
    MonteCarloResult,
    PathEvaluator,
    PathMetric,
)
from persistra.monte_carlo.distributions import (
    EmpiricalDistribution,
    MultivariateNormalDistribution,
    NormalDistribution,
    StudentTDistribution,
)
from persistra.monte_carlo.models import (
    GeometricBrownianMotion,
    MovingBlockBootstrap,
    MultivariateNormalReturns,
)
from persistra.monte_carlo.runner import run_experiment

__all__ = [
    "Distribution",
    "EmpiricalDistribution",
    "GeometricBrownianMotion",
    "MonteCarloExecution",
    "MonteCarloExperiment",
    "MonteCarloModel",
    "MonteCarloResult",
    "MovingBlockBootstrap",
    "MultivariateNormalDistribution",
    "MultivariateNormalReturns",
    "NormalDistribution",
    "PathEvaluator",
    "PathMetric",
    "StudentTDistribution",
    "fit_geometric_brownian_motion",
    "run_experiment",
]
