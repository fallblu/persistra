from __future__ import annotations

from datetime import UTC, date, datetime

from persistra.domain import AssetClass
from persistra.reference import (
    SYNTHETIC_OTC_VENUE_ID,
    SecurityKind,
    market_convention_issuer_id,
)
from persistra.sources.alphavantage.pairs import (
    crypto_pair_instrument,
    fx_pair_instrument,
    utc_day_sessions,
)

_FROM = datetime(2025, 12, 1, tzinfo=UTC)


def test_crypto_pair_instrument_uses_pair_conventions() -> None:
    pair = crypto_pair_instrument("btc", "eur", valid_from=_FROM)
    assert pair.security_kind is SecurityKind.CRYPTO_PAIR
    assert pair.asset_class is AssetClass.CRYPTO
    assert pair.issuer_id == market_convention_issuer_id(AssetClass.CRYPTO)
    assert pair.venue_id == SYNTHETIC_OTC_VENUE_ID
    assert pair.base_currency == "BTC"
    assert pair.quote_currency == "EUR"
    assert pair.currency == "EUR"
    assert pair.mic == ""
    assert pair.timezone_name == "UTC"


def test_crypto_pair_identities_are_deterministic_per_pair() -> None:
    first = crypto_pair_instrument("BTC", "EUR", valid_from=_FROM)
    second = crypto_pair_instrument("BTC", "EUR", valid_from=_FROM)
    other = crypto_pair_instrument("ETH", "EUR", valid_from=_FROM)
    assert first.instrument_id == second.instrument_id
    assert first.security_id == second.security_id
    assert first.listing_id == second.listing_id
    assert first.instrument_id != other.instrument_id


def test_fx_pair_instrument_uses_pair_conventions() -> None:
    pair = fx_pair_instrument("eur", "usd", valid_from=_FROM)
    assert pair.security_kind is SecurityKind.FX_PAIR
    assert pair.asset_class is AssetClass.FX
    assert pair.issuer_id == market_convention_issuer_id(AssetClass.FX)
    assert pair.venue_id == SYNTHETIC_OTC_VENUE_ID
    assert pair.base_currency == "EUR"
    assert pair.quote_currency == "USD"
    assert pair.currency == "USD"
    assert pair.mic == ""
    assert pair.timezone_name == "UTC"


def test_fx_pair_identities_are_deterministic_and_distinct_from_crypto() -> None:
    first = fx_pair_instrument("EUR", "USD", valid_from=_FROM)
    second = fx_pair_instrument("EUR", "USD", valid_from=_FROM)
    crypto = crypto_pair_instrument("EUR", "USD", valid_from=_FROM)
    assert first.instrument_id == second.instrument_id
    assert first.instrument_id != crypto.instrument_id
    assert first.issuer_id != crypto.issuer_id


def test_utc_day_sessions_match_the_synthetic_calendars() -> None:
    continuous = utc_day_sessions(date(2026, 1, 2), date(2026, 1, 6))
    assert sorted(continuous) == [
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
        date(2026, 1, 5),
    ]
    open_at, close_at = continuous[date(2026, 1, 3)]
    assert open_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert close_at == datetime(2026, 1, 4, tzinfo=UTC)
    weekdays = utc_day_sessions(
        date(2026, 1, 2), date(2026, 1, 6), weekdays_only=True
    )
    assert sorted(weekdays) == [date(2026, 1, 2), date(2026, 1, 5)]
