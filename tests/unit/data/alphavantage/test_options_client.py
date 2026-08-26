"""Offline tests for historical option-chain acquisition."""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.data import AlphaVantageClient
from persistra.data.alphavantage.transport import TokenRateLimiter
from persistra.errors import NoDataError
from persistra.model import InstrumentKind


@dataclass
class Response:
    """A small Requests-compatible response."""

    content: bytes
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})


class Session:
    """A sequence-driven HTTP session."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.responses = [Response(json.dumps(item).encode()) for item in payloads]
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Response:
        del url, timeout
        self.calls.append(params)
        return self.responses.pop(0)


def chain_payload(day: str = "2025-01-17", *, extra: bool = False) -> dict[str, object]:
    """Create a historical option fixture."""
    row: dict[str, object] = {
        "contractID": "IBM250221C00100000",
        "symbol": "IBM",
        "expiration": "2025-02-21",
        "strike": "100",
        "type": "call",
        "last": "5.1",
        "mark": "5.2",
        "bid": "5.0",
        "bid_size": "10",
        "ask": "5.4",
        "ask_size": "12",
        "volume": "100",
        "open_interest": "1000",
        "date": day,
        "implied_volatility": "0.25",
        "delta": "0.55",
        "gamma": "0.04",
        "theta": "-0.03",
        "vega": "0.12",
        "rho": "0.05",
    }
    if extra:
        row["provider_new_field"] = "x"
    return {"data": [row]}


def client(
    tmp_path: Path,
    payloads: list[dict[str, object]],
    *,
    strict: bool = False,
) -> tuple[AlphaVantageClient, Session]:
    """Create a fast offline options client."""
    session = Session(payloads)
    api = AlphaVantageClient(
        "secret",
        cache_directory=tmp_path,
        session=session,
        limiter=TokenRateLimiter(150, capacity=100),
        strict_schema=strict,
    )
    return api, session


def test_historical_chain_with_requested_and_provider_date(tmp_path: Path) -> None:
    api, session = client(tmp_path, [chain_payload(), chain_payload()])
    requested = api.options.historical_chain("IBM", date="2025-01-17")
    inferred = api.options.historical_chain("IBM")
    assert requested.chain_date == date(2025, 1, 17)
    assert inferred.chain_date == date(2025, 1, 17)
    assert requested.contracts.loc[0, "strike"] == 100
    assert requested.observations.loc[0, "open_interest"] == 1000
    assert session.calls[0]["function"] == "HISTORICAL_OPTIONS"
    assert session.calls[0]["date"] == "2025-01-17"


def test_historical_chain_reports_crossed_quote(tmp_path: Path) -> None:
    payload = chain_payload()
    rows = payload["data"]
    assert isinstance(rows, list)
    row = cast("dict[str, object]", rows[0])
    row["bid"] = "5.5"
    row["ask"] = "5.4"
    api, _ = client(tmp_path, [payload])

    result = api.options.historical_chain("IBM")

    diagnostic = result.metadata.diagnostics[0]
    assert diagnostic.field == "bid_ask"
    assert "crossed" in diagnostic.message
    assert "IBM250221C00100000" in diagnostic.message


def test_historical_chain_no_data_validation_and_diagnostics(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [{"data": []}])
    with pytest.raises(NoDataError):
        api.options.historical_chain("IBM", date="2025-01-18")
    api, _ = client(tmp_path / "diagnostic", [chain_payload(extra=True)])
    result = api.options.historical_chain("IBM")
    assert result.metadata.diagnostics[0].field == "provider_new_field"
    strict, _ = client(tmp_path / "strict", [chain_payload(extra=True)], strict=True)
    with pytest.raises(Exception, match="unknown provider fields"):
        strict.options.historical_chain("IBM")
    with pytest.raises(ValueError, match="underlying kind"):
        result_api, _ = client(tmp_path / "kind", [chain_payload()])
        result_api.options.historical_chain("IBM", kind=InstrumentKind.INDEX)


def test_historical_chain_iterator_is_inclusive_and_skips_only_no_data(tmp_path: Path) -> None:
    api, session = client(
        tmp_path,
        [chain_payload("2025-01-17"), {"data": []}, chain_payload("2025-01-19")],
    )
    results = list(
        api.options.iter_historical_chains("IBM", start=date(2025, 1, 17), end=date(2025, 1, 19))
    )
    assert [result.chain_date for result in results] == [date(2025, 1, 17), date(2025, 1, 19)]
    assert len(session.calls) == 3
    with pytest.raises(ValueError, match="must not follow"):
        list(
            api.options.iter_historical_chains(
                "IBM", start=date(2025, 1, 20), end=date(2025, 1, 19)
            )
        )
