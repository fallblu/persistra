# pyright: reportPrivateUsage=false
"""Audit the implemented and fixture-backed Alpha Vantage boundary."""

import ast
import json
from pathlib import Path
from typing import Any, cast

from persistra.data.alphavantage import commodities, economics
from persistra.data.alphavantage.pairs import _operation as pair_operation
from persistra.data.alphavantage.securities import _operation as security_operation

FIXTURE_DIRECTORY = Path("tests/fixtures/alphavantage")
TEST_DIRECTORY = Path("tests/unit/data/alphavantage")

EXPECTED_FUNCTIONS = {
    "ALUMINUM",
    "ALL_COMMODITIES",
    "BRENT",
    "COFFEE",
    "COPPER",
    "CORN",
    "COTTON",
    "CPI",
    "CRYPTO_INTRADAY",
    "CURRENCY_EXCHANGE_RATE",
    "DIGITAL_CURRENCY_DAILY",
    "DIGITAL_CURRENCY_MONTHLY",
    "DIGITAL_CURRENCY_WEEKLY",
    "DURABLES",
    "FEDERAL_FUNDS_RATE",
    "FX_DAILY",
    "FX_INTRADAY",
    "FX_MONTHLY",
    "FX_WEEKLY",
    "GLOBAL_QUOTE",
    "GOLD_SILVER_HISTORY",
    "GOLD_SILVER_SPOT",
    "HISTORICAL_OPTIONS",
    "INDEX_CATALOG",
    "INDEX_DATA",
    "INFLATION",
    "MARKET_STATUS",
    "NATURAL_GAS",
    "NONFARM_PAYROLL",
    "REALTIME_BULK_BID_ASK_PRICES",
    "REALTIME_BULK_QUOTES",
    "REAL_GDP",
    "REAL_GDP_PER_CAPITA",
    "RETAIL_SALES",
    "SUGAR",
    "SYMBOL_SEARCH",
    "TIME_SERIES_DAILY",
    "TIME_SERIES_DAILY_ADJUSTED",
    "TIME_SERIES_INTRADAY",
    "TIME_SERIES_MONTHLY",
    "TIME_SERIES_MONTHLY_ADJUSTED",
    "TIME_SERIES_WEEKLY",
    "TIME_SERIES_WEEKLY_ADJUSTED",
    "TREASURY_YIELD",
    "UNEMPLOYMENT",
    "WHEAT",
    "WTI",
}

EXCLUDED_FUNCTIONS = {
    "HISTORICAL_PUT_CALL_RATIO",
    "HISTORICAL_VOLUME_OPEN_INTEREST_RATIO",
    "REALTIME_OPTIONS",
    "REALTIME_PUT_CALL_RATIO",
    "REALTIME_VOLUME_OPEN_INTEREST_RATIO",
}


def test_every_supported_function_has_a_fixture_and_parser_test() -> None:
    manifest = cast(
        "dict[str, dict[str, list[str]]]",
        json.loads((FIXTURE_DIRECTORY / "endpoint_manifest.json").read_text()),
    )
    pairs = {
        (family, operation)
        for family, operations in manifest.items()
        for operation in operations
    }
    functions = {operation for _, operation in pairs}
    assert len(pairs) == 48
    assert functions == EXPECTED_FUNCTIONS
    assert len(functions) == 47
    assert functions.isdisjoint(EXCLUDED_FUNCTIONS)

    test_names = _test_names()
    for operations in manifest.values():
        for fixture_name, test_name in operations.values():
            fixture = FIXTURE_DIRECTORY / fixture_name
            assert fixture.is_file(), fixture
            assert test_name in test_names, test_name
            _validate_fixture(fixture)


def test_implementation_operation_set_matches_the_fixture_manifest() -> None:
    security = {
        security_operation(interval, adjusted)
        for interval, adjusted in (
            ("5min", False),
            ("daily", False),
            ("daily", True),
            ("weekly", False),
            ("weekly", True),
            ("monthly", False),
            ("monthly", True),
        )
    }
    pairs = {
        pair_operation(crypto, interval)
        for crypto in (False, True)
        for interval in ("5min", "daily", "weekly", "monthly")
    }
    direct = {
        "CURRENCY_EXCHANGE_RATE",
        "GLOBAL_QUOTE",
        "HISTORICAL_OPTIONS",
        "INDEX_CATALOG",
        "INDEX_DATA",
        "MARKET_STATUS",
        "REALTIME_BULK_BID_ASK_PRICES",
        "REALTIME_BULK_QUOTES",
        "SYMBOL_SEARCH",
        "GOLD_SILVER_SPOT",
        "GOLD_SILVER_HISTORY",
    }
    commodity_series = commodities._ENERGY | commodities._INDUSTRIAL
    implemented = security | pairs | direct | commodity_series | economics._FREQUENCIES.keys()
    assert implemented == EXPECTED_FUNCTIONS


def _test_names() -> set[str]:
    names: set[str] = set()
    for path in TEST_DIRECTORY.glob("test_*_client.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(node.name for node in tree.body if isinstance(node, ast.FunctionDef))
    return names


def _validate_fixture(path: Path) -> None:
    if path.suffix == ".json":
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
    else:
        assert path.read_text(encoding="utf-8").startswith("symbol,")
