"""This module contains the standard-library Alpha Vantage HTTP client. The client has rate limits
and bounded retries.

The client reads the API key from ``PERSISTRA_ALPHAVANTAGE_API_KEY``. The client does not put
the key in log context or error messages. :mod:`persistra.logging` uses field names for
redaction. Thus, do not put the raw key in message text."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from persistra.errors import (
    SourceCredentialError,
    SourceRateLimitError,
    SourceResponseError,
    SourceTransportError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

API_KEY_ENVIRONMENT_VARIABLE = "PERSISTRA_ALPHAVANTAGE_API_KEY"
DEFAULT_BASE_URL = "https://www.alphavantage.co/query"
DEFAULT_REQUESTS_PER_MINUTE = 75
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """This class represents the raw HTTP outcome that a transport callable returns."""

    status: int
    body: bytes


def _urllib_transport(url: str, timeout_seconds: float) -> TransportResponse:
    request = urllib.request.Request(url, headers={"User-Agent": "persistra"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return TransportResponse(int(response.status), response.read())
    except urllib.error.HTTPError as error:
        return TransportResponse(int(error.code), error.read())


class TokenBucketRateLimiter:
    """This class controls calls for a fixed request budget for each minute.

    An internal lock serializes ``acquire``. Thus, threads can share one limiter and one client
    without an excessive request rate."""

    __slots__ = (
        "_capacity",
        "_clock",
        "_lock",
        "_refill_per_second",
        "_sleep",
        "_tokens",
        "_updated_at",
    )

    def __init__(
        self,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute < 1:
            raise SourceTransportError("rate limiter requires a positive request budget")
        self._capacity = float(requests_per_minute)
        self._refill_per_second = requests_per_minute / 60.0
        self._tokens = float(requests_per_minute)
        self._clock = clock
        self._sleep = sleep
        self._updated_at = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until one request token is available, then consume it."""
        with self._lock:
            now = self._clock()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._updated_at) * self._refill_per_second,
            )
            self._updated_at = now
            if self._tokens < 1.0:
                self._sleep((1.0 - self._tokens) / self._refill_per_second)
                self._tokens = 1.0
                self._updated_at = self._clock()
            self._tokens -= 1.0


class AlphaVantageClient:
    """This class represents the rate-limited JSON client for the Alpha Vantage query endpoint."""

    __slots__ = (
        "_api_key",
        "_backoff_seconds",
        "_base_url",
        "_limiter",
        "_max_attempts",
        "_sleep",
        "_timeout_seconds",
        "_transport",
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
        transport: Callable[[str, float], TransportResponse] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved = api_key or os.environ.get(API_KEY_ENVIRONMENT_VARIABLE)
        if not resolved:
            raise SourceCredentialError(
                f"alpha vantage api key is missing; set {API_KEY_ENVIRONMENT_VARIABLE}"
            )
        if max_attempts < 1 or timeout_seconds <= 0 or backoff_seconds < 0:
            raise SourceTransportError("alpha vantage client limits are invalid")
        self._api_key = resolved
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._transport = transport or _urllib_transport
        self._limiter = TokenBucketRateLimiter(
            requests_per_minute, clock=clock, sleep=sleep
        )
        self._sleep = sleep

    def get(self, function: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Fetch the decoded JSON object of one endpoint. Retry transient failures."""
        payload = self._fetch(function, params, json_expected=True)
        return cast("dict[str, Any]", payload)

    def get_csv(self, function: str, params: Mapping[str, str] | None = None) -> str:
        """Fetch the text of one CSV endpoint. Retry transient failures.

        Alpha Vantage reports CSV endpoint errors as JSON envelopes. The client detects
        these envelopes and raises typed errors.
        """
        body = self._fetch(function, params, json_expected=False)
        return cast("bytes", body).decode("utf-8", errors="replace")

    def _fetch(
        self,
        function: str,
        params: Mapping[str, str] | None,
        *,
        json_expected: bool,
    ) -> dict[str, Any] | bytes:
        if not function:
            raise SourceResponseError("alpha vantage function name is required")
        query = dict(params or {})
        query["function"] = function
        query["apikey"] = self._api_key
        url = f"{self._base_url}?{urllib.parse.urlencode(query)}"
        throttled = False
        for attempt in range(1, self._max_attempts + 1):
            self._limiter.acquire()
            try:
                response = self._transport(url, self._timeout_seconds)
            except (OSError, urllib.error.URLError):
                response = None
            if response is not None:
                if response.status == 200:
                    if not json_expected and not response.body.lstrip().startswith(
                        b"{"
                    ):
                        return response.body
                    payload = self._decode(function, response.body)
                    envelope = self._envelope_state(payload)
                    if envelope is None:
                        if not json_expected:
                            raise SourceResponseError(
                                f"alpha vantage {function} response is not CSV"
                            )
                        return payload
                    if envelope == "error":
                        raise SourceResponseError(
                            f"alpha vantage rejected the {function} request"
                        )
                    throttled = True
                elif response.status not in _RETRYABLE_STATUSES:
                    raise SourceTransportError(
                        f"alpha vantage {function} request failed "
                        f"with status {response.status}"
                    )
                elif response.status == 429:
                    throttled = True
            if attempt < self._max_attempts:
                self._sleep(self._backoff_seconds * (2.0 ** (attempt - 1)))
        if throttled:
            raise SourceRateLimitError(
                f"alpha vantage {function} request stayed rate limited "
                f"after {self._max_attempts} attempts"
            )
        raise SourceTransportError(
            f"alpha vantage {function} request failed after {self._max_attempts} attempts"
        )

    @staticmethod
    def _decode(function: str, body: bytes) -> dict[str, Any]:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as cause:
            raise SourceResponseError(
                f"alpha vantage {function} response is not valid JSON"
            ) from cause
        if not isinstance(decoded, dict):
            raise SourceResponseError(
                f"alpha vantage {function} response is not a JSON object"
            )
        return cast("dict[str, Any]", decoded)

    @staticmethod
    def _envelope_state(payload: dict[str, Any]) -> str | None:
        if "Error Message" in payload:
            return "error"
        if "Note" in payload or "Information" in payload:
            return "throttled"
        return None
