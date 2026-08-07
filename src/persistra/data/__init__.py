"""Acquisition capabilities and offline synthetic data."""

from persistra.data import synthetic
from persistra.data.protocols import (
    BarSource,
    OptionChainSource,
    QuoteSource,
    ReferenceSource,
    ScalarSeriesSource,
)

__all__ = [
    "BarSource",
    "OptionChainSource",
    "QuoteSource",
    "ReferenceSource",
    "ScalarSeriesSource",
    "synthetic",
]
