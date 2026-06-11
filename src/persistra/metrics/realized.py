from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from persistra.core.result import Result


def realized_pnl(result: Result) -> pd.Series:
    """FIFO realized P&L per closing trade fill.

    Returns a Series indexed by timestamp, one entry per closing fill.
    Empty if there are no closing trades.
    """
    trades = result.trades
    if trades.empty:
        return pd.Series(dtype=float)

    df = trades.sort_values("timestamp")
    realized: list[tuple[pd.Timestamp, float]] = []

    for _symbol, group in df.groupby("symbol", sort=False):
        lots: deque[list[float]] = deque()
        for _, row in group.iterrows():
            qty = float(row["quantity"])
            price = float(row["fill_price"])
            commission = float(row["commission"])
            if qty == 0.0:
                continue
            comm_per_unit = commission / abs(qty) if abs(qty) > 0 else 0.0
            remaining = qty
            while lots and remaining != 0.0 and (lots[0][0] > 0) != (remaining > 0):
                lot = lots[0]
                lot_qty, lot_price, lot_cpu = lot[0], lot[1], lot[2]
                matched = min(abs(lot_qty), abs(remaining))
                pnl = (
                    (price - lot_price) * matched if lot_qty > 0 else (lot_price - price) * matched
                )
                pnl -= (comm_per_unit + lot_cpu) * matched
                realized.append((pd.Timestamp(row["timestamp"]), pnl))
                lot[0] = lot_qty - math.copysign(matched, lot_qty)
                remaining = remaining - math.copysign(matched, remaining)
                if lot[0] == 0.0:
                    lots.popleft()
            if remaining != 0.0:
                lots.append([remaining, price, comm_per_unit])

    if not realized:
        return pd.Series(dtype=float)
    idx = pd.Index([t for t, _ in realized], name="timestamp")
    return pd.Series([p for _, p in realized], index=idx, name="pnl")
