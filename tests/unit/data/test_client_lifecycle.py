"""Provider client HTTP-session lifecycle tests."""

from pathlib import Path
from typing import Any

import pytest

import persistra.data.alphavantage.transport as alpha_transport
import persistra.data.fred.transport as fred_transport
from persistra.data import AlphaVantageClient, FredClient
from persistra.data.alphavantage.transport import ResponseLike, TokenRateLimiter


class ClosableSession:
    """Session double that records lifecycle calls."""

    def __init__(self) -> None:
        self.close_calls = 0

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> ResponseLike:
        del url, params, timeout
        raise AssertionError("closed clients must not issue requests")

    def close(self) -> None:
        self.close_calls += 1


def test_clients_leave_injected_sessions_open_and_reject_use_after_close(
    tmp_path: Path,
) -> None:
    alpha_session = ClosableSession()
    alpha = AlphaVantageClient(
        "key",
        cache_directory=tmp_path / "alpha",
        session=alpha_session,
        limiter=TokenRateLimiter(150, capacity=100),
    )
    fred_session = ClosableSession()
    fred = FredClient(
        "key",
        cache_directory=tmp_path / "fred",
        session=fred_session,
    )

    alpha.close()
    alpha.close()
    fred.close()
    fred.close()

    assert alpha_session.close_calls == 0
    assert fred_session.close_calls == 0
    with pytest.raises(RuntimeError, match="Alpha Vantage transport is closed"):
        alpha.reference.market_status()
    with pytest.raises(RuntimeError, match="FRED transport is closed"):
        fred.series.definition("GDP")


def test_client_context_managers_close_owned_sessions_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alpha_session = ClosableSession()
    with monkeypatch.context() as context:
        context.setattr(alpha_transport.requests, "Session", lambda: alpha_session)
        with AlphaVantageClient(
            "key",
            cache_directory=tmp_path / "alpha",
            limiter=TokenRateLimiter(150, capacity=100),
        ) as alpha:
            assert isinstance(alpha, AlphaVantageClient)
        alpha.close()
    assert alpha_session.close_calls == 1

    fred_session = ClosableSession()
    with monkeypatch.context() as context:
        context.setattr(fred_transport.requests, "Session", lambda: fred_session)
        with FredClient("key", cache_directory=tmp_path / "fred") as fred:
            assert isinstance(fred, FredClient)
        fred.close()
    assert fred_session.close_calls == 1
