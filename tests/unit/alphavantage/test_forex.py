from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from persistra.data.schema import BAR_SCHEMA
from persistra.data.store import BarQuery, ParquetMarketData, UniverseQuery
from persistra.providers.alphavantage.forex import fetch_fx_bars, ingest_fx, parse_fx_symbol


class FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[dict[str, Any]] = []

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(params)
        return self.payload


def test_parse_fx_symbol_normalizes_compact_pairs():
    assert parse_fx_symbol("eurusd") == ("EUR", "USD")


@pytest.mark.parametrize("symbol", ["EUR/USD", "EUR_USD", "EUR", "EURUSD1"])
def test_parse_fx_symbol_rejects_non_compact_pairs(symbol: str):
    with pytest.raises(ValueError, match="compact 6-letter pair"):
        parse_fx_symbol(symbol)


def test_fetch_fx_daily_builds_bar_schema_table():
    client = FakeClient(
        {
            "Time Series FX (Daily)": {
                "2024-01-03": {
                    "1. open": "1.0900",
                    "2. high": "1.1100",
                    "3. low": "1.0800",
                    "4. close": "1.1000",
                },
                "2024-01-02": {
                    "1. open": "1.0800",
                    "2. high": "1.1000",
                    "3. low": "1.0700",
                    "4. close": "1.0900",
                },
                "2023-12-29": {
                    "1. open": "1.0000",
                    "2. high": "1.0000",
                    "3. low": "1.0000",
                    "4. close": "1.0000",
                },
            }
        }
    )

    table = fetch_fx_bars(client, "eurusd", "1d", "2024-01-01", "2024-01-31")

    assert table.schema.equals(BAR_SCHEMA)
    assert client.requests == [
        {
            "function": "FX_DAILY",
            "from_symbol": "EUR",
            "to_symbol": "USD",
            "outputsize": "full",
        }
    ]
    df = table.to_pandas()
    assert df["symbol"].tolist() == ["EURUSD", "EURUSD"]
    assert df["bar_time"].tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]
    assert df["close"].tolist() == [1.09, 1.1]
    assert df["volume"].tolist() == [0.0, 0.0]
    assert df["vwap"].isna().all()
    assert df["transactions"].isna().all()


def test_fetch_fx_bars_without_bounds_returns_all_provider_rows():
    client = FakeClient(
        {
            "Time Series FX (Daily)": {
                "2024-01-03": {
                    "1. open": "1.0900",
                    "2. high": "1.1100",
                    "3. low": "1.0800",
                    "4. close": "1.1000",
                },
                "2020-01-02": {
                    "1. open": "1.0800",
                    "2. high": "1.1000",
                    "3. low": "1.0700",
                    "4. close": "1.0900",
                },
            }
        }
    )

    table = fetch_fx_bars(client, "eurusd", "1d")

    df = table.to_pandas()
    assert df["bar_time"].tolist() == [
        pd.Timestamp("2020-01-02"),
        pd.Timestamp("2024-01-03"),
    ]


def test_fetch_fx_intraday_requests_supported_interval():
    client = FakeClient(
        {
            "Time Series FX (5min)": {
                "2024-01-02 00:05:00": {
                    "1. open": "1.0800",
                    "2. high": "1.1000",
                    "3. low": "1.0700",
                    "4. close": "1.0900",
                }
            }
        }
    )

    table = fetch_fx_bars(
        client,
        "GBPUSD",
        "5m",
        "2024-01-02 00:00:00",
        "2024-01-02 00:10:00",
    )

    assert table.num_rows == 1
    assert client.requests[0]["function"] == "FX_INTRADAY"
    assert client.requests[0]["interval"] == "5min"


def test_fetch_fx_bars_rejects_unsupported_timeframe():
    client = FakeClient({})
    with pytest.raises(ValueError, match="unsupported Alpha Vantage FX timeframe"):
        fetch_fx_bars(client, "EURUSD", "2h", "2024-01-01", "2024-01-02")


@pytest.mark.parametrize("payload_key", ["Error Message", "Note", "Information"])
def test_fetch_fx_bars_raises_provider_errors(payload_key: str):
    client = FakeClient({payload_key: "problem"})
    with pytest.raises(RuntimeError, match="Alpha Vantage error"):
        fetch_fx_bars(client, "EURUSD", "1d", "2024-01-01", "2024-01-02")


def test_fetch_fx_bars_empty_response_returns_empty_schema_table():
    client = FakeClient({"Time Series FX (Daily)": {}})

    table = fetch_fx_bars(client, "EURUSD", "1d", "2024-01-01", "2024-01-02")

    assert table.num_rows == 0
    assert table.schema.equals(BAR_SCHEMA)


def test_ingest_fx_writes_bars_and_universe(tmp_path):
    client = FakeClient(
        {
            "Time Series FX (Daily)": {
                "2024-01-02": {
                    "1. open": "1.0800",
                    "2. high": "1.1000",
                    "3. low": "1.0700",
                    "4. close": "1.0900",
                }
            }
        }
    )
    store = ParquetMarketData(tmp_path / "fx")

    ingest_fx(["eurusd"], ["1d"], "2024-01-01", "2024-01-31", store, client)

    universe = store.universe(UniverseQuery(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")))
    assert universe == ["EURUSD"]
    bars = store.bars(
        BarQuery(
            ("EURUSD",),
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-31"),
            timeframe="1d",
        )
    )
    assert bars.num_rows == 1
    assert bars.to_pandas()["close"].tolist() == [1.09]


def test_ingest_fx_defaults_to_all_available_history(tmp_path):
    client = FakeClient(
        {
            "Time Series FX (Daily)": {
                "2024-01-02": {
                    "1. open": "1.0800",
                    "2. high": "1.1000",
                    "3. low": "1.0700",
                    "4. close": "1.0900",
                },
                "2020-01-02": {
                    "1. open": "1.0000",
                    "2. high": "1.0000",
                    "3. low": "1.0000",
                    "4. close": "1.0000",
                },
            }
        }
    )
    store = ParquetMarketData(tmp_path / "fx")

    ingest_fx(["eurusd"], ["1d"], store=store, client=client)

    universe = store.universe(UniverseQuery(pd.Timestamp("2020-01-02"), pd.Timestamp("2024-01-02")))
    assert universe == ["EURUSD"]
    bars = store.bars(
        BarQuery(
            ("EURUSD",),
            pd.Timestamp("2020-01-02"),
            pd.Timestamp("2024-01-02"),
            timeframe="1d",
        )
    )
    assert bars.to_pandas()["close"].tolist() == [1.0, 1.09]
