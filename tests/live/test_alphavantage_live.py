"""Opt-in, redacted Alpha Vantage family certification."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.data import AlphaVantageClient
from persistra.data.alphavantage.client import API_KEY_ENV
from persistra.model import CacheStatus, EntitlementMode, InstrumentKind, ResultMetadata

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
    operations: list[tuple[str, Callable[[bool, bool], Any]]] = [
        (
            "security_bars",
            lambda refresh, offline: client.securities.bars(
                "IBM",
                kind=InstrumentKind.EQUITY,
                interval="daily",
                refresh=refresh,
                offline=offline,
            ),
        ),
        (
            "latest_quote",
            lambda refresh, offline: client.quotes.latest(
                "IBM", entitlement=entitlement, refresh=refresh, offline=offline
            ),
        ),
        (
            "bulk_quotes",
            lambda refresh, offline: client.quotes.bulk(["IBM"], refresh=refresh, offline=offline),
        ),
        (
            "top_of_book",
            lambda refresh, offline: client.quotes.top_of_book(
                ["IBM"], refresh=refresh, offline=offline
            ),
        ),
        (
            "index_bars",
            lambda refresh, offline: client.indices.bars(
                "SPX", interval="weekly", refresh=refresh, offline=offline
            ),
        ),
        (
            "index_catalog",
            lambda refresh, offline: client.indices.catalog(refresh=refresh, offline=offline),
        ),
        (
            "historical_options",
            lambda refresh, offline: client.options.historical_chain(
                "IBM", refresh=refresh, offline=offline
            ),
        ),
        (
            "fx_rate",
            lambda refresh, offline: client.fx.rate("EUR", "USD", refresh=refresh, offline=offline),
        ),
        (
            "fx_bars",
            lambda refresh, offline: client.fx.bars(
                "EUR", "USD", interval="daily", refresh=refresh, offline=offline
            ),
        ),
        (
            "crypto_rate",
            lambda refresh, offline: client.crypto.rate(
                "BTC", "USD", refresh=refresh, offline=offline
            ),
        ),
        (
            "crypto_bars",
            lambda refresh, offline: client.crypto.bars(
                "BTC", "USD", interval="daily", refresh=refresh, offline=offline
            ),
        ),
        (
            "commodity_series",
            lambda refresh, offline: client.commodities.series(
                "WTI", frequency="monthly", refresh=refresh, offline=offline
            ),
        ),
        (
            "commodity_spot",
            lambda refresh, offline: client.commodities.spot(
                "gold", refresh=refresh, offline=offline
            ),
        ),
        (
            "economic_series",
            lambda refresh, offline: client.economics.series(
                "CPI", frequency="monthly", refresh=refresh, offline=offline
            ),
        ),
        (
            "symbol_search",
            lambda refresh, offline: client.reference.search(
                "IBM", refresh=refresh, offline=offline
            ),
        ),
        (
            "market_status",
            lambda refresh, offline: client.reference.market_status(
                refresh=refresh, offline=offline
            ),
        ),
    ]
    report: list[dict[str, object]] = []
    fingerprints: dict[str, str] = {}
    for family, acquire in operations:
        refreshed = acquire(True, False)
        offline = acquire(False, True)
        refreshed_fingerprint = _fingerprint(refreshed)
        offline_fingerprint = _fingerprint(offline)
        if refreshed_fingerprint != offline_fingerprint:
            raise AssertionError(
                f"{family} offline replay differs: {refreshed_fingerprint} != {offline_fingerprint}"
            )
        if refreshed.metadata.cache_status is not CacheStatus.REFRESHED:
            raise AssertionError(f"{family} did not report a refreshed cache status")
        if offline.metadata.cache_status is not CacheStatus.OFFLINE:
            raise AssertionError(f"{family} did not report an offline cache status")
        fingerprints[family] = refreshed_fingerprint
        metadata = refreshed.metadata
        report.append(
            {
                "family": family,
                "operation": metadata.operation,
                "result_type": type(refreshed).__name__,
                "tables": _table_contracts(refreshed),
                "result_fields": _result_fields(refreshed),
                "diagnostic_fields": [item.field for item in metadata.diagnostics],
                "entitlement": metadata.entitlement.value,
                "refresh_cache_status": refreshed.metadata.cache_status.value,
                "offline_cache_status": offline.metadata.cache_status.value,
                "deterministic_offline_replay": True,
                "outcome": "ok",
            }
        )
    cache_hit = client.securities.bars("IBM", kind=InstrumentKind.EQUITY, interval="daily")
    if cache_hit.metadata.cache_status is not CacheStatus.HIT:
        raise AssertionError("security_bars did not report a cache hit")
    if _fingerprint(cache_hit) != fingerprints["security_bars"]:
        raise AssertionError("security_bars cache-hit replay differs from refreshed parsing")
    with capsys.disabled():
        print(
            json.dumps(
                {
                    "api_key_environment": API_KEY_ENV,
                    "quote_entitlement": entitlement.value,
                    "requests_per_minute": 150,
                    "cache_hit_verified": True,
                    "results": report,
                },
                indent=2,
            )
        )


def _fingerprint(result: object) -> str:
    encoded = json.dumps(_normalized(result), sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _normalized(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        row_hashes = pd.util.hash_pandas_object(value, index=True, categorize=True)
        return {
            "columns": list(value.columns),
            "dtypes": [str(dtype) for dtype in value.dtypes],
            "content_hash": sha256(row_hashes.to_numpy(dtype="uint64").tobytes()).hexdigest(),
        }
    if isinstance(value, ResultMetadata):
        return {
            field.name: _normalized(getattr(value, field.name))
            for field in fields(value)
            if field.name != "cache_status"
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _normalized(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            str(key): _normalized(item)
            for key, item in sorted(mapping.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in cast("Sequence[object]", value)]
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _table_contracts(result: object) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    for name in ("frame", "contracts", "observations"):
        value = getattr(result, name, None)
        if isinstance(value, pd.DataFrame):
            tables[name] = {"columns": list(value.columns), "row_count": len(value)}
    return tables


def _result_fields(result: object) -> list[str]:
    if not is_dataclass(result):
        return []
    return [
        field.name
        for field in fields(result)
        if field.name not in {"frame", "contracts", "observations", "metadata"}
    ]
