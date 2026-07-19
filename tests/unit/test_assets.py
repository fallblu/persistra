from __future__ import annotations

import pytest

from persistra.domain import AssetClass


def test_asset_class_members_are_stable() -> None:
    assert [member.value for member in AssetClass] == [
        "equity",
        "fx",
        "crypto",
        "commodity",
        "index",
        "rate",
        "macro",
    ]


@pytest.mark.parametrize(
    ("asset_class", "expected"),
    [
        (AssetClass.EQUITY, False),
        (AssetClass.FX, True),
        (AssetClass.CRYPTO, True),
        (AssetClass.COMMODITY, False),
        (AssetClass.INDEX, False),
        (AssetClass.RATE, False),
        (AssetClass.MACRO, False),
    ],
)
def test_pair_shaped_classes(asset_class: AssetClass, expected: bool) -> None:
    assert asset_class.is_pair_shaped is expected


@pytest.mark.parametrize(
    ("asset_class", "expected"),
    [
        (AssetClass.EQUITY, False),
        (AssetClass.FX, True),
        (AssetClass.CRYPTO, True),
        (AssetClass.COMMODITY, False),
        (AssetClass.INDEX, False),
        (AssetClass.RATE, False),
        (AssetClass.MACRO, False),
    ],
)
def test_continuous_trading_classes(asset_class: AssetClass, expected: bool) -> None:
    assert asset_class.is_continuous_trading is expected


@pytest.mark.parametrize(
    ("asset_class", "expected"),
    [
        (AssetClass.EQUITY, True),
        (AssetClass.FX, False),
        (AssetClass.CRYPTO, False),
        (AssetClass.COMMODITY, False),
        (AssetClass.INDEX, False),
        (AssetClass.RATE, False),
        (AssetClass.MACRO, False),
    ],
)
def test_venue_listed_classes(asset_class: AssetClass, expected: bool) -> None:
    assert asset_class.is_venue_listed is expected


def test_asset_class_round_trips_from_text() -> None:
    assert AssetClass("fx") is AssetClass.FX
    assert str(AssetClass.CRYPTO) == "crypto"


def test_every_security_kind_maps_to_an_asset_class() -> None:
    from persistra.reference import SecurityKind

    mapped = {kind: kind.asset_class for kind in SecurityKind}
    assert mapped[SecurityKind.COMMON_STOCK] is AssetClass.EQUITY
    assert mapped[SecurityKind.ETF] is AssetClass.EQUITY
    assert mapped[SecurityKind.REIT] is AssetClass.EQUITY
    assert mapped[SecurityKind.ADR] is AssetClass.EQUITY
    assert mapped[SecurityKind.SPAC_COMMON] is AssetClass.EQUITY
    assert mapped[SecurityKind.PREFERRED_STOCK] is AssetClass.EQUITY
    assert mapped[SecurityKind.CLOSED_END_FUND] is AssetClass.EQUITY
    assert mapped[SecurityKind.FX_PAIR] is AssetClass.FX
    assert mapped[SecurityKind.CRYPTO_PAIR] is AssetClass.CRYPTO
    assert mapped[SecurityKind.COMMODITY] is AssetClass.COMMODITY
    assert mapped[SecurityKind.INDEX] is AssetClass.INDEX


def test_pair_kinds_are_pair_shaped() -> None:
    from persistra.reference import SecurityKind

    for kind in SecurityKind:
        if kind in {SecurityKind.FX_PAIR, SecurityKind.CRYPTO_PAIR}:
            assert kind.asset_class.is_pair_shaped
        else:
            assert not kind.asset_class.is_pair_shaped
