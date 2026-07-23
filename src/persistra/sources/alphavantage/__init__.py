"""This package contains the Alpha Vantage adapter and its live HTTP client.

The package root re-exports the client and the workflow entry points. These entry points support
registration, ingestion, and pair-instrument conventions. The endpoint parser submodules are
``equity``, ``pairs``, ``macro``, ``rates``, and ``indices``."""

from persistra.sources.alphavantage.client import (
    API_KEY_ENVIRONMENT_VARIABLE,
    DEFAULT_BASE_URL,
    DEFAULT_REQUESTS_PER_MINUTE,
    AlphaVantageClient,
    TokenBucketRateLimiter,
    TransportResponse,
)
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    IngestReport,
    ParsedFamilyBatch,
)
from persistra.sources.alphavantage.pairs import (
    crypto_pair_instrument,
    fx_pair_instrument,
    utc_day_sessions,
)
from persistra.sources.alphavantage.registration import (
    ALPHAVANTAGE_SOURCE,
    register_alphavantage,
)

__all__ = [
    "ALPHAVANTAGE_SOURCE",
    "API_KEY_ENVIRONMENT_VARIABLE",
    "DEFAULT_BASE_URL",
    "DEFAULT_REQUESTS_PER_MINUTE",
    "AlphaVantageClient",
    "AlphaVantageIngestor",
    "IngestReport",
    "ParsedFamilyBatch",
    "TokenBucketRateLimiter",
    "TransportResponse",
    "crypto_pair_instrument",
    "fx_pair_instrument",
    "register_alphavantage",
    "utc_day_sessions",
]
