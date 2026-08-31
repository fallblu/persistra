"""Tests for Alpha Vantage transport behavior."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import requests
from requests.exceptions import ChunkedEncodingError, ContentDecodingError

from persistra.data._retry import retry_after_seconds
from persistra.data.alphavantage.transport import AlphaVantageTransport, TokenRateLimiter
from persistra.data.cache import RawResponseCache
from persistra.errors import (
    AuthenticationError,
    CacheError,
    EntitlementError,
    RateLimitError,
    ResponseError,
    TransportError,
)
from persistra.model import CacheStatus

VALID_BODY = b'{"data": []}'


@dataclass
class FakeResponse:
    """A minimal test response."""

    content: bytes
    status_code: int = 200
    headers: dict[str, str] = field(
        default_factory=lambda: {"Content-Type": "application/json; charset=utf-8"}
    )


class FakeSession:
    """A sequence-driven synchronous session."""

    def __init__(self, outcomes: list[FakeResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> FakeResponse:
        del url
        self.calls.append({"params": params, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def transport(
    outcomes: list[FakeResponse | Exception],
    *,
    cache: RawResponseCache | None = None,
    delays: list[float] | None = None,
) -> tuple[AlphaVantageTransport, FakeSession]:
    session = FakeSession(outcomes)
    client = AlphaVantageTransport(
        "secret",
        session=session,
        cache=cache,
        limiter=TokenRateLimiter(150, capacity=100),
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        delay=(delays if delays is not None else []).append,
        random_source=lambda: 0,
    )
    return client, session


def test_success_cache_hit_refresh_and_offline(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    outcomes: list[FakeResponse | Exception] = [
        FakeResponse(b'{"data": [1]}'),
        FakeResponse(b'{"data": [2]}'),
    ]
    client, session = transport(outcomes, cache=cache)
    first = client.request("TEST", {"symbol": "IBM"})
    assert first.cache_status is CacheStatus.MISS
    second = client.request("TEST", {"symbol": "IBM"})
    assert second.cache_status is CacheStatus.HIT
    offline = client.request("TEST", {"symbol": "IBM"}, offline=True)
    assert offline.cache_status is CacheStatus.OFFLINE
    refreshed = client.request("TEST", {"symbol": "IBM"}, refresh=True)
    assert refreshed.cache_status is CacheStatus.REFRESHED
    assert len(session.calls) == 2
    assert session.calls[0]["params"]["apikey"] == "secret"
    with pytest.raises(ValueError, match="cannot"):
        client.request("TEST", {}, refresh=True, offline=True)
    with pytest.raises(CacheError, match="offline"):
        client.request("MISSING", {}, offline=True)


def test_live_policy_writes_cache_but_does_not_reuse_it(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    client, session = transport(
        [FakeResponse(b'{"data": [1]}'), FakeResponse(b'{"data": [2]}')],
        cache=cache,
    )
    first = client.request("LIVE", {}, cache_age=None)
    second = client.request("LIVE", {}, cache_age=None)
    offline = client.request("LIVE", {}, cache_age=None, offline=True)
    assert first.body == b'{"data": [1]}'
    assert second.body == offline.body == b'{"data": [2]}'
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (b'{"Information":"invalid API key"}', AuthenticationError),
        (b'{"Information":"premium subscription required"}', EntitlementError),
        (b'{"Error Message":"bad parameter"}', ResponseError),
        (b"{broken", ResponseError),
        (b"[]", ResponseError),
    ],
)
def test_envelope_classification(body: bytes, error: type[Exception]) -> None:
    client, _ = transport([FakeResponse(body)])
    with pytest.raises(error):
        client.request("TEST", {}, cache_age=None)


def test_retries_connection_rate_and_server_failures() -> None:
    delays: list[float] = []
    client, session = transport(
        [requests.Timeout(), FakeResponse(b'{"Note":"rate limit"}'), FakeResponse(VALID_BODY)],
        delays=delays,
    )
    assert client.request("TEST", {}).body == VALID_BODY
    assert len(session.calls) == 3
    assert delays == [0.5, 1.0]

    rate, _ = transport([FakeResponse(b"x", 429)] * 4)
    with pytest.raises(RateLimitError, match="exhausted"):
        rate.request("TEST", {})
    server, _ = transport([FakeResponse(b"x", 500)] * 4)
    with pytest.raises(TransportError, match="server"):
        server.request("TEST", {})
    connection, _ = transport([requests.ConnectionError()] * 4)
    with pytest.raises(TransportError, match="transport"):
        connection.request("TEST", {})


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("connection"),
        requests.Timeout("timeout"),
        ChunkedEncodingError("chunked"),
        ContentDecodingError("decoding"),
    ],
)
def test_retryable_requests_failures_use_bounded_retries(error: Exception) -> None:
    delays: list[float] = []
    client, session = transport([error, FakeResponse(VALID_BODY)], delays=delays)

    assert client.request("TEST", {}).body == VALID_BODY
    assert len(session.calls) == 2
    assert delays == [0.5]


@pytest.mark.parametrize(
    "error",
    [requests.TooManyRedirects("redirect"), requests.RequestException("generic")],
)
def test_nonretryable_requests_failures_fail_immediately(error: Exception) -> None:
    client, session = transport([error, FakeResponse(b"{}")])

    with pytest.raises(TransportError, match="request failed for TEST") as caught:
        client.request("TEST", {})
    assert caught.value.__cause__ is error
    assert len(session.calls) == 1


def test_alpha_vantage_honors_bounded_retry_after_guidance() -> None:
    delays: list[float] = []
    client, _ = transport(
        [
            FakeResponse(b"{}", status_code=429, headers={"Retry-After": "5"}),
            FakeResponse(VALID_BODY),
        ],
        delays=delays,
    )

    assert client.request("TEST", {}).body == VALID_BODY
    assert delays == [5.0]


def test_empty_envelope_retries_before_returning_provider_data() -> None:
    delays: list[float] = []
    client, session = transport(
        [FakeResponse(b"{}"), FakeResponse(VALID_BODY)],
        delays=delays,
    )

    assert client.request("TEST", {}).body == VALID_BODY
    assert len(session.calls) == 2
    assert delays == [0.5]


def test_empty_envelope_exhaustion_does_not_publish_cache(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    delays: list[float] = []
    client, session = transport([FakeResponse(b"{}")] * 4, cache=cache, delays=delays)

    with pytest.raises(ResponseError, match="empty response envelope for TEST"):
        client.request("TEST", {})

    assert len(session.calls) == 4
    assert delays == [0.5, 1.0, 2.0]
    with pytest.raises(CacheError, match="offline cache miss for TEST"):
        client.request("TEST", {}, offline=True)


def test_retry_after_parser_accepts_bounded_delta_and_http_date_values() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    assert retry_after_seconds("5", now=now) == 5
    assert retry_after_seconds("Wed, 01 Jan 2025 00:00:07 GMT", now=now) == 7
    assert retry_after_seconds("Tue, 31 Dec 2024 23:59:59 GMT", now=now) == 0
    assert retry_after_seconds("60", now=now) == 60
    assert retry_after_seconds("invalid", now=now) is None
    assert retry_after_seconds("-1", now=now) is None
    assert retry_after_seconds("61", now=now) is None


def test_nonretryable_http_and_constructor_validation() -> None:
    client, _ = transport([FakeResponse(b"x", 400)])
    with pytest.raises(ResponseError, match="HTTP 400"):
        client.request("TEST", {})
    with pytest.raises(ValueError, match="api_key"):
        AlphaVantageTransport("")
    with pytest.raises(ValueError, match="timeout"):
        AlphaVantageTransport("key", timeout=0)


def test_credential_free_transport_fails_before_network() -> None:
    session = FakeSession([FakeResponse(VALID_BODY)])
    client = AlphaVantageTransport(None, session=session)

    with pytest.raises(AuthenticationError, match="credentials are required"):
        client.request("TEST", {})

    assert session.calls == []


def test_rate_limiter_waits_and_validates() -> None:
    now = [0.0]
    waits: list[float] = []

    def delay(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = TokenRateLimiter(60, clock=lambda: now[0], delay=delay)
    limiter.acquire()
    limiter.acquire()
    assert waits == [1.0]

    exactly_one = TokenRateLimiter(60, capacity=1)
    exactly_one.acquire()

    for rate in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="positive and finite"):
            TokenRateLimiter(rate)
    for capacity in (0, 0.5, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="at least one request token and finite"):
            TokenRateLimiter(60, capacity=capacity)
