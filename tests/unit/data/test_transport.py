"""Tests for Alpha Vantage transport behavior."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import requests

from persistra.data.alphavantage.transport import AlphaVantageTransport, TokenRateLimiter
from persistra.data.cache import RawResponseCache
from persistra.errors import (
    AuthenticationError,
    EntitlementError,
    RateLimitError,
    ResponseError,
    TransportError,
)
from persistra.model import CacheStatus


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
    with pytest.raises(TransportError, match="offline"):
        client.request("MISSING", {}, offline=True)


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
        [requests.Timeout(), FakeResponse(b'{"Note":"rate limit"}'), FakeResponse(b"{}")],
        delays=delays,
    )
    assert client.request("TEST", {}).body == b"{}"
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


def test_nonretryable_http_and_constructor_validation() -> None:
    client, _ = transport([FakeResponse(b"x", 400)])
    with pytest.raises(ResponseError, match="HTTP 400"):
        client.request("TEST", {})
    with pytest.raises(ValueError, match="api_key"):
        AlphaVantageTransport("")
    with pytest.raises(ValueError, match="timeout"):
        AlphaVantageTransport("key", timeout=0)


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
    with pytest.raises(ValueError, match="positive"):
        TokenRateLimiter(0)
