"""Tests for provider-neutral identities and mappings."""

import pytest

from persistra.model import (
    Catalog,
    Instrument,
    InstrumentKind,
    OptionContract,
    OptionType,
    ProviderSymbol,
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


def test_option_contract_requires_positive_strike() -> None:
    with pytest.raises(ValueError, match="positive"):
        OptionContract("id", "provider", "underlying", "2025-01-01", 0, OptionType.CALL)


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
