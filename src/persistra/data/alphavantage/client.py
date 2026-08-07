"""Configured namespaced Alpha Vantage client."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from persistra.data.alphavantage._common import AdapterContext
from persistra.data.alphavantage.commodities import CommoditiesNamespace
from persistra.data.alphavantage.economics import EconomicsNamespace
from persistra.data.alphavantage.indices import IndicesNamespace
from persistra.data.alphavantage.pairs import PairNamespace
from persistra.data.alphavantage.quotes import QuotesNamespace
from persistra.data.alphavantage.reference import ReferenceNamespace
from persistra.data.alphavantage.securities import SecuritiesNamespace
from persistra.data.alphavantage.transport import (
    AlphaVantageTransport,
    SessionLike,
    TokenRateLimiter,
)
from persistra.data.cache import RawResponseCache

API_KEY_ENV = "PERSISTRA_ALPHAVANTAGE_API_KEY"


class AlphaVantageClient:
    """A synchronous client for supported Alpha Vantage primary datasets."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://www.alphavantage.co/query",
        cache_directory: str | Path | None = None,
        requests_per_minute: float = 150,
        timeout: float = 30,
        strict_schema: bool = False,
        session: SessionLike | None = None,
        limiter: TokenRateLimiter | None = None,
        transport_options: dict[str, Any] | None = None,
    ) -> None:
        cache = RawResponseCache(None if cache_directory is None else Path(cache_directory))
        options = dict(transport_options or {})
        transport = AlphaVantageTransport(
            api_key,
            base_url=base_url,
            session=session,
            cache=cache,
            limiter=limiter or TokenRateLimiter(requests_per_minute),
            timeout=timeout,
            **options,
        )
        context = AdapterContext(transport, strict_schema)
        self.securities = SecuritiesNamespace(context)
        self.quotes = QuotesNamespace(context)
        self.indices = IndicesNamespace(context)
        self.fx = PairNamespace(context, crypto=False)
        self.crypto = PairNamespace(context, crypto=True)
        self.commodities = CommoditiesNamespace(context)
        self.economics = EconomicsNamespace(context)
        self.reference = ReferenceNamespace(context)

    @classmethod
    def from_env(cls, **options: Any) -> AlphaVantageClient:
        """Create a client from the Persistra Alpha Vantage API-key variable."""
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise ValueError(f"{API_KEY_ENV} is not set")
        return cls(api_key, **options)
