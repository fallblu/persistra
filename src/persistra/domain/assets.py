"""Asset-class taxonomy shared by reference, market, and source subsystems."""

from __future__ import annotations

from enum import StrEnum


class AssetClass(StrEnum):
    """Top-level asset-class vocabulary for instruments and source series."""

    EQUITY = "equity"
    FX = "fx"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    INDEX = "index"
    RATE = "rate"
    MACRO = "macro"

    @property
    def is_pair_shaped(self) -> bool:
        """Return whether instruments quote one currency against another."""
        return self in _PAIR_SHAPED

    @property
    def is_continuous_trading(self) -> bool:
        """Return whether trading runs around the clock instead of venue sessions."""
        return self in _CONTINUOUS_TRADING

    @property
    def is_venue_listed(self) -> bool:
        """Return whether instruments trade on an identified exchange venue."""
        return self in _VENUE_LISTED


_PAIR_SHAPED = frozenset({AssetClass.FX, AssetClass.CRYPTO})
_CONTINUOUS_TRADING = frozenset({AssetClass.FX, AssetClass.CRYPTO})
_VENUE_LISTED = frozenset({AssetClass.EQUITY})
