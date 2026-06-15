import pandas as pd
import pyarrow as pa
import pytest

from persistra import Engine, Portfolio, Strategy
from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA
from persistra.data.store import ParquetMarketData
from tests.conftest import (
    BuyAndHoldOnce,
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


def test_engine_universe_excludes_symbol_after_membership_end(tmp_path):
    class Recorder(Strategy):
        timeframes = ("1d",)
        warmup = 1

        def __init__(self):
            self.members: dict[pd.Timestamp, frozenset[str]] = {}

        def on_bar(self, ctx):
            self.members[pd.Timestamp(ctx.timestamp)] = ctx.universe

    times = list(pd.bdate_range("2022-01-03", periods=4))
    store = ParquetMarketData(tmp_path / "store")
    store.write_bars(bars_table("AAA", times, [100.0, 101.0, 102.0, 103.0]), "1d")
    store.write_bars(bars_table("OLD", times, [50.0, 51.0, 52.0, 53.0]), "1d")
    membership = pd.DataFrame(
        {
            "universe_name": ["default", "default"],
            "symbol": ["AAA", "OLD"],
            "start_date": [pd.Timestamp("2020-01-01").date()] * 2,
            "end_date": [None, pd.Timestamp("2022-01-04").date()],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(
            membership,
            schema=UNIVERSE_MEMBERSHIP_SCHEMA,
            preserve_index=False,
        )
    )
    strategy = Recorder()

    Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=100_000),
        start="2022-01-03",
        end="2022-01-06",
    ).run()

    assert strategy.members[pd.Timestamp("2022-01-04")] == frozenset({"AAA", "OLD"})
    assert strategy.members[pd.Timestamp("2022-01-05")] == frozenset({"AAA"})


def _store_with_ending_old_membership(
    tmp_path,
    *,
    old_times,
    old_closes,
    all_times,
):
    store = ParquetMarketData(tmp_path / "store")
    store.write_bars(bars_table("AAA", all_times, [100.0] * len(all_times)), "1d")
    store.write_bars(bars_table("OLD", old_times, old_closes), "1d")
    membership = pd.DataFrame(
        {
            "universe_name": ["default", "default"],
            "symbol": ["AAA", "OLD"],
            "start_date": [pd.Timestamp("2020-01-01").date()] * 2,
            "end_date": [None, pd.Timestamp("2022-01-04").date()],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(
            membership,
            schema=UNIVERSE_MEMBERSHIP_SCHEMA,
            preserve_index=False,
        )
    )
    return store


def test_engine_liquidates_stale_holding_when_later_bar_exists(tmp_path):
    class BuyOldThenRecord(Strategy):
        timeframes = ("1d",)
        warmup = 1

        def __init__(self):
            self.members: dict[pd.Timestamp, frozenset[str]] = {}
            self._bought = False

        def on_bar(self, ctx):
            self.members[pd.Timestamp(ctx.timestamp)] = ctx.universe
            if not self._bought:
                ctx.signal({"OLD": 1.0})
                self._bought = True

    all_times = list(pd.bdate_range("2022-01-03", periods=4))
    store = _store_with_ending_old_membership(
        tmp_path,
        old_times=all_times,
        old_closes=[50.0, 51.0, 52.0, 53.0],
        all_times=all_times,
    )
    strategy = BuyOldThenRecord()

    result = Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=100_000),
        start="2022-01-03",
        end="2022-01-06",
    ).run()

    assert strategy.members[pd.Timestamp("2022-01-05")] == frozenset({"AAA"})
    engine_orders = result.orders[result.orders["origin"] == "engine_universe_exit"]
    assert len(engine_orders) == 1
    order = engine_orders.iloc[0]
    assert order["symbol"] == "OLD"
    assert order["status"] == "filled"
    assert order["reason"] == "filled"
    assert pd.Timestamp(order["fill_timestamp"]) == pd.Timestamp("2022-01-05")
    final_symbols = set(result.positions[result.positions["bar_time"] == all_times[-1]]["symbol"])
    assert "OLD" not in final_symbols
    assert "holding_stale" in set(result.diagnostics["name"])
    assert "universe_exit" in set(result.diagnostics["name"])


def test_engine_records_unfilled_stale_holding_when_final_bar_is_membership_end(tmp_path):
    # OLD's final bar is on its inclusive membership end date. The engine does
    # not fabricate an exit on that date; it marks the holding stale afterward
    # and leaves the liquidation order unfilled when no later OLD bar appears.
    all_times = list(pd.bdate_range("2022-01-03", periods=5))
    store = _store_with_ending_old_membership(
        tmp_path,
        old_times=all_times[:2],
        old_closes=[50.0, 51.0],
        all_times=all_times,
    )

    result = Engine(
        data=store,
        strategy=BuyAndHoldOnce({"OLD": 1.0}),
        portfolio=Portfolio(initial_capital=100_000),
        start="2022-01-03",
        end="2022-01-07",
    ).run()

    engine_orders = result.orders[result.orders["origin"] == "engine_universe_exit"]
    assert len(engine_orders) == 1
    order = engine_orders.iloc[0]
    assert order["symbol"] == "OLD"
    assert order["status"] == "unfilled"
    assert order["reason"] == "stale_holding_no_price"
    assert order["bars_seen"] == 0
    final_positions = result.positions[result.positions["bar_time"] == all_times[-1]]
    assert "OLD" in set(final_positions["symbol"])
