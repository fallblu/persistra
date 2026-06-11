from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from persistra.core.state import PortfolioState
from persistra.pipeline.allocation import TopN
from persistra.pipeline.signal import LinearSignal
from persistra.strategy.context import StrategyContext
from persistra.strategy.factor import FactorStrategy

if TYPE_CHECKING:
    from persistra.core.history import HistoryView

_STATE = PortfolioState(
    equity=1000.0,
    cash=1000.0,
    positions={},
    weights={},
    gross_exposure=0.0,
    net_exposure=0.0,
)

_UNIVERSE = frozenset({"AAA", "BBB"})


def _ctx(populated_history: HistoryView) -> StrategyContext:
    return StrategyContext(
        timestamp=pd.Timestamp("2022-01-06"),
        timeframe="1d",
        histories={"1d": populated_history},
        portfolio=_STATE,
        universe=_UNIVERSE,
    )


class ConstantFeatureFactor(FactorStrategy):
    """Concrete FactorStrategy: returns a constant feature table each bar.

    compute_features returns a DataFrame with index = universe, column "score"
    carrying the values supplied at construction time.
    """

    def __init__(self, scores: dict[str, float], **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._scores = scores

    def compute_features(self, ctx: StrategyContext) -> pd.DataFrame:
        return (
            pd.DataFrame(
                {"score": self._scores},
            )
            .T.rename(index={"score": "score"})
            .T
        )


class DirectScoreFactor(FactorStrategy):
    """Returns a feature DataFrame with index=symbols, column='score'."""

    def __init__(self, scores: dict[str, float], **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._scores = scores

    def compute_features(self, ctx: StrategyContext) -> pd.DataFrame:
        return pd.DataFrame({"score": pd.Series(self._scores)})


class EmptyFactor(FactorStrategy):
    """Always returns an empty DataFrame — should produce no emission."""

    def compute_features(self, ctx: StrategyContext) -> pd.DataFrame:
        return pd.DataFrame()


def test_factor_emits_weights_whose_keys_are_subset_of_universe(populated_history):
    """on_bar with a constant-score factor should produce emitted_weights with
    keys that are a subset of the universe."""
    factor = DirectScoreFactor(
        scores={"AAA": 2.0, "BBB": 1.0},
        signal_combiner=LinearSignal({"score": 1.0}),
    )
    ctx = _ctx(populated_history)
    factor.on_bar(ctx)
    w = ctx.emitted_weights
    assert w is not None, "FactorStrategy must emit weights when features are non-empty"
    assert set(w.keys()) <= _UNIVERSE


def test_factor_with_allocation_rule_produces_correct_long_short_weights(populated_history):
    """With TopN(n=1, long_short=True) and AAA > BBB, AAA gets +0.5 and BBB gets -0.5."""
    factor = DirectScoreFactor(
        scores={"AAA": 3.0, "BBB": 1.0},
        signal_combiner=LinearSignal({"score": 1.0}),
        allocation=TopN(n=1, long_short=True),
    )
    ctx = _ctx(populated_history)
    factor.on_bar(ctx)
    w = ctx.emitted_weights
    assert w is not None
    # Derived independently: top-1 long = AAA at +0.5; bottom-1 short = BBB at -0.5
    assert w["AAA"] == pytest.approx(0.5)
    assert w["BBB"] == pytest.approx(-0.5)


def test_factor_emits_nothing_when_compute_features_returns_empty(populated_history):
    """If compute_features returns an empty DataFrame, on_bar must not call ctx.signal()."""
    factor = EmptyFactor(signal_combiner=LinearSignal({"score": 1.0}))
    ctx = _ctx(populated_history)
    factor.on_bar(ctx)
    assert ctx.emitted_weights is None


def test_factor_construct_and_on_bar_without_optional_pipeline(populated_history):
    """FactorStrategy with only a SignalCombiner (no allocation/sizer/risk) still works.
    Emitted weights are the raw combined scores stored as direct target weights."""
    factor = DirectScoreFactor(
        scores={"AAA": 0.7, "BBB": 0.3},
        signal_combiner=LinearSignal({"score": 1.0}),
    )
    ctx = _ctx(populated_history)
    factor.on_bar(ctx)
    w = ctx.emitted_weights
    assert w is not None
    # LinearSignal with weight 1.0 on "score" passes scores straight through
    assert w["AAA"] == pytest.approx(0.7)
    assert w["BBB"] == pytest.approx(0.3)
