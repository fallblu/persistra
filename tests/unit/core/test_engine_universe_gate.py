import pandas as pd
import pytest

from persistra.data.store import ParquetMarketData
from tests.conftest import (
    EqualWeightRebalance,
    bars_table,
    build_store,
    make_engine,
    reference_table,
)


def test_gate_ignores_reference_symbols_without_bars(tmp_path):
    # Reference lists 5 symbols; only 2 ever print a bar.
    times = list(pd.bdate_range("2022-01-03", periods=5))
    daily = {
        "AAA": (times, [100.0, 101.0, 102.0, 103.0, 104.0]),
        "BBB": (times, [50.0, 50.0, 50.0, 50.0, 50.0]),
    }
    store = build_store(tmp_path / "store", daily)
    store.write_universe(reference_table(["AAA", "BBB", "XXX", "YYY", "ZZZ"]))

    result = make_engine(store, EqualWeightRebalance(), "2022-01-03", "2022-01-07").run()
    gross = result.equity_curve["gross_exposure"]
    # Fully invested across the 2 priced symbols -> ~1.0, not diluted to 2/5.
    assert gross.iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_late_listing_symbol_gets_no_weight_before_first_bar(tmp_path):
    all_times = list(pd.bdate_range("2022-01-03", periods=6))
    store = ParquetMarketData(tmp_path / "store")
    store.write_bars(bars_table("AAA", all_times, [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]), "1d")
    # BBB only starts printing on the 4th session.
    store.write_bars(bars_table("BBB", all_times[3:], [50.0, 51.0, 52.0]), "1d")
    store.write_universe(reference_table(["AAA", "BBB"]))

    result = make_engine(store, EqualWeightRebalance(), "2022-01-03", "2022-01-11").run()
    positions = result.positions.copy()
    positions["bar_time"] = pd.to_datetime(positions["bar_time"])

    early = positions[positions["bar_time"] < all_times[3]]
    assert not early.empty, "expected positions before BBB listing"
    assert set(early["symbol"]) == {"AAA"}
    first_aaa = early[early["symbol"] == "AAA"]["weight"].iloc[0]
    assert first_aaa == pytest.approx(1.0, abs=1e-6)

    # Once BBB starts printing it joins the book at equal weight (no longer gated out).
    late = positions[positions["bar_time"] >= all_times[3]]
    assert "BBB" in set(late["symbol"])
    bbb_weight = late[late["symbol"] == "BBB"]["weight"].iloc[0]
    assert bbb_weight == pytest.approx(0.5, abs=1e-6)
