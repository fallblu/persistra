"""Massive (formerly Polygon) SDK-backed ingest."""

from persistra.providers.massive.actions import fetch_dividends, fetch_splits, ingest_actions
from persistra.providers.massive.aggregates import (
    fetch_aggregates,
    ingest_aggregates,
    parse_timeframe,
)
from persistra.providers.massive.client import make_client
from persistra.providers.massive.flat_files import ingest_flat_files
from persistra.providers.massive.reference import build_universe, fetch_tickers
from persistra.providers.massive.session_filter import filter_regular_hours

__all__ = [
    "build_universe",
    "fetch_aggregates",
    "fetch_dividends",
    "fetch_splits",
    "fetch_tickers",
    "filter_regular_hours",
    "ingest_actions",
    "ingest_aggregates",
    "ingest_flat_files",
    "make_client",
    "parse_timeframe",
]
