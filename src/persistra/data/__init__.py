"""Acquisition capabilities and offline synthetic data."""

from persistra.data import synthetic
from persistra.data.alphavantage import AlphaVantageClient
from persistra.data.cache import RawCacheEntry, RawResponseCache
from persistra.data.protocols import (
    BarSource,
    OptionChainSource,
    QuoteSource,
    ReferenceSource,
    ScalarSeriesSource,
)
from persistra.data.store import DuckDBStore
from persistra.data.utils import align, asof_align, pivot_bars, pivot_series, resample_bars

__all__ = [
    "AlphaVantageClient",
    "BarSource",
    "DuckDBStore",
    "OptionChainSource",
    "QuoteSource",
    "RawCacheEntry",
    "RawResponseCache",
    "ReferenceSource",
    "ScalarSeriesSource",
    "align",
    "asof_align",
    "pivot_bars",
    "pivot_series",
    "resample_bars",
    "synthetic",
]
