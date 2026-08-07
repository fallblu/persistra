"""Opt-in, redacted Alpha Vantage family certification."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import pytest

from persistra.data import AlphaVantageClient
from persistra.data.alphavantage.client import API_KEY_ENV
from persistra.model import EntitlementMode, InstrumentKind

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

RUN_LIVE = os.environ.get("PERSISTRA_RUN_LIVE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not RUN_LIVE, reason="set PERSISTRA_RUN_LIVE=1 for live certification"),
]


def test_supported_families_against_live_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise every provider family and emit no values or raw provider data."""
    entitlement = EntitlementMode(
        os.environ.get("PERSISTRA_ALPHAVANTAGE_LIVE_ENTITLEMENT", "historical")
    )
    client = AlphaVantageClient.from_env(cache_directory=tmp_path, requests_per_minute=150)
    operations: list[tuple[str, Callable[[], Any]]] = [
        (
            "security_bars",
            lambda: client.securities.bars(
                "IBM", kind=InstrumentKind.EQUITY, interval="daily", refresh=True
            ),
        ),
        (
            "latest_quote",
            lambda: client.quotes.latest("IBM", entitlement=entitlement, refresh=True),
        ),
        (
            "bulk_quotes",
            lambda: client.quotes.bulk(["IBM"], refresh=True),
        ),
        (
            "top_of_book",
            lambda: client.quotes.top_of_book(["IBM"], refresh=True),
        ),
        ("index_bars", lambda: client.indices.bars("SPX", refresh=True)),
        ("index_catalog", lambda: client.indices.catalog(refresh=True)),
        ("historical_options", lambda: client.options.historical_chain("IBM", refresh=True)),
        ("fx_rate", lambda: client.fx.rate("EUR", "USD", refresh=True)),
        ("fx_bars", lambda: client.fx.bars("EUR", "USD", interval="daily", refresh=True)),
        ("crypto_rate", lambda: client.crypto.rate("BTC", "USD", refresh=True)),
        (
            "crypto_bars",
            lambda: client.crypto.bars("BTC", "USD", interval="daily", refresh=True),
        ),
        (
            "commodity_series",
            lambda: client.commodities.series("WTI", frequency="monthly", refresh=True),
        ),
        ("commodity_spot", lambda: client.commodities.spot("gold", refresh=True)),
        (
            "economic_series",
            lambda: client.economics.series("CPI", frequency="monthly", refresh=True),
        ),
        ("symbol_search", lambda: client.reference.search("IBM", refresh=True)),
        ("market_status", lambda: client.reference.market_status(refresh=True)),
    ]
    report: list[dict[str, object]] = []
    for family, acquire in operations:
        result = acquire()
        metadata = result.metadata
        frame = getattr(result, "frame", None)
        report.append(
            {
                "family": family,
                "operation": metadata.operation,
                "result_type": type(result).__name__,
                "columns": [] if frame is None else list(frame.columns),
                "diagnostic_fields": [item.field for item in metadata.diagnostics],
                "entitlement": metadata.entitlement.value,
                "outcome": "ok",
            }
        )
    with capsys.disabled():
        print(json.dumps({"api_key_environment": API_KEY_ENV, "results": report}, indent=2))
