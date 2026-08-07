"""Provider-neutral catalog identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class InstrumentKind(StrEnum):
    """Supported instrument families."""

    EQUITY = "equity"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    INDEX = "index"
    FIAT_PAIR = "fiat_pair"
    CRYPTO_PAIR = "crypto_pair"
    COMMODITY = "commodity"


class OptionType(StrEnum):
    """Option contract sides."""

    CALL = "call"
    PUT = "put"


class SeriesKind(StrEnum):
    """Supported scalar series families."""

    COMMODITY = "commodity"
    ECONOMIC = "economic"


@dataclass(frozen=True, slots=True)
class Instrument:
    """A provider-neutral financial or economic instrument."""

    instrument_id: str
    kind: InstrumentKind
    display_name: str
    base_currency: str | None = None
    quote_currency: str | None = None

    def __post_init__(self) -> None:
        if not self.instrument_id or not self.display_name:
            raise ValueError("instrument_id and display_name must not be empty")
        pair = self.kind in {InstrumentKind.FIAT_PAIR, InstrumentKind.CRYPTO_PAIR}
        if pair != (self.base_currency is not None and self.quote_currency is not None):
            raise ValueError("pair instruments require both base and quote currencies")


@dataclass(frozen=True, slots=True)
class Listing:
    """A venue listing for an instrument."""

    listing_id: str
    instrument_id: str
    symbol: str
    exchange: str | None = None
    mic: str | None = None
    currency: str | None = None
    source_timezone: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderSymbol:
    """A provider key mapped to one instrument or listing."""

    provider: str
    kind: InstrumentKind
    symbol: str
    instrument_id: str
    listing_id: str | None = None


@dataclass(frozen=True, slots=True)
class OptionContract:
    """Provider-scoped option terms."""

    contract_id: str
    provider: str
    underlying_instrument_id: str
    expiration: str
    strike: float
    option_type: OptionType

    def __post_init__(self) -> None:
        if self.strike <= 0:
            raise ValueError("strike must be positive")


@dataclass(frozen=True, slots=True)
class SeriesDefinition:
    """Provider-neutral identity for a scalar series."""

    series_id: str
    kind: SeriesKind
    display_name: str
    provider: str
    provider_series: str
    frequency: str
    unit: str
    geography: str | None = None
    seasonal_adjustment: str | None = None
    maturity: str | None = None


def provider_instrument_id(provider: str, kind: InstrumentKind, symbol: str) -> str:
    """Create a stable provider-scoped instrument identity."""
    return _scoped_id("instrument", provider, kind.value, symbol.upper())


def provider_series_id(provider: str, provider_series: str, frequency: str) -> str:
    """Create a stable provider-scoped series identity."""
    return _scoped_id("series", provider, provider_series, frequency)


def _scoped_id(*parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode()).hexdigest()[:24]
    return f"ps_{digest}"
