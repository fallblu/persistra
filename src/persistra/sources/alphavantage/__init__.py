"""Alpha Vantage adapter: live HTTP client feeding typed canonical services."""

from persistra.sources.alphavantage.client import (
    API_KEY_ENVIRONMENT_VARIABLE,
    DEFAULT_BASE_URL,
    DEFAULT_REQUESTS_PER_MINUTE,
    AlphaVantageClient,
    TokenBucketRateLimiter,
    TransportResponse,
)

__all__ = [
    "API_KEY_ENVIRONMENT_VARIABLE",
    "DEFAULT_BASE_URL",
    "DEFAULT_REQUESTS_PER_MINUTE",
    "AlphaVantageClient",
    "TokenBucketRateLimiter",
    "TransportResponse",
]
