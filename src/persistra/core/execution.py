from __future__ import annotations

import math
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persistra.core.events import BarCloseEvent, FillEvent, OrderEvent


class ExecutionTiming(StrEnum):
    """When strategy-generated orders are eligible to execute."""

    SAME_CLOSE = "same_close"
    NEXT_OPEN = "next_open"
    NEXT_CLOSE = "next_close"
    DELAY_BARS = "delay_bars"


class ExecutionModel(ABC):
    """Abstract fill model. Receives an order and the bar that triggered it;
    returns a fully-formed FillEvent."""

    @abstractmethod
    def fill(self, order: OrderEvent, bar: BarCloseEvent) -> FillEvent:
        """Simulate execution of an order at bar close and return a FillEvent.

        Implementations must construct a :class:`~persistra.core.events.FillEvent`
        for the given order using the bar's OHLCV data to determine the fill
        price and any commissions/slippage.

        Args:
            order: The order to execute (symbol, quantity, timestamp).
            bar: The bar-close event that triggered the order (provides close
                price, volume, etc.).

        Returns:
            A fully-formed :class:`~persistra.core.events.FillEvent` with
            ``fill_price`` and ``commission`` set.
        """
        ...


class IdealFill(ExecutionModel):
    """Fill at bar close with zero commission — replicates the original engine behaviour."""

    def fill(self, order: OrderEvent, bar: BarCloseEvent) -> FillEvent:
        """Fill at bar close with zero commission.

        Args:
            order: The order to execute.
            bar: The bar whose ``close`` price is used as the fill price.

        Returns:
            :class:`~persistra.core.events.FillEvent` with
            ``fill_price=bar.close`` and ``commission=0.0``.
        """
        from persistra.core.events import FillEvent

        return FillEvent(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=bar.close,
            commission=0.0,
            order_timestamp=order.timestamp,
        )


class FixedCommission(ExecutionModel):
    """Fill at bar close; commission = ``rate × |quantity × close|``.

    Parameters
    ----------
    rate : float
        Fractional commission per unit of notional (e.g. 0.001 = 10 bps).
    """

    def __init__(self, rate: float) -> None:
        if rate < 0:
            raise ValueError(f"rate must be >= 0, got {rate}")
        self.rate = float(rate)

    def fill(self, order: OrderEvent, bar: BarCloseEvent) -> FillEvent:
        """Fill at bar close; commission is ``rate × |quantity × close|``.

        Args:
            order: The order to execute.
            bar: The bar whose ``close`` price is used as the fill price.

        Returns:
            :class:`~persistra.core.events.FillEvent` with
            ``fill_price=bar.close`` and
            ``commission=rate × |quantity × close|``.
        """
        from persistra.core.events import FillEvent

        notional = abs(order.quantity * bar.close)
        return FillEvent(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=bar.close,
            commission=self.rate * notional,
            order_timestamp=order.timestamp,
        )


class ProportionalSlippage(ExecutionModel):
    """Adverse price adjustment as a fixed fraction of close, plus optional commission.

    Buys fill at ``close × (1 + bps/10_000)``; sells fill at
    ``close × (1 - bps/10_000)``. Commission is applied to the post-slippage
    notional.

    Parameters
    ----------
    bps : float
        One-way slippage in basis points (e.g. 5.0 = 0.05 %).
    rate : float
        Fractional commission on post-slippage notional. Default 0.
    """

    def __init__(self, bps: float, rate: float = 0.0) -> None:
        if bps < 0:
            raise ValueError(f"bps must be >= 0, got {bps}")
        if rate < 0:
            raise ValueError(f"rate must be >= 0, got {rate}")
        self.bps = float(bps)
        self.rate = float(rate)

    def fill(self, order: OrderEvent, bar: BarCloseEvent) -> FillEvent:
        """Fill with fixed basis-point slippage and optional proportional commission.

        Buys execute at ``close × (1 + bps/10 000)``; sells at
        ``close × (1 - bps/10 000)``.  Commission is ``rate × post-slippage
        notional``.

        Args:
            order: The order to execute.
            bar: The bar supplying the reference ``close`` price.

        Returns:
            :class:`~persistra.core.events.FillEvent` with an adversely
            adjusted ``fill_price`` and the corresponding commission.
        """
        from persistra.core.events import FillEvent

        slip = self.bps / 10_000.0
        if order.quantity >= 0:
            fill_price = bar.close * (1.0 + slip)
        else:
            fill_price = bar.close * (1.0 - slip)
        notional = abs(order.quantity * fill_price)
        return FillEvent(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=self.rate * notional,
            order_timestamp=order.timestamp,
        )


class VolumeImpact(ExecutionModel):
    """Price impact proportional to ``sqrt(volume)``, plus optional commission.

    Buys fill at ``close + impact × sqrt(volume)``; sells fill at
    ``close - impact × sqrt(volume)``. Falls back to close when ``volume <= 0``.
    Commission is applied to the post-impact notional.

    Parameters
    ----------
    impact : float
        Price-per-sqrt-share scalar (e.g. 0.01 shifts price by $1 per 10 000
        shares traded).
    rate : float
        Fractional commission on post-impact notional. Default 0.
    """

    def __init__(self, impact: float, rate: float = 0.0) -> None:
        if impact < 0:
            raise ValueError(f"impact must be >= 0, got {impact}")
        if rate < 0:
            raise ValueError(f"rate must be >= 0, got {rate}")
        self.impact = float(impact)
        self.rate = float(rate)

    def fill(self, order: OrderEvent, bar: BarCloseEvent) -> FillEvent:
        """Fill with market-impact adjustment proportional to ``sqrt(volume)``.

        Buys execute at ``close + impact × sqrt(volume)``; sells at
        ``close - impact × sqrt(volume)``.  Falls back to ``close`` when
        ``bar.volume <= 0``.  Commission is ``rate × post-impact notional``.

        Args:
            order: The order to execute.
            bar: The bar supplying ``close`` and ``volume``.

        Returns:
            :class:`~persistra.core.events.FillEvent` with a price shifted by
            the square-root impact model and the corresponding commission.
        """
        from persistra.core.events import FillEvent

        if bar.volume > 0:
            shift = self.impact * math.sqrt(bar.volume)
            fill_price = bar.close + shift if order.quantity >= 0 else bar.close - shift
        else:
            fill_price = bar.close
        notional = abs(order.quantity * fill_price)
        return FillEvent(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=self.rate * notional,
            order_timestamp=order.timestamp,
        )


__all__ = [
    "ExecutionModel",
    "ExecutionTiming",
    "FixedCommission",
    "IdealFill",
    "ProportionalSlippage",
    "VolumeImpact",
]
