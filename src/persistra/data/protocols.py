"""Small provider-neutral acquisition capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from persistra.model import (
        BarSet,
        InstrumentSearchResult,
        MarketStatusResult,
        OptionChain,
        QuoteSet,
        SeriesSet,
    )


@runtime_checkable
class BarSource(Protocol):
    """A source of normalized bars."""

    def bars(self, symbol: str, *, interval: str) -> BarSet:
        """Return bars for one provider symbol."""
        ...


@runtime_checkable
class QuoteSource(Protocol):
    """A source of normalized latest quotes."""

    def latest(self, symbol: str) -> QuoteSet:
        """Return one latest quote."""
        ...


@runtime_checkable
class OptionChainSource(Protocol):
    """A source of normalized historical option chains."""

    def historical_chain(self, symbol: str, *, date: date | None = None) -> OptionChain:
        """Return one historical option chain."""
        ...


@runtime_checkable
class ScalarSeriesSource(Protocol):
    """A source of normalized scalar series."""

    def series(self, key: str, *, frequency: str) -> SeriesSet:
        """Return one scalar series."""
        ...


@runtime_checkable
class ReferenceSource(Protocol):
    """A source of normalized provider reference data."""

    def search(self, keywords: str) -> InstrumentSearchResult:
        """Search provider symbols."""
        ...

    def market_status(self) -> MarketStatusResult:
        """Return provider market status."""
        ...
