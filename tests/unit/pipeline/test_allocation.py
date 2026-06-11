import pandas as pd
import pytest

from persistra.pipeline.allocation import Decile, Direct, RankWeighted, TopN


def test_topn_long_short_dollar_neutral():
    scores = pd.Series({"A": 5.0, "B": 4.0, "C": 1.0, "D": 0.0})
    w = TopN(n=1, long_short=True).allocate(scores)
    assert w["A"] == pytest.approx(0.5)
    assert w["D"] == pytest.approx(-0.5)
    assert sum(abs(v) for v in w.values()) == pytest.approx(1.0)
    assert sum(w.values()) == pytest.approx(0.0)


def test_topn_long_only_sums_to_one():
    scores = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    w = TopN(n=2, long_short=False).allocate(scores)
    assert set(w) == {"A", "B"}
    assert sum(w.values()) == pytest.approx(1.0)


def test_topn_empty_universe_returns_empty():
    assert TopN(n=1).allocate(pd.Series(dtype=float)) == {}


def test_topn_rejects_zero_n():
    with pytest.raises(ValueError):
        TopN(n=0)


def test_decile_rejects_fraction_out_of_range():
    with pytest.raises(ValueError):
        Decile(fraction=0.0)
    with pytest.raises(ValueError):
        Decile(fraction=0.75)


def test_rankweighted_abs_sum_one_and_neutral():
    scores = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0})
    w = RankWeighted().allocate(scores)
    assert sum(abs(v) for v in w.values()) == pytest.approx(1.0)
    assert sum(w.values()) == pytest.approx(0.0)


def test_direct_passes_scores_through():
    w = Direct().allocate(pd.Series({"A": 0.3, "B": -0.2}))
    assert w == {"A": pytest.approx(0.3), "B": pytest.approx(-0.2)}
