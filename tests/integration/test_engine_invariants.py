from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from persistra import Engine, ParquetMarketData, Portfolio
from persistra.core.engine import rebucket_to_sessions
from persistra.core.execution import ExecutionTiming
from persistra.data.schema import BAR_SCHEMA
from persistra.data.store import BarQuery
from tests.conftest import (
    BuyAndHoldOnce,
    EqualWeightRebalance,
    LookaheadProbe,
    actions_table,
    bars_table,
    build_store,
    make_engine,
    reference_table,
)

START = "2022-01-03"
END = "2023-12-29"


class EagerOnlyData:
    def __init__(self, store):
        self._store = store

    def bars(self, query):
        return self._store.bars(query)

    def corporate_actions(self, query):
        return self._store.corporate_actions(query)

    def universe(self, query):
        return self._store.universe(query)

    def active_universe(self, date, universe_name="default"):
        return self._store.active_universe(date, universe_name)


def _engine(store, strategy, start=START, end=END):
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start=start,
        end=end,
    )


def _ohlc_store(tmp_path, opens, closes):
    times = list(pd.bdate_range("2022-01-03", periods=len(closes)))
    store = ParquetMarketData(tmp_path / "timing")
    df = pd.DataFrame(
        {
            "bar_time": times,
            "symbol": ["AAA"] * len(times),
            "open": opens,
            "high": [max(o, c) for o, c in zip(opens, closes, strict=True)],
            "low": [min(o, c) for o, c in zip(opens, closes, strict=True)],
            "close": closes,
            "volume": [1000.0] * len(times),
            "vwap": closes,
            "transactions": pd.array([100] * len(times), dtype="Int64"),
        }
    )
    import pyarrow as pa

    store.write_bars(pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False), "1d")
    store.write_universe(reference_table(["AAA"]))
    return store, times


def _timing_engine(store, strategy, start, end, timing, delay_bars=None):
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000.0),
        start=start,
        end=end,
        execution_timing=timing,
        delay_bars=delay_bars,
    )


def test_no_lookahead_history_never_exceeds_decision_timestamp(sample_data_dir):
    probe = LookaheadProbe()
    _engine(ParquetMarketData(sample_data_dir), probe).run()
    assert probe.records, "probe never fired"
    for decision_ts, latest_visible in probe.records:
        assert latest_visible <= decision_ts


def test_fills_use_contemporaneous_close_not_future(sample_data_dir):
    store = ParquetMarketData(sample_data_dir)
    result = _engine(store, EqualWeightRebalance()).run()
    trades = result.trades.copy()
    trades["timestamp"] = pd.to_datetime(trades["timestamp"])
    # Sample a handful of trades and confirm fill_price == that bar's close.
    for _, row in trades.head(20).iterrows():
        ts = pd.Timestamp(row["timestamp"])
        bars = store.bars(BarQuery((row["symbol"],), ts, ts, "1d")).to_pandas()
        assert len(bars) == 1
        assert row["fill_price"] == pytest.approx(float(bars.iloc[0]["close"]))


def test_same_close_timing_preserves_current_default(tmp_path):
    store, times = _ohlc_store(tmp_path, [10.0, 20.0, 30.0], [11.0, 21.0, 31.0])
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 1.0}),
        times[0],
        times[-1],
        ExecutionTiming.SAME_CLOSE,
    ).run()

    trade = result.trades.iloc[0]
    assert pd.Timestamp(trade["order_timestamp"]) == times[0]
    assert pd.Timestamp(trade["timestamp"]) == times[0]
    assert trade["fill_price"] == pytest.approx(11.0)
    order = result.orders.iloc[0]
    assert order["status"] == "filled"
    assert order["reason"] == "filled"
    assert order["origin"] == "strategy"
    assert order["execution_timing"] == "same_close"
    assert pd.Timestamp(order["fill_timestamp"]) == times[0]
    assert order["fill_price"] == pytest.approx(11.0)


def test_next_open_timing_fills_on_following_bar_open(tmp_path):
    store, times = _ohlc_store(tmp_path, [10.0, 20.0, 30.0], [11.0, 21.0, 31.0])
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 0.25}),
        times[0],
        times[-1],
        "next_open",
    ).run()

    trade = result.trades.iloc[0]
    assert pd.Timestamp(trade["order_timestamp"]) == times[0]
    assert pd.Timestamp(trade["timestamp"]) == times[1]
    assert trade["fill_price"] == pytest.approx(20.0)
    order = result.orders.iloc[0]
    assert order["status"] == "filled"
    assert order["delay_required"] == 1
    assert order["bars_seen"] == 1


def test_next_close_timing_fills_on_following_bar_close(tmp_path):
    store, times = _ohlc_store(tmp_path, [10.0, 20.0, 30.0], [11.0, 21.0, 31.0])
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 0.25}),
        times[0],
        times[-1],
        "next_close",
    ).run()

    trade = result.trades.iloc[0]
    assert pd.Timestamp(trade["order_timestamp"]) == times[0]
    assert pd.Timestamp(trade["timestamp"]) == times[1]
    assert trade["fill_price"] == pytest.approx(21.0)
    order = result.orders.iloc[0]
    assert order["status"] == "filled"
    assert order["delay_required"] == 1
    assert order["bars_seen"] == 1


def test_delay_bars_timing_carries_order_across_multiple_bars(tmp_path):
    store, times = _ohlc_store(
        tmp_path,
        [10.0, 20.0, 30.0, 40.0],
        [11.0, 21.0, 31.0, 41.0],
    )
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 0.25}),
        times[0],
        times[-1],
        "delay_bars",
        delay_bars=2,
    ).run()

    trade = result.trades.iloc[0]
    assert pd.Timestamp(trade["order_timestamp"]) == times[0]
    assert pd.Timestamp(trade["timestamp"]) == times[2]
    assert trade["fill_price"] == pytest.approx(31.0)
    order = result.orders.iloc[0]
    assert order["status"] == "filled"
    assert order["delay_required"] == 2
    assert order["bars_seen"] == 2


def test_rejected_portfolio_order_is_recorded_as_diagnostic(tmp_path):
    store, times = _ohlc_store(tmp_path, [10.0, 10.0], [10.0, 10.0])
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 1.1}),
        times[0],
        times[-1],
        ExecutionTiming.SAME_CLOSE,
    ).run()

    assert result.trades.empty
    order = result.orders.iloc[0]
    assert order["status"] == "rejected"
    assert order["reason"] == "portfolio_constraint"
    assert order["portfolio_constraint"] == pytest.approx(1.0)
    assert "portfolio_order_rejected" in set(result.diagnostics["name"])
    reason = result.diagnostic("portfolio_rejection_constraint")
    assert reason.loc[times[0], "AAA"] == pytest.approx(1.0)


def test_delayed_order_unfilled_at_end_of_run(tmp_path):
    store, times = _ohlc_store(tmp_path, [10.0], [11.0])
    result = _timing_engine(
        store,
        BuyAndHoldOnce({"AAA": 0.25}),
        times[0],
        times[0],
        "next_open",
    ).run()

    assert result.trades.empty
    order = result.orders.iloc[0]
    assert order["status"] == "unfilled"
    assert order["reason"] == "no_future_matching_bar"
    assert order["bars_seen"] == 0
    assert pd.Timestamp(order["terminal_timestamp"]) == pd.Timestamp(times[0]).normalize()


def test_conservation_identity_holds_every_bar(sample_result):
    ec = sample_result.equity_curve
    # equity == cash + mark-to-market, and net_exposure*equity == mark-to-market.
    reconstructed = ec["cash"] + ec["net_exposure"] * ec["equity"]
    assert np.allclose(reconstructed.to_numpy(), ec["equity"].to_numpy(), rtol=1e-9, atol=1e-6)


def test_determinism_identical_runs(sample_data_dir):
    r1 = _engine(ParquetMarketData(sample_data_dir), EqualWeightRebalance()).run()
    r2 = _engine(ParquetMarketData(sample_data_dir), EqualWeightRebalance()).run()
    pd.testing.assert_frame_equal(r1.equity_curve, r2.equity_curve)
    pd.testing.assert_frame_equal(r1.trades, r2.trades)


def test_engine_run_is_single_use(sample_data_dir):
    engine = _engine(ParquetMarketData(sample_data_dir), EqualWeightRebalance())
    engine.run()

    with pytest.raises(RuntimeError, match="single-use"):
        engine.run()


def test_streaming_engine_matches_eager_engine(sample_data_dir, monkeypatch):
    monkeypatch.setattr(Engine, "_STREAM_CHUNK_DAYS", 7)

    streaming = _engine(ParquetMarketData(sample_data_dir), EqualWeightRebalance()).run()
    eager = _engine(EagerOnlyData(ParquetMarketData(sample_data_dir)), EqualWeightRebalance()).run()

    pd.testing.assert_frame_equal(streaming.equity_curve, eager.equity_curve)
    pd.testing.assert_frame_equal(streaming.trades, eager.trades)
    pd.testing.assert_frame_equal(streaming.orders, eager.orders)
    pd.testing.assert_frame_equal(streaming.positions, eager.positions)
    pd.testing.assert_frame_equal(streaming.diagnostics, eager.diagnostics)
    assert streaming.meta["n_sessions"] == eager.meta["n_sessions"]


def test_split_doubles_shares_and_keeps_equity_continuous(tmp_path):
    # AAA flat at 100 for 5 sessions, 2-for-1 split, then flat at 50 for 5 sessions.
    pre = list(pd.bdate_range("2022-01-03", periods=5))
    post = list(pd.bdate_range(pre[-1] + pd.Timedelta(days=1), periods=5))
    times = pre + post
    closes = [100.0] * 5 + [50.0] * 5
    split_date = post[0].strftime("%Y-%m-%d")
    store = build_store(
        tmp_path / "split",
        {"AAA": (times, closes)},
        actions=[
            {
                "date": split_date,
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            }
        ],
    )
    result = _engine(
        store,
        BuyAndHoldOnce({"AAA": 1.0}),
        start=times[0].strftime("%Y-%m-%d"),
        end=times[-1].strftime("%Y-%m-%d"),
    ).run()
    ec = result.equity_curve
    # Equity is flat across the split (price halves exactly as shares double).
    assert ec["equity"].max() - ec["equity"].min() == pytest.approx(0.0, abs=1.0)
    # Final positions weight ~1.0 (fully invested in AAA throughout).
    assert ec["net_exposure"].iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_dividend_credits_cash(tmp_path):
    # BBB flat at 100 throughout; a 2.0/share dividend mid-stream.
    times = list(pd.bdate_range("2022-01-03", periods=8))
    div_date = times[4].strftime("%Y-%m-%d")
    store = build_store(
        tmp_path / "div",
        {"BBB": (times, [100.0] * 8)},
        actions=[
            {
                "date": div_date,
                "symbol": "BBB",
                "action_type": "dividend",
                "amount": 2.0,
                "ratio": None,
            }
        ],
    )
    result = _engine(
        store,
        BuyAndHoldOnce({"BBB": 1.0}),
        start=times[0].strftime("%Y-%m-%d"),
        end=times[-1].strftime("%Y-%m-%d"),
    ).run()
    ec = result.equity_curve
    # Equity steps up by exactly shares*amount on the dividend date (model
    # credits cash; flat fixture has no ex-date price drop). 1_000_000 capital
    # fully invested in BBB at 100 -> 10_000 shares; 10_000 * 2.0 == 20_000.
    before = ec["equity"].iloc[3]
    after = ec["equity"].iloc[5]
    assert after - before == pytest.approx(20_000.0)


def test_rebucket_rolls_nonsession_dates_forward():
    # Use two full weeks so Saturday Jan 8 falls between sessions (not past the end).
    sessions = pd.DatetimeIndex(pd.bdate_range("2022-01-03", periods=10))
    # Saturday Jan 8 is between Fri Jan 7 and Mon Jan 10 — both in sessions.
    sat = pd.Timestamp("2022-01-08")
    out, dropped = rebucket_to_sessions({sat: ["payload"]}, sessions)
    assert dropped == []
    target = sessions[int(sessions.searchsorted(sat, side="left"))]
    assert out[pd.Timestamp(target)] == ["payload"]


def test_rebucket_drops_dates_after_last_session():
    sessions = pd.DatetimeIndex(pd.bdate_range("2022-01-03", periods=3))
    future = pd.Timestamp("2030-01-01")
    out, dropped = rebucket_to_sessions({future: ["x"]}, sessions)
    assert dropped == [future]
    assert out == {}


def test_split_keeps_equity_continuous_on_unadjusted_bars(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=5))
    store = ParquetMarketData(tmp_path / "store")
    # AAA splits 2-for-1 on the 3rd session; the unadjusted close halves 100 -> 50.
    store.write_bars(bars_table("AAA", times, [100.0, 100.0, 50.0, 50.0, 50.0]), "1d")
    store.write_universe(reference_table(["AAA"]))
    store.write_corporate_actions(
        actions_table(
            [
                {
                    "date": str(times[2].date()),
                    "symbol": "AAA",
                    "action_type": "split",
                    "amount": None,
                    "ratio": 2.0,
                }
            ]
        )
    )

    result = make_engine(
        store, EqualWeightRebalance(), str(times[0].date()), str(times[-1].date())
    ).run()
    equity = result.equity_curve["equity"]
    # Position doubles while price halves on the ex-date -> no equity jump.
    bar_to_bar = equity.pct_change().dropna().abs()
    assert (bar_to_bar < 1e-6).all()
