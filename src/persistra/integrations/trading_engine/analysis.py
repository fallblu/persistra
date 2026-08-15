"""Analyze deterministic Trading Engine replay results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from persistra.integrations.trading_engine import ExecutionReplayResult
    from persistra.portfolio import BacktestResult

type InitialEquitySource = Literal["scenario_initial_cash", "first_valuation"]
type TurnoverDenominator = Literal["average_equity", "initial_equity"]


@dataclass(frozen=True, slots=True)
class ExecutionAnalysisPolicy:
    """Explicit return, annualization, turnover, and price-reference policies."""

    periods_per_year: float | None = None
    annual_risk_free_rate: float = 0.0
    annual_downside_target: float = 0.0
    initial_equity: InitialEquitySource | float = "scenario_initial_cash"
    turnover_denominator: TurnoverDenominator = "average_equity"
    decision_price_reference: Literal["decision_slice_close"] = "decision_slice_close"
    eligible_price_reference: Literal["fill_slice_open"] = "fill_slice_open"

    def __post_init__(self) -> None:
        if self.periods_per_year is not None:
            _positive_finite(self.periods_per_year, name="periods_per_year")
        _finite(self.annual_risk_free_rate, name="annual_risk_free_rate")
        _finite(self.annual_downside_target, name="annual_downside_target")
        if self.periods_per_year is None and (
            self.annual_risk_free_rate != 0.0 or self.annual_downside_target != 0.0
        ):
            raise ValueError("annual rates require periods_per_year")
        if isinstance(self.initial_equity, str):
            if self.initial_equity not in {"scenario_initial_cash", "first_valuation"}:
                raise ValueError("unsupported initial_equity policy")
        else:
            _positive_finite(self.initial_equity, name="initial_equity")
        if self.turnover_denominator not in {"average_equity", "initial_equity"}:
            raise ValueError("unsupported turnover denominator")
        if self.decision_price_reference != "decision_slice_close":
            raise ValueError("unsupported decision price reference")
        if self.eligible_price_reference != "fill_slice_open":
            raise ValueError("unsupported eligible price reference")


@dataclass(frozen=True, slots=True)
class ExecutionAnalysisResult:
    """Order, fill, lifecycle, and event-time performance diagnostics."""

    order_diagnostics: pd.DataFrame
    fill_diagnostics: pd.DataFrame
    lifecycle_summary: pd.DataFrame
    performance_path: pd.DataFrame
    performance_summary: pd.DataFrame
    policy: ExecutionAnalysisPolicy

    def __post_init__(self) -> None:
        for name in (
            "order_diagnostics",
            "fill_diagnostics",
            "lifecycle_summary",
            "performance_path",
            "performance_summary",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))


@dataclass(frozen=True, slots=True)
class ExecutionComparisonPolicy:
    """Explicit terminal alignment and P&L bridge definitions."""

    vectorized_return_basis: Literal["persistra_close_to_close"] = "persistra_close_to_close"
    engine_execution_basis: Literal["trading_engine_slice_execution"] = (
        "trading_engine_slice_execution"
    )
    alignment: Literal["terminal_observation"] = "terminal_observation"
    vectorized_equity_scale: Literal["engine_initial_equity"] = "engine_initial_equity"
    residual_method: Literal["balancing_component"] = "balancing_component"

    def __post_init__(self) -> None:
        if self.vectorized_return_basis != "persistra_close_to_close":
            raise ValueError("unsupported vectorized return basis")
        if self.engine_execution_basis != "trading_engine_slice_execution":
            raise ValueError("unsupported engine execution basis")
        if self.alignment != "terminal_observation":
            raise ValueError("unsupported comparison alignment")
        if self.vectorized_equity_scale != "engine_initial_equity":
            raise ValueError("unsupported vectorized equity scale")
        if self.residual_method != "balancing_component":
            raise ValueError("unsupported residual method")


@dataclass(frozen=True, slots=True)
class ExecutionComparisonResult:
    """Terminal comparison and an additive currency P&L implementation bridge."""

    terminal_summary: pd.DataFrame
    pnl_bridge: pd.DataFrame
    policy: ExecutionComparisonPolicy
    caveat: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "terminal_summary", self.terminal_summary.copy(deep=True))
        object.__setattr__(self, "pnl_bridge", self.pnl_bridge.copy(deep=True))


def analyze_execution(
    replay: ExecutionReplayResult,
    *,
    policy: ExecutionAnalysisPolicy | None = None,
) -> ExecutionAnalysisResult:
    """Analyze imported orders, fills, and valuation events under explicit policies.

    Returns are changes between consecutive valuation events. These events need not be equally
    spaced and a multi-instrument replay can produce more than one valuation at one timestamp.
    Annualized statistics therefore remain undefined unless ``periods_per_year`` is supplied.

    Positive slippage values are adverse for both buys and sells. Decision-close slippage is
    separated into the move from decision close to the fill slice open and the move from that open
    to the actual fill price. References are missing when the journal does not contain the linked
    bar; the summary reports only observed-reference slippage in that case.
    """
    resolved = policy or ExecutionAnalysisPolicy()
    fills = _fill_diagnostics(replay)
    orders = _order_diagnostics(replay, fills)
    lifecycle = _lifecycle_summary(replay, orders, fills)
    performance, summary = _performance(replay, fills, policy=resolved)
    return ExecutionAnalysisResult(
        order_diagnostics=orders,
        fill_diagnostics=fills,
        lifecycle_summary=lifecycle,
        performance_path=performance,
        performance_summary=summary,
        policy=resolved,
    )


def compare_execution(
    vectorized: BacktestResult,
    execution: ExecutionAnalysisResult,
    *,
    policy: ExecutionComparisonPolicy | None = None,
) -> ExecutionComparisonResult:
    """Compare terminal equity and build an additive currency P&L bridge.

    Persistra's price-input backtest uses close-to-close returns. Trading Engine market orders
    fill on the next eligible slice open, while limit orders follow its slice execution rules. The
    bridge measures observed fill-price effects but assigns all remaining differences to a
    balancing residual. It does not describe that residual as slippage.
    """
    resolved = policy or ExecutionComparisonPolicy()
    if vectorized.equity.empty:
        raise ValueError("vectorized backtest must contain an equity path")
    engine_row = execution.performance_summary.loc[["engine"]]
    engine_initial = float(_numeric(engine_row, "initial_equity").to_numpy(dtype=float)[0])
    engine_terminal = float(_numeric(engine_row, "terminal_equity").to_numpy(dtype=float)[0])
    engine_pnl = engine_terminal - engine_initial
    vectorized_growth = float(vectorized.equity.iloc[-1]) / float(vectorized.initial_equity)
    vectorized_terminal = engine_initial * vectorized_growth
    vectorized_pnl = vectorized_terminal - engine_initial

    fills = execution.fill_diagnostics
    decision_to_fill_slice_open_cost = _observed_sum(
        fills, "decision_to_fill_slice_open_adverse_cost"
    )
    open_fill_cost = _observed_sum(fills, "eligible_open_adverse_cost")
    fees = _observed_sum(fills, "fee")
    decision_to_fill_slice_open_impact = -decision_to_fill_slice_open_cost
    open_fill_impact = -open_fill_cost
    fee_impact = -fees
    residual = engine_pnl - (
        vectorized_pnl + decision_to_fill_slice_open_impact + open_fill_impact + fee_impact
    )

    decision_to_fill_slice_open_coverage = _coverage(
        fills, "decision_to_fill_slice_open_adverse_cost"
    )
    open_fill_coverage = _coverage(fills, "eligible_open_adverse_cost")
    bridge = pd.DataFrame.from_records(
        [
            {
                "component": "vectorized_close_to_close_research_pnl",
                "pnl": vectorized_pnl,
                "evidence": "exact",
                "coverage": 1.0,
                "description": "Persistra terminal P&L scaled to engine initial equity.",
            },
            {
                "component": "decision_to_fill_slice_open_timing",
                "pnl": decision_to_fill_slice_open_impact,
                "evidence": "fill_based_estimate",
                "coverage": decision_to_fill_slice_open_coverage,
                "description": "Filled quantity times decision close-to-fill-slice-open move.",
            },
            {
                "component": "eligible_open_fill_price",
                "pnl": open_fill_impact,
                "evidence": "fill_based_estimate",
                "coverage": open_fill_coverage,
                "description": "Filled quantity times fill-slice-open-to-fill-price move.",
            },
            {
                "component": "engine_fees",
                "pnl": fee_impact,
                "evidence": "exact",
                "coverage": 1.0,
                "description": "Fees reported by imported fill events.",
            },
            {
                "component": "unfilled_exposure_and_model_residual",
                "pnl": residual,
                "evidence": "balancing_component",
                "coverage": 1.0,
                "description": (
                    "Partial fills and residual cash plus sizing, valuation-grid, marking, "
                    "and cost-model differences."
                ),
            },
        ]
    ).set_index("component")
    if not np.isclose(float(bridge["pnl"].sum()), engine_pnl, rtol=1e-12, atol=1e-9):
        raise AssertionError("implementation bridge must reconcile to engine P&L")

    vectorized_return = vectorized_growth - 1.0
    engine_return = engine_terminal / engine_initial - 1.0
    terminal = pd.DataFrame.from_records(
        [
            {
                "model": "vectorized_close_to_close",
                "initial_equity": engine_initial,
                "terminal_equity": vectorized_terminal,
                "pnl": vectorized_pnl,
                "total_return": vectorized_return,
            },
            {
                "model": "engine_event_driven",
                "initial_equity": engine_initial,
                "terminal_equity": engine_terminal,
                "pnl": engine_pnl,
                "total_return": engine_return,
            },
            {
                "model": "engine_minus_vectorized",
                "initial_equity": 0.0,
                "terminal_equity": engine_terminal - vectorized_terminal,
                "pnl": engine_pnl - vectorized_pnl,
                "total_return": engine_return - vectorized_return,
            },
        ]
    ).set_index("model")
    caveat = (
        "Persistra is close-to-close while Trading Engine applies next-eligible-slice execution "
        "rules. The residual balances partial execution and residual cash together with sizing, "
        "valuation-grid, marking, and cost-model differences; it is not pure slippage."
    )
    return ExecutionComparisonResult(terminal, bridge, resolved, caveat)


def _fill_diagnostics(replay: ExecutionReplayResult) -> pd.DataFrame:
    fills = replay.fills.copy(deep=True)
    orders = replay.orders.copy(deep=True)
    bars = replay.bars.copy(deep=True)
    _require_columns(
        fills,
        name="fills",
        columns={
            "fill_id",
            "order_id",
            "instrument_id",
            "side",
            "quantity",
            "price",
            "notional",
            "fee",
            "slice_sequence",
        },
    )
    _require_columns(
        orders,
        name="orders",
        columns={"order_id", "instrument_id", "eligible_after_slice_sequence"},
    )
    _require_columns(
        bars,
        name="bars",
        columns={"slice_sequence", "instrument_id", "open", "close", "volume"},
    )
    if orders["order_id"].duplicated().any():
        raise ValueError("orders must contain one submission event per order_id")
    if bars.duplicated(["instrument_id", "slice_sequence"]).any():
        raise ValueError("bars must contain unique instrument and slice sequence keys")

    order_rows = {str(row["order_id"]): row for _, row in orders.iterrows()}
    bar_rows = {
        (str(row["instrument_id"]), int(row["slice_sequence"])): row for _, row in bars.iterrows()
    }
    instrument_bars = _instrument_bars(bars)
    order_for_fill: list[pd.Series] = []
    for order_id in fills["order_id"]:
        order = order_rows.get(str(order_id))
        if order is None:
            raise ValueError(f"fill refers to unknown order_id {order_id}")
        order_for_fill.append(order)

    decision_anchors = [int(row["eligible_after_slice_sequence"]) for row in order_for_fill]
    decision_sequences: list[int | None] = []
    decision_closes: list[float] = []
    eligible_opens: list[float] = []
    bar_volumes: list[float] = []
    for (_, fill), decision_anchor in zip(fills.iterrows(), decision_anchors, strict=True):
        instrument = str(fill["instrument_id"])
        decision_bar = _latest_bar(instrument_bars.get(instrument, []), decision_anchor)
        fill_bar = bar_rows.get((instrument, int(fill["slice_sequence"])))
        decision_sequences.append(
            None if decision_bar is None else int(decision_bar["slice_sequence"])
        )
        decision_closes.append(_optional_number(decision_bar, "close"))
        eligible_opens.append(_optional_number(fill_bar, "open"))
        bar_volumes.append(_optional_number(fill_bar, "volume"))

    quantity = _numeric(fills, "quantity")
    price = _numeric(fills, "price")
    side = fills["side"].astype("string")
    if not side.isin(["buy", "sell"]).all():
        raise ValueError("fill side must be buy or sell")
    sign = side.map({"buy": 1.0, "sell": -1.0}).astype(float)
    decision_close = pd.Series(decision_closes, index=fills.index, dtype=float)
    eligible_open = pd.Series(eligible_opens, index=fills.index, dtype=float)
    fill_volume = pd.Series(bar_volumes, index=fills.index, dtype=float)

    fills["decision_anchor_sequence"] = pd.array(decision_anchors, dtype="Int64")
    fills["decision_slice_sequence"] = pd.array(decision_sequences, dtype="Int64")
    fills["decision_close"] = decision_close
    fills["eligible_open"] = eligible_open
    fills["decision_close_adverse_cost"] = sign * (price - decision_close) * quantity
    fills["decision_to_fill_slice_open_adverse_cost"] = (
        sign * (eligible_open - decision_close) * quantity
    )
    fills["eligible_open_adverse_cost"] = sign * (price - eligible_open) * quantity
    fills["decision_close_slippage_bps"] = _slippage_bps(
        fills["decision_close_adverse_cost"], quantity, decision_close
    )
    fills["decision_to_fill_slice_open_slippage_bps"] = _slippage_bps(
        fills["decision_to_fill_slice_open_adverse_cost"], quantity, decision_close
    )
    fills["eligible_open_slippage_bps"] = _slippage_bps(
        fills["eligible_open_adverse_cost"], quantity, eligible_open
    )
    fills["implementation_shortfall"] = fills["decision_close_adverse_cost"].add(
        _numeric(fills, "fee")
    )
    fills["bar_volume"] = fill_volume
    total_on_slice = quantity.groupby([fills["instrument_id"], fills["slice_sequence"]]).transform(
        "sum"
    )
    fills["slice_filled_quantity"] = total_on_slice
    fills["slice_volume_participation"] = total_on_slice.div(fill_volume.where(fill_volume > 0))
    return fills


def _order_diagnostics(replay: ExecutionReplayResult, fills: pd.DataFrame) -> pd.DataFrame:
    orders = replay.orders.copy(deep=True)
    cancellations = replay.cancellations.copy(deep=True)
    bars = replay.bars.copy(deep=True)
    _require_columns(
        orders,
        name="orders",
        columns={
            "order_id",
            "instrument_id",
            "quantity",
            "eligible_after_slice_sequence",
            "status",
        },
    )
    _require_columns(cancellations, name="cancellations", columns={"order_id", "reason"})
    if orders["order_id"].duplicated().any():
        raise ValueError("orders must contain one submission event per order_id")
    if cancellations["order_id"].duplicated().any():
        raise ValueError("cancellations must contain at most one event per order_id")

    diagnostics = orders.set_index("order_id", drop=False)
    if "event_type" in diagnostics:
        accepted = diagnostics["event_type"].eq("order_accepted")
        rejected = diagnostics["event_type"].eq("order_rejected")
        if not accepted.ne(rejected).all():
            raise ValueError("order event_type must be order_accepted or order_rejected")
    else:
        rejected = diagnostics["status"].eq("rejected")
        accepted = ~rejected
    diagnostics["accepted"] = accepted.astype(bool)
    diagnostics["rejected"] = rejected.astype(bool)
    diagnostics["requested_quantity"] = _numeric(diagnostics, "quantity")

    filled_quantity = fills.groupby("order_id", sort=False)["quantity"].sum()
    filled_notional = fills.groupby("order_id", sort=False)["notional"].sum()
    total_fee = fills.groupby("order_id", sort=False)["fee"].sum()
    fill_count = fills.groupby("order_id", sort=False).size()
    first_fill_sequence = fills.groupby("order_id", sort=False)["slice_sequence"].min()
    filled_quantity_by_order = {str(key): float(value) for key, value in filled_quantity.items()}
    filled_notional_by_order = {str(key): float(value) for key, value in filled_notional.items()}
    total_fee_by_order = {str(key): float(value) for key, value in total_fee.items()}
    fill_count_by_order = {str(key): int(value) for key, value in fill_count.items()}
    first_fill_by_order = {str(key): int(value) for key, value in first_fill_sequence.items()}
    order_ids = [str(value) for value in diagnostics.index]
    diagnostics["filled_quantity"] = [
        filled_quantity_by_order.get(order_id, 0.0) for order_id in order_ids
    ]
    diagnostics["filled_notional"] = [
        filled_notional_by_order.get(order_id, 0.0) for order_id in order_ids
    ]
    diagnostics["total_fee"] = [total_fee_by_order.get(order_id, 0.0) for order_id in order_ids]
    diagnostics["fill_count"] = [fill_count_by_order.get(order_id, 0) for order_id in order_ids]
    diagnostics["first_fill_slice_sequence"] = pd.Series(
        [first_fill_by_order.get(order_id) for order_id in order_ids],
        index=diagnostics.index,
        dtype="Int64",
    )
    diagnostics["unfilled_quantity"] = diagnostics["requested_quantity"].sub(
        diagnostics["filled_quantity"]
    )
    diagnostics["quantity_fill_rate"] = diagnostics["filled_quantity"].div(
        diagnostics["requested_quantity"].where(diagnostics["accepted"])
    )
    diagnostics["average_fill_price"] = diagnostics["filled_notional"].div(
        diagnostics["filled_quantity"].where(diagnostics["filled_quantity"] > 0)
    )

    cancellation_reason = {
        str(row["order_id"]): str(row["reason"]) for _, row in cancellations.iterrows()
    }
    diagnostics["cancellation_reason"] = pd.Series(
        [cancellation_reason.get(order_id) for order_id in order_ids],
        index=diagnostics.index,
        dtype="string",
    )
    diagnostics["cancelled"] = diagnostics["cancellation_reason"].notna()
    diagnostics["final_status"] = [_final_order_status(row) for _, row in diagnostics.iterrows()]

    slice_ordinals: dict[tuple[str, int], int] = {}
    instrument_sequences: dict[str, list[int]] = {}
    for instrument, group in bars.sort_values("slice_sequence", kind="stable").groupby(
        "instrument_id", sort=False
    ):
        sequences = [int(value) for value in group["slice_sequence"]]
        instrument_sequences[str(instrument)] = sequences
        for ordinal, sequence in enumerate(sequences):
            slice_ordinals[(str(instrument), sequence)] = ordinal
    slices_to_fill: list[float] = []
    for _, row in diagnostics.iterrows():
        first_fill = row["first_fill_slice_sequence"]
        if pd.isna(first_fill):
            slices_to_fill.append(np.nan)
            continue
        instrument = str(row["instrument_id"])
        decision_sequence = _latest_sequence(
            instrument_sequences.get(instrument, []),
            int(row["eligible_after_slice_sequence"]),
        )
        decision_key = None if decision_sequence is None else (instrument, decision_sequence)
        fill_key = (instrument, int(first_fill))
        decision_ordinal = None if decision_key is None else slice_ordinals.get(decision_key)
        fill_ordinal = slice_ordinals.get(fill_key)
        slices_to_fill.append(
            np.nan
            if decision_ordinal is None or fill_ordinal is None
            else float(fill_ordinal - decision_ordinal)
        )
    diagnostics["slices_to_first_fill"] = slices_to_fill

    decision_cost = fills.groupby("order_id", sort=False)["decision_close_adverse_cost"].sum(
        min_count=1
    )
    decision_cost_by_order = {str(key): float(value) for key, value in decision_cost.items()}
    diagnostics["decision_close_adverse_cost"] = [
        decision_cost_by_order.get(order_id, np.nan) for order_id in order_ids
    ]
    diagnostics["implementation_shortfall"] = diagnostics["decision_close_adverse_cost"].add(
        diagnostics["total_fee"]
    )
    return diagnostics.reset_index(drop=True)


def _lifecycle_summary(
    replay: ExecutionReplayResult,
    orders: pd.DataFrame,
    fills: pd.DataFrame,
) -> pd.DataFrame:
    accepted = orders["accepted"]
    rejected = orders["rejected"]
    accepted_count = int(accepted.sum())
    rejected_count = int(rejected.sum())
    submitted_count = accepted_count + rejected_count
    filled_order = accepted & orders["filled_quantity"].gt(0)
    completely_filled = accepted & orders["unfilled_quantity"].eq(0)
    cancelled = accepted & orders["cancelled"]
    accepted_quantity = float(orders.loc[accepted, "requested_quantity"].sum())
    filled_quantity = float(orders.loc[accepted, "filled_quantity"].sum())
    rejections = replay.rejections
    intent_rejections = 0
    if len(rejections):
        if "event_type" in rejections:
            intent_rejections = int(rejections["event_type"].eq("intent_rejected").sum())
        elif "order_id" not in rejections:
            intent_rejections = len(rejections)
    reference_notional = _reference_notional(fills, "decision_close")
    eligible_notional = _reference_notional(fills, "eligible_open")
    record = {
        "submitted_orders": submitted_count,
        "accepted_orders": accepted_count,
        "rejected_orders": rejected_count,
        "intent_rejections": intent_rejections,
        "cancelled_orders": int(cancelled.sum()),
        "orders_with_fills": int(filled_order.sum()),
        "completely_filled_orders": int(completely_filled.sum()),
        "fill_events": len(fills),
        "acceptance_rate": _ratio(accepted_count, submitted_count),
        "rejection_rate": _ratio(rejected_count, submitted_count),
        "cancellation_rate": _ratio(int(cancelled.sum()), accepted_count),
        "order_fill_rate": _ratio(int(filled_order.sum()), accepted_count),
        "complete_fill_rate": _ratio(int(completely_filled.sum()), accepted_count),
        "accepted_quantity": accepted_quantity,
        "filled_quantity": filled_quantity,
        "quantity_fill_rate": _ratio(filled_quantity, accepted_quantity),
        "filled_notional": _observed_sum(fills, "notional"),
        "total_fees": _observed_sum(fills, "fee"),
        "decision_close_slippage_bps": _ratio(
            _observed_sum(fills, "decision_close_adverse_cost") * 10_000,
            reference_notional,
        ),
        "eligible_open_slippage_bps": _ratio(
            _observed_sum(fills, "eligible_open_adverse_cost") * 10_000,
            eligible_notional,
        ),
        "mean_slices_to_first_fill": float(orders["slices_to_first_fill"].mean()),
        "median_slices_to_first_fill": float(orders["slices_to_first_fill"].median()),
    }
    return pd.DataFrame([record], index=pd.Index(["engine"], name="scope"))


def _performance(
    replay: ExecutionReplayResult,
    fills: pd.DataFrame,
    *,
    policy: ExecutionAnalysisPolicy,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    valuations = replay.valuations.copy(deep=True)
    _require_columns(
        valuations,
        name="valuations",
        columns={"engine_sequence", "recorded_at", "equity", "total_fees"},
    )
    if valuations.empty:
        raise ValueError("valuations must contain at least one event")
    valuations = valuations.sort_values("engine_sequence", kind="stable").reset_index(drop=True)
    equity = _numeric(valuations, "equity")
    initial_equity = _initial_equity(replay, equity, policy=policy)
    previous = equity.shift(1)
    returns = equity.div(previous.where(previous.ne(0))).sub(1.0)
    if policy.initial_equity != "first_valuation":
        returns.iloc[0] = equity.iloc[0] / initial_equity - 1.0
    running_peak = pd.Series(
        np.maximum.accumulate(np.concatenate(([initial_equity], equity.to_numpy(dtype=float))))[1:],
        index=equity.index,
    )
    drawdown = equity.div(running_peak).sub(1.0)
    path = valuations.copy(deep=True)
    path["return"] = returns
    path["drawdown"] = drawdown

    observed_returns = returns.dropna()
    return_count = len(observed_returns)
    terminal_equity = float(equity.iloc[-1])
    total_return = terminal_equity / initial_equity - 1.0
    annual_return = np.nan
    annual_volatility = np.nan
    sharpe = np.nan
    sortino = np.nan
    if policy.periods_per_year is not None:
        scale = policy.periods_per_year
        if return_count > 0 and terminal_equity > 0:
            annual_return = (terminal_equity / initial_equity) ** (scale / return_count) - 1.0
        if return_count >= 2:
            standard_deviation = float(observed_returns.std(ddof=1))
            annual_volatility = standard_deviation * np.sqrt(scale)
            annual_mean = float(observed_returns.mean()) * scale
            if annual_volatility > 0:
                sharpe = (annual_mean - policy.annual_risk_free_rate) / annual_volatility
            period_target = policy.annual_downside_target / scale
            downside = np.minimum(observed_returns.to_numpy(dtype=float) - period_target, 0.0)
            downside_deviation = float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(scale))
            if downside_deviation > 0:
                sortino = (annual_mean - policy.annual_downside_target) / downside_deviation

    executed_notional = _observed_sum(fills, "notional")
    denominator = (
        float(equity.mean()) if policy.turnover_denominator == "average_equity" else initial_equity
    )
    executed_notional_turnover = executed_notional / denominator if denominator > 0 else np.nan
    fill_fees = _observed_sum(fills, "fee")
    reported_fees = float(_numeric(valuations, "total_fees").iloc[-1])
    record = {
        "valuation_observations": len(valuations),
        "return_observations": return_count,
        "initial_equity": initial_equity,
        "terminal_equity": terminal_equity,
        "net_pnl": terminal_equity - initial_equity,
        "total_return": total_return,
        "annualized_return": annual_return,
        "annualized_volatility": annual_volatility,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_duration_observations": _maximum_drawdown_duration(drawdown),
        "executed_notional": executed_notional,
        "executed_notional_turnover": executed_notional_turnover,
        "total_fees": fill_fees,
        "fee_return_drag": fill_fees / initial_equity,
        "reported_total_fees": reported_fees,
        "fee_reconciliation_difference": reported_fees - fill_fees,
    }
    summary = pd.DataFrame([record], index=pd.Index(["engine"], name="model"))
    return path, summary


def _initial_equity(
    replay: ExecutionReplayResult,
    equity: pd.Series,
    *,
    policy: ExecutionAnalysisPolicy,
) -> float:
    source = policy.initial_equity
    if source == "scenario_initial_cash":
        if replay.initial_cash is None:
            raise ValueError(
                "scenario initial cash is unavailable; choose first_valuation or a numeric value"
            )
        value = float(replay.initial_cash)
    elif source == "first_valuation":
        value = float(equity.iloc[0])
    else:
        value = float(source)
    _positive_finite(value, name="resolved initial equity")
    return value


def _final_order_status(row: pd.Series) -> str:
    if bool(row["rejected"]):
        return "rejected"
    if bool(row["cancelled"]):
        return "cancelled"
    if float(row["unfilled_quantity"]) == 0:
        return "filled"
    if float(row["filled_quantity"]) > 0:
        return "partially_filled"
    return "working"


def _slippage_bps(cost: pd.Series, quantity: pd.Series, reference: pd.Series) -> pd.Series:
    denominator = quantity.mul(reference).where(reference.gt(0))
    return cost.div(denominator).mul(10_000)


def _reference_notional(frame: pd.DataFrame, reference: str) -> float:
    if frame.empty:
        return 0.0
    values = _numeric(frame, reference)
    quantity = _numeric(frame, "quantity")
    observed = values.notna()
    return float(values[observed].mul(quantity[observed]).sum())


def _coverage(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].notna().mean()) if len(frame) else np.nan


def _observed_sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty:
        return 0.0
    return float(_numeric(frame, column).sum())


def _maximum_drawdown_duration(drawdown: pd.Series) -> int:
    maximum = 0
    current = 0
    for value in drawdown:
        if value < 0:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _optional_number(row: pd.Series | None, column: str) -> float:
    if row is None or pd.isna(row[column]):
        return np.nan
    return float(row[column])


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="raise").astype(float)


def _instrument_bars(bars: pd.DataFrame) -> dict[str, list[pd.Series]]:
    grouped: dict[str, list[pd.Series]] = {}
    for _, row in bars.sort_values("slice_sequence", kind="stable").iterrows():
        grouped.setdefault(str(row["instrument_id"]), []).append(row)
    return grouped


def _latest_bar(rows: list[pd.Series], anchor: int) -> pd.Series | None:
    applicable = [row for row in rows if int(row["slice_sequence"]) <= anchor]
    return applicable[-1] if applicable else None


def _latest_sequence(sequences: list[int], anchor: int) -> int | None:
    applicable = [sequence for sequence in sequences if sequence <= anchor]
    return applicable[-1] if applicable else None


def _ratio(numerator: float | int, denominator: float | int) -> float:
    return float(numerator) / float(denominator) if denominator else np.nan


def _require_columns(frame: pd.DataFrame, *, name: str, columns: set[str]) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _positive_finite(value: float, *, name: str) -> float:
    result = _finite(value, name=name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result
