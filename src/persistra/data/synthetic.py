"""Deterministic offline data for research and tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType

import numpy as np
import pandas as pd

from persistra.model import (
    BarSet,
    CacheStatus,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    ResultMetadata,
    SeriesDefinition,
    SeriesKind,
    SeriesSet,
    TopOfBookSet,
    provider_instrument_id,
    provider_series_id,
)
from persistra.model._frames import (
    BAR_DTYPES,
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    QUOTE_DTYPES,
    SERIES_DTYPES,
    TOP_OF_BOOK_DTYPES,
    typed_frame,
)
from persistra.model.reference import INDEX_CATALOG_DTYPES, MARKET_STATUS_DTYPES, SEARCH_DTYPES

SYNTHETIC_NOW = datetime(2025, 1, 31, 21, tzinfo=UTC)

__all__ = [
    "SYNTHETIC_NOW",
    "bars",
    "commodity_spot",
    "exchange_rate",
    "index_catalog",
    "market_status",
    "metadata",
    "option_chain",
    "quotes",
    "search",
    "series",
    "top_of_book",
    "treasury_curve",
]


def metadata(operation: str, *, retrieved_at: datetime = SYNTHETIC_NOW) -> ResultMetadata:
    """Create deterministic synthetic provenance."""
    return ResultMetadata(
        provider="synthetic",
        operation=operation,
        request_parameters=MappingProxyType({}),
        retrieved_at=retrieved_at,
        cache_status=CacheStatus.NOT_USED,
    )


def bars(
    symbol: str = "SYNTH",
    *,
    periods: int = 90,
    seed: int = 7,
    interval: str = "daily",
    kind: InstrumentKind = InstrumentKind.EQUITY,
    adjusted: bool = False,
    session: str | None = None,
) -> BarSet:
    """Create deterministic bars with price and volume regimes."""
    if periods < 0:
        raise ValueError("periods must be nonnegative")
    instrument_id = provider_instrument_id("synthetic", kind, symbol)
    is_pair = kind in {InstrumentKind.FIAT_PAIR, InstrumentKind.CRYPTO_PAIR}
    instrument = Instrument(
        instrument_id,
        kind,
        symbol,
        base_currency="BASE" if is_pair else None,
        quote_currency="QUOTE" if is_pair else None,
    )
    if periods == 0:
        frame = typed_frame({name: [] for name in BAR_DTYPES}, BAR_DTYPES)
        return BarSet(instrument, frame, metadata("bars"))
    generator = np.random.default_rng(seed)
    volatility = np.where(np.arange(periods) < periods // 2, 0.006, 0.018)
    close = 100 * np.exp(np.cumsum(generator.normal(0.0004, volatility)))
    open_price = close * (1 + generator.normal(0, volatility / 3))
    width = np.abs(generator.normal(0.008, volatility / 2))
    high = np.maximum(open_price, close) * (1 + width)
    low = np.minimum(open_price, close) * (1 - width)
    volume = np.where(np.arange(periods) < periods // 2, 1_000_000, 2_000_000)
    volume = volume * generator.uniform(0.75, 1.25, periods)
    dates = pd.date_range(date(2025, 1, 1), periods=periods, freq="D")
    is_intraday = interval.endswith("min")
    normalized_session = session or ("all" if is_intraday else "not_applicable")
    if is_intraday and normalized_session not in {"regular", "all"}:
        raise ValueError("intraday session must be regular or all")
    if not is_intraday and normalized_session != "not_applicable":
        raise ValueError("session applies only to intraday bars")
    adjusted_close = close * 0.99 if adjusted and not is_intraday else [pd.NA] * periods
    frame = typed_frame(
        {
            "instrument_id": [instrument_id] * periods,
            "provider": ["synthetic"] * periods,
            "provider_symbol": [symbol] * periods,
            "interval": [interval] * periods,
            "date": [pd.NaT] * periods if is_intraday else dates,
            "timestamp": dates.tz_localize("UTC") if is_intraday else [pd.NaT] * periods,
            "timestamp_position": ["provider_label" if is_intraday else "not_applicable"] * periods,
            "source_timezone": ["UTC"] * periods,
            "session": [normalized_session] * periods,
            "price_adjustment": ["adjusted" if adjusted else "raw"] * periods,
            "currency": ["USD"] * periods,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": adjusted_close,
            "volume": volume,
            "dividend_amount": [0.0] * periods
            if adjusted and not is_intraday
            else [pd.NA] * periods,
            "split_coefficient": [1.0] * periods
            if adjusted and not is_intraday
            else [pd.NA] * periods,
            "provider_as_of": [pd.NaT] * periods,
            "retrieved_at": [SYNTHETIC_NOW] * periods,
        },
        BAR_DTYPES,
    )
    return BarSet(instrument, frame, metadata("bars"))


def quotes(symbols: tuple[str, ...] = ("AAA", "BBB")) -> QuoteSet:
    """Create deterministic latest quotes."""
    count = len(symbols)
    prices = np.arange(100.0, 100.0 + count)
    frame = typed_frame(
        {
            "instrument_id": [
                provider_instrument_id("synthetic", InstrumentKind.EQUITY, symbol)
                for symbol in symbols
            ],
            "provider": ["synthetic"] * count,
            "provider_symbol": list(symbols),
            "price": prices,
            "open": prices - 1,
            "high": prices + 1,
            "low": prices - 2,
            "previous_close": prices - 0.5,
            "change": [0.5] * count,
            "change_percent": [0.5] * count,
            "volume": [1_000_000.0] * count,
            "latest_trading_day": [date(2025, 1, 31)] * count,
            "observed_at": [pd.NaT] * count,
            "entitlement": ["historical"] * count,
            "provider_as_of": [pd.NaT] * count,
            "retrieved_at": [SYNTHETIC_NOW] * count,
        },
        QUOTE_DTYPES,
    )
    return QuoteSet(frame.reset_index(drop=True), metadata("quotes"))


def top_of_book(symbols: tuple[str, ...] = ("AAA", "BBB")) -> TopOfBookSet:
    """Create deterministic top-of-book observations."""
    count = len(symbols)
    frame = typed_frame(
        {
            "instrument_id": [
                provider_instrument_id("synthetic", InstrumentKind.EQUITY, symbol)
                for symbol in symbols
            ],
            "provider": ["synthetic"] * count,
            "provider_symbol": list(symbols),
            "bid_price": np.arange(99.9, 99.9 + count),
            "bid_size": [100] * count,
            "ask_price": np.arange(100.1, 100.1 + count),
            "ask_size": [120] * count,
            "observed_at": [SYNTHETIC_NOW] * count,
            "provider_as_of": [SYNTHETIC_NOW] * count,
            "retrieved_at": [SYNTHETIC_NOW] * count,
        },
        TOP_OF_BOOK_DTYPES,
    )
    return TopOfBookSet(frame.reset_index(drop=True), metadata("top_of_book"))


def option_chain(
    symbol: str = "SYNTH",
    *,
    chain_date: date = date(2025, 1, 17),
) -> OptionChain:
    """Create a chain with several strikes, expirations, and both sides."""
    underlying_id = provider_instrument_id("synthetic", InstrumentKind.EQUITY, symbol)
    terms: list[tuple[str, date, float, str]] = []
    for expiration_days in (28, 56):
        expiration = chain_date + timedelta(days=expiration_days)
        for strike in (90.0, 100.0, 110.0):
            for option_type in ("call", "put"):
                contract_id = f"{symbol}-{expiration:%Y%m%d}-{option_type[0]}-{strike:.0f}"
                terms.append((contract_id, expiration, strike, option_type))
    contracts = typed_frame(
        {
            "contract_id": [term[0] for term in terms],
            "provider": ["synthetic"] * len(terms),
            "underlying_instrument_id": [underlying_id] * len(terms),
            "provider_symbol": [symbol] * len(terms),
            "expiration": [term[1] for term in terms],
            "strike": [term[2] for term in terms],
            "option_type": [term[3] for term in terms],
        },
        OPTION_CONTRACT_DTYPES,
    ).sort_values(["expiration", "strike", "option_type", "contract_id"])
    distances = np.array([abs(term[2] - 100) for term in terms])
    marks = 6 - distances * 0.25
    observations = typed_frame(
        {
            "contract_id": [term[0] for term in terms],
            "provider": ["synthetic"] * len(terms),
            "chain_date": [chain_date] * len(terms),
            "last": marks,
            "mark": marks,
            "bid": marks - 0.1,
            "bid_size": [10] * len(terms),
            "ask": marks + 0.1,
            "ask_size": [12] * len(terms),
            "volume": [100] * len(terms),
            "open_interest": [1_000] * len(terms),
            "implied_volatility": 0.2 + distances * 0.002,
            "delta": [0.5 if term[3] == "call" else -0.5 for term in terms],
            "gamma": [0.04] * len(terms),
            "theta": [-0.03] * len(terms),
            "vega": [0.12] * len(terms),
            "rho": [0.05 if term[3] == "call" else -0.05 for term in terms],
            "provider_as_of": [pd.NaT] * len(terms),
            "retrieved_at": [SYNTHETIC_NOW] * len(terms),
        },
        OPTION_OBSERVATION_DTYPES,
    ).sort_values(["provider", "contract_id"])
    return OptionChain(
        underlying_id,
        symbol,
        chain_date,
        contracts.reset_index(drop=True),
        observations.reset_index(drop=True),
        metadata("historical_options"),
    )


def series(
    provider_series: str = "SYNTH_GDP",
    *,
    periods: int = 24,
    frequency: str = "monthly",
    kind: SeriesKind = SeriesKind.ECONOMIC,
    unit: str = "index",
    geography: str | None = "United States",
    maturity: str | None = None,
) -> SeriesSet:
    """Create a deterministic scalar series with units and frequency."""
    series_id = provider_series_id("synthetic", provider_series, frequency)
    definition = SeriesDefinition(
        series_id,
        kind,
        provider_series.replace("_", " ").title(),
        "synthetic",
        provider_series,
        frequency,
        unit,
        geography=geography,
        maturity=maturity,
    )
    dates = pd.date_range(date(2023, 1, 1), periods=periods, freq="MS")
    frame = typed_frame(
        {
            "series_id": [series_id] * periods,
            "provider": ["synthetic"] * periods,
            "provider_series": [provider_series] * periods,
            "series_kind": [kind.value] * periods,
            "frequency": [frequency] * periods,
            "period_label": [item.strftime("%Y-%m-%d") for item in dates],
            "period_start": dates,
            "period_end": [pd.NaT] * periods,
            "value": np.linspace(100.0, 112.0, periods),
            "unit": [unit] * periods,
            "geography": [geography if geography is not None else pd.NA] * periods,
            "seasonal_adjustment": [pd.NA] * periods,
            "maturity": [maturity if maturity is not None else pd.NA] * periods,
            "provider_as_of": [pd.NaT] * periods,
            "retrieved_at": [SYNTHETIC_NOW] * periods,
        },
        SERIES_DTYPES,
    )
    return SeriesSet(definition, frame, metadata("series"))


def exchange_rate(
    base_currency: str = "EUR",
    quote_currency: str = "USD",
    *,
    crypto: bool = False,
) -> ExchangeRateQuote:
    """Create one deterministic fiat or crypto exchange-rate quote."""
    base_currency = base_currency.upper()
    quote_currency = quote_currency.upper()
    if not base_currency or not quote_currency or base_currency == quote_currency:
        raise ValueError("base and quote currencies must be nonempty and differ")
    kind = InstrumentKind.CRYPTO_PAIR if crypto else InstrumentKind.FIAT_PAIR
    label = f"{base_currency}/{quote_currency}"
    return ExchangeRateQuote(
        provider_instrument_id("synthetic", kind, label),
        "synthetic",
        base_currency,
        quote_currency,
        1.25,
        1.24,
        1.26,
        SYNTHETIC_NOW,
        "UTC",
        SYNTHETIC_NOW,
        metadata("exchange_rate"),
    )


def commodity_spot(metal: str = "gold") -> CommoditySpotQuote:
    """Create one deterministic precious-metal spot quote."""
    normalized = metal.lower()
    if normalized not in {"gold", "silver"}:
        raise ValueError("metal must be gold or silver")
    return CommoditySpotQuote(
        provider_series_id("synthetic", f"{normalized}_spot", "spot"),
        "synthetic",
        normalized,
        2_400.0 if normalized == "gold" else 30.0,
        "USD per troy ounce",
        SYNTHETIC_NOW,
        SYNTHETIC_NOW,
        metadata("commodity_spot"),
    )


def search(query: str = "DEMO") -> InstrumentSearchResult:
    """Create deterministic provider symbol-search matches."""
    frame = typed_frame(
        {
            "provider_symbol": [query.upper()],
            "name": [f"{query.title()} Corporation"],
            "provider_type": ["Equity"],
            "region": ["United States"],
            "market_open": ["09:30"],
            "market_close": ["16:00"],
            "timezone": ["UTC-04"],
            "currency": ["USD"],
            "match_score": [1.0],
        },
        SEARCH_DTYPES,
    )
    return InstrumentSearchResult(query, frame, metadata("search"))


def market_status() -> MarketStatusResult:
    """Create one deterministic market-status result."""
    frame = typed_frame(
        {
            "market_type": ["Equity"],
            "region": ["United States"],
            "primary_exchanges": ["NASDAQ, NYSE"],
            "local_open": ["09:30"],
            "local_close": ["16:00"],
            "current_status": ["open"],
            "notes": [pd.NA],
            "retrieved_at": [SYNTHETIC_NOW],
        },
        MARKET_STATUS_DTYPES,
    )
    return MarketStatusResult(frame, metadata("market_status"))


def index_catalog() -> IndexCatalogResult:
    """Create deterministic provider index-catalog rows."""
    symbols = ("COMP", "DJI", "NDX", "RUT", "SPX", "VIX")
    frame = typed_frame(
        {
            "provider_symbol": symbols,
            "name": [f"Synthetic {symbol}" for symbol in symbols],
            "market": ["United States"] * len(symbols),
            "currency": ["USD"] * len(symbols),
            "provider_type": ["index"] * len(symbols),
        },
        INDEX_CATALOG_DTYPES,
    )
    return IndexCatalogResult(frame, metadata("index_catalog"))


def treasury_curve(
    maturities: tuple[str, ...] = ("3month", "2year", "5year", "10year", "30year"),
    *,
    periods: int = 12,
) -> tuple[SeriesSet, ...]:
    """Create Treasury series while allowing explicitly missing maturities."""
    supported = {"3month", "2year", "5year", "7year", "10year", "30year"}
    if not maturities or not set(maturities) <= supported:
        raise ValueError("maturities must contain supported Treasury labels")
    return tuple(
        series(
            f"TREASURY_YIELD:{maturity}",
            periods=periods,
            frequency="monthly",
            kind=SeriesKind.ECONOMIC,
            unit="percent",
            maturity=maturity,
        )
        for maturity in maturities
    )
