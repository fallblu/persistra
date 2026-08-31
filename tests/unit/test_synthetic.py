"""Tests for deterministic offline research data."""

from datetime import date

import pandas as pd
import pytest

from persistra.data import synthetic
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    InstrumentKind,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    SeriesSet,
    TopOfBookSet,
)


def test_synthetic_bars_are_deterministic_and_have_regimes() -> None:
    first = synthetic.bars(periods=20, seed=2)
    second = synthetic.bars(periods=20, seed=2)
    assert isinstance(first, BarSet)
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert first.frame.iloc[10:]["volume"].mean() > first.frame.iloc[:10]["volume"].mean()


def test_synthetic_intraday_uses_utc_instants() -> None:
    result = synthetic.bars(interval="5min", periods=2, session="regular", adjusted=True)
    assert result.frame["date"].isna().all()
    assert result.frame["timestamp"].notna().all()
    assert set(result.frame["timestamp_position"]) == {"unspecified"}
    assert result.frame["provider_timestamp_label"].tolist() == [
        "2025-01-01 00:00:00",
        "2025-01-02 00:00:00",
    ]
    assert set(result.frame["session"]) == {"regular"}
    assert set(result.frame["price_adjustment"]) == {"adjusted"}


def test_synthetic_adjusted_daily_fields_are_applicable() -> None:
    result = synthetic.bars(periods=2, adjusted=True)
    assert result.frame["adjusted_close"].notna().all()
    assert result.frame["dividend_amount"].eq(0).all()


def test_synthetic_families_are_typed() -> None:
    assert isinstance(synthetic.quotes(), QuoteSet)
    assert isinstance(synthetic.top_of_book(), TopOfBookSet)
    assert isinstance(synthetic.option_chain(), OptionChain)
    assert isinstance(synthetic.series(), SeriesSet)
    assert isinstance(synthetic.exchange_rate(), ExchangeRateQuote)
    assert isinstance(synthetic.exchange_rate("BTC", "USD", crypto=True), ExchangeRateQuote)
    assert isinstance(synthetic.commodity_spot(), CommoditySpotQuote)
    assert isinstance(synthetic.search(), InstrumentSearchResult)
    assert isinstance(synthetic.market_status(), MarketStatusResult)
    assert isinstance(synthetic.index_catalog(), IndexCatalogResult)
    assert len(synthetic.option_chain().contracts) == 12
    curve = synthetic.treasury_curve()
    assert len(curve) == 5
    assert {item.definition.maturity for item in curve} == {
        "3month",
        "2year",
        "5year",
        "10year",
        "30year",
    }


def test_synthetic_supports_empty_inputs() -> None:
    assert synthetic.quotes(()).frame.empty
    assert synthetic.top_of_book(()).frame.empty
    assert synthetic.series(periods=0).frame.empty
    with pytest.raises(ValueError, match="nonnegative"):
        synthetic.bars(periods=-1)
    with pytest.raises(ValueError, match="session"):
        synthetic.bars(interval="5min", session="not_applicable")


def test_synthetic_preserves_requested_identity() -> None:
    bars = synthetic.bars("PAIR", kind=InstrumentKind.CRYPTO_PAIR)
    assert bars.instrument.kind is InstrumentKind.CRYPTO_PAIR
    assert synthetic.option_chain(chain_date=date(2024, 3, 1)).chain_date == date(2024, 3, 1)
