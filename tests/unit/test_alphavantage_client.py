from __future__ import annotations

import json
from typing import Any

import pytest

from persistra.errors import (
    SourceCredentialError,
    SourceRateLimitError,
    SourceResponseError,
    SourceTransportError,
)
from persistra.sources.alphavantage import (
    API_KEY_ENVIRONMENT_VARIABLE,
    AlphaVantageClient,
    TokenBucketRateLimiter,
    TransportResponse,
)

_KEY = "unit-test-key-123"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeSleep:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.now += seconds


class FakeTransport:
    def __init__(self, responses: list[TransportResponse | Exception]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str, timeout_seconds: float) -> TransportResponse:
        self.urls.append(url)
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ok(payload: dict[str, Any]) -> TransportResponse:
    return TransportResponse(200, json.dumps(payload).encode())


def _client(
    transport: FakeTransport,
    *,
    requests_per_minute: int = 75,
    max_attempts: int = 4,
) -> tuple[AlphaVantageClient, FakeSleep]:
    clock = FakeClock()
    sleep = FakeSleep(clock)
    client = AlphaVantageClient(
        api_key=_KEY,
        requests_per_minute=requests_per_minute,
        max_attempts=max_attempts,
        backoff_seconds=1.0,
        transport=transport,
        clock=clock,
        sleep=sleep,
    )
    return client, sleep


def test_rate_limiter_paces_calls_beyond_the_budget() -> None:
    clock = FakeClock()
    sleep = FakeSleep(clock)
    limiter = TokenBucketRateLimiter(2, clock=clock, sleep=sleep)
    limiter.acquire()
    limiter.acquire()
    assert sleep.calls == []
    limiter.acquire()
    assert len(sleep.calls) == 1
    assert sleep.calls[0] == pytest.approx(30.0)


def test_rate_limiter_rejects_a_nonpositive_budget() -> None:
    with pytest.raises(SourceTransportError):
        TokenBucketRateLimiter(0)


def test_get_returns_decoded_payload_and_carries_key_only_in_url() -> None:
    transport = FakeTransport([_ok({"data": {"a": 1}})])
    client, _ = _client(transport)
    payload = client.get("TIME_SERIES_DAILY", {"symbol": "IBM"})
    assert payload == {"data": {"a": 1}}
    assert len(transport.urls) == 1
    assert f"apikey={_KEY}" in transport.urls[0]
    assert "symbol=IBM" in transport.urls[0]
    assert "function=TIME_SERIES_DAILY" in transport.urls[0]


def test_get_retries_status_429_then_succeeds() -> None:
    transport = FakeTransport(
        [TransportResponse(429, b""), _ok({"value": 2})]
    )
    client, sleep = _client(transport)
    assert client.get("CPI") == {"value": 2}
    assert len(transport.urls) == 2
    assert 1.0 in sleep.calls


def test_get_retries_network_failures_then_raises_transport_error() -> None:
    transport = FakeTransport(
        [OSError("boom"), OSError("boom"), OSError("boom")]
    )
    client, _ = _client(transport, max_attempts=3)
    with pytest.raises(SourceTransportError) as info:
        client.get("CPI")
    assert _KEY not in str(info.value)
    assert len(transport.urls) == 3


def test_get_raises_rate_limit_error_after_persistent_notes() -> None:
    note = {"Note": "Thank you for using Alpha Vantage! Your call frequency is..."}
    transport = FakeTransport([_ok(note), _ok(note)])
    client, _ = _client(transport, max_attempts=2)
    with pytest.raises(SourceRateLimitError) as info:
        client.get("TIME_SERIES_DAILY")
    assert _KEY not in str(info.value)


def test_get_raises_response_error_on_error_envelope_without_retry() -> None:
    transport = FakeTransport([_ok({"Error Message": "Invalid API call."})])
    client, _ = _client(transport)
    with pytest.raises(SourceResponseError) as info:
        client.get("TIME_SERIES_DAILY", {"symbol": "NOPE"})
    assert _KEY not in str(info.value)
    assert len(transport.urls) == 1


def test_get_rejects_non_object_and_invalid_json_bodies() -> None:
    client, _ = _client(FakeTransport([TransportResponse(200, b"[1, 2]")]))
    with pytest.raises(SourceResponseError):
        client.get("CPI")
    client, _ = _client(FakeTransport([TransportResponse(200, b"not-json")]))
    with pytest.raises(SourceResponseError):
        client.get("CPI")


def test_get_fails_fast_on_non_retryable_status() -> None:
    transport = FakeTransport([TransportResponse(403, b"")])
    client, _ = _client(transport)
    with pytest.raises(SourceTransportError) as info:
        client.get("CPI")
    assert "403" in str(info.value)
    assert len(transport.urls) == 1


def test_get_requires_a_function_name() -> None:
    client, _ = _client(FakeTransport([]))
    with pytest.raises(SourceResponseError):
        client.get("")


def test_api_key_resolution_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(API_KEY_ENVIRONMENT_VARIABLE, raising=False)
    with pytest.raises(SourceCredentialError):
        AlphaVantageClient()
    monkeypatch.setenv(API_KEY_ENVIRONMENT_VARIABLE, "env-key")
    transport = FakeTransport([_ok({"ok": True})])
    client = AlphaVantageClient(transport=transport)
    assert client.get("CPI") == {"ok": True}
    assert "apikey=env-key" in transport.urls[0]


def test_client_rejects_invalid_limits() -> None:
    with pytest.raises(SourceTransportError):
        AlphaVantageClient(api_key=_KEY, max_attempts=0)
    with pytest.raises(SourceTransportError):
        AlphaVantageClient(api_key=_KEY, timeout_seconds=0)
