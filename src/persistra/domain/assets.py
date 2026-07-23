"""This module contains the asset-class taxonomy for the reference, market, and source
subsystems."""

from __future__ import annotations

from enum import StrEnum


class AssetClass(StrEnum):
    """This class represents the top-level asset-class vocabulary for instruments and source
    series."""

    EQUITY = "equity"
    FX = "fx"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    INDEX = "index"
    RATE = "rate"
    MACRO = "macro"

    @property
    def is_pair_shaped(self) -> bool:
        """Return true if instruments quote one currency against the other currency."""
        return self in _PAIR_SHAPED

    @property
    def is_continuous_trading(self) -> bool:
        """Return true if trading runs around the clock. Continuous trading does not use venue
        sessions."""
        return self in _CONTINUOUS_TRADING

    @property
    def is_venue_listed(self) -> bool:
        """Return true if instruments trade on an identified exchange venue."""
        return self in _VENUE_LISTED


_PAIR_SHAPED = frozenset({AssetClass.FX, AssetClass.CRYPTO})
_CONTINUOUS_TRADING = frozenset({AssetClass.FX, AssetClass.CRYPTO})
_VENUE_LISTED = frozenset({AssetClass.EQUITY})
