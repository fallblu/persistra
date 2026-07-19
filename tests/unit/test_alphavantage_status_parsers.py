from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.errors import SourceResponseError
from persistra.market import TradingStatus
from persistra.reference import InstrumentId, ListingStatus
from persistra.sources.alphavantage import AlphaVantageClient, TransportResponse
from persistra.sources.alphavantage.equity import (
    parse_listing_status,
    parse_market_status,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_EFFECTIVE = datetime(2026, 1, 9, 14, 30, tzinfo=UTC)
_AVAILABLE = datetime(2026, 1, 9, 15, tzinfo=UTC)


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_market_status_maps_region_onto_instruments() -> None:
    instruments = (InstrumentId.new(), InstrumentId.new())
    observations = parse_market_status(
        _fixture("market_status.json"),
        region="United States",
        market_type="Equity",
        instruments=instruments,
        effective_at=_EFFECTIVE,
        available_at=_AVAILABLE,
    )
    assert [item.instrument_id for item in observations] == list(instruments)
    assert all(item.status is TradingStatus.TRADING for item in observations)
    closed = parse_market_status(
        _fixture("market_status.json"),
        region="United Kingdom",
        market_type="Equity",
        instruments=instruments[:1],
        effective_at=_EFFECTIVE,
        available_at=_AVAILABLE,
    )
    assert closed[0].status is TradingStatus.CLOSED


def test_market_status_rejects_missing_market_or_bad_payload() -> None:
    with pytest.raises(SourceResponseError):
        parse_market_status(
            {"markets": "nope"},
            region="United States",
            market_type="Equity",
            instruments=(InstrumentId.new(),),
            effective_at=_EFFECTIVE,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_market_status(
            _fixture("market_status.json"),
            region="Atlantis",
            market_type="Equity",
            instruments=(InstrumentId.new(),),
            effective_at=_EFFECTIVE,
            available_at=_AVAILABLE,
        )


def test_listing_status_csv_round_trips_records() -> None:
    text = (FIXTURES / "listing_status.csv").read_text(encoding="utf-8")
    records = parse_listing_status(text)
    assert len(records) == 2
    active = records[0]
    assert active.symbol == "IBM"
    assert active.status is ListingStatus.ACTIVE
    assert active.ipo_date == date(1962, 1, 2)
    assert active.delisting_date is None
    delisted = records[1]
    assert delisted.status is ListingStatus.DELISTED
    assert delisted.delisting_date == date(2021, 5, 14)


def test_listing_status_rejects_malformed_rows() -> None:
    with pytest.raises(SourceResponseError):
        parse_listing_status("symbol,status\n,Active\n")
    with pytest.raises(SourceResponseError):
        parse_listing_status("symbol,status\nIBM,Halted\n")
    with pytest.raises(SourceResponseError):
        parse_listing_status("symbol,status\n")
    with pytest.raises(SourceResponseError):
        parse_listing_status(
            "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
            "IBM,IBM,NYSE,Stock,bad-date,null,Active\n"
        )


class FakeTransport:
    def __init__(self, responses: list[TransportResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str, timeout_seconds: float) -> TransportResponse:
        self.urls.append(url)
        return self.responses.pop(0)


def test_client_get_csv_returns_text_and_recognizes_json_envelopes() -> None:
    csv_body = b"symbol,name\nIBM,IBM\n"
    transport = FakeTransport([TransportResponse(200, csv_body)])
    client = AlphaVantageClient(api_key="k", transport=transport)
    assert client.get_csv("LISTING_STATUS") == csv_body.decode()

    transport = FakeTransport(
        [TransportResponse(200, json.dumps({"Error Message": "bad"}).encode())]
    )
    client = AlphaVantageClient(api_key="k", transport=transport)
    with pytest.raises(SourceResponseError):
        client.get_csv("LISTING_STATUS")

    transport = FakeTransport(
        [TransportResponse(200, json.dumps({"unexpected": "json"}).encode())]
    )
    client = AlphaVantageClient(api_key="k", transport=transport)
    with pytest.raises(SourceResponseError):
        client.get_csv("LISTING_STATUS")
