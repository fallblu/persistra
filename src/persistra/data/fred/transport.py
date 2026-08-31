"""Synchronous FRED transport with raw caching and error normalization."""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast

import requests

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

LOGGER = logging.getLogger("persistra.fred")

_ENDPOINTS = {
    "series": "series",
    "series_categories": "series/categories",
    "series_observations": "series/observations",
    "series_release": "series/release",
    "series_search": "series/search",
    "series_tags": "series/tags",
    "series_vintagedates": "series/vintagedates",
}


class ResponseLike(Protocol):
    """The HTTP response surface used by the transport."""

    status_code: int
    content: bytes
    headers: dict[str, str]


class SessionLike(Protocol):
    """The synchronous HTTP session surface used by the transport."""

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> ResponseLike:
        """Issue one HTTP GET request."""
        ...


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Classified provider bytes ready for normalization."""

    body: bytes
    media_type: str
    retrieved_at: datetime
    cache_status: CacheStatus


class FredTransport:
    """FRED transport with raw caching, retries, and redacted failures."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.stlouisfed.org/fred",
        session: SessionLike | None = None,
        cache: RawResponseCache | None = None,
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
        self.base_url = base_url.rstrip("/")
        owned_session = requests.Session() if session is None else None
        self.session = session if session is not None else cast("SessionLike", owned_session)
        self._owned_session = owned_session
        self._closed = False
        self.cache = cache
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
        """Return classified bytes for one supported FRED operation."""
        if self._closed:
            raise RuntimeError("FRED transport is closed")
        if operation not in _ENDPOINTS:
            raise ValueError(f"unsupported FRED operation: {operation}")
        if refresh and offline:
            raise ValueError("refresh and offline cannot apply together")
        public_parameters = {**parameters, "file_type": "json"}
        now = self.clock()
        if self.cache is not None and not refresh:
            cached = self.cache.get(
                "fred",
                operation,
                public_parameters,
                now=now,
                max_age=cache_age,
                offline=offline,
            )
            if cached is not None:
                _classify(cached.body, operation, public_parameters, api_key=self.api_key)
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
                    "fred",
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
                f"FRED credentials are required for network request {operation}"
            )
        request_parameters = {**parameters, "api_key": self.api_key}
        url = f"{self.base_url}/{_ENDPOINTS[operation]}"
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                response = self.session.get(
                    url,
                    params=request_parameters,
                    timeout=self.timeout,
                )
            except requests.RequestException as error:
                if attempt == self.retries:
                    raise TransportError(f"request retries exhausted for {operation}") from error
                self._backoff(attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.retries:
                    if response.status_code == 429:
                        raise RateLimitError(f"rate limit exhausted for {operation}")
                    raise TransportError(f"server retries exhausted for {operation}")
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue
            if response.status_code >= 400:
                _raise_http_error(
                    response.status_code,
                    response.content,
                    operation,
                    parameters,
                    api_key=self.api_key,
                )
            try:
                _classify(response.content, operation, parameters, api_key=self.api_key)
            except RateLimitError:
                if attempt == self.retries:
                    raise
                self._backoff(attempt)
                continue
            retrieved_at = self.clock()
            LOGGER.debug(
                "provider request complete operation=%s attempt=%s elapsed=%.3f",
                operation,
                attempt + 1,
                time.monotonic() - started,
            )
            return RawResponse(
                response.content,
                response.headers.get("Content-Type", "application/octet-stream"),
                retrieved_at,
                CacheStatus.NOT_USED,
            )
        raise AssertionError("unreachable retry loop")

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        local_delay = (2**attempt) + self.random_source()
        provider_delay = retry_after_seconds(retry_after, now=self.clock())
        self.delay(max(local_delay, provider_delay or 0.0))


def _raise_http_error(
    status_code: int,
    body: bytes,
    operation: str,
    parameters: dict[str, Any],
    *,
    api_key: str | None,
) -> None:
    message = _error_message(body)
    if status_code == 400 and "api_key" in message.lower():
        raise AuthenticationError(f"authentication failed for {operation}")
    if status_code == 404:
        raise NoDataError(f"no provider data for {operation}")
    if status_code == 423:
        raise EntitlementError(f"provider access is locked for {operation}")
    details = _error_details(body)
    raise _response_error(
        f"HTTP {status_code}",
        operation,
        parameters,
        http_status=status_code,
        provider_code=details[0],
        provider_message=details[1],
        api_key=api_key,
    )


def _classify(
    body: bytes,
    operation: str,
    parameters: dict[str, Any],
    *,
    api_key: str | None,
) -> None:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(value, dict) or "error_code" not in value:
        return
    payload = cast("dict[str, Any]", value)
    code = _error_code(payload["error_code"], operation, parameters, api_key=api_key)
    message = str(payload.get("error_message", ""))
    if code == 429:
        raise RateLimitError(f"rate limit response for {operation}")
    if code == 400 and "api_key" in message.lower():
        raise AuthenticationError(f"authentication failed for {operation}")
    if code == 404:
        raise NoDataError(f"no provider data for {operation}")
    if code == 423:
        raise EntitlementError(f"provider access is locked for {operation}")
    raise _response_error(
        f"provider error {code}",
        operation,
        parameters,
        provider_code=code,
        provider_message=message,
        api_key=api_key,
    )


def _error_code(
    value: object,
    operation: str,
    parameters: dict[str, Any],
    *,
    api_key: str | None,
) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit():
            return int(text)
    raise _response_error(
        "malformed provider error code",
        operation,
        parameters,
        api_key=api_key,
    )


def _error_message(body: bytes) -> str:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(value, dict):
        return ""
    return str(cast("dict[str, Any]", value).get("error_message", ""))


def _error_details(body: bytes) -> tuple[int | None, str]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ""
    if not isinstance(value, dict):
        return None, ""
    payload = cast("dict[str, Any]", value)
    raw_code = payload.get("error_code")
    code = raw_code if type(raw_code) is int else None
    if isinstance(raw_code, str) and raw_code.isascii() and raw_code.isdigit():
        code = int(raw_code)
    return code, str(payload.get("error_message", ""))


def _response_error(
    label: str,
    operation: str,
    parameters: dict[str, Any],
    *,
    http_status: int | None = None,
    provider_code: int | None = None,
    provider_message: str = "",
    api_key: str | None,
) -> ResponseError:
    context: dict[str, str | int] = {"operation": operation}
    series_id = parameters.get("series_id")
    if isinstance(series_id, str) and series_id.strip():
        context["series_id"] = " ".join(series_id.split())[:120]
    if http_status is not None:
        context["http_status"] = http_status
    if provider_code is not None:
        context["provider_code"] = provider_code
    safe_message = _bounded_provider_message(provider_message, api_key=api_key)
    if safe_message:
        context["provider_message"] = safe_message
    rendered = ", ".join(f"{key}={value}" for key, value in context.items())
    return ResponseError(f"{label} for {operation} ({rendered})", context=context)


def _bounded_provider_message(message: str, *, api_key: str | None) -> str:
    normalized = " ".join(message.split())
    lowered = normalized.lower()
    if any(marker in lowered for marker in ("api key", "api_key", "apikey")) or (
        api_key is not None and api_key.lower() in lowered
    ):
        return ""
    return normalized[:240]
