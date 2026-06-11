from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from .events import OrderEvent, OrderType
from .state import PortfolioState

if TYPE_CHECKING:
    from .events import BarCloseEvent, DividendEvent, FillEvent, SplitEvent

_EPS = 1e-9


class Portfolio:
    """Handles cash/position accounting, mark-to-market, corporate actions
    (splits/dividends), and weight reconciliation. No rate accrual, risk
    constraints, or sizer abstraction yet. Target weights convert directly to
    share deltas against the latest close.
    """

    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = float(initial_capital)
        self._cash = float(initial_capital)
        self._positions: dict[str, float] = {}
        self._last_prices: dict[str, float] = {}
        self._equity_history: list[tuple[pd.Timestamp, float, float, float, float]] = []

    def on_bar_close(self, event: BarCloseEvent) -> None:
        """Update the last-known close price for a symbol.

        Args:
            event: The bar-close event carrying the new close price.
        """
        self._last_prices[event.symbol] = event.close

    def on_fill(self, event: FillEvent) -> None:
        """Apply a fill to cash and position ledgers.

        Adds ``quantity`` shares to the position, deducts
        ``quantity × fill_price + commission`` from cash, and removes
        the entry when the resulting position is negligible (< ``_EPS``).

        Args:
            event: The fill event (symbol, quantity, fill_price, commission).
        """
        self._positions[event.symbol] = self._positions.get(event.symbol, 0.0) + event.quantity
        self._cash -= event.quantity * event.fill_price + event.commission
        if abs(self._positions[event.symbol]) < _EPS:
            del self._positions[event.symbol]

    def on_dividend(self, event: DividendEvent) -> None:
        """Credit (or, for shorts, debit) ex-date cash: shares * per-share amount."""
        self._cash += self._positions.get(event.symbol, 0.0) * event.amount

    def on_split(self, event: SplitEvent) -> None:
        """Multiply a held position by the split ratio (e.g. 2.0 = 2-for-1).

        No price adjustment: the ex-date bar supplies the post-split price.
        """
        if event.symbol in self._positions:
            self._positions[event.symbol] *= event.ratio

    def record_equity(self, timestamp: pd.Timestamp, snap: PortfolioState | None = None) -> None:
        """Append an equity-curve row. If ``snap`` is provided, skips snapshot()."""
        if snap is None:
            snap = self.snapshot()
        self._equity_history.append(
            (timestamp, snap.equity, snap.cash, snap.gross_exposure, snap.net_exposure)
        )

    def on_session_end(self, timestamp: pd.Timestamp) -> None:
        """Back-compat alias: record one equity row at session end."""
        self.record_equity(timestamp)

    def target_orders(
        self,
        weights: dict[str, float],
        timestamp: pd.Timestamp,
        equity: float,
    ) -> list[OrderEvent]:
        """Reconcile holdings to a *complete* target-weight vector.

        ``weights`` is treated as the full desired portfolio: any currently held
        symbol that is absent from it is targeted to zero (liquidated). Emitting
        ``{}`` would therefore flatten the book, while emitting nothing at all
        (``StrategyContext`` never calls ``signal``) leaves holdings untouched.
        """
        targets = dict(weights)
        for symbol, shares in self._positions.items():
            if abs(shares) > _EPS and symbol not in targets:
                targets[symbol] = 0.0
        orders: list[OrderEvent] = []
        for symbol, weight in targets.items():
            price = self._last_prices.get(symbol)
            if not price:
                continue
            target_shares = weight * equity / price
            delta = target_shares - self._positions.get(symbol, 0.0)
            if abs(delta) < _EPS:
                continue
            orders.append(
                OrderEvent(
                    timestamp=timestamp,
                    symbol=symbol,
                    order_type=OrderType.MOC,
                    quantity=delta,
                )
            )
        return orders

    def snapshot(self) -> PortfolioState:
        """Return a point-in-time read-only snapshot of portfolio state.

        Computes mark-to-market equity, per-symbol weights, and gross/net
        exposure using the most recent close prices.

        Returns:
            :class:`~persistra.core.state.PortfolioState` with ``equity``,
            ``cash``, ``positions``, ``weights``, ``gross_exposure``, and
            ``net_exposure`` populated.
        """
        equity = self._equity()
        if equity == 0:
            weights: dict[str, float] = {}
        else:
            weights = {
                sym: (qty * self._last_prices.get(sym, 0.0)) / equity
                for sym, qty in self._positions.items()
            }
        gross = sum(abs(w) for w in weights.values())
        net = sum(weights.values())
        return PortfolioState(
            equity=equity,
            cash=self._cash,
            positions=dict(self._positions),
            weights=weights,
            gross_exposure=gross,
            net_exposure=net,
        )

    def _equity(self) -> float:
        mtm = sum(qty * self._last_prices.get(sym, 0.0) for sym, qty in self._positions.items())
        return self._cash + mtm

    def equity_curve(self) -> pd.DataFrame:
        """Return the accumulated equity-curve history as a DataFrame.

        Rows are appended by :meth:`record_equity` (called each bar by the
        engine on the finest subscribed timeframe).

        Returns:
            DataFrame indexed by ``timestamp`` with columns
            ``["equity", "cash", "gross_exposure", "net_exposure"]``.
            Returns an empty DataFrame with those columns if no rows have
            been recorded yet.
        """
        cols = ["equity", "cash", "gross_exposure", "net_exposure"]
        if not self._equity_history:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(self._equity_history, columns=["timestamp", *cols])
        return df.set_index("timestamp")
