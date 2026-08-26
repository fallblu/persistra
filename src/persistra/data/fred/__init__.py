"""Focused FRED and ALFRED series support."""

from persistra.data.fred.client import FredClient
from persistra.data.fred.discovery import (
    DiscoveryNamespace,
    FredCategory,
    FredRelease,
    FredSeriesCategoriesResult,
    FredSeriesReleaseResult,
    FredSeriesSearchResult,
    FredSeriesSummary,
    FredSeriesTagsResult,
    FredTag,
)
from persistra.data.fred.transport import FredTransport

__all__ = [
    "DiscoveryNamespace",
    "FredCategory",
    "FredClient",
    "FredRelease",
    "FredSeriesCategoriesResult",
    "FredSeriesReleaseResult",
    "FredSeriesSearchResult",
    "FredSeriesSummary",
    "FredSeriesTagsResult",
    "FredTag",
    "FredTransport",
]
