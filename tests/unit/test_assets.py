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
