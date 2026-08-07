"""Offline tests for security, quote, index, and reference namespaces."""

import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from persistra.data import AlphaVantageClient
from persistra.data.alphavantage.client import API_KEY_ENV
from persistra.data.alphavantage.transport import TokenRateLimiter
from persistra.errors import ResponseError
from persistra.model import EntitlementMode, InstrumentKind


@dataclass
class Response:
    """A small Requests-compatible response."""

    content: bytes
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})


class Session:
    """A sequence-driven HTTP session."""

    def __init__(self, responses: list[Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Response:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


def response(value: object, *, media_type: str = "application/json") -> Response:
    """Encode one fake provider response."""
    if isinstance(value, bytes):
        body = value
    else:
        body = json.dumps(value).encode()
    return Response(body, headers={"Content-Type": media_type})


def client(
    tmp_path: Path,
    responses: list[Response],
    *,
    strict: bool = False,
) -> tuple[AlphaVantageClient, Session]:
    """Create a client with no real waits or network access."""
    session = Session(responses)
    result = AlphaVantageClient(
        "secret",
        base_url="https://example.invalid/query",
        cache_directory=tmp_path,
        session=session,
        limiter=TokenRateLimiter(150, capacity=100),
        strict_schema=strict,
    )
    return result, session


def bar_payload(*, unknown: bool = False) -> dict[str, object]:
    """Create a provider time-series fixture."""
    row = {
        "1. open": "100",
        "2. high": "105",
        "3. low": "95",
        "4. close": "103",
        "5. adjusted close": "102.5",
        "6. volume": "1000",
        "7. dividend amount": "0.50",
        "8. split coefficient": "1.0",
    }
    if unknown:
        row["9. surprise"] = "value"
    return {
        "Meta Data": {"5. Time Zone": "UTC"},
        "Time Series (Daily)": {
            "2025-01-02": row,
            "2025-01-01": row,
        },
    }


@pytest.mark.parametrize(
    ("interval", "adjusted", "operation"),
    [
        ("daily", False, "TIME_SERIES_DAILY"),
        ("daily", True, "TIME_SERIES_DAILY_ADJUSTED"),
        ("weekly", False, "TIME_SERIES_WEEKLY"),
        ("weekly", True, "TIME_SERIES_WEEKLY_ADJUSTED"),
        ("monthly", False, "TIME_SERIES_MONTHLY"),
        ("monthly", True, "TIME_SERIES_MONTHLY_ADJUSTED"),
    ],
)
def test_security_bar_endpoint_selection(
    tmp_path: Path, interval: str, adjusted: bool, operation: str
) -> None:
    api, session = client(tmp_path, [response(bar_payload())])
    result = api.securities.bars(
        "IBM", kind=InstrumentKind.EQUITY, interval=interval, adjusted=adjusted
    )
    assert result.metadata.operation == operation
    assert result.frame["date"].is_monotonic_increasing
    assert result.frame.loc[0, "adjusted_close"] == 102.5
    assert session.calls[0]["params"]["function"] == operation


def test_intraday_and_month_iteration(tmp_path: Path) -> None:
    payload = bar_payload()
    payload["Time Series (5min)"] = payload.pop("Time Series (Daily)")
    api, session = client(tmp_path, [response(payload), response(payload), response(payload)])
    result = api.securities.bars(
        "IBM",
        kind=InstrumentKind.ETF,
        interval="5min",
        adjusted=True,
        extended_hours=True,
        month="2025-01",
    )
    assert result.frame["timestamp"].dt.tz is not None
    assert set(result.frame["session"]) == {"all"}
    months = list(
        api.securities.iter_intraday_months("IBM", ["2025-01", "2025-02"], kind=InstrumentKind.ETF)
    )
    assert len(months) == 2
    assert session.calls[0]["params"]["extended_hours"] == "true"


@pytest.mark.parametrize("interval", ["1min", "5min", "15min", "30min", "60min"])
@pytest.mark.parametrize("entitlement", list(EntitlementMode)[:3])
def test_intraday_entitlement_modes(
    tmp_path: Path, entitlement: EntitlementMode, interval: str
) -> None:
    payload = bar_payload()
    payload[f"Time Series ({interval})"] = payload.pop("Time Series (Daily)")
    api, session = client(tmp_path, [response(payload)])
    result = api.securities.bars(
        "IBM",
        kind=InstrumentKind.EQUITY,
        interval=interval,
        entitlement=entitlement,
    )
    assert result.metadata.entitlement is entitlement
    assert session.calls[0]["params"].get("entitlement") == (
        None if entitlement is EntitlementMode.HISTORICAL else entitlement.value
    )


def test_security_validation_and_schema_diagnostics(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [response(bar_payload(unknown=True))])
    result = api.securities.bars("IBM", kind=InstrumentKind.EQUITY)
    assert result.metadata.diagnostics[0].field == "surprise"
    strict, _ = client(tmp_path / "strict", [response(bar_payload(unknown=True))], strict=True)
    with pytest.raises(ResponseError, match="unknown provider bar"):
        strict.securities.bars("IBM", kind=InstrumentKind.EQUITY)
    with pytest.raises(ValueError, match="security kind"):
        api.securities.bars("IBM", kind=InstrumentKind.INDEX)
    with pytest.raises(ValueError, match="unsupported"):
        api.securities.bars("IBM", kind=InstrumentKind.EQUITY, interval="hourly")
    with pytest.raises(ValueError, match="intraday"):
        api.securities.bars(
            "IBM", kind=InstrumentKind.EQUITY, interval="daily", extended_hours=True
        )
    with pytest.raises(ValueError, match="YYYY-MM"):
        api.securities.bars("IBM", kind=InstrumentKind.EQUITY, interval="5min", month="January")
    with pytest.raises(ValueError, match="entitlement applies"):
        api.securities.bars(
            "IBM",
            kind=InstrumentKind.EQUITY,
            interval="daily",
            entitlement=EntitlementMode.DELAYED,
        )
    with pytest.raises(ValueError, match="intraday entitlement"):
        api.securities.bars(
            "IBM",
            kind=InstrumentKind.EQUITY,
            interval="5min",
            entitlement=EntitlementMode.NOT_APPLICABLE,
        )


@pytest.mark.parametrize(
    ("entitlement", "container"),
    [
        (EntitlementMode.HISTORICAL, "Global Quote"),
        (EntitlementMode.DELAYED, "Global Quote - DATA DELAYED BY 15 MINUTES"),
        (EntitlementMode.REALTIME, "Global Quote"),
    ],
)
def test_latest_quote_and_entitlement(
    tmp_path: Path, entitlement: EntitlementMode, container: str
) -> None:
    fixture = {
        container: {
            "01. symbol": "IBM",
            "02. open": "100",
            "03. high": "105",
            "04. low": "99",
            "05. price": "104",
            "06. volume": "1000",
            "07. latest trading day": "2025-01-02",
            "08. previous close": "101",
            "09. change": "3",
            "10. change percent": "2.9703%",
        }
    }
    api, session = client(tmp_path, [response(fixture)])
    result = api.quotes.latest("IBM", entitlement=entitlement)
    assert result.frame.loc[0, "price"] == 104
    assert result.frame.loc[0, "change_percent"] == pytest.approx(2.9703)
    assert result.metadata.entitlement is entitlement
    assert session.calls[0]["params"].get("entitlement") == (
        None if entitlement is EntitlementMode.HISTORICAL else entitlement.value
    )
    with pytest.raises(ValueError, match="entitlement"):
        api.quotes.latest("IBM", entitlement=EntitlementMode.NOT_APPLICABLE)


def test_bulk_quotes_chunk_and_preserve_input_success(tmp_path: Path) -> None:
    symbols = ["ZZZ", *[f"S{number:03d}" for number in range(99)], "AAA"]
    first = {
        "data": [
            {
                "symbol": symbol,
                "close": "10",
                "extended_hours_quote": "10.1",
                "extended_hours_change": "0.1",
                "extended_hours_change_percent": "1%",
            }
            for symbol in reversed(symbols[:100])
        ]
    }
    second = {"data": [{"symbol": symbols[-1], "close": "11"}]}
    api, session = client(tmp_path, [response(first), response(second)], strict=True)
    result = api.quotes.bulk(symbols)
    assert len(result.frame) == 101
    assert result.frame.loc[0, "price"] == 10
    assert result.metadata.entitlement is EntitlementMode.REALTIME
    assert len(session.calls) == 2
    assert len(session.calls[0]["params"]["symbol"].split(",")) == 100
    assert "entitlement" not in session.calls[0]["params"]
    assert result.frame["provider_symbol"].tolist() == symbols

    invalid, _ = client(tmp_path / "invalid", [])
    with pytest.raises(ValueError, match="duplicates"):
        invalid.quotes.bulk(["IBM", "IBM"])


def test_top_of_book_normalization(tmp_path: Path) -> None:
    fixture = {
        "data": [
            {
                "symbol": "IBM",
                "bid_price": "103.9",
                "bid_size": "10",
                "ask_price": "104.1",
                "ask_size": "12",
                "timestamp": "2025-01-02T15:00:00Z",
            }
        ]
    }
    api, session = client(tmp_path, [response(fixture)])
    result = api.quotes.top_of_book(["IBM"])
    assert result.frame.loc[0, "bid_size"] == 10
    assert result.frame.loc[0, "observed_at"] == pd.Timestamp("2025-01-02T15:00:00Z")
    assert result.metadata.entitlement is EntitlementMode.REALTIME
    assert "entitlement" not in session.calls[0]["params"]

    fixture["data"][0]["bid_price"] = "104.1"  # type: ignore[index]
    crossed, _ = client(tmp_path / "crossed", [response(fixture)])
    diagnostic = crossed.quotes.top_of_book(["IBM"]).metadata.diagnostics[0]
    assert diagnostic.field == "bid_ask"
    assert "locked" in diagnostic.message


def test_reference_endpoints(tmp_path: Path) -> None:
    search = {
        "bestMatches": [
            {
                "1. symbol": "IBM",
                "2. name": "International Business Machines",
                "3. type": "Equity",
                "4. region": "United States",
                "5. marketOpen": "09:30",
                "6. marketClose": "16:00",
                "7. timezone": "UTC-04",
                "8. currency": "USD",
                "9. matchScore": "1.0",
            }
        ]
    }
    status = {
        "markets": [
            {
                "market_type": "Equity",
                "region": "United States",
                "primary_exchanges": "NASDAQ, NYSE",
                "local_open": "09:30",
                "local_close": "16:00",
                "current_status": "open",
                "notes": "",
            }
        ]
    }
    api, _ = client(tmp_path, [response(search), response(status)])
    assert api.reference.search("IBM").frame.loc[0, "provider_symbol"] == "IBM"
    assert api.reference.market_status().frame.loc[0, "current_status"] == "open"


@pytest.mark.parametrize("interval", ["daily", "weekly", "monthly"])
def test_index_bar_frequencies(tmp_path: Path, interval: str) -> None:
    api, _ = client(tmp_path, [response(bar_payload())])
    bars = api.indices.bars("SPX", interval=interval)
    assert bars.instrument.kind is InstrumentKind.INDEX
    assert bars.frame.loc[0, "interval"] == interval


def test_index_endpoints(tmp_path: Path) -> None:
    catalog = (
        b"symbol,name,market,currency,type\n"
        b"DJI,Dow Jones Industrial Average,US,USD,index\n"
        b"SPX,S&P 500,US,USD,index\n"
        b"COMP,Nasdaq Composite,US,USD,index\n"
        b"NDX,Nasdaq 100,US,USD,index\n"
        b"VIX,CBOE Volatility Index,US,USD,index\n"
        b"RUT,Russell 2000,US,USD,index\n"
    )
    api, _ = client(tmp_path, [response(catalog, media_type="text/csv")])
    indices = api.indices.catalog()
    assert set(indices.frame["provider_symbol"]) == {"DJI", "SPX", "COMP", "NDX", "VIX", "RUT"}


def test_client_environment_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(ValueError, match=API_KEY_ENV):
        AlphaVantageClient.from_env()
    monkeypatch.setenv(API_KEY_ENV, "secret")
    configured = AlphaVantageClient.from_env(cache_directory=tmp_path)
    assert configured.securities is not None
    with pytest.raises(ValueError, match="cache ages"):
        AlphaVantageClient("secret", cache_ages={"TIME_SERIES_DAILY": timedelta(seconds=-1)})


def test_operation_cache_age_override(tmp_path: Path) -> None:
    session = Session([response(bar_payload()), response(bar_payload())])
    api = AlphaVantageClient(
        "secret",
        cache_directory=tmp_path,
        cache_ages={"TIME_SERIES_DAILY": None},
        session=session,
        limiter=TokenRateLimiter(150, capacity=100),
    )
    api.securities.bars("IBM", kind=InstrumentKind.EQUITY)
    api.securities.bars("IBM", kind=InstrumentKind.EQUITY)
    assert len(session.calls) == 2
