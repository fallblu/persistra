"""Configured focused FRED and ALFRED client."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Self

from persistra.data.cache import RawResponseCache
from persistra.data.fred._common import AdapterContext
from persistra.data.fred.discovery import DiscoveryNamespace
from persistra.data.fred.series import SeriesNamespace
from persistra.data.fred.transport import FredTransport, SessionLike

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import timedelta

API_KEY_ENV = "PERSISTRA_FRED_API_KEY"


class FredClient:
    """A synchronous client for source-level FRED discovery and ALFRED series data."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.stlouisfed.org/fred",
        cache_directory: str | Path | None = None,
        timeout: float = 30,
        strict_schema: bool = False,
        cache_ages: Mapping[str, timedelta | None] | None = None,
        session: SessionLike | None = None,
    ) -> None:
        configured_cache_ages = dict(cache_ages or {})
        if any(
            age is not None and age.total_seconds() < 0 for age in configured_cache_ages.values()
        ):
            raise ValueError("cache ages must be nonnegative")
        cache = RawResponseCache(None if cache_directory is None else Path(cache_directory))
        transport = FredTransport(
            api_key,
            base_url=base_url,
            session=session,
            cache=cache,
            timeout=timeout,
        )
        self._transport = transport
        context = AdapterContext(transport, strict_schema, configured_cache_ages)
        self.discovery = DiscoveryNamespace(context)
        self.series = SeriesNamespace(context)

    def close(self) -> None:
        """Close the client and its Persistra-owned HTTP session."""
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str = "https://api.stlouisfed.org/fred",
        cache_directory: str | Path | None = None,
        timeout: float = 30,
        strict_schema: bool = False,
        cache_ages: Mapping[str, timedelta | None] | None = None,
        session: SessionLike | None = None,
    ) -> Self:
        """Create a client from ``PERSISTRA_FRED_API_KEY``."""
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise ValueError(f"{API_KEY_ENV} is not set")
        return cls(
            api_key,
            base_url=base_url,
            cache_directory=cache_directory,
            timeout=timeout,
            strict_schema=strict_schema,
            cache_ages=cache_ages,
            session=session,
        )

    @classmethod
    def from_cache(
        cls,
        *,
        cache_directory: str | Path | None = None,
        strict_schema: bool = False,
        cache_ages: Mapping[str, timedelta | None] | None = None,
    ) -> Self:
        """Create a credential-free client for raw-cache replay."""
        return cls(
            None,
            cache_directory=cache_directory,
            strict_schema=strict_schema,
            cache_ages=cache_ages,
        )
