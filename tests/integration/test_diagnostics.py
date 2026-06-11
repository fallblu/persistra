from __future__ import annotations

from persistra import Engine, Portfolio, Strategy


class RecordingStrategy(Strategy):
    timeframes = ("1d",)
    warmup = 1

    def on_bar(self, ctx) -> None:
        closes = ctx.history().closes(1)
        if not len(closes.columns):
            return
        ctx.record("last_close", {s: float(closes.iloc[-1][s]) for s in closes.columns})
        n = len(ctx.universe)
        ctx.signal({s: 1.0 / n for s in ctx.universe})


def test_engine_populates_diagnostics(tiny_store):
    result = Engine(
        data=tiny_store,
        strategy=RecordingStrategy(),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()
    diag = result.diagnostics
    assert not diag.empty
    assert set(diag["name"]) == {"last_close"}
    wide = result.diagnostic("last_close")
    assert "AAA" in wide.columns


def test_engine_diagnostics_empty_when_unused(tiny_store, equal_weight_strategy):
    result = Engine(
        data=tiny_store,
        strategy=equal_weight_strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()
    assert result.diagnostics.empty
    assert list(result.diagnostics.columns) == [
        "bar_time",
        "timeframe",
        "name",
        "symbol",
        "value",
    ]
