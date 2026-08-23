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
    BorrowPolicy,
    MarketImpactModel,
    MissingCostPolicy,
    MultiCurrencyPolicy,
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
    local_return_attribution: pd.DataFrame
    fx_return_attribution: pd.DataFrame
    cash_return_attribution: pd.Series
    cost_attribution: pd.DataFrame
    trade_cost_attribution: pd.DataFrame
    impact_cost_attribution: pd.DataFrame
    borrow_cost_attribution: pd.DataFrame
    costs: pd.Series
    trade_costs: pd.Series
    impact_costs: pd.Series
    borrow_costs: pd.Series
    borrow_events: pd.DataFrame
    blocked_assets: dict[int, tuple[object, ...]]


def backtest_portfolio(
    target_weights: PortfolioConstructionResult | pd.DataFrame,
    *,
    returns: pd.DataFrame | None = None,
    prices: pd.DataFrame | None = None,
    timing: BacktestTiming | None = None,
    policies: BacktestPolicies | None = None,
    transaction_cost_bps: float | pd.Series | pd.DataFrame = 0.0,
    buy_cost_bps: float | pd.Series | pd.DataFrame | None = None,
    sell_cost_bps: float | pd.Series | pd.DataFrame | None = None,
    missing_cost: MissingCostPolicy = "error",
    market_impact: MarketImpactModel | None = None,
    liquidity: pd.DataFrame | None = None,
    shortable: pd.DataFrame | None = None,
    borrow_rates: float | pd.Series | pd.DataFrame = 0.0,
    borrow_policy: BorrowPolicy | None = None,
    fx_rates: pd.DataFrame | None = None,
    multi_currency: MultiCurrencyPolicy | None = None,
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

    Trade costs may be scalar, asset-specific, or dated and asymmetric. Optional impact uses
    supplied liquidity, while borrow fees accrue separately on beginning short weights. Cash is
    the residual needed to make beginning weights sum to one; it can be greater than one after
    short sales or negative under net leverage. Returns, cash, holdings, and every cost component
    reconcile in the returned result.

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
    local_returns = market_returns.copy(deep=True)
    if multi_currency is None:
        if fx_rates is not None:
            raise ValueError("fx_rates require multi_currency")
        base_currency = "base"
        currencies = pd.Index([base_currency], name="currency")
        resolved_fx = pd.DataFrame(1.0, index=return_index, columns=currencies)
        fx_staleness = pd.DataFrame(0, index=return_index, columns=currencies, dtype=int)
        asset_fx_returns = pd.DataFrame(
            0.0,
            index=return_index,
            columns=market_returns.columns,
        )
    else:
        if fx_rates is None:
            raise ValueError("multi_currency requires fx_rates")
        base_currency = multi_currency.base_currency
        resolved_fx, fx_staleness = _resolved_fx_rates(
            fx_rates,
            return_index,
            market_returns.columns,
            multi_currency,
        )
        currencies = resolved_fx.columns
        asset_rates = resolved_fx.loc[:, multi_currency.asset_currencies.to_list()]
        asset_rates.columns = market_returns.columns
        asset_fx_returns = asset_rates.pct_change(fill_method=None).fillna(0.0)
        market_returns = (1.0 + local_returns) * (1.0 + asset_fx_returns) - 1.0
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
    if missing_cost not in {"error", "zero"}:
        raise ValueError("unsupported missing-cost policy")
    base_cost_rates, base_cost_coverage = _cost_rate_panel(
        transaction_cost_bps,
        return_index,
        targets.columns,
        name="transaction_cost_bps",
        missing=missing_cost,
    )
    buy_rates, buy_coverage = (
        (base_cost_rates, base_cost_coverage)
        if buy_cost_bps is None
        else _cost_rate_panel(
            buy_cost_bps,
            return_index,
            targets.columns,
            name="buy_cost_bps",
            missing=missing_cost,
        )
    )
    sell_rates, sell_coverage = (
        (base_cost_rates, base_cost_coverage)
        if sell_cost_bps is None
        else _cost_rate_panel(
            sell_cost_bps,
            return_index,
            targets.columns,
            name="sell_cost_bps",
            missing=missing_cost,
        )
    )
    impact_liquidity, liquidity_coverage = _liquidity_panel(
        liquidity,
        market_returns,
        required=market_impact is not None,
        missing=missing_cost,
    )
    effective_borrow_policy = borrow_policy or BorrowPolicy()
    borrow_rate_panel, borrow_coverage = _rate_panel(
        borrow_rates,
        return_index,
        targets.columns,
        name="borrow_rates",
        missing=effective_borrow_policy.missing_rate,
        scale=1.0,
    )
    shortable_panel = _boolean_panel(shortable, market_returns, name="shortable")
    coverage = pd.DataFrame(
        {
            "buy_cost": buy_coverage,
            "sell_cost": sell_coverage,
            "liquidity": liquidity_coverage,
            "borrow_rate": borrow_coverage,
            "shortable": np.ones(len(return_index), dtype=float),
        },
        index=return_index,
    )
    cash_path = _cash_return_path(cash_returns, return_index)
    tradeable_panel = _tradeable_panel(tradeable, market_returns)
    plan = _timing_plan(targets, return_index, effective_timing)
    simulation = _simulate(
        targets,
        market_returns,
        local_returns=local_returns.to_numpy(dtype=float, na_value=np.nan),
        fx_returns=asset_fx_returns.to_numpy(dtype=float),
        plan=plan,
        policies=effective_policies,
        buy_cost_rates=buy_rates,
        sell_cost_rates=sell_rates,
        market_impact=market_impact,
        liquidity=impact_liquidity,
        borrow_rates=borrow_rate_panel,
        shortable=shortable_panel,
        borrow_policy=effective_borrow_policy,
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
        local_returns=local_returns.to_numpy(dtype=float, na_value=np.nan),
        fx_returns=asset_fx_returns.to_numpy(dtype=float),
        timing=effective_timing,
        policies=effective_policies,
        buy_cost_rates=buy_rates,
        sell_cost_rates=sell_rates,
        market_impact=market_impact,
        liquidity=impact_liquidity,
        borrow_rates=borrow_rate_panel,
        shortable=shortable_panel,
        borrow_policy=effective_borrow_policy,
        cash_returns=cash_path,
        tradeable=tradeable_panel,
        initial_equity=equity_start,
        tolerance=numeric_tolerance,
    )
    comparison = _compare_benchmarks(net_returns, benchmark_returns)
    currency_cash = pd.DataFrame(0.0, index=return_index, columns=currencies)
    currency_cash[base_currency] = simulation.cash
    ending_currency_cash = pd.DataFrame(0.0, index=return_index, columns=currencies)
    ending_currency_cash[base_currency] = simulation.ending_cash
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
        local_return_attribution=simulation.local_return_attribution,
        fx_return_attribution=simulation.fx_return_attribution,
        cash_return_attribution=simulation.cash_return_attribution,
        currency_cash=currency_cash,
        ending_currency_cash=ending_currency_cash,
        fx_rates=resolved_fx,
        fx_staleness=fx_staleness,
        cost_attribution=simulation.cost_attribution,
        trade_cost_attribution=simulation.trade_cost_attribution,
        impact_cost_attribution=simulation.impact_cost_attribution,
        borrow_cost_attribution=simulation.borrow_cost_attribution,
        costs=simulation.costs,
        trade_costs=simulation.trade_costs,
        impact_costs=simulation.impact_costs,
        borrow_costs=simulation.borrow_costs,
        cost_input_coverage=coverage,
        borrow_events=simulation.borrow_events,
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


def _cost_rate_panel(
    costs: float | pd.Series | pd.DataFrame,
    index: pd.DatetimeIndex,
    columns: pd.Index,
    *,
    name: str,
    missing: MissingCostPolicy,
) -> tuple[np.ndarray, np.ndarray]:
    return _rate_panel(
        costs,
        index,
        columns,
        name=name,
        missing=missing,
        scale=10_000.0,
    )


def _resolved_fx_rates(
    fx_rates: pd.DataFrame,
    index: pd.DatetimeIndex,
    assets: pd.Index,
    policy: MultiCurrencyPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not fx_rates.index.equals(index):
        raise ValueError("fx_rates must use the portfolio-return index")
    if not policy.asset_currencies.index.equals(assets):
        raise ValueError("asset_currencies must use the asset columns")
    if policy.asset_currencies.isna().any() or any(
        not isinstance(value, str) or not value
        for value in policy.asset_currencies.to_list()
    ):
        raise ValueError("asset currencies must be nonempty strings")
    if fx_rates.columns.has_duplicates:
        raise ValueError("fx_rates columns must be unique currency pairs")

    pairs: list[tuple[str, str]] = []
    for raw_column in cast("list[object]", fx_rates.columns.to_list()):
        if not isinstance(raw_column, str) or raw_column.count("/") != 1:
            raise ValueError("fx_rates columns must use BASE/QUOTE currency pairs")
        column = raw_column
        source, destination = column.split("/")
        if not source or not destination or source == destination:
            raise ValueError("FX currency pairs must contain two distinct currencies")
        pairs.append((source, destination))
    values = fx_rates.to_numpy(dtype=float, na_value=np.nan)
    present = ~np.isnan(values)
    if not np.isfinite(values[present]).all():
        raise AnalysisError("fx_rates must be finite or missing")
    if (values[present] <= 0.0).any():
        raise ValueError("fx_rates must be positive")

    currencies = pd.Index(
        dict.fromkeys([policy.base_currency, *policy.asset_currencies.to_list()]),
        name="currency",
    )
    raw = np.full((len(index), len(currencies)), np.nan, dtype=float)
    base_position = currencies.get_loc(policy.base_currency)
    raw[:, base_position] = 1.0
    for row in range(len(index)):
        graph: dict[str, list[tuple[str, float]]] = {}
        for column, (source, destination) in enumerate(pairs):
            rate = values[row, column]
            if np.isnan(rate):
                continue
            graph.setdefault(source, []).append((destination, float(rate)))
            graph.setdefault(destination, []).append((source, 1.0 / float(rate)))
        for neighbours in graph.values():
            neighbours.sort(key=lambda edge: edge[0])
        for currency_position, currency in enumerate(currencies):
            if currency == policy.base_currency:
                continue
            queue: list[tuple[str, float]] = [(str(currency), 1.0)]
            visited = {str(currency)}
            for node, accumulated in queue:
                for destination, rate in graph.get(node, []):
                    if destination in visited:
                        continue
                    converted = accumulated * rate
                    if destination == policy.base_currency:
                        raw[row, currency_position] = converted
                        queue = []
                        break
                    visited.add(destination)
                    queue.append((destination, converted))
                else:
                    continue
                break

    resolved = raw.copy()
    staleness = np.zeros(raw.shape, dtype=int)
    for column, currency in enumerate(currencies):
        if currency == policy.base_currency:
            continue
        last_value = np.nan
        age = 0
        for row in range(len(index)):
            if np.isfinite(raw[row, column]):
                last_value = raw[row, column]
                age = 0
            elif policy.missing_fx == "error":
                raise AnalysisError(f"missing FX rate for {currency} on {index[row]}")
            elif not np.isfinite(last_value):
                raise AnalysisError(f"missing initial FX rate for {currency}")
            else:
                age += 1
                if age > policy.maximum_staleness:
                    raise AnalysisError(
                        f"FX rate for {currency} exceeds maximum staleness on {index[row]}"
                    )
                resolved[row, column] = last_value
                staleness[row, column] = age
    return (
        pd.DataFrame(resolved, index=index, columns=currencies),
        pd.DataFrame(staleness, index=index, columns=currencies),
    )


def _rate_panel(
    rates: float | pd.Series | pd.DataFrame,
    index: pd.DatetimeIndex,
    columns: pd.Index,
    *,
    name: str,
    missing: MissingCostPolicy,
    scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(rates, pd.DataFrame):
        if not rates.index.equals(index) or not rates.columns.equals(columns):
            raise ValueError(f"{name} must use the portfolio-return index and columns")
        values = rates.to_numpy(dtype=float, na_value=np.nan)
    elif isinstance(rates, pd.Series):
        if not rates.index.equals(columns):
            raise ValueError(f"{name} must use the asset columns")
        values = np.broadcast_to(
            rates.to_numpy(dtype=float, na_value=np.nan),
            (len(index), len(columns)),
        ).copy()
    else:
        if isinstance(rates, bool):
            raise TypeError(f"{name} must be numeric")
        values = np.full((len(index), len(columns)), float(rates), dtype=float)
    present = np.isfinite(values)
    if not present.all() and missing == "error":
        raise AnalysisError(f"{name} must be finite")
    values = np.where(present, values, 0.0)
    if (values < 0.0).any():
        raise ValueError(f"{name} must be nonnegative")
    return values / scale, present.mean(axis=1)


def _liquidity_panel(
    liquidity: pd.DataFrame | None,
    market_returns: pd.DataFrame,
    *,
    required: bool,
    missing: MissingCostPolicy,
) -> tuple[np.ndarray, np.ndarray]:
    if liquidity is None:
        if required:
            raise ValueError("market impact requires liquidity")
        return (
            np.ones(market_returns.shape, dtype=float),
            np.full(len(market_returns.index), np.nan, dtype=float),
        )
    values, coverage = _rate_panel(
        liquidity,
        cast("pd.DatetimeIndex", market_returns.index),
        market_returns.columns,
        name="liquidity",
        missing=missing,
        scale=1.0,
    )
    return values, coverage


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


def _boolean_panel(
    values: pd.DataFrame | None,
    market_returns: pd.DataFrame,
    *,
    name: str,
) -> np.ndarray:
    if values is None:
        return np.ones(market_returns.shape, dtype=bool)
    if not values.index.equals(market_returns.index) or not values.columns.equals(
        market_returns.columns
    ):
        raise ValueError(f"{name} must use the portfolio-return index and columns")
    if any(not pd.api.types.is_bool_dtype(dtype) for dtype in values.dtypes):
        raise TypeError(f"{name} columns must be boolean")
    if values.isna().any(axis=None):
        raise ValueError(f"{name} must not contain missing values")
    return values.to_numpy(dtype=bool)


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
    local_returns: np.ndarray,
    fx_returns: np.ndarray,
    plan: _TimingPlan,
    policies: BacktestPolicies,
    buy_cost_rates: np.ndarray,
    sell_cost_rates: np.ndarray,
    market_impact: MarketImpactModel | None,
    liquidity: np.ndarray,
    borrow_rates: np.ndarray,
    shortable: np.ndarray,
    borrow_policy: BorrowPolicy,
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
    local_attribution = np.zeros((rows, assets), dtype=float)
    fx_attribution = np.zeros((rows, assets), dtype=float)
    cash_attribution = np.zeros(rows, dtype=float)
    cost_attribution = np.zeros((rows, assets), dtype=float)
    trade_cost_attribution = np.zeros((rows, assets), dtype=float)
    impact_cost_attribution = np.zeros((rows, assets), dtype=float)
    borrow_cost_attribution = np.zeros((rows, assets), dtype=float)
    total_costs = np.zeros(rows, dtype=float)
    total_trade_costs = np.zeros(rows, dtype=float)
    total_impact_costs = np.zeros(rows, dtype=float)
    total_borrow_costs = np.zeros(rows, dtype=float)
    exposure_rows: list[dict[str, float]] = []
    blocked_assets: dict[int, tuple[object, ...]] = {}
    borrow_event_rows: list[dict[str, object]] = []
    previous_weights = np.zeros(assets, dtype=float)
    previous_cash = 1.0
    return_values = market_returns.to_numpy(dtype=float, na_value=np.nan)

    for position in range(rows):
        beginning = previous_weights.copy()
        beginning_cash = previous_cash
        desired = previous_weights.copy()
        event_row = plan.event_rows.get(position)
        if position in plan.events:
            desired = plan.events[position].copy()
        unavailable = (~shortable[position]) & (desired < -tolerance)
        forced_cover = unavailable & (previous_weights < -tolerance)
        if unavailable.any():
            labels = tuple(
                cast("object", targets.columns[int(asset)])
                for asset in np.flatnonzero(unavailable)
            )
            if borrow_policy.unavailable == "error":
                raise AnalysisError(
                    f"unavailable shorts on {market_returns.index[position]}: "
                    + ", ".join(map(str, labels))
                )
            for asset in np.flatnonzero(unavailable):
                borrow_event_rows.append(
                    {
                        "date": market_returns.index[position],
                        "asset": targets.columns[int(asset)],
                        "action": (
                            "forced_cover" if forced_cover[int(asset)] else "blocked_target"
                        ),
                        "previous_weight": float(previous_weights[int(asset)]),
                        "requested_weight": float(desired[int(asset)]),
                        "realized_weight": 0.0,
                    }
                )
            desired[unavailable] = 0.0
            if event_row is not None:
                blocked_assets[event_row] = labels
        if position in plan.events or unavailable.any():
            blocked = (
                (~tradeable[position])
                & (~forced_cover)
                & (np.abs(desired - previous_weights) > tolerance)
            )
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
                if event_row is not None:
                    existing = blocked_assets.get(event_row, ())
                    blocked_assets[event_row] = tuple(dict.fromkeys((*existing, *labels)))
            beginning = desired
            beginning_cash = 1.0 - float(beginning.sum())

        delta = beginning - previous_weights
        delta_cash = beginning_cash - previous_cash
        trade_asset_costs = (
            np.maximum(delta, 0.0) * buy_cost_rates[position]
            + np.maximum(-delta, 0.0) * sell_cost_rates[position]
        )
        impact_asset_costs = _impact_costs(
            delta,
            liquidity[position],
            market_impact,
            date=market_returns.index[position],
            columns=market_returns.columns,
            tolerance=tolerance,
        )
        borrow_asset_costs = np.maximum(-beginning, 0.0) * borrow_rates[position]
        asset_costs = trade_asset_costs + impact_asset_costs + borrow_asset_costs
        period_trade_cost = float(trade_asset_costs.sum())
        period_impact_cost = float(impact_asset_costs.sum())
        period_borrow_cost = float(borrow_asset_costs.sum())
        period_cost = period_trade_cost + period_impact_cost + period_borrow_cost
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
        period_local_returns = local_returns[position].copy()
        period_local_returns[np.isnan(period_local_returns)] = 0.0
        local_contributions = beginning * period_local_returns
        fx_contributions = beginning * (1.0 + period_local_returns) * fx_returns[position]
        asset_contributions = local_contributions + fx_contributions
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
        local_attribution[position] = local_contributions
        fx_attribution[position] = fx_contributions
        cash_attribution[position] = cash_contribution
        cost_attribution[position] = asset_costs
        trade_cost_attribution[position] = trade_asset_costs
        impact_cost_attribution[position] = impact_asset_costs
        borrow_cost_attribution[position] = borrow_asset_costs
        total_costs[position] = period_cost
        total_trade_costs[position] = period_trade_cost
        total_impact_costs[position] = period_impact_cost
        total_borrow_costs[position] = period_borrow_cost
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
        local_return_attribution=pd.DataFrame(
            local_attribution, index=index, columns=columns
        ),
        fx_return_attribution=pd.DataFrame(fx_attribution, index=index, columns=columns),
        cash_return_attribution=pd.Series(
            cash_attribution,
            index=index,
            name="cash_return_attribution",
            dtype=float,
        ),
        cost_attribution=pd.DataFrame(cost_attribution, index=index, columns=columns),
        trade_cost_attribution=pd.DataFrame(
            trade_cost_attribution, index=index, columns=columns
        ),
        impact_cost_attribution=pd.DataFrame(
            impact_cost_attribution, index=index, columns=columns
        ),
        borrow_cost_attribution=pd.DataFrame(
            borrow_cost_attribution, index=index, columns=columns
        ),
        costs=pd.Series(total_costs, index=index, name="cost", dtype=float),
        trade_costs=pd.Series(total_trade_costs, index=index, name="trade_cost", dtype=float),
        impact_costs=pd.Series(
            total_impact_costs, index=index, name="impact_cost", dtype=float
        ),
        borrow_costs=pd.Series(
            total_borrow_costs, index=index, name="borrow_cost", dtype=float
        ),
        borrow_events=pd.DataFrame(
            borrow_event_rows,
            columns=[
                "date",
                "asset",
                "action",
                "previous_weight",
                "requested_weight",
                "realized_weight",
            ],
        ),
        blocked_assets=blocked_assets,
    )


def _impact_costs(
    trades: np.ndarray,
    liquidity: np.ndarray,
    model: MarketImpactModel | None,
    *,
    date: object,
    columns: pd.Index,
    tolerance: float,
) -> np.ndarray:
    if model is None or model.coefficient_bps == 0.0:
        return np.zeros_like(trades)
    active = np.abs(trades) > tolerance
    unavailable = active & (liquidity <= 0.0)
    if unavailable.any():
        labels = ", ".join(
            str(columns[int(position)]) for position in np.flatnonzero(unavailable)
        )
        raise AnalysisError(f"market impact has zero liquidity on {date}: {labels}")
    participation = np.zeros_like(trades)
    participation[active] = np.abs(trades[active]) / liquidity[active]
    return (
        (model.coefficient_bps / 10_000.0)
        * np.abs(trades)
        * np.power(participation, model.exponent)
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
    local_returns: np.ndarray,
    fx_returns: np.ndarray,
    timing: BacktestTiming,
    policies: BacktestPolicies,
    buy_cost_rates: np.ndarray,
    sell_cost_rates: np.ndarray,
    market_impact: MarketImpactModel | None,
    liquidity: np.ndarray,
    borrow_rates: np.ndarray,
    shortable: np.ndarray,
    borrow_policy: BorrowPolicy,
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
            local_returns=local_returns,
            fx_returns=fx_returns,
            plan=plan,
            policies=policies,
            buy_cost_rates=buy_cost_rates,
            sell_cost_rates=sell_cost_rates,
            market_impact=market_impact,
            liquidity=liquidity,
            borrow_rates=borrow_rates,
            shortable=shortable,
            borrow_policy=borrow_policy,
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
