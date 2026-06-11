import pandas as pd

from persistra.data.store import ParquetMarketData
from persistra.providers.massive.reference import build_universe, fetch_tickers


def test_fetch_tickers_lists_active(fake_rest_client):
    tickers = fetch_tickers(fake_rest_client)
    assert [t.ticker for t in tickers] == ["AAA", "BBB"]


def test_build_universe_writes_open_membership(fake_rest_client, tmp_path):
    store = ParquetMarketData(tmp_path / "s")
    build_universe(store, fake_rest_client, since="2010-01-01")
    # All tickers should be active on any date after the floor.
    assert store.active_universe(pd.Timestamp("2020-01-01")) == frozenset({"AAA", "BBB"})
    assert store.active_universe(pd.Timestamp("2005-01-01")) == frozenset()
