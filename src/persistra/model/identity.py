"""Provider-neutral catalog identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from numbers import Real
from typing import cast


def _require_text(value: str, name: str) -> None:
    raw = cast("object", value)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must not be empty")


def _require_optional_text(value: str | None, name: str) -> None:
    if value is not None:
        _require_text(value, name)


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
        _require_text(self.instrument_id, "instrument_id")
        _require_text(self.display_name, "display_name")
        if not isinstance(cast("object", self.kind), InstrumentKind):
            raise ValueError("kind must be an InstrumentKind")
        _require_optional_text(self.base_currency, "base_currency")
        _require_optional_text(self.quote_currency, "quote_currency")
        pair = self.kind in {InstrumentKind.FIAT_PAIR, InstrumentKind.CRYPTO_PAIR}
        if pair != (self.base_currency is not None and self.quote_currency is not None):
            raise ValueError("pair instruments require both base and quote currencies")
        if (
            pair
            and self.base_currency is not None
            and self.quote_currency is not None
            and self.base_currency.casefold() == self.quote_currency.casefold()
        ):
            raise ValueError("pair instrument currencies must differ")


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

    def __post_init__(self) -> None:
        _require_text(self.listing_id, "listing_id")
        _require_text(self.instrument_id, "instrument_id")
        _require_text(self.symbol, "symbol")
        _require_optional_text(self.exchange, "exchange")
        _require_optional_text(self.mic, "mic")
        _require_optional_text(self.currency, "currency")
        _require_optional_text(self.source_timezone, "source_timezone")


@dataclass(frozen=True, slots=True)
class ProviderSymbol:
    """A provider key mapped to one instrument or listing."""

    provider: str
    kind: InstrumentKind
    symbol: str
    instrument_id: str
    listing_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.provider, "provider")
        if not isinstance(cast("object", self.kind), InstrumentKind):
            raise ValueError("kind must be an InstrumentKind")
        _require_text(self.symbol, "symbol")
        _require_text(self.instrument_id, "instrument_id")
        _require_optional_text(self.listing_id, "listing_id")


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
        _require_text(self.contract_id, "contract_id")
        _require_text(self.provider, "provider")
        _require_text(self.underlying_instrument_id, "underlying_instrument_id")
        _require_text(self.expiration, "expiration")
        raw_strike = cast("object", self.strike)
        if (
            isinstance(raw_strike, bool)
            or not isinstance(raw_strike, Real)
            or not isfinite(float(raw_strike))
        ):
            raise ValueError("strike must be finite")
        if self.strike <= 0:
            raise ValueError("strike must be positive")
        if not isinstance(cast("object", self.option_type), OptionType):
            raise ValueError("option_type must be an OptionType")


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

    def __post_init__(self) -> None:
        _require_text(self.series_id, "series_id")
        if not isinstance(cast("object", self.kind), SeriesKind):
            raise ValueError("kind must be a SeriesKind")
        _require_text(self.display_name, "display_name")
        _require_text(self.provider, "provider")
        _require_text(self.provider_series, "provider_series")
        _require_text(self.frequency, "frequency")
        _require_text(self.unit, "unit")
        _require_optional_text(self.geography, "geography")
        _require_optional_text(self.seasonal_adjustment, "seasonal_adjustment")
        _require_optional_text(self.maturity, "maturity")


def provider_instrument_id(provider: str, kind: InstrumentKind, symbol: str) -> str:
    """Create a stable provider-scoped instrument identity."""
    return _scoped_id("instrument", provider, kind.value, symbol.upper())


def provider_series_id(provider: str, provider_series: str, frequency: str) -> str:
    """Create a stable provider-scoped series identity."""
    return _scoped_id("series", provider, provider_series, frequency)


def _scoped_id(*parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode()).hexdigest()[:24]
    return f"ps_{digest}"
