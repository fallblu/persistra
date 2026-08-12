"""Portfolio-level vectorized backtesting with explicit timing and accounting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError
from persistra.portfolio._validation import asset_panel, finite_scalar
from persistra.portfolio.model import (
    BacktestPolicies,
    BacktestResult,
    BacktestTiming,
    PortfolioConstructionResult,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class _TimingPlan:
    events: dict[int, np.ndarray]
    event_rows: dict[int, int | None]
    log: pd.DataFrame


@dataclass(frozen=True, slots=True)
class _Simulation:
    realized_weights: pd.DataFrame
    ending_weights: pd.DataFrame
    cash: pd.Series
    ending_cash: pd.Series
    returns: pd.Series
    gross_returns: pd.Series
    exposures: pd.DataFrame
    turnover: pd.Series
    trades: pd.DataFrame
    asset_return_attribution: pd.DataFrame
    cash_return_attribution: pd.Series
    cost_attribution: pd.DataFrame
    costs: pd.Series
    blocked_assets: dict[int, tuple[object, ...]]


def backtest_portfolio(
    target_weights: PortfolioConstructionResult | pd.DataFrame,
    *,
    returns: pd.DataFrame | None = None,
    prices: pd.DataFrame | None = None,
    timing: BacktestTiming | None = None,
    policies: BacktestPolicies | None = None,
    transaction_cost_bps: float | pd.Series = 0.0,
    cash_returns: float | pd.Series = 0.0,
    tradeable: pd.DataFrame | None = None,
    benchmarks: Mapping[str, pd.DataFrame | pd.Series] | None = None,
    initial_equity: float = 1.0,
    tolerance: float = 1e-10,
) -> BacktestResult:
    """Simulate rebalances to supplied targets over returns or prices.

    Target row dates are signal-observation dates. ``BacktestTiming`` maps each observation
    to a decision date and first holding period. The default applies a target one period after
    its signal observation. Zero total lag is rejected unless the caller asserts that the
    signal was available before the assumed trade.

    Transaction costs are linear per risky-asset traded notional. Cash is the residual needed
    to make beginning weights sum to one; it can be greater than one after short sales or
    negative under net leverage. Returns, cash, holdings, and cost attribution reconcile in the
    returned result.

    A benchmark value can be a static weight series or a date-by-asset target panel. Static
    weights enter on the first strategy signal date and then drift. Panel benchmarks use the
    same timing and policies as the strategy. This supports explicit static and naive-signal
    comparisons without hiding their definitions.
    """
    targets = _target_panel(target_weights)
    market_returns = _market_returns(returns=returns, prices=prices)
    if not targets.columns.equals(market_returns.columns):
        raise ValueError("target weights must use the portfolio-return columns")
    return_index = cast("pd.DatetimeIndex", market_returns.index)
    if len(targets.index) == 0:
        raise ValueError("target weights must contain at least one signal observation")
    missing_dates = targets.index.difference(market_returns.index)
    if len(missing_dates):
        raise ValueError("target-weight dates must belong to the portfolio-return index")
    if not np.isfinite(targets.to_numpy(dtype=float, na_value=np.nan)).all():
        raise AnalysisError("target weights must be finite")

    effective_timing = timing or BacktestTiming()
    effective_policies = policies or BacktestPolicies()
    numeric_tolerance = finite_scalar(tolerance, name="tolerance", minimum=0.0)
    equity_start = finite_scalar(initial_equity, name="initial_equity", minimum=0.0)
    if equity_start == 0:
        raise ValueError("initial_equity must be positive")
    cost_rates = _cost_rates(transaction_cost_bps, targets.columns)
    cash_path = _cash_return_path(cash_returns, return_index)
    tradeable_panel = _tradeable_panel(tradeable, market_returns)
    plan = _timing_plan(targets, return_index, effective_timing)
    simulation = _simulate(
        targets,
        market_returns,
        plan=plan,
        policies=effective_policies,
        cost_rates=cost_rates,
        cash_returns=cash_path,
        tradeable=tradeable_panel,
        tolerance=numeric_tolerance,
    )
    rebalance_log = plan.log.copy(deep=True)
    for row_number, blocked in simulation.blocked_assets.items():
        rebalance_log.at[row_number, "blocked_assets"] = ", ".join(map(str, blocked))

    net_returns = simulation.returns
    equity = net_returns.add(1.0).cumprod().mul(equity_start).rename("equity")
    running_peak = equity.cummax().clip(lower=equity_start)
    drawdown = equity.div(running_peak).sub(1.0).rename("drawdown")
    benchmark_returns, benchmark_equity = _run_benchmarks(
        benchmarks,
        strategy_targets=targets,
        market_returns=market_returns,
        timing=effective_timing,
        policies=effective_policies,
        cost_rates=cost_rates,
        cash_returns=cash_path,
        tradeable=tradeable_panel,
        initial_equity=equity_start,
        tolerance=numeric_tolerance,
    )
    comparison = _compare_benchmarks(net_returns, benchmark_returns)
    return BacktestResult(
        target_weights=targets,
        realized_weights=simulation.realized_weights,
        ending_weights=simulation.ending_weights,
        cash=simulation.cash,
        ending_cash=simulation.ending_cash,
        returns=net_returns,
        gross_returns=simulation.gross_returns,
        equity=equity,
        drawdown=drawdown,
        exposures=simulation.exposures,
        turnover=simulation.turnover,
        trades=simulation.trades,
        asset_return_attribution=simulation.asset_return_attribution,
        cash_return_attribution=simulation.cash_return_attribution,
        cost_attribution=simulation.cost_attribution,
        costs=simulation.costs,
        rebalance_log=rebalance_log,
        benchmark_returns=benchmark_returns,
        benchmark_equity=benchmark_equity,
        benchmark_comparison=comparison,
        initial_equity=equity_start,
        timing=effective_timing,
        policies=effective_policies,
        tolerance=numeric_tolerance,
    )


def _target_panel(
    targets: PortfolioConstructionResult | pd.DataFrame,
) -> pd.DataFrame:
    if isinstance(targets, PortfolioConstructionResult):
        return asset_panel(targets.weights, name="target weights")
    return asset_panel(targets, name="target weights")


def _market_returns(
    *,
    returns: pd.DataFrame | None,
    prices: pd.DataFrame | None,
) -> pd.DataFrame:
    if (returns is None) == (prices is None):
        raise ValueError("supply exactly one of returns or prices")
    if returns is not None:
        result = asset_panel(returns, name="portfolio returns")
    else:
        assert prices is not None
        levels = asset_panel(prices, name="portfolio prices")
        values = levels.to_numpy(dtype=float, na_value=np.nan)
        if (values[~np.isnan(values)] <= 0).any():
            raise AnalysisError("portfolio prices must be positive")
        result = levels.pct_change(fill_method=None)
    values = result.to_numpy(dtype=float, na_value=np.nan)
    if (values[~np.isnan(values)] < -1.0).any():
        raise AnalysisError("simple asset returns must not be less than -1")
    return result


def _cost_rates(costs: float | pd.Series, columns: pd.Index) -> np.ndarray:
    if isinstance(costs, pd.Series):
        if not costs.index.equals(columns):
            raise ValueError("transaction_cost_bps must use the asset columns")
        values = costs.to_numpy(dtype=float, na_value=np.nan)
    else:
        values = np.full(len(columns), float(costs), dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("transaction_cost_bps must be finite and nonnegative")
    return values / 10_000.0


def _cash_return_path(cash_returns: float | pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    if isinstance(cash_returns, pd.Series):
        if not cash_returns.index.equals(index):
            raise ValueError("cash_returns must use the portfolio-return index")
        values = cash_returns.to_numpy(dtype=float, na_value=np.nan)
    else:
        values = np.full(len(index), float(cash_returns), dtype=float)
    if not np.isfinite(values).all():
        raise AnalysisError("cash_returns must be finite")
    if (values < -1.0).any():
        raise AnalysisError("cash_returns must not be less than -1")
    return values


def _tradeable_panel(
    tradeable: pd.DataFrame | None,
    market_returns: pd.DataFrame,
) -> np.ndarray:
    if tradeable is None:
        return np.ones(market_returns.shape, dtype=bool)
    if not tradeable.index.equals(market_returns.index) or not tradeable.columns.equals(
        market_returns.columns
    ):
        raise ValueError("tradeable must use the portfolio-return index and columns")
    if any(not pd.api.types.is_bool_dtype(dtype) for dtype in tradeable.dtypes):
        raise TypeError("tradeable columns must be boolean")
    if tradeable.isna().any(axis=None):
        raise ValueError("tradeable must not contain missing values")
    return tradeable.to_numpy(dtype=bool)


def _timing_plan(
    targets: pd.DataFrame,
    return_index: pd.DatetimeIndex,
    timing: BacktestTiming,
) -> _TimingPlan:
    if (
        timing.decision_lag + timing.execution_lag == 0
        and not timing.signal_available_before_trade
    ):
        raise AnalysisError(
            "same-period signal use requires signal_available_before_trade=True"
        )
    events: dict[int, np.ndarray] = {}
    event_rows: dict[int, int | None] = {}
    records: list[dict[str, object]] = []
    executable: list[tuple[int, int]] = []
    for row_number, (signal_date, row) in enumerate(targets.iterrows()):
        location = return_index.get_loc(cast("pd.Timestamp", signal_date))
        if not isinstance(location, (int, np.integer)):
            raise AssertionError("validated target dates must have scalar locations")
        signal_position = int(location)
        decision_position = signal_position + timing.decision_lag
        holding_start = decision_position + timing.execution_lag
        decision_date = (
            return_index[decision_position] if decision_position < len(return_index) else pd.NaT
        )
        start_date = return_index[holding_start] if holding_start < len(return_index) else pd.NaT
        status = "scheduled" if holding_start < len(return_index) else "outside_sample"
        records.append(
            {
                "signal_observation": signal_date,
                "decision": decision_date,
                "holding_start": start_date,
                "holding_end": pd.NaT,
                "status": status,
                "blocked_assets": "",
            }
        )
        if holding_start < len(return_index):
            events[holding_start] = row.to_numpy(dtype=float)
            event_rows[holding_start] = row_number
            executable.append((row_number, holding_start))

    for position, (row_number, start) in enumerate(executable):
        next_start = (
            executable[position + 1][1] if position + 1 < len(executable) else len(return_index)
        )
        end = next_start - 1
        if timing.holding_period is not None:
            scheduled_end = min(start + timing.holding_period - 1, len(return_index) - 1)
            end = min(end, scheduled_end)
            exit_position = end + 1
            if exit_position < next_start and exit_position < len(return_index):
                events[exit_position] = np.zeros(targets.shape[1], dtype=float)
                event_rows[exit_position] = None
        records[row_number]["holding_end"] = return_index[end]
        records[row_number]["status"] = "executed"
    log = pd.DataFrame(
        records,
        columns=[
            "signal_observation",
            "decision",
            "holding_start",
            "holding_end",
            "status",
            "blocked_assets",
        ],
    )
    return _TimingPlan(events=events, event_rows=event_rows, log=log)


def _simulate(
    targets: pd.DataFrame,
    market_returns: pd.DataFrame,
    *,
    plan: _TimingPlan,
    policies: BacktestPolicies,
    cost_rates: np.ndarray,
    cash_returns: np.ndarray,
    tradeable: np.ndarray,
    tolerance: float,
) -> _Simulation:
    rows, assets = market_returns.shape
    realized = np.zeros((rows, assets), dtype=float)
    ending = np.zeros((rows, assets), dtype=float)
    cash = np.zeros(rows, dtype=float)
    ending_cash = np.zeros(rows, dtype=float)
    net_returns = np.zeros(rows, dtype=float)
    gross_returns = np.zeros(rows, dtype=float)
    turnover = np.zeros(rows, dtype=float)
    trades = np.zeros((rows, assets), dtype=float)
    asset_attribution = np.zeros((rows, assets), dtype=float)
    cash_attribution = np.zeros(rows, dtype=float)
    cost_attribution = np.zeros((rows, assets), dtype=float)
    total_costs = np.zeros(rows, dtype=float)
    exposure_rows: list[dict[str, float]] = []
    blocked_assets: dict[int, tuple[object, ...]] = {}
    previous_weights = np.zeros(assets, dtype=float)
    previous_cash = 1.0
    return_values = market_returns.to_numpy(dtype=float, na_value=np.nan)

    for position in range(rows):
        beginning = previous_weights.copy()
        beginning_cash = previous_cash
        if position in plan.events:
            desired = plan.events[position].copy()
            blocked = (~tradeable[position]) & (np.abs(desired - previous_weights) > tolerance)
            if blocked.any():
                labels = tuple(
                    cast("object", targets.columns[int(asset)])
                    for asset in np.flatnonzero(blocked)
                )
                if policies.nontradeable == "error":
                    raise AnalysisError(
                        f"nontradeable assets require trades on {market_returns.index[position]}: "
                        + ", ".join(map(str, labels))
                    )
                desired[blocked] = previous_weights[blocked]
                event_row = plan.event_rows[position]
                if event_row is not None:
                    blocked_assets[event_row] = labels
            beginning = desired
            beginning_cash = 1.0 - float(beginning.sum())

        delta = beginning - previous_weights
        delta_cash = beginning_cash - previous_cash
        asset_costs = np.abs(delta) * cost_rates
        period_cost = float(asset_costs.sum())
        period_turnover = 0.5 * (float(np.abs(delta).sum()) + abs(delta_cash))
        period_asset_returns = return_values[position].copy()
        missing_held = np.isnan(period_asset_returns) & (np.abs(beginning) > tolerance)
        if missing_held.any() and policies.missing_return == "error":
            labels = [
                cast("object", market_returns.columns[int(asset)])
                for asset in np.flatnonzero(missing_held)
            ]
            raise AnalysisError(
                f"held assets have missing returns on {market_returns.index[position]}: "
                + ", ".join(map(str, labels))
            )
        period_asset_returns[np.isnan(period_asset_returns)] = 0.0
        asset_contributions = beginning * period_asset_returns
        cash_contribution = beginning_cash * cash_returns[position]
        gross_return = float(asset_contributions.sum() + cash_contribution)
        net_return = gross_return - period_cost
        growth = 1.0 + net_return
        if growth <= tolerance:
            raise AnalysisError(
                f"portfolio equity is nonpositive on {market_returns.index[position]}"
            )
        ending_values = beginning * (1.0 + period_asset_returns)
        ending_cash_value = beginning_cash * (1.0 + cash_returns[position]) - period_cost
        period_ending = ending_values / growth
        period_ending_cash = ending_cash_value / growth

        realized[position] = beginning
        ending[position] = period_ending
        cash[position] = beginning_cash
        ending_cash[position] = period_ending_cash
        net_returns[position] = net_return
        gross_returns[position] = gross_return
        turnover[position] = period_turnover
        trades[position] = delta
        asset_attribution[position] = asset_contributions
        cash_attribution[position] = cash_contribution
        cost_attribution[position] = asset_costs
        total_costs[position] = period_cost
        exposure_rows.append(_exposures(beginning, beginning_cash))
        previous_weights = period_ending
        previous_cash = period_ending_cash

    index = market_returns.index
    columns = market_returns.columns
    return _Simulation(
        realized_weights=pd.DataFrame(realized, index=index, columns=columns),
        ending_weights=pd.DataFrame(ending, index=index, columns=columns),
        cash=pd.Series(cash, index=index, name="cash", dtype=float),
        ending_cash=pd.Series(ending_cash, index=index, name="ending_cash", dtype=float),
        returns=pd.Series(net_returns, index=index, name="return", dtype=float),
        gross_returns=pd.Series(gross_returns, index=index, name="gross_return", dtype=float),
        exposures=pd.DataFrame(exposure_rows, index=index),
        turnover=pd.Series(turnover, index=index, name="turnover", dtype=float),
        trades=pd.DataFrame(trades, index=index, columns=columns),
        asset_return_attribution=pd.DataFrame(asset_attribution, index=index, columns=columns),
        cash_return_attribution=pd.Series(
            cash_attribution,
            index=index,
            name="cash_return_attribution",
            dtype=float,
        ),
        cost_attribution=pd.DataFrame(cost_attribution, index=index, columns=columns),
        costs=pd.Series(total_costs, index=index, name="cost", dtype=float),
        blocked_assets=blocked_assets,
    )


def _exposures(weights: np.ndarray, cash: float) -> dict[str, float]:
    long = float(np.maximum(weights, 0).sum())
    short = float(np.maximum(-weights, 0).sum())
    return {
        "long": long,
        "short": short,
        "gross": long + short,
        "net": long - short,
        "cash": cash,
    }


def _run_benchmarks(
    benchmarks: Mapping[str, pd.DataFrame | pd.Series] | None,
    *,
    strategy_targets: pd.DataFrame,
    market_returns: pd.DataFrame,
    timing: BacktestTiming,
    policies: BacktestPolicies,
    cost_rates: np.ndarray,
    cash_returns: np.ndarray,
    tradeable: np.ndarray,
    initial_equity: float,
    tolerance: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result_returns: dict[str, pd.Series] = {}
    result_equity: dict[str, pd.Series] = {}
    if benchmarks is None:
        empty = pd.DataFrame(index=market_returns.index)
        return empty, empty.copy()
    for name, supplied in benchmarks.items():
        if not name:
            raise ValueError("benchmark names must be nonempty strings")
        benchmark_timing = timing
        if isinstance(supplied, pd.Series):
            if not supplied.index.equals(market_returns.columns):
                raise ValueError(f"static benchmark {name} must use the asset columns")
            benchmark_targets = pd.DataFrame(
                [supplied.to_numpy(dtype=float, na_value=np.nan)],
                index=pd.DatetimeIndex([strategy_targets.index[0]]),
                columns=market_returns.columns,
            )
            benchmark_timing = BacktestTiming(
                decision_lag=timing.decision_lag,
                execution_lag=timing.execution_lag,
                holding_period=None,
                signal_available_before_trade=timing.signal_available_before_trade,
            )
        else:
            benchmark_targets = asset_panel(supplied, name=f"benchmark {name}")
            if not benchmark_targets.columns.equals(market_returns.columns):
                raise ValueError(f"benchmark {name} must use the asset columns")
        if not np.isfinite(
            benchmark_targets.to_numpy(dtype=float, na_value=np.nan)
        ).all():
            raise AnalysisError(f"benchmark {name} weights must be finite")
        missing_dates = benchmark_targets.index.difference(market_returns.index)
        if len(missing_dates):
            raise ValueError(f"benchmark {name} dates must belong to the return index")
        plan = _timing_plan(
            benchmark_targets,
            cast("pd.DatetimeIndex", market_returns.index),
            benchmark_timing,
        )
        simulated = _simulate(
            benchmark_targets,
            market_returns,
            plan=plan,
            policies=policies,
            cost_rates=cost_rates,
            cash_returns=cash_returns,
            tradeable=tradeable,
            tolerance=tolerance,
        )
        result_returns[name] = simulated.returns
        result_equity[name] = simulated.returns.add(1.0).cumprod().mul(initial_equity)
    return pd.DataFrame(result_returns), pd.DataFrame(result_equity)


def _compare_benchmarks(
    strategy: pd.Series,
    benchmarks: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "count",
        "mean_return",
        "benchmark_mean_return",
        "mean_difference",
        "tracking_error",
        "win_rate",
        "correlation",
    ]
    records: list[dict[str, float]] = []
    names: list[str] = []
    for name in benchmarks.columns:
        benchmark = benchmarks[name]
        valid = strategy.notna() & benchmark.notna()
        candidate = strategy[valid]
        reference = benchmark[valid]
        difference = candidate - reference
        correlation = (
            float("nan")
            if candidate.nunique() < 2 or reference.nunique() < 2
            else float(candidate.corr(reference))
        )
        records.append(
            {
                "count": float(valid.sum()),
                "mean_return": float(candidate.mean()),
                "benchmark_mean_return": float(reference.mean()),
                "mean_difference": float(difference.mean()),
                "tracking_error": float(difference.std(ddof=1)),
                "win_rate": float((difference > 0).mean()),
                "correlation": correlation,
            }
        )
        names.append(str(name))
    result = pd.DataFrame(records, index=pd.Index(names, name="benchmark"), columns=columns)
    return result
