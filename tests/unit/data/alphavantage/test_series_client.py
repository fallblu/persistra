"""Offline tests for pair, commodity, and economic namespaces."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from persistra.data import AlphaVantageClient
from persistra.data.alphavantage.transport import TokenRateLimiter
from persistra.model import InstrumentKind, SeriesKind


@dataclass
class Response:
    """A small Requests-compatible response."""

    content: bytes
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})


class Session:
    """A sequence-driven HTTP session."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.responses = [Response(json.dumps(payload).encode()) for payload in payloads]
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Response:
        del url, timeout
        self.calls.append(params)
        return self.responses.pop(0)


def client(tmp_path: Path, payloads: list[dict[str, object]]) -> tuple[AlphaVantageClient, Session]:
    """Create a fast offline client."""
    session = Session(payloads)
    result = AlphaVantageClient(
        "secret",
        cache_directory=tmp_path,
        session=session,
        limiter=TokenRateLimiter(150, capacity=100),
    )
    return result, session


def pair_bars() -> dict[str, object]:
    """Create a pair bar fixture."""
    return {
        "Meta Data": {"5. Time Zone": "UTC"},
        "Time Series FX (Daily)": {
            "2025-01-01": {
                "1. open": "1.10",
                "2. high": "1.12",
                "3. low": "1.09",
                "4. close": "1.11",
                "5. volume": "120.5",
                "6. market cap (USD)": "5000",
            }
        },
    }


def scalar_series() -> dict[str, object]:
    """Create a scalar-series fixture."""
    return {
        "name": "Fixture series",
        "interval": "monthly",
        "unit": "percent",
        "data": [
            {"date": "2025-02-01", "value": "2.1"},
            {"date": "2025-01-01", "value": "2.0"},
        ],
    }


@pytest.mark.parametrize(
    ("crypto", "interval", "operation"),
    [
        (False, "5min", "FX_INTRADAY"),
        (False, "daily", "FX_DAILY"),
        (False, "weekly", "FX_WEEKLY"),
        (False, "monthly", "FX_MONTHLY"),
        (True, "5min", "CRYPTO_INTRADAY"),
        (True, "daily", "DIGITAL_CURRENCY_DAILY"),
        (True, "weekly", "DIGITAL_CURRENCY_WEEKLY"),
        (True, "monthly", "DIGITAL_CURRENCY_MONTHLY"),
    ],
)
def test_pair_bar_functions(tmp_path: Path, crypto: bool, interval: str, operation: str) -> None:
    api, session = client(tmp_path, [pair_bars()])
    namespace = api.crypto if crypto else api.fx
    result = namespace.bars("BTC" if crypto else "EUR", "USD", interval=interval)
    expected = InstrumentKind.CRYPTO_PAIR if crypto else InstrumentKind.FIAT_PAIR
    assert result.instrument.kind is expected
    assert result.metadata.operation == operation
    assert session.calls[0]["function"] == operation
    assert result.frame.loc[0, "currency"] == "USD"


@pytest.mark.parametrize("crypto", [False, True])
def test_pair_exchange_rate(tmp_path: Path, crypto: bool) -> None:
    fixture: dict[str, object] = {
        "Realtime Currency Exchange Rate": {
            "5. Exchange Rate": "1.25",
            "6. Last Refreshed": "2025-01-01 12:00:00",
            "7. Time Zone": "UTC",
            "8. Bid Price": "1.24",
            "9. Ask Price": "1.26",
        }
    }
    api, _ = client(tmp_path, [fixture])
    namespace = api.crypto if crypto else api.fx
    result = namespace.rate("BTC" if crypto else "EUR", "USD")
    assert result.exchange_rate == 1.25
    assert result.provider_timestamp is not None


def test_pair_validation(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [])
    with pytest.raises(ValueError, match="differ"):
        api.fx.rate("USD", "USD")
    with pytest.raises(ValueError, match="unsupported"):
        api.crypto.bars("BTC", "USD", interval="yearly")
    with pytest.raises(ValueError, match="outputsize"):
        api.fx.bars("EUR", "USD", outputsize="large")


@pytest.mark.parametrize(
    ("commodity", "frequency", "metal"),
    [
        ("GOLD_SILVER_HISTORY", "daily", "gold"),
        ("WTI", "weekly", None),
        ("BRENT", "monthly", None),
        ("NATURAL_GAS", "daily", None),
        ("COPPER", "quarterly", None),
        ("ALUMINUM", "annual", None),
        ("WHEAT", "monthly", None),
        ("CORN", "quarterly", None),
        ("COTTON", "annual", None),
        ("SUGAR", "monthly", None),
        ("COFFEE", "quarterly", None),
        ("ALL_COMMODITIES", "annual", None),
    ],
)
def test_all_commodity_series_functions(
    tmp_path: Path, commodity: str, frequency: str, metal: str | None
) -> None:
    api, session = client(tmp_path, [scalar_series()])
    result = api.commodities.series(commodity, frequency=frequency, metal=metal)
    assert result.definition.kind is SeriesKind.COMMODITY
    assert session.calls[0]["function"] == commodity
    assert result.frame["period_label"].is_monotonic_increasing


@pytest.mark.parametrize("metal", ["gold", "silver"])
def test_metal_spot(tmp_path: Path, metal: str) -> None:
    fixture: dict[str, object] = {
        "data": {
            "price": "2400.5",
            "unit": "USD per troy ounce",
            "timestamp": "2025-01-01T12:00:00Z",
        }
    }
    api, _ = client(tmp_path, [fixture])
    result = api.commodities.spot(metal)
    assert result.metal == metal
    assert result.value == 2400.5


@pytest.mark.parametrize(
    ("indicator", "frequency", "maturity"),
    [
        ("REAL_GDP", "quarterly", None),
        ("REAL_GDP_PER_CAPITA", None, None),
        ("TREASURY_YIELD", "daily", "10year"),
        ("FEDERAL_FUNDS_RATE", "weekly", None),
        ("CPI", "semiannual", None),
        ("INFLATION", None, None),
        ("RETAIL_SALES", None, None),
        ("DURABLES", None, None),
        ("UNEMPLOYMENT", None, None),
        ("NONFARM_PAYROLL", None, None),
    ],
)
def test_all_economic_functions(
    tmp_path: Path,
    indicator: str,
    frequency: str | None,
    maturity: str | None,
) -> None:
    api, session = client(tmp_path, [scalar_series()])
    result = api.economics.series(indicator, frequency=frequency, maturity=maturity)
    assert result.definition.kind is SeriesKind.ECONOMIC
    assert session.calls[0]["function"] == indicator


def test_series_dimension_validation(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [])
    with pytest.raises(ValueError, match="unsupported commodity"):
        api.commodities.series("PLATINUM", frequency="daily")
    with pytest.raises(ValueError, match="supports frequencies"):
        api.commodities.series("WTI", frequency="annual")
    with pytest.raises(ValueError, match="gold or silver"):
        api.commodities.spot("platinum")
    with pytest.raises(ValueError, match="unsupported economic"):
        api.economics.series("PMI")
    with pytest.raises(ValueError, match="requires a maturity"):
        api.economics.series("TREASURY_YIELD", frequency="daily")
    with pytest.raises(ValueError, match="only"):
        api.economics.series("CPI", maturity="10year")
