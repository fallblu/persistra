"""Deterministic Trading Engine replay fixtures."""

from __future__ import annotations

import pandas as pd
import pytest

from persistra.integrations.trading_engine.model import (
    ExecutionReplayResult,
    RunCompletion,
)


@pytest.fixture
def execution_replay() -> ExecutionReplayResult:
    """Return a replay with a partial fill, rejection, cancellation, fees, and drawdown."""
    timestamps = pd.to_datetime(
        [
            "2026-01-02T21:00:02Z",
            "2026-01-05T21:00:02Z",
            "2026-01-06T21:00:02Z",
            "2026-01-07T21:00:02Z",
        ],
        utc=True,
    )
    bars = pd.DataFrame(
        {
            "engine_sequence": [1, 6, 10, 14],
            "source_sequence": pd.array([1, 2, 3, 4], dtype="Int64"),
            "instrument_id": ["acme"] * 4,
            "recorded_at": timestamps,
            "start_at": timestamps - pd.Timedelta(hours=6, minutes=30, seconds=2),
            "end_at": timestamps - pd.Timedelta(seconds=2),
            "open": [100.0, 103.0, 107.0, 105.0],
            "close": [104.0, 107.0, 105.0, 106.0],
            "volume": pd.array([100, 12, 100, 100], dtype="Int64"),
        }
    )
    orders = pd.DataFrame(
        {
            "engine_sequence": [3, 4, 12],
            "recorded_at": [timestamps[0], timestamps[0], timestamps[2]],
            "event_type": ["order_accepted", "order_rejected", "order_accepted"],
            "order_id": ["order-1", "order-rejected", "order-2"],
            "instrument_id": ["acme"] * 3,
            "side": ["buy", "buy", "sell"],
            "quantity": pd.array([10, 200, 4], dtype="Int64"),
            "order_kind": ["market"] * 3,
            "eligible_after_bar_sequence": pd.array([1, 1, 3], dtype="Int64"),
            "status": ["working", "rejected", "working"],
            "rejection_reason": [None, "risk limit", None],
        }
    )
    fills = pd.DataFrame(
        {
            "engine_sequence": [7, 15],
            "recorded_at": [timestamps[1], timestamps[3]],
            "fill_id": ["fill-1", "fill-2"],
            "order_id": ["order-1", "order-2"],
            "instrument_id": ["acme", "acme"],
            "side": ["buy", "sell"],
            "quantity": pd.array([6, 4], dtype="Int64"),
            "price": [103.0, 105.0],
            "notional": [618.0, 420.0],
            "fee": [0.868, 0.67],
            "executed_at": [
                timestamps[1] - pd.Timedelta(hours=6, minutes=30, seconds=2),
                timestamps[3] - pd.Timedelta(hours=6, minutes=30, seconds=2),
            ],
            "bar_sequence": pd.array([2, 4], dtype="Int64"),
        }
    )
    cancellations = pd.DataFrame(
        {
            "engine_sequence": [8],
            "recorded_at": [timestamps[1]],
            "order_id": ["order-1"],
            "reason": ["market_ioc"],
        }
    )
    rejections = pd.DataFrame(
        {
            "engine_sequence": [4, 5],
            "recorded_at": [timestamps[0], timestamps[0]],
            "event_type": ["order_rejected", "intent_rejected"],
            "order_id": ["order-rejected", None],
            "reason": ["risk limit", "bad metric"],
        }
    )
    valuations = pd.DataFrame(
        {
            "engine_sequence": pd.array([5, 9, 13, 16], dtype="Int64"),
            "recorded_at": timestamps,
            "cash": [10000.0, 9381.132, 9381.132, 9800.462],
            "market_value": [0.0, 642.0, 630.0, 212.0],
            "realized_pnl": [0.0, 0.0, 0.0, 6.751334],
            "unrealized_pnl": [0.0, 23.132, 11.132, 5.710666],
            "equity": [10000.0, 10023.132, 10011.132, 10012.462],
            "total_fees": [0.0, 0.868, 0.868, 1.538],
        }
    )
    completion = RunCompletion(
        recorded_at=timestamps[-1],
        engine_sequence=17,
        cash_micros=9_800_462_000,
        market_value_micros=212_000_000,
        cost_basis_micros=206_289_334,
        realized_pnl_micros=6_751_334,
        unrealized_pnl_micros=5_710_666,
        equity_micros=10_012_462_000,
        total_fees_micros=1_538_000,
        total_orders=3,
        active_orders=0,
        filled_orders=1,
        rejected_orders=1,
        cancelled_orders=1,
    )
    return ExecutionReplayResult(
        run_id="analysis-demo",
        bars=bars,
        targets=pd.DataFrame(),
        orders=orders,
        fills=fills,
        cancellations=cancellations,
        rejections=rejections,
        valuations=valuations,
        metrics=pd.DataFrame(),
        events=(),
        completion=completion,
        base_currency="USD",
        initial_cash=10_000.0,
        initial_cash_micros=10_000_000_000,
    )
