from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import pandas as pd

from .events import OrderEvent, OrderType
from .state import PortfolioState

if TYPE_CHECKING:
    from .events import BarCloseEvent, DividendEvent, FillEvent, SplitEvent

_EPS = 1e-9


class PortfolioConstraint(IntEnum):
    """Numeric reason codes for portfolio policy decisions."""

    NONE = 0
    INSUFFICIENT_CASH = 1
    SHORT_DISABLED = 2
    MAX_GROSS_EXPOSURE = 3
    MAX_NET_EXPOSURE = 4
    NONPOSITIVE_EQUITY = 5


@dataclass(frozen=True)
class PortfolioPolicy:
    """Portfolio-level accounting constraints enforced at fill time.

    Args:
        allow_short: Whether fills may leave any symbol with a negative share
            balance.
        max_gross_exposure: Maximum ``sum(abs(position_value)) / equity``.
        max_net_exposure: Maximum absolute ``sum(position_value) / equity``.
        min_cash: Minimum cash fraction of equity.
    """

    allow_short: bool = False
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0
    min_cash: float = 0.0

    def __post_init__(self) -> None:
        if self.max_gross_exposure < 0:
            raise ValueError(f"max_gross_exposure must be >= 0, got {self.max_gross_exposure}")
        if self.max_net_exposure < 0:
            raise ValueError(f"max_net_exposure must be >= 0, got {self.max_net_exposure}")
        if self.min_cash < 0:
            raise ValueError(f"min_cash must be >= 0, got {self.min_cash}")


@dataclass(frozen=True)
class FillDecision:
    """Result of applying or rejecting a fill under portfolio policy."""

    accepted: bool
    constraint: PortfolioConstraint = PortfolioConstraint.NONE
    requested_quantity: float = 0.0
    filled_quantity: float = 0.0
    post_cash: float = 0.0
    post_equity: float = 0.0
    post_gross_exposure: float = 0.0
    post_net_exposure: float = 0.0


class Portfolio:
    """Handles cash/position accounting, mark-to-market, corporate actions
    (splits/dividends), fill-time policy constraints, and weight reconciliation.
    No rate accrual or sizer abstraction yet. Target weights convert directly
    to share deltas against the latest close.
    """

    def __init__(
        self,
        initial_capital: float,
        policy: PortfolioPolicy | None = None,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.policy = policy if policy is not None else PortfolioPolicy()
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

    def on_fill(self, event: FillEvent) -> FillDecision:
        """Apply a fill to cash and position ledgers.

        Adds ``quantity`` shares to the position, deducts
        ``quantity × fill_price + commission`` from cash, and removes
        the entry when the resulting position is negligible (< ``_EPS``). If
        the configured :class:`PortfolioPolicy` would be violated, the fill is
        rejected and ledgers are left unchanged.

        Args:
            event: The fill event (symbol, quantity, fill_price, commission).

        Returns:
            A :class:`FillDecision` describing whether the fill was accepted.
        """
        decision = self._evaluate_fill(event)
        if not decision.accepted:
            return decision
        self._positions[event.symbol] = self._positions.get(event.symbol, 0.0) + event.quantity
        self._cash -= event.quantity * event.fill_price + event.commission
        if abs(self._positions[event.symbol]) < _EPS:
            del self._positions[event.symbol]
        return decision

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
        orders.sort(key=lambda order: (order.quantity > 0, order.symbol))
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

    def _evaluate_fill(self, event: FillEvent) -> FillDecision:
        positions = dict(self._positions)
        new_qty = positions.get(event.symbol, 0.0) + event.quantity
        if abs(new_qty) < _EPS:
            positions.pop(event.symbol, None)
        else:
            positions[event.symbol] = new_qty

        cash = self._cash - event.quantity * event.fill_price - event.commission
        equity, gross, net = self._exposures(
            positions,
            price_overrides={event.symbol: event.fill_price},
        )
        equity += cash

        decision_kwargs = {
            "requested_quantity": float(event.quantity),
            "filled_quantity": float(event.quantity),
            "post_cash": float(cash),
            "post_equity": float(equity),
            "post_gross_exposure": float(gross),
            "post_net_exposure": float(net),
        }

        if equity <= _EPS:
            return FillDecision(
                accepted=False,
                constraint=PortfolioConstraint.NONPOSITIVE_EQUITY,
                filled_quantity=0.0,
                **{k: v for k, v in decision_kwargs.items() if k != "filled_quantity"},
            )

        gross_exposure = gross / equity
        net_exposure = net / equity
        min_cash_amount = self.policy.min_cash * equity
        decision_kwargs["post_gross_exposure"] = float(gross_exposure)
        decision_kwargs["post_net_exposure"] = float(net_exposure)

        if cash + _EPS < min_cash_amount:
            return FillDecision(
                accepted=False,
                constraint=PortfolioConstraint.INSUFFICIENT_CASH,
                filled_quantity=0.0,
                **{k: v for k, v in decision_kwargs.items() if k != "filled_quantity"},
            )
        if not self.policy.allow_short and any(qty < -_EPS for qty in positions.values()):
            return FillDecision(
                accepted=False,
                constraint=PortfolioConstraint.SHORT_DISABLED,
                filled_quantity=0.0,
                **{k: v for k, v in decision_kwargs.items() if k != "filled_quantity"},
            )
        if gross_exposure > self.policy.max_gross_exposure + _EPS:
            return FillDecision(
                accepted=False,
                constraint=PortfolioConstraint.MAX_GROSS_EXPOSURE,
                filled_quantity=0.0,
                **{k: v for k, v in decision_kwargs.items() if k != "filled_quantity"},
            )
        if abs(net_exposure) > self.policy.max_net_exposure + _EPS:
            return FillDecision(
                accepted=False,
                constraint=PortfolioConstraint.MAX_NET_EXPOSURE,
                filled_quantity=0.0,
                **{k: v for k, v in decision_kwargs.items() if k != "filled_quantity"},
            )
        return FillDecision(accepted=True, constraint=PortfolioConstraint.NONE, **decision_kwargs)

    def _exposures(
        self,
        positions: dict[str, float],
        price_overrides: dict[str, float] | None = None,
    ) -> tuple[float, float, float]:
        prices = price_overrides or {}
        values = [
            qty * prices.get(sym, self._last_prices.get(sym, 0.0)) for sym, qty in positions.items()
        ]
        mtm = sum(values)
        gross = sum(abs(value) for value in values)
        net = mtm
        return mtm, gross, net

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
