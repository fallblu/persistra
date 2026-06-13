from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
import pytest

from persistra import Engine, ParquetMarketData, Portfolio, Strategy
from persistra.core.events import BarCloseEvent
from persistra.core.history import HistoryView
from persistra.data.schema import (
    BAR_SCHEMA,
    CORPORATE_ACTION_SCHEMA,
    UNIVERSE_MEMBERSHIP_SCHEMA,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA = REPO_ROOT / "examples" / "sample_data"


# --------------------------------------------------------------------------- #
# Table builders
# --------------------------------------------------------------------------- #
def bars_table(
    symbol: str,
    times: list[pd.Timestamp],
    closes: list[float],
    volume: float = 1000.0,
) -> pa.Table:
    """Build a BAR_SCHEMA table for one symbol with flat OHLC == close."""
    df = pd.DataFrame(
        {
            "bar_time": [pd.Timestamp(t) for t in times],
            "symbol": symbol,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": volume,
            "vwap": closes,
            "transactions": pd.array([100] * len(closes), dtype="Int64"),
        }
    )
    return pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)


def reference_table(symbols: list[str], start: str = "2000-01-01") -> pa.Table:
    """Open-ended membership rows for each symbol (end_date null)."""
    floor = pd.Timestamp(start).date()
    df = pd.DataFrame(
        {
            "universe_name": ["default"] * len(symbols),
            "symbol": symbols,
            "start_date": [floor] * len(symbols),
            "end_date": [None] * len(symbols),
        }
    )
    return pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)


def actions_table(rows: list[dict]) -> pa.Table:
    """Build a CORPORATE_ACTION_SCHEMA table from row dicts.

    Each row dict: {date: 'YYYY-MM-DD', symbol, action_type, amount, ratio}.
    """
    if not rows:
        return CORPORATE_ACTION_SCHEMA.empty_table()
    df = pd.DataFrame(rows, columns=["date", "symbol", "action_type", "amount", "ratio"])
    df["date"] = [pd.Timestamp(d).date() for d in df["date"]]
    return pa.Table.from_pandas(df, schema=CORPORATE_ACTION_SCHEMA, preserve_index=False)


def build_store(
    root: Path,
    daily: dict[str, tuple[list[pd.Timestamp], list[float]]],
    actions: list[dict] | None = None,
) -> ParquetMarketData:
    """Materialise a ParquetMarketData on disk with daily bars, reference, actions."""
    store = ParquetMarketData(root)
    for symbol, (times, closes) in daily.items():
        store.write_bars(bars_table(symbol, times, closes), "1d")
    store.write_universe(reference_table(sorted(daily.keys())))
    if actions:
        store.write_corporate_actions(actions_table(actions))
    return store


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def sample_data_dir() -> Path:
    """Path to the committed deterministic sample dataset."""
    assert SAMPLE_DATA.exists(), f"missing sample data at {SAMPLE_DATA}"
    return SAMPLE_DATA


@pytest.fixture
def tiny_store(tmp_path: Path) -> ParquetMarketData:
    """A 3-symbol store with 6 flat daily bars each, no corporate actions."""
    times = list(pd.bdate_range("2022-01-03", periods=6))
    daily = {
        "AAA": (times, [100.0, 101.0, 102.0, 101.0, 103.0, 104.0]),
        "BBB": (times, [50.0, 50.5, 49.5, 50.0, 51.0, 52.0]),
        "CCC": (times, [200.0, 198.0, 202.0, 205.0, 204.0, 206.0]),
    }
    return build_store(tmp_path / "store", daily)


@pytest.fixture
def populated_history() -> HistoryView:
    """A HistoryView with 4 bars for two symbols (AAA volatile, BBB calm)."""
    hist = HistoryView(max_bars=100)
    times = list(pd.bdate_range("2022-01-03", periods=4))
    aaa = [100.0, 110.0, 99.0, 115.0]
    bbb = [100.0, 100.5, 100.2, 100.6]
    for i, t in enumerate(times):
        for sym, series in (("AAA", aaa), ("BBB", bbb)):
            hist.update(
                BarCloseEvent(
                    timestamp=t,
                    symbol=sym,
                    open=series[i],
                    high=series[i],
                    low=series[i],
                    close=series[i],
                    volume=1000.0,
                )
            )
    return hist


@pytest.fixture
def fake_rest_client() -> SimpleNamespace:
    """Stub RESTClient: list_aggs / list_splits / list_dividends / list_tickers."""

    def list_aggs(ticker, multiplier, timespan, from_, to, adjusted, sort, limit):
        base = dt.datetime(2023, 1, 3, tzinfo=dt.UTC)
        for i in range(3):
            ts = int((base + dt.timedelta(days=i)).timestamp() * 1000)
            yield SimpleNamespace(
                timestamp=ts,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1_000.0 + i,
                vwap=100.4 + i,
                transactions=42 + i,
            )

    def list_splits(ticker):
        yield SimpleNamespace(execution_date="2023-06-15", split_to=2, split_from=1)

    def list_dividends(ticker):
        yield SimpleNamespace(ex_dividend_date="2023-09-20", cash_amount=0.25)

    def list_tickers(market, active, limit):
        yield SimpleNamespace(ticker="AAA")
        yield SimpleNamespace(ticker="BBB")

    return SimpleNamespace(
        list_aggs=list_aggs,
        list_splits=list_splits,
        list_dividends=list_dividends,
        list_tickers=list_tickers,
    )


# --------------------------------------------------------------------------- #
# Reusable strategies (returned via fixtures so tests can instantiate/inspect)
# --------------------------------------------------------------------------- #
class EqualWeightRebalance(Strategy):
    """Rebalance the whole universe to equal weight every bar."""

    timeframes = ("1d",)
    warmup = 1

    def on_bar(self, ctx) -> None:
        n = len(ctx.universe)
        if n:
            ctx.signal({sym: 1.0 / n for sym in ctx.universe})


class BuyAndHoldOnce(Strategy):
    """Target a fixed weight on the first bar, then never re-signal."""

    timeframes = ("1d",)
    warmup = 1

    def __init__(self, weights: dict[str, float]) -> None:
        self._weights = dict(weights)
        self._emitted = False

    def on_bar(self, ctx) -> None:
        if not self._emitted:
            ctx.signal(self._weights)
            self._emitted = True


class LookaheadProbe(Strategy):
    """Record, each bar, the decision timestamp and the latest timestamp visible
    in history. Used to assert no-lookahead. Holds equal weight too so trades
    are generated for fill-price checks."""

    timeframes = ("1d",)
    warmup = 1

    def __init__(self) -> None:
        self.records: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def on_bar(self, ctx) -> None:
        closes = ctx.history().closes(10)
        if len(closes.index):
            self.records.append((ctx.timestamp, closes.index.max()))
        n = len(ctx.universe)
        if n:
            ctx.signal({sym: 1.0 / n for sym in ctx.universe})


@pytest.fixture
def equal_weight_strategy() -> EqualWeightRebalance:
    return EqualWeightRebalance()


@pytest.fixture
def strategy_classes() -> SimpleNamespace:
    """Expose strategy classes for tests that need to instantiate them."""
    return SimpleNamespace(
        EqualWeightRebalance=EqualWeightRebalance,
        BuyAndHoldOnce=BuyAndHoldOnce,
        LookaheadProbe=LookaheadProbe,
    )


def make_engine(store: ParquetMarketData, strategy: Strategy, start: str, end: str) -> Engine:
    """Helper for integration tests."""
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start=start,
        end=end,
    )


@pytest.fixture(scope="session")
def sample_result(sample_data_dir):
    """A full EqualWeightRebalance backtest on the committed sample data."""
    engine = Engine(
        data=ParquetMarketData(sample_data_dir),
        strategy=EqualWeightRebalance(),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2023-12-29",
    )
    return engine.run()
