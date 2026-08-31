"""Shared synchronous Alpha Vantage transport."""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import TYPE_CHECKING, Any, Protocol, cast

import requests
from requests.exceptions import ChunkedEncodingError, ContentDecodingError

from persistra.data._retry import retry_after_seconds
from persistra.data.cache import RawCacheEntry, RawResponseCache
from persistra.errors import (
    AuthenticationError,
    CacheError,
    EntitlementError,
    NoDataError,
    RateLimitError,
    ResponseError,
    TransportError,
)
from persistra.model import CacheStatus

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger("persistra.alphavantage")


class _EmptyResponseError(ResponseError):
    """An empty provider object that can succeed on a later attempt."""


class ResponseLike(Protocol):
    """The response surface needed from Requests or a test double."""

    status_code: int
    content: bytes
    headers: dict[str, str]


class SessionLike(Protocol):
    """The synchronous HTTP surface needed by the transport."""

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> ResponseLike:
        """Issue one HTTP GET request."""
        ...


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Classified provider bytes ready for endpoint normalization."""

    body: bytes
    media_type: str
    retrieved_at: datetime
    cache_status: CacheStatus


class TokenRateLimiter:
    """A thread-safe request-token limiter with a smoothed default burst."""

    def __init__(
        self,
        requests_per_minute: float = 150,
        *,
        capacity: float = 1,
        clock: Callable[[], float] = time.monotonic,
        delay: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isfinite(requests_per_minute) or requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive and finite")
        if not isfinite(capacity) or capacity < 1:
            raise ValueError("capacity must be at least one request token and finite")
        self.rate = requests_per_minute / 60
        self.capacity = capacity
        self._tokens = capacity
        self._updated = clock()
        self._clock = clock
        self._delay = delay
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Wait until one request token is available."""
        while True:
            with self._lock:
                now = self._clock()
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self.rate
            self._delay(wait)


class AlphaVantageTransport:
    """Rate-controlled transport with cache, retry, and envelope classification."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://www.alphavantage.co/query",
        session: SessionLike | None = None,
        cache: RawResponseCache | None = None,
        limiter: TokenRateLimiter | None = None,
        timeout: float = 30,
        clock: Callable[[], datetime] | None = None,
        delay: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
        retries: int = 3,
    ) -> None:
        if api_key is not None and not api_key:
            raise ValueError("api_key must not be empty")
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries must be nonnegative")
        self.api_key = api_key
        self.base_url = base_url
        owned_session = requests.Session() if session is None else None
        self.session = session if session is not None else cast("SessionLike", owned_session)
        self._owned_session = owned_session
        self._closed = False
        self.cache = cache
        self.limiter = limiter or TokenRateLimiter()
        self.timeout = timeout
        self.clock = clock or (lambda: datetime.now(UTC))
        self.delay = delay
        self.random_source = random_source
        self.retries = retries

    def close(self) -> None:
        """Close the transport and its Persistra-owned HTTP session."""
        if self._closed:
            return
        self._closed = True
        if self._owned_session is not None:
            self._owned_session.close()

    def request(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        cache_age: timedelta | None = timedelta(hours=24),
        refresh: bool = False,
        offline: bool = False,
    ) -> RawResponse:
        """Return classified raw bytes for one provider operation."""
        if self._closed:
            raise RuntimeError("Alpha Vantage transport is closed")
        if refresh and offline:
            raise ValueError("refresh and offline cannot apply together")
        public_parameters = {"function": operation, **parameters}
        now = self.clock()
        if self.cache is not None and not refresh:
            cached = self.cache.get(
                "alpha_vantage",
                operation,
                public_parameters,
                now=now,
                max_age=cache_age,
                offline=offline,
            )
            if cached is not None:
                _classify(cached.body, operation)
                status = CacheStatus.OFFLINE if offline else CacheStatus.HIT
                return RawResponse(cached.body, cached.media_type, cached.retrieved_at, status)
        if offline:
            raise CacheError(f"offline cache miss for {operation}")
        response = self._network_request(operation, public_parameters)
        if self.cache is not None:
            self.cache.put(
                RawCacheEntry(
                    response.body,
                    response.media_type,
                    response.retrieved_at,
                    "alpha_vantage",
                    operation,
                    public_parameters,
                )
            )
            status = CacheStatus.REFRESHED if refresh else CacheStatus.MISS
            return RawResponse(response.body, response.media_type, response.retrieved_at, status)
        return response

    def _network_request(self, operation: str, parameters: dict[str, Any]) -> RawResponse:
        if self.api_key is None:
            raise AuthenticationError(
                f"Alpha Vantage credentials are required for network request {operation}"
            )
        request_parameters = {**parameters, "apikey": self.api_key}
        for attempt in range(self.retries + 1):
            self.limiter.acquire()
            started = time.monotonic()
            try:
                response = self.session.get(
                    self.base_url,
                    params=request_parameters,
                    timeout=self.timeout,
                )
                retryable_http = response.status_code == 429 or response.status_code >= 500
                if retryable_http:
                    if attempt == self.retries:
                        if response.status_code == 429:
                            raise RateLimitError(f"rate limit exhausted for {operation}")
                        raise TransportError(f"server retries exhausted for {operation}")
                    self._backoff(attempt, response.headers.get("Retry-After"))
                    continue
                if response.status_code >= 400:
                    raise ResponseError(f"HTTP {response.status_code} for {operation}")
                try:
                    _classify(response.content, operation)
                except (RateLimitError, _EmptyResponseError):
                    if attempt == self.retries:
                        raise
                    self._backoff(attempt)
                    continue
                media_type = response.headers.get("Content-Type", "application/octet-stream")
                retrieved_at = self.clock()
                LOGGER.debug(
                    "provider request complete operation=%s attempt=%s elapsed=%.3f",
                    operation,
                    attempt + 1,
                    time.monotonic() - started,
                )
                return RawResponse(
                    response.content,
                    media_type.split(";", 1)[0],
                    retrieved_at,
                    CacheStatus.NOT_USED,
                )
            except (
                requests.ConnectionError,
                requests.Timeout,
                ChunkedEncodingError,
                ContentDecodingError,
            ) as error:
                if attempt == self.retries:
                    raise TransportError(f"transport retries exhausted for {operation}") from error
                self._backoff(attempt)
            except requests.RequestException as error:
                raise TransportError(f"request failed for {operation}") from error
        raise TransportError(f"transport retries exhausted for {operation}")

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        local_delay = min(8.0, 0.5 * (2**attempt)) + self.random_source() * 0.25
        provider_delay = retry_after_seconds(retry_after, now=self.clock())
        self.delay(max(local_delay, provider_delay or 0.0))


def _classify(body: bytes, operation: str) -> None:
    """Raise a typed exception for a provider error envelope."""
    stripped = body.lstrip()
    if stripped.startswith(b"["):
        raise ResponseError(f"malformed response envelope for {operation}")
    if not stripped.startswith(b"{"):
        return
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResponseError(f"malformed JSON response for {operation}") from error
    if not isinstance(payload, dict):
        raise ResponseError(f"malformed response envelope for {operation}")
    envelope = cast("dict[str, Any]", payload)
    if not envelope:
        raise _EmptyResponseError(f"empty response envelope for {operation}")
    message = str(
        envelope.get("Error Message") or envelope.get("Information") or envelope.get("Note") or ""
    )
    if not message:
        return
    lowered = message.lower()
    if "no data" in lowered or "no historical options" in lowered:
        raise NoDataError(f"no provider data for {operation}")
    if "api key" in lowered or "apikey" in lowered:
        raise AuthenticationError(f"authentication failed for {operation}")
    if "premium" in lowered or "entitlement" in lowered or "subscription" in lowered:
        raise EntitlementError(f"entitlement failed for {operation}")
    if "rate limit" in lowered or "call frequency" in lowered or "requests per" in lowered:
        raise RateLimitError(f"rate limit reached for {operation}")
    raise ResponseError(f"provider rejected {operation}")
