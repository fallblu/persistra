import pandas as pd

from persistra.core.state import PortfolioState
from persistra.pipeline.allocation import TopN
from persistra.strategy.context import StrategyContext

_STATE = PortfolioState(
    equity=1000.0, cash=1000.0, positions={}, weights={}, gross_exposure=0.0, net_exposure=0.0
)


def _ctx(populated_history):
    return StrategyContext(
        timestamp=pd.Timestamp("2022-01-06"),
        timeframe="1d",
        histories={"1d": populated_history},
        portfolio=_STATE,
        universe=frozenset({"AAA", "BBB"}),
    )


def test_signal_direct_dict_stored_as_weights(populated_history):
    ctx = _ctx(populated_history)
    ctx.signal({"AAA": 0.5, "BBB": -0.5})
    assert ctx.emitted_weights == {"AAA": 0.5, "BBB": -0.5}


def test_signal_none_until_emitted(populated_history):
    assert _ctx(populated_history).emitted_weights is None


def test_signal_runs_allocation_pipeline(populated_history):
    ctx = _ctx(populated_history)
    ctx.signal(pd.Series({"AAA": 2.0, "BBB": 1.0}), allocation=TopN(n=1, long_short=True))
    w = ctx.emitted_weights
    assert w is not None
    assert w["AAA"] == 0.5 and w["BBB"] == -0.5


def test_fork_has_clean_emission_state(populated_history):
    ctx = _ctx(populated_history)
    ctx.signal({"AAA": 1.0})
    child = ctx._fork()
    assert child.emitted_weights is None


def _bare_ctx():
    return StrategyContext(
        timestamp=pd.Timestamp("2022-01-03"),
        timeframe="1d",
        histories={},
        portfolio=_STATE,
        universe=frozenset({"AAA", "BBB"}),
    )


def test_record_scalar_appends_one_row_with_null_symbol():
    ctx = _bare_ctx()
    ctx.record("regime", 1.0)
    rows = ctx.recorded
    assert len(rows) == 1
    assert rows[0]["name"] == "regime"
    assert rows[0]["symbol"] is None
    assert rows[0]["value"] == 1.0
    assert str(rows[0]["bar_time"]) == "2022-01-03 00:00:00"
    assert rows[0]["timeframe"] == "1d"


def test_record_dict_appends_one_row_per_symbol():
    ctx = _bare_ctx()
    ctx.record("zscore", {"AAA": 1.5, "BBB": -0.5})
    rows = ctx.recorded
    assert {r["symbol"] for r in rows} == {"AAA", "BBB"}
    assert all(r["name"] == "zscore" for r in rows)


def test_record_series_appends_one_row_per_symbol():
    ctx = _bare_ctx()
    ctx.record("mom", pd.Series({"AAA": 0.1, "BBB": 0.2}))
    rows = ctx.recorded
    assert {r["symbol"] for r in rows} == {"AAA", "BBB"}
    assert {r["value"] for r in rows} == {0.1, 0.2}


def test_record_same_name_twice_in_bar_overwrites():
    ctx = _bare_ctx()
    ctx.record("zscore", {"AAA": 1.0})
    ctx.record("zscore", {"AAA": 2.0})
    rows = [r for r in ctx.recorded if r["name"] == "zscore"]
    assert len(rows) == 1
    assert rows[0]["value"] == 2.0


def test_fork_has_clean_recorded_state():
    ctx = _bare_ctx()
    ctx.record("a", 1.0)
    child = ctx._fork()
    assert child.recorded == []
