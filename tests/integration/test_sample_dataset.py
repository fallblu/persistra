import pandas as pd

from persistra.data.store import BarQuery, ParquetMarketData, UniverseQuery
from scripts.sample_universe import SAMPLE_SYMBOLS


def test_reference_is_curated_to_sample_universe(sample_data_dir):
    store = ParquetMarketData(sample_data_dir)
    symbols = store.universe(UniverseQuery(pd.Timestamp("2000-01-01"), pd.Timestamp("2100-01-01")))
    assert sorted(symbols) == sorted(SAMPLE_SYMBOLS)


def test_intraday_bars_are_regular_hours_only(sample_data_dir):
    store = ParquetMarketData(sample_data_dir)
    bars = store.bars(
        BarQuery(("AAPL",), pd.Timestamp("2024-03-01"), pd.Timestamp("2024-03-31"), "1h")
    ).to_pandas()
    hours = set(pd.to_datetime(bars["bar_time"]).dt.hour)
    assert hours <= {9, 10, 11, 12, 13, 14, 15, 16}
    assert hours, "no intraday bars loaded"
