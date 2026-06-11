"""Parameter sweeps, walk-forward validation, and multi-run comparison.

Factories must be picklable when ``n_jobs > 1`` (joblib loky backend): use
named functions or ``functools.partial``, not lambdas. The backtest engine is
deterministic, so sweeps take no engine seed — ``random_search`` and
``bayes_search`` accept a ``seed`` that controls parameter sampling only.
"""

from .bayes import bayes_search
from .compare import compare
from .grid import grid_search
from .random import random_search
from .sweep_result import (
    ComparisonResult,
    SweepResult,
    WalkForwardOptimizationResult,
    WalkForwardResult,
)
from .walk_forward import walk_forward, walk_forward_grid_search

__all__ = [
    "ComparisonResult",
    "SweepResult",
    "WalkForwardOptimizationResult",
    "WalkForwardResult",
    "bayes_search",
    "compare",
    "grid_search",
    "random_search",
    "walk_forward",
    "walk_forward_grid_search",
]
