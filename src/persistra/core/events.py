from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Priority ordering within a single timestamp (lower = handled first).
P_CORPORATE = 10
P_CLOSE = 30
P_ORDER = 60
P_FILL = 70


@dataclass(frozen=True, kw_only=True)
class Event:
    """Base engine event. Ordered only by (timestamp, priority)."""

    timestamp: pd.Timestamp
    priority: int = 99

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return (self.timestamp, self.priority) < (other.timestamp, other.priority)


@dataclass(frozen=True, kw_only=True)
class BarCloseEvent(Event):
    """Emitted when a price bar closes for a symbol.

    Carries the full OHLCV data for the completed bar.  The engine uses this
    event to update ``HistoryView`` and trigger strategy on-bar callbacks.

    Attributes:
        symbol: Ticker the bar belongs to.
        open: Opening price of the bar.
        high: Highest price during the bar.
        low: Lowest price during the bar.
        close: Closing price of the bar.
        volume: Total volume traded during the bar.
        vwap: Volume-weighted average price for the bar, if available.
        transactions: Number of transactions during the bar, if available.
        priority: Fixed at ``P_CLOSE``; set automatically, not by the caller.
    """

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    transactions: int | None = None
    priority: int = field(default=P_CLOSE, init=False)


@dataclass(frozen=True, kw_only=True)
class DividendEvent(Event):
    """Cash dividend applied on the ex-date for a symbol.

    Attributes:
        symbol: Ticker that issued the dividend.
        amount: Cash dividend per share.
        priority: Fixed at ``P_CORPORATE``; set automatically, not by the
            caller.
    """

    symbol: str
    amount: float  # cash per share, applied on the ex-date
    priority: int = field(default=P_CORPORATE, init=False)


@dataclass(frozen=True, kw_only=True)
class SplitEvent(Event):
    """Stock split applied to a symbol's position.

    Attributes:
        symbol: Ticker that is splitting.
        ratio: Multiplier applied to the held share count.  A value of
            ``2.0`` represents a 2-for-1 forward split.
        priority: Fixed at ``P_CORPORATE``; set automatically, not by the
            caller.
    """

    symbol: str
    ratio: float  # 2.0 = 2-for-1 (position multiplied by ratio)
    priority: int = field(default=P_CORPORATE, init=False)


class OrderType(Enum):
    """Execution style for an order.

    Members:
        MKT: Market order — fill at the next available price.
        MOC: Market-on-close order — fill at the closing price of the bar.
    """

    MKT = "mkt"
    MOC = "moc"  # market on close


@dataclass(frozen=True, kw_only=True)
class OrderEvent(Event):
    """Instruction to buy or sell a symbol.

    Produced by a strategy and consumed by the execution model, which
    converts it into a ``FillEvent``.

    Attributes:
        symbol: Ticker to trade.
        order_type: Execution style (``MKT`` or ``MOC``).
        quantity: Signed share count; positive values are buys, negative
            values are sells.
        strategy_id: Optional identifier of the originating strategy.
        priority: Fixed at ``P_ORDER``; set automatically, not by the caller.
    """

    symbol: str
    order_type: OrderType
    quantity: float  # signed; >0 buy, <0 sell
    strategy_id: str = ""
    priority: int = field(default=P_ORDER, init=False)


@dataclass(frozen=True, kw_only=True)
class FillEvent(Event):
    """Confirmation that an order was executed.

    Produced by the execution model in response to an ``OrderEvent`` and
    consumed by the portfolio to update positions and cash.

    Attributes:
        symbol: Ticker that was traded.
        quantity: Signed share count actually filled; positive for a buy,
            negative for a sell.
        fill_price: Price per share at which the order was executed.
        commission: Total commission charged for the fill.
        order_ref: Optional reference string linking back to the originating
            order.
        priority: Fixed at ``P_FILL``; set automatically, not by the caller.
    """

    symbol: str
    quantity: float
    fill_price: float
    commission: float
    order_ref: str = ""
    priority: int = field(default=P_FILL, init=False)
