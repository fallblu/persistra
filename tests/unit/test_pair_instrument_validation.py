from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from persistra.domain import AssetClass
from persistra.errors import ReferenceDefinitionError
from persistra.reference import (
    SYNTHETIC_OTC_VENUE_ID,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    ListingStatus,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    VenueId,
    market_convention_issuer_id,
)

_AT = datetime(2025, 1, 6, tzinfo=UTC)


def _pair(**overrides: object) -> InstrumentDefinition:
    values: dict[str, Any] = {
        "issuer_id": market_convention_issuer_id(AssetClass.FX),
        "security_id": SecurityId.new(),
        "venue_id": SYNTHETIC_OTC_VENUE_ID,
        "listing_id": ListingId.new(),
        "instrument_id": InstrumentId.new(),
        "mic": "",
        "timezone_name": "UTC",
        "security_kind": SecurityKind.FX_PAIR,
        "security_status": SecurityStatus.ACTIVE,
        "listing_status": ListingStatus.ACTIVE,
        "currency": "USD",
        "valid_from": _AT,
        "base_currency": "EUR",
        "quote_currency": "USD",
    }
    values.update(overrides)
    return InstrumentDefinition(**values)


def test_fx_pair_definition_resolves_asset_class() -> None:
    pair = _pair()
    assert pair.asset_class is AssetClass.FX
    assert pair.base_currency == "EUR"
    assert pair.quote_currency == "USD"
    assert pair.mic == ""


def test_crypto_pair_accepts_non_iso_base_asset() -> None:
    pair = _pair(
        issuer_id=market_convention_issuer_id(AssetClass.CRYPTO),
        security_kind=SecurityKind.CRYPTO_PAIR,
        base_currency="BTC",
        quote_currency="EUR",
        currency="EUR",
    )
    assert pair.asset_class is AssetClass.CRYPTO
    assert pair.base_currency == "BTC"


def test_pair_validation_rejects_invalid_shapes() -> None:
    with pytest.raises(ReferenceDefinitionError):
        _pair(base_currency=None)
    with pytest.raises(ReferenceDefinitionError):
        _pair(quote_currency=None)
    with pytest.raises(ReferenceDefinitionError):
        _pair(base_currency="USD")
    with pytest.raises(ReferenceDefinitionError):
        _pair(quote_currency="EUR")
    with pytest.raises(ReferenceDefinitionError):
        _pair(base_currency="ZZZ")
    with pytest.raises(ReferenceDefinitionError):
        _pair(mic="otc")
    with pytest.raises(ReferenceDefinitionError):
        _pair(asset_class=AssetClass.CRYPTO)
    with pytest.raises(ReferenceDefinitionError):
        _pair(
            issuer_id=market_convention_issuer_id(AssetClass.CRYPTO),
            security_kind=SecurityKind.CRYPTO_PAIR,
            base_currency="btc",
            quote_currency="USD",
        )


def test_equity_definition_rejects_pair_fields() -> None:
    with pytest.raises(ReferenceDefinitionError):
        InstrumentDefinition(
            IssuerId.new(),
            SecurityId.new(),
            VenueId.new(),
            ListingId.new(),
            InstrumentId.new(),
            "XNYS",
            "America/New_York",
            SecurityKind.COMMON_STOCK,
            SecurityStatus.ACTIVE,
            ListingStatus.ACTIVE,
            "USD",
            _AT,
            base_currency="EUR",
            quote_currency="USD",
        )


def test_equity_definition_accepts_non_usd_currency() -> None:
    definition = InstrumentDefinition(
        IssuerId.new(),
        SecurityId.new(),
        VenueId.new(),
        ListingId.new(),
        InstrumentId.new(),
        "XLON",
        "Europe/London",
        SecurityKind.COMMON_STOCK,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        "GBP",
        _AT,
    )
    assert definition.asset_class is AssetClass.EQUITY
    assert definition.currency == "GBP"


def test_market_convention_issuers_are_deterministic_per_class() -> None:
    assert market_convention_issuer_id(AssetClass.FX) == market_convention_issuer_id(
        AssetClass.FX
    )
    assert market_convention_issuer_id(AssetClass.FX) != market_convention_issuer_id(
        AssetClass.CRYPTO
    )
    with pytest.raises(ReferenceDefinitionError):
        market_convention_issuer_id(AssetClass.EQUITY)
