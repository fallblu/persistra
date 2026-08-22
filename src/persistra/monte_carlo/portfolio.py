"""Bounded portfolio evaluation for Monte Carlo paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd

from persistra.monte_carlo._validation import finite_scalar
from persistra.portfolio import BacktestPolicies, BacktestTiming, backtest_portfolio

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class PortfolioBacktestEvaluator:
    """Evaluate return or price paths through the vectorized portfolio backtester."""

    target_weights: pd.DataFrame
    timing: BacktestTiming = field(default_factory=BacktestTiming)
    policies: BacktestPolicies = field(default_factory=BacktestPolicies)
    transaction_cost_bps: float | pd.Series = 0.0
    initial_equity: float = 1.0
    path_kind: Literal["returns", "prices"] = "returns"

    def __post_init__(self) -> None:
        targets = self.target_weights.copy(deep=True)
        if not isinstance(targets.index, pd.DatetimeIndex):
            raise TypeError("portfolio target_weights must use a DatetimeIndex")
        if targets.empty or targets.shape[1] == 0:
            raise ValueError("portfolio target_weights must not be empty")
        if not targets.index.is_unique or not targets.index.is_monotonic_increasing:
            raise ValueError("portfolio target_weights index must be unique and ordered")
        if not targets.columns.is_unique:
            raise ValueError("portfolio target_weights columns must be unique")
        if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in targets.dtypes):
            raise TypeError("portfolio target_weights must be numeric")
        if not np.isfinite(targets.to_numpy(dtype=float)).all():
            raise ValueError("portfolio target_weights must be finite and complete")
        if self.path_kind not in {"returns", "prices"}:
            raise ValueError("path_kind must be returns or prices")
        initial_equity = finite_scalar(self.initial_equity, name="initial_equity", positive=True)
        costs: float | pd.Series
        if isinstance(self.transaction_cost_bps, pd.Series):
            costs = self.transaction_cost_bps.astype(float).copy(deep=True)
            if not costs.index.equals(targets.columns):
                raise ValueError("transaction_cost_bps must use the target asset axis")
            if not np.isfinite(costs.to_numpy(dtype=float)).all() or costs.lt(0).any():
                raise ValueError("transaction_cost_bps must be finite and nonnegative")
        else:
            costs = finite_scalar(self.transaction_cost_bps, name="transaction_cost_bps")
            if costs < 0.0:
                raise ValueError("transaction_cost_bps must be nonnegative")
        object.__setattr__(self, "target_weights", targets.astype(float))
        object.__setattr__(self, "transaction_cost_bps", costs)
        object.__setattr__(self, "initial_equity", initial_equity)

    @property
    def name(self) -> str:
        return "portfolio_backtest"

    @property
    def version(self) -> str:
        return "1"

    @property
    def metric_names(self) -> tuple[str, ...]:
        return (
            "portfolio_terminal_equity",
            "portfolio_return",
            "portfolio_maximum_drawdown",
            "portfolio_turnover",
            "portfolio_cost",
        )

    @property
    def parameters(self) -> Mapping[str, Any]:
        costs: float | list[float]
        if isinstance(self.transaction_cost_bps, pd.Series):
            costs = self.transaction_cost_bps.tolist()
        else:
            costs = self.transaction_cost_bps
        return {
            "target_index": [str(value) for value in self.target_weights.index],
            "target_assets": [str(value) for value in self.target_weights.columns],
            "target_weights": self.target_weights.to_numpy(dtype=float).tolist(),
            "timing": {
                "decision_lag": self.timing.decision_lag,
                "execution_lag": self.timing.execution_lag,
                "holding_period": self.timing.holding_period,
                "signal_available_before_trade": self.timing.signal_available_before_trade,
            },
            "policies": {
                "missing_return": self.policies.missing_return,
                "nontradeable": self.policies.nontradeable,
            },
            "transaction_cost_bps": costs,
            "initial_equity": self.initial_equity,
            "path_kind": self.path_kind,
        }

    def evaluate(
        self,
        path: NDArray[np.float64],
        output_index: pd.Index,
        variable_names: tuple[str, ...],
    ) -> Mapping[str, float]:
        if not isinstance(output_index, pd.DatetimeIndex):
            raise TypeError("portfolio path output_index must be a DatetimeIndex")
        if tuple(self.target_weights.columns) != variable_names:
            raise ValueError("portfolio targets must use the path variable axis")
        frame = pd.DataFrame(path, index=output_index.copy(), columns=list(variable_names))
        if self.path_kind == "returns":
            result = backtest_portfolio(
                self.target_weights,
                returns=frame,
                timing=self.timing,
                policies=self.policies,
                transaction_cost_bps=self.transaction_cost_bps,
                initial_equity=self.initial_equity,
            )
        else:
            result = backtest_portfolio(
                self.target_weights,
                prices=frame,
                timing=self.timing,
                policies=self.policies,
                transaction_cost_bps=self.transaction_cost_bps,
                initial_equity=self.initial_equity,
            )
        terminal_equity = float(result.equity.iloc[-1])
        return {
            "portfolio_terminal_equity": terminal_equity,
            "portfolio_return": terminal_equity / self.initial_equity - 1.0,
            "portfolio_maximum_drawdown": float(-result.drawdown.min()),
            "portfolio_turnover": float(result.turnover.sum()),
            "portfolio_cost": float(result.costs.sum()),
        }
