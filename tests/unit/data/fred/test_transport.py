"""Tests for FRED transport classification, caching, and redaction."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from persistra.data.cache import RawResponseCache
from persistra.data.fred.transport import FredTransport
from persistra.errors import (
    AuthenticationError,
    EntitlementError,
    NoDataError,
    RateLimitError,
    ResponseError,
    TransportError,
)
from persistra.model import CacheStatus

if TYPE_CHECKING:
    from pathlib import Path


class Response:
    """Minimal response double."""

    def __init__(
        self,
        status_code: int,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = json.dumps(payload).encode()
        self.headers = {
            "Content-Type": "application/json; charset=utf-8",
            **(headers or {}),
        }


class Session:
    """Queued session double."""

    def __init__(self, responses: list[Response]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Response:
        assert timeout == 30
        assert url.startswith("https://")
        self.calls.append(dict(params))
        return self.responses.pop(0)


def transport(
    tmp_path: Path,
    responses: list[Response],
    *,
    retries: int = 0,
    delays: list[float] | None = None,
) -> FredTransport:
    """Create a deterministic transport."""
    return FredTransport(
        "top-secret-key",
        session=Session(responses),
        cache=RawResponseCache(tmp_path),
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        delay=(delays if delays is not None else []).append,
        random_source=lambda: 0,
        retries=retries,
    )


@pytest.mark.parametrize(
    ("status", "payload", "error"),
    [
        (
            400,
            {"error_code": 400, "error_message": "Variable api_key is not registered"},
            AuthenticationError,
        ),
        (404, {"error_code": 404, "error_message": "Not found"}, NoDataError),
        (423, {"error_code": 423, "error_message": "Locked"}, EntitlementError),
        (422, {"error_code": 422, "error_message": "Bad parameter"}, ResponseError),
    ],
)
def test_http_errors_are_normalized_and_redacted(
    tmp_path: Path,
    status: int,
    payload: dict[str, Any],
    error: type[Exception],
) -> None:
    client = transport(tmp_path, [Response(status, payload)])
    with pytest.raises(error) as raised:
        client.request("series", {"series_id": "GDP"})
    assert "top-secret-key" not in str(raised.value)


def test_response_error_has_bounded_allowlisted_context(tmp_path: Path) -> None:
    client = transport(
        tmp_path,
        [
            Response(
                422,
                {
                    "error_code": "422",
                    "error_message": "Bad parameter " + ("detail " * 100),
                },
            )
        ],
    )

    with pytest.raises(ResponseError) as raised:
        client.request(
            "series",
            {
                "series_id": "GOLDAMGBD228NLBM",
                "api_key": "request-secret",
                "unrelated": "private-value",
            },
        )

    error = raised.value
    assert error.context["operation"] == "series"
    assert error.context["series_id"] == "GOLDAMGBD228NLBM"
    assert error.context["http_status"] == 422
    assert error.context["provider_code"] == 422
    assert len(str(error.context["provider_message"])) == 240
    assert "GOLDAMGBD228NLBM" in str(error)
    assert "private-value" not in str(error)
    assert "secret" not in str(error)


def test_response_error_omits_credential_bearing_provider_message(tmp_path: Path) -> None:
    client = transport(
        tmp_path,
        [
            Response(
                422,
                {
                    "error_code": 422,
                    "error_message": "Rejected credential top-secret-key",
                },
            )
        ],
    )

    with pytest.raises(ResponseError) as raised:
        client.request("series", {"series_id": "GDP"})

    assert "provider_message" not in raised.value.context
    assert "top-secret-key" not in str(raised.value)


def test_rate_limit_and_server_failures_retry(tmp_path: Path) -> None:
    limited = transport(
        tmp_path / "limited",
        [Response(429, {}), Response(200, {"seriess": []})],
        retries=1,
    )
    assert limited.request("series", {"series_id": "GDP"}).cache_status is CacheStatus.MISS

    exhausted = transport(
        tmp_path / "exhausted",
        [Response(429, {}), Response(429, {})],
        retries=1,
    )
    with pytest.raises(RateLimitError, match="exhausted"):
        exhausted.request("series", {"series_id": "GDP"})

    server = transport(tmp_path / "server", [Response(500, {})])
    with pytest.raises(TransportError, match="server retries"):
        server.request("series", {"series_id": "GDP"})


def test_success_error_envelope_is_classified(tmp_path: Path) -> None:
    client = transport(
        tmp_path,
        [Response(200, {"error_code": 400, "error_message": "api_key is invalid"})],
    )
    with pytest.raises(AuthenticationError):
        client.request("series", {"series_id": "GDP"})


@pytest.mark.parametrize("code", [None, True, False, "broken", "4.0", [], {}])
def test_malformed_error_codes_are_response_errors(tmp_path: Path, code: object) -> None:
    client = transport(
        tmp_path,
        [Response(200, {"error_code": code, "error_message": "provider body"})],
    )

    with pytest.raises(ResponseError, match="malformed provider error code for series"):
        client.request("series", {})


@pytest.mark.parametrize(
    ("code", "message", "error"),
    [
        (400, "Variable api_key is not registered", AuthenticationError),
        ("404", "Not found", NoDataError),
        (423, "Locked", EntitlementError),
        ("429", "Rate limited", RateLimitError),
        (451, "Unexpected", ResponseError),
    ],
)
def test_valid_error_codes_keep_provider_classification(
    tmp_path: Path,
    code: int | str,
    message: str,
    error: type[Exception],
) -> None:
    client = transport(
        tmp_path,
        [Response(200, {"error_code": code, "error_message": message})],
    )

    with pytest.raises(error):
        client.request("series", {})


def test_missing_error_code_is_not_an_error_envelope(tmp_path: Path) -> None:
    client = transport(tmp_path, [Response(200, {"error_message": "informational"})])
    assert client.request("series", {}).body


def test_fred_honors_http_date_retry_after_guidance(tmp_path: Path) -> None:
    delays: list[float] = []
    client = transport(
        tmp_path,
        [
            Response(
                503,
                {},
                headers={"Retry-After": "Wed, 01 Jan 2025 00:00:07 GMT"},
            ),
            Response(200, {"seriess": []}),
        ],
        retries=1,
        delays=delays,
    )

    assert client.request("series", {}).body
    assert delays == [7.0]


def test_cache_identity_and_document_exclude_api_key(tmp_path: Path) -> None:
    session = Session([Response(200, {"seriess": []})])
    client = FredTransport(
        "top-secret-key",
        session=session,
        cache=RawResponseCache(tmp_path),
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
        retries=0,
    )

    first = client.request("series", {"series_id": "GDP", "api_key": "also-secret"})
    second = client.request("series", {"series_id": "GDP", "api_key": "different-secret"})

    assert first.cache_status is CacheStatus.MISS
    assert second.cache_status is CacheStatus.HIT
    assert len(session.calls) == 1
    cache_text = next(tmp_path.rglob("*.json")).read_text(encoding="utf-8")
    assert "secret" not in cache_text


def test_transport_validates_configuration_and_modes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        FredTransport("")
    with pytest.raises(ValueError, match="timeout"):
        FredTransport("key", timeout=0)
    client = transport(tmp_path, [])
    with pytest.raises(ValueError, match="unsupported"):
        client.request("categories", {})
    with pytest.raises(ValueError, match="cannot apply together"):
        client.request("series", {}, refresh=True, offline=True)


def test_credential_free_transport_fails_before_network(tmp_path: Path) -> None:
    session = Session([Response(200, {"seriess": []})])
    client = FredTransport(None, session=session, cache=RawResponseCache(tmp_path))

    with pytest.raises(AuthenticationError, match="credentials are required"):
        client.request("series", {"series_id": "GDP"})

    assert session.calls == []
