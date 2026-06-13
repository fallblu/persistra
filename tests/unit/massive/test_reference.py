from types import SimpleNamespace

import pandas as pd
import pytest

from persistra.data.store import ParquetMarketData
from persistra.providers.massive.reference import (
    build_active_universe,
    build_point_in_time_universe,
    build_universe,
    fetch_tickers,
)


def test_fetch_tickers_lists_active(fake_rest_client):
    tickers = fetch_tickers(fake_rest_client)
    assert [t.ticker for t in tickers] == ["AAA", "BBB"]


def test_build_universe_writes_open_membership(fake_rest_client, tmp_path):
    store = ParquetMarketData(tmp_path / "s")
    with pytest.warns(DeprecationWarning, match="survivorship bias"):
        build_universe(store, fake_rest_client, since="2010-01-01")
    # All tickers should be active on any date after the floor.
    assert store.active_universe(pd.Timestamp("2020-01-01")) == frozenset({"AAA", "BBB"})
    assert store.active_universe(pd.Timestamp("2005-01-01")) == frozenset()


def test_build_active_universe_writes_named_membership(fake_rest_client, tmp_path):
    store = ParquetMarketData(tmp_path / "active")

    build_active_universe(store, fake_rest_client, since="2010-01-01", universe_name="screen")

    assert store.active_universe(pd.Timestamp("2020-01-01")) == frozenset()
    assert store.active_universe(pd.Timestamp("2020-01-01"), "screen") == frozenset({"AAA", "BBB"})


def test_build_point_in_time_universe_bounds_delisted_symbols(tmp_path):
    def list_tickers(market, active, limit, date=None):
        assert market == "stocks"
        assert active is None
        assert limit == 1000
        assert date == "2024-01-01"
        yield SimpleNamespace(ticker="AAA", delisted_utc=None)
        yield SimpleNamespace(ticker="OLD", delisted_utc="2021-06-30")

    def get_ticker_details(ticker, date=None):
        assert date == "2024-01-01"
        details = {
            "AAA": SimpleNamespace(ticker="AAA", list_date="2018-01-02", delisted_utc=None),
            "OLD": SimpleNamespace(
                ticker="OLD",
                list_date="2010-03-15",
                delisted_utc="2021-06-30",
            ),
        }
        return details[ticker]

    client = SimpleNamespace(
        list_tickers=list_tickers,
        get_ticker_details=get_ticker_details,
        get_ticker_events=lambda ticker, types=None: SimpleNamespace(events=[]),
    )
    store = ParquetMarketData(tmp_path / "pit")

    build_point_in_time_universe(
        store,
        client,
        as_of="2024-01-01",
        universe_name="research",
    )

    assert store.active_universe(pd.Timestamp("2017-12-29"), "research") == frozenset({"OLD"})
    assert store.active_universe(pd.Timestamp("2018-01-02"), "research") == frozenset(
        {"AAA", "OLD"}
    )
    assert store.active_universe(pd.Timestamp("2021-06-30"), "research") == frozenset(
        {"AAA", "OLD"}
    )
    assert store.active_universe(pd.Timestamp("2021-07-01"), "research") == frozenset({"AAA"})
