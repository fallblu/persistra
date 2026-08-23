"""Transparent, reconciled portfolio performance reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from persistra.portfolio._validation import finite_scalar

if TYPE_CHECKING:
    from persistra.portfolio.model import BacktestResult


@dataclass(frozen=True, slots=True)
class PortfolioPerformanceReport:
    """Performance metrics, benchmark comparisons, and accounting aggregates."""

    summary: pd.Series
    benchmarks: pd.DataFrame
    attribution: pd.Series
    coverage: pd.Series
    periods_per_year: float
    risk_free_returns: pd.Series
    return_index: pd.Index

    def __post_init__(self) -> None:
        if not self.risk_free_returns.index.equals(self.return_index):
            raise ValueError("risk-free returns must use the report return index")
        for name in ("summary", "attribution", "coverage", "risk_free_returns"):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        object.__setattr__(self, "benchmarks", self.benchmarks.copy(deep=True))
        object.__setattr__(self, "return_index", self.return_index.copy())


def portfolio_performance_report(
    result: BacktestResult,
    *,
    periods_per_year: float,
    risk_free_returns: float | pd.Series,
) -> PortfolioPerformanceReport:
    """Summarize a backtest with explicit annualization and risk-free assumptions."""
    annualization = finite_scalar(
        periods_per_year, name="periods_per_year", minimum=0.0
    )
    if annualization == 0.0:
        raise ValueError("periods_per_year must be positive")
    risk_free = _risk_free_path(risk_free_returns, result.returns.index)
    returns = result.returns.to_numpy(dtype=float)
    excess = returns - risk_free.to_numpy(dtype=float)
    count = len(returns)
    annualized_return = _annualized_geometric(returns, annualization)
    volatility = _annualized_deviation(returns, annualization)
    excess_volatility = float(np.std(excess, ddof=1)) if count > 1 else np.nan
    sharpe = (
        float(np.mean(excess) * np.sqrt(annualization) / excess_volatility)
        if excess_volatility > 0.0
        else np.nan
    )
    downside = float(np.sqrt(np.mean(np.square(np.minimum(excess, 0.0)))))
    sortino = (
        float(np.mean(excess) * np.sqrt(annualization) / downside)
        if downside > 0.0
        else np.nan
    )
    maximum_drawdown = float(result.drawdown.min())
    calmar = (
        annualized_return / abs(maximum_drawdown)
        if maximum_drawdown < 0.0
        else np.nan
    )
    summary = pd.Series(
        {
            "observations": float(count),
            "annualized_return": annualized_return,
            "annualized_volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "maximum_drawdown": maximum_drawdown,
            "maximum_drawdown_duration": float(_maximum_drawdown_duration(result.drawdown)),
            "total_turnover": float(result.turnover.sum()),
            "annualized_turnover": float(result.turnover.mean() * annualization),
            "total_cost_drag": float(result.costs.sum()),
            "annualized_cost_drag": float(result.costs.mean() * annualization),
        },
        name="portfolio",
        dtype=float,
    )
    attribution = _attribution(result)
    coverage = _coverage(result)
    benchmarks = _benchmark_report(result, annualization)
    return PortfolioPerformanceReport(
        summary=summary,
        benchmarks=benchmarks,
        attribution=attribution,
        coverage=coverage,
        periods_per_year=annualization,
        risk_free_returns=risk_free,
        return_index=result.returns.index,
    )


def _risk_free_path(values: float | pd.Series, index: pd.Index) -> pd.Series:
    if isinstance(values, pd.Series):
        if not values.index.equals(index):
            raise ValueError("risk_free_returns must use the backtest return index")
        result = values.astype(float).rename("risk_free_return")
    else:
        if isinstance(values, bool):
            raise TypeError("risk_free_returns must be numeric")
        result = pd.Series(float(values), index=index, name="risk_free_return")
    raw = result.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(raw).all():
        raise ValueError("risk_free_returns must be finite")
    if (raw < -1.0).any():
        raise ValueError("risk_free_returns must not be less than -1")
    return result


def _annualized_geometric(returns: np.ndarray, periods_per_year: float) -> float:
    if len(returns) == 0:
        return np.nan
    growth = float(np.prod(1.0 + returns))
    return float(growth ** (periods_per_year / len(returns)) - 1.0)


def _annualized_deviation(returns: np.ndarray, periods_per_year: float) -> float:
    if len(returns) < 2:
        return np.nan
    return float(np.std(returns, ddof=1) * np.sqrt(periods_per_year))


def _maximum_drawdown_duration(drawdown: pd.Series) -> int:
    longest = 0
    current = 0
    for value in drawdown.to_numpy(dtype=float):
        current = current + 1 if value < 0.0 else 0
        longest = max(longest, current)
    return longest


def _attribution(result: BacktestResult) -> pd.Series:
    values = pd.Series(
        {
            "local_return": float(result.local_return_attribution.to_numpy().sum()),
            "fx_return": float(result.fx_return_attribution.to_numpy().sum()),
            "corporate_action_return": float(
                result.corporate_action_attribution.to_numpy().sum()
            ),
            "asset_return": float(result.asset_return_attribution.to_numpy().sum()),
            "cash_return": float(result.cash_return_attribution.sum()),
            "gross_return": float(result.gross_returns.sum()),
            "trade_cost": float(result.trade_costs.sum()),
            "impact_cost": float(result.impact_costs.sum()),
            "borrow_cost": float(result.borrow_costs.sum()),
            "total_cost": float(result.costs.sum()),
            "net_return": float(result.returns.sum()),
        },
        name="aggregate",
        dtype=float,
    )
    if not np.isclose(
        values["local_return"]
        + values["fx_return"]
        + values["corporate_action_return"],
        values["asset_return"],
        atol=result.tolerance,
        rtol=0.0,
    ):
        raise ValueError("aggregate asset attribution does not reconcile")
    if not np.isclose(
        values["asset_return"] + values["cash_return"],
        values["gross_return"],
        atol=result.tolerance,
        rtol=0.0,
    ):
        raise ValueError("aggregate gross attribution does not reconcile")
    if not np.isclose(
        values["trade_cost"] + values["impact_cost"] + values["borrow_cost"],
        values["total_cost"],
        atol=result.tolerance,
        rtol=0.0,
    ):
        raise ValueError("aggregate costs do not reconcile")
    if not np.isclose(
        values["gross_return"] - values["total_cost"],
        values["net_return"],
        atol=result.tolerance,
        rtol=0.0,
    ):
        raise ValueError("aggregate net return does not reconcile")
    return values


def _coverage(result: BacktestResult) -> pd.Series:
    values: dict[str, float] = {
        "return_coverage": float(result.returns.notna().mean()),
        "fresh_fx_coverage": float(result.fx_staleness.eq(0).to_numpy().mean()),
        "executed_target_coverage": float(
            result.rebalance_log["status"].eq("executed").mean()
        ),
    }
    values.update(
        {
            f"{column}_coverage": float(result.cost_input_coverage[column].mean())
            for column in result.cost_input_coverage
        }
    )
    return pd.Series(values, name="coverage", dtype=float)


def _benchmark_report(
    result: BacktestResult, periods_per_year: float
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for name in result.benchmark_returns:
        benchmark = result.benchmark_returns[name].to_numpy(dtype=float)
        strategy = result.returns.to_numpy(dtype=float)
        active = strategy - benchmark
        tracking_error = _annualized_deviation(active, periods_per_year)
        information_ratio = (
            float(np.mean(active) * periods_per_year / tracking_error)
            if tracking_error > 0.0
            else np.nan
        )
        relative_growth = float(np.prod(1.0 + strategy) / np.prod(1.0 + benchmark))
        rows.append(
            {
                "benchmark_annualized_return": _annualized_geometric(
                    benchmark, periods_per_year
                ),
                "annualized_relative_return": float(
                    relative_growth ** (periods_per_year / len(active)) - 1.0
                ),
                "tracking_error": tracking_error,
                "information_ratio": information_ratio,
                "correlation": (
                    np.nan
                    if result.returns.nunique() < 2
                    or result.benchmark_returns[name].nunique() < 2
                    else float(result.returns.corr(result.benchmark_returns[name]))
                ),
            }
        )
    columns = [
        "benchmark_annualized_return",
        "annualized_relative_return",
        "tracking_error",
        "information_ratio",
        "correlation",
    ]
    return pd.DataFrame(rows, index=result.benchmark_returns.columns, columns=columns)
