import pandas as pd

from persistra.strategy.base import Strategy


def test_strategy_id_defaults_to_class_name():
    class MyAlpha(Strategy):
        pass

    assert MyAlpha.strategy_id == "MyAlpha"


def test_universe_on_returns_full_pool_by_default():
    pool = frozenset({"AAA", "BBB"})
    assert Strategy().universe_on(pd.Timestamp("2022-01-03"), pool) == pool
