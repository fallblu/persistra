"""Tests for provider-neutral identities and mappings."""

from dataclasses import replace
from typing import cast

import pytest

from persistra.model import (
    Catalog,
    Instrument,
    InstrumentKind,
    Listing,
    OptionContract,
    OptionType,
    ProviderSymbol,
    SeriesDefinition,
    SeriesKind,
    provider_instrument_id,
    provider_series_id,
)


def test_provider_ids_are_stable_and_scoped() -> None:
    first = provider_instrument_id("alpha_vantage", InstrumentKind.EQUITY, "ibm")
    assert first == provider_instrument_id("alpha_vantage", InstrumentKind.EQUITY, "IBM")
    assert first != provider_instrument_id("another", InstrumentKind.EQUITY, "IBM")
    assert provider_series_id("alpha_vantage", "GDP", "annual") != provider_series_id(
        "alpha_vantage", "GDP", "quarterly"
    )


def test_instrument_validates_pair_fields() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Instrument("", InstrumentKind.EQUITY, "")
    with pytest.raises(ValueError, match="pair instruments"):
        Instrument("pair", InstrumentKind.FIAT_PAIR, "USD/EUR")
    with pytest.raises(ValueError, match="pair instruments"):
        Instrument("equity", InstrumentKind.EQUITY, "IBM", "USD", "EUR")
    pair = Instrument("pair", InstrumentKind.FIAT_PAIR, "USD/EUR", "USD", "EUR")
    assert pair.base_currency == "USD"
    with pytest.raises(ValueError, match="currencies must differ"):
        replace(pair, quote_currency="usd")


def test_identity_models_reject_blank_required_fields() -> None:
    instrument = Instrument("instrument", InstrumentKind.EQUITY, "Instrument")
    for field in ("instrument_id", "display_name"):
        with pytest.raises(ValueError, match=field):
            replace(instrument, **{field: " \t"})

    listing = Listing("listing", "instrument", "SYMBOL")
    for field in ("listing_id", "instrument_id", "symbol"):
        with pytest.raises(ValueError, match=field):
            replace(listing, **{field: " \t"})

    mapping = ProviderSymbol("provider", InstrumentKind.EQUITY, "SYMBOL", "instrument")
    for field in ("provider", "symbol", "instrument_id"):
        with pytest.raises(ValueError, match=field):
            replace(mapping, **{field: " \t"})

    contract = OptionContract(
        "contract", "provider", "instrument", "2025-01-01", 100.0, OptionType.CALL
    )
    for field in ("contract_id", "provider", "underlying_instrument_id", "expiration"):
        with pytest.raises(ValueError, match=field):
            replace(contract, **{field: " \t"})

    definition = SeriesDefinition(
        "series",
        SeriesKind.ECONOMIC,
        "Series",
        "provider",
        "PROVIDER_SERIES",
        "monthly",
        "index",
    )
    for field in ("series_id", "display_name", "provider", "provider_series", "frequency", "unit"):
        with pytest.raises(ValueError, match=field):
            replace(definition, **{field: " \t"})


def test_identity_models_reject_blank_optional_fields() -> None:
    listing = Listing("listing", "instrument", "SYMBOL")
    for field in ("exchange", "mic", "currency", "source_timezone"):
        with pytest.raises(ValueError, match=field):
            replace(listing, **{field: " "})

    mapping = ProviderSymbol("provider", InstrumentKind.EQUITY, "SYMBOL", "instrument")
    with pytest.raises(ValueError, match="listing_id"):
        replace(mapping, listing_id=" ")

    definition = SeriesDefinition(
        "series",
        SeriesKind.ECONOMIC,
        "Series",
        "provider",
        "PROVIDER_SERIES",
        "monthly",
        "index",
    )
    for field in ("geography", "seasonal_adjustment", "maturity"):
        with pytest.raises(ValueError, match=field):
            replace(definition, **{field: " "})

    pair = Instrument("pair", InstrumentKind.FIAT_PAIR, "USD/EUR", "USD", "EUR")
    with pytest.raises(ValueError, match="base_currency"):
        replace(pair, base_currency=" ")
    with pytest.raises(ValueError, match="quote_currency"):
        replace(pair, quote_currency=" ")


def test_identity_models_require_declared_enum_types() -> None:
    with pytest.raises(ValueError, match="InstrumentKind"):
        Instrument("instrument", cast("InstrumentKind", "equity"), "Instrument")
    with pytest.raises(ValueError, match="InstrumentKind"):
        ProviderSymbol("provider", cast("InstrumentKind", "equity"), "SYMBOL", "instrument")
    with pytest.raises(ValueError, match="SeriesKind"):
        SeriesDefinition(
            "series",
            cast("SeriesKind", "economic"),
            "Series",
            "provider",
            "PROVIDER_SERIES",
            "monthly",
            "index",
        )
    with pytest.raises(ValueError, match="OptionType"):
        OptionContract(
            "contract",
            "provider",
            "instrument",
            "2025-01-01",
            100.0,
            cast("OptionType", "call"),
        )


@pytest.mark.parametrize("strike", [float("nan"), float("inf"), float("-inf")])
def test_option_contract_requires_finite_strike(strike: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        OptionContract("id", "provider", "underlying", "2025-01-01", strike, OptionType.CALL)


@pytest.mark.parametrize("strike", [0.0, -1.0])
def test_option_contract_requires_positive_strike(strike: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        OptionContract("id", "provider", "underlying", "2025-01-01", strike, OptionType.CALL)


def test_catalog_requires_explicit_consistent_mappings() -> None:
    catalog = Catalog()
    instrument = Instrument("canonical", InstrumentKind.EQUITY, "Example")
    mapping = ProviderSymbol("alpha_vantage", InstrumentKind.EQUITY, "EX", "canonical")
    with pytest.raises(ValueError, match="before"):
        catalog.map_provider_symbol(mapping)
    catalog.add_instrument(instrument)
    catalog.add_instrument(instrument)
    catalog.map_provider_symbol(mapping)
    catalog.map_provider_symbol(mapping)
    assert catalog.resolve("alpha_vantage", "equity", "EX") == instrument
    assert catalog.resolve("alpha_vantage", "equity", "MISSING") is None
    with pytest.raises(ValueError, match="different instrument"):
        catalog.add_instrument(Instrument("canonical", InstrumentKind.EQUITY, "Other"))
    catalog.add_instrument(Instrument("second", InstrumentKind.EQUITY, "Second"))
    with pytest.raises(ValueError, match="another instrument"):
        catalog.map_provider_symbol(
            ProviderSymbol("alpha_vantage", InstrumentKind.EQUITY, "EX", "second")
        )
