from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

_DIAGNOSTICS_COLUMNS = ["bar_time", "timeframe", "name", "symbol", "value"]
_ORDERS_COLUMNS = [
    "order_id",
    "order_timestamp",
    "terminal_timestamp",
    "timeframe",
    "symbol",
    "quantity",
    "execution_timing",
    "delay_required",
    "bars_seen",
    "status",
    "reason",
    "fill_timestamp",
    "fill_price",
    "commission",
    "portfolio_constraint",
    "origin",
]


def _empty_diagnostics() -> pd.DataFrame:
    return pd.DataFrame(columns=_DIAGNOSTICS_COLUMNS)


def _empty_orders() -> pd.DataFrame:
    return pd.DataFrame(columns=_ORDERS_COLUMNS)


@dataclass
class Result:
    """Output of a finished backtest run.

    Attributes:
        equity_curve: Daily snapshot with columns ``equity``, ``cash``,
            ``gross_exposure``, and ``net_exposure``, indexed by session date.
        trades: One row per ``FillEvent``; columns include ``order_timestamp``,
            fill ``timestamp``, ``symbol``, ``quantity``, ``fill_price``, and
            ``commission``.
        orders: One row per generated order with terminal status ``filled``,
            ``rejected``, or ``unfilled``.
        positions: Sparse weight log — columns ``bar_time``, ``symbol``,
            ``weight``; zero-share symbols are omitted.
        diagnostics: Long-form strategy diagnostics — columns ``bar_time``,
            ``timeframe``, ``name``, ``symbol``, ``value`` (``symbol`` null for
            portfolio-level records). Empty when no strategy called ``ctx.record()``.
        meta: Arbitrary key/value metadata written by the engine (e.g.
            ``run_seconds``, engine configuration).
    """

    equity_curve: pd.DataFrame  # index: session; cols: equity, cash, gross_exposure, net_exposure
    trades: pd.DataFrame  # one row per FillEvent
    positions: pd.DataFrame  # cols: bar_time, symbol, weight  (sparse: zero-share symbols omitted)
    diagnostics: pd.DataFrame = field(default_factory=_empty_diagnostics)
    orders: pd.DataFrame = field(default_factory=_empty_orders)
    meta: dict[str, Any] = field(default_factory=dict)

    def diagnostic(self, name: str) -> pd.DataFrame:
        """Pivot one recorded diagnostic to a ``bar_time`` x ``symbol`` wide frame.

        Scalar (portfolio-level) diagnostics yield a single column named ``name``.
        Raises ``KeyError`` naming the available diagnostics if ``name`` was never
        recorded.
        """
        diag = self.diagnostics
        names = set(diag["name"]) if not diag.empty else set()
        if name not in names:
            raise KeyError(f"diagnostic {name!r} not recorded; available: {sorted(names)}")
        sub = diag[diag["name"] == name]
        if sub["symbol"].isna().all():
            return sub.set_index("bar_time")[["value"]].rename(columns={"value": name})
        return sub.pivot_table(index="bar_time", columns="symbol", values="value")
