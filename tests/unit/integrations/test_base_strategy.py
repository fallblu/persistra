"""Tests for the reusable Trading Engine strategy lifecycle."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    BarObservation,
    BaseStrategy,
    CashBalance,
    ComponentRequirements,
    CompositeStrategy,
    ElapsedSchedule,
    EmitMetricIntent,
    ExecutionInstrument,
    ExecutionPolicy,
    FillReceivedEvent,
    FxRate,
    IntentRejectedEvent,
    MarketSlice,
    MarketSliceClosedEvent,
    MinimumTargetChangeGuard,
    ObservationSchedule,
    OrderUpdatedEvent,
    OutstandingOrdersGuard,
    RiskPolicy,
    ScenarioBar,
    ScheduleState,
    StrategyCashBalance,
    StrategyConfiguration,
    StrategyContext,
    StrategyFill,
    StrategyForecast,
    StrategyHistory,
    StrategyInitialization,
    StrategyLifecycleError,
    StrategyOrder,
    StrategyPortfolio,
    StrategyPosition,
    StrategyView,
    TargetPortfolio,
    TargetQuantitiesIntent,
    TargetWeightsIntent,
    UniverseChange,
    WarmupPolicy,
    WeightedForecastCombiner,
    security_filter,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from persistra.integrations.trading_engine import ScenarioIntent


def _initialization() -> StrategyInitialization:
    instruments = (
        ExecutionInstrument("asset-a", "AAA", "USD", "0.01"),
        ExecutionInstrument("asset-b", "BBB", "USD", "0.01"),
    )
    return StrategyInitialization(
        engine_version="test-engine",
        scenario_contract_version="3",
        scenario_sha256="a" * 64,
        run_id="base-strategy",
        base_currency="USD",
        initial_cash=(CashBalance("USD", "10000"),),
        instruments=instruments,
        risk=RiskPolicy("1000", "1000", "1000", "1000000", "2", 5000, 2500, 0),
        execution=ExecutionPolicy(10000),
        metadata={},
    )


def _bars(sequence: int) -> tuple[ScenarioBar, ...]:
    return (
        ScenarioBar(
            "asset-a",
            Decimal(99 + sequence),
            Decimal(105),
            Decimal(98),
            Decimal(100 + sequence),
            Decimal(100),
        ),
        ScenarioBar(
            "asset-b",
            Decimal(199 + sequence),
            Decimal(205),
            Decimal(198),
            Decimal(200 + sequence),
            Decimal(100),
        ),
    )


def _market_slice(sequence: int) -> MarketSlice:
    start = pd.Timestamp("2026-01-01T14:30:00Z") + pd.Timedelta(days=sequence)
    end = start + pd.Timedelta(hours=6)
    return MarketSlice(
        slice_sequence=sequence,
        start_at=start,
        end_at=end,
        available_at=end + pd.Timedelta(seconds=1),
        received_at=end + pd.Timedelta(seconds=2),
        bars=_bars(sequence),
        fx_rates=(FxRate("USD", 1),),
    )


def _portfolio(
    *,
    held_asset_a: bool = False,
    weights_available: bool = True,
) -> StrategyPortfolio:
    if held_asset_a:
        cash = Decimal(9800)
        equity = Decimal(10000)
        position_value = Decimal(200)
        quantity = Decimal(2)
        weight: Decimal | None = Decimal("0.02") if weights_available else None
        cash_weight: Decimal | None = Decimal("0.98") if weights_available else None
    else:
        cash = Decimal(10000) if weights_available else Decimal(0)
        equity = cash
        position_value = Decimal(0)
        quantity = Decimal(0)
        weight = Decimal(0) if weights_available else None
        cash_weight = Decimal(1) if weights_available else None
    return StrategyPortfolio(
        base_currency="USD",
        cash=cash,
        net_market_value=position_value,
        long_market_value=position_value,
        short_market_value=0,
        gross_exposure=position_value,
        equity=equity,
        weights_available=weights_available,
        cash_weight=cash_weight,
        cash_balances=(StrategyCashBalance("USD", cash, 1, cash),),
        positions=(
            StrategyPosition("asset-a", quantity, 100, position_value, weight),
            StrategyPosition("asset-b", 0, 200, 0, Decimal(0) if weights_available else None),
        ),
    )


def _context(sequence: int, *, held_asset_a: bool = False) -> StrategyContext:
    market_slice = _market_slice(sequence)
    return StrategyContext(
        now=market_slice.received_at,
        portfolio=_portfolio(held_asset_a=held_asset_a),
        working_orders=(),
        latest_bars=market_slice.bars,
    )


def _market_event(sequence: int) -> MarketSliceClosedEvent:
    return MarketSliceClosedEvent(_market_slice(sequence))


class LifecycleStrategy(BaseStrategy):
    """Exercise warmup, filtering, history, schedules, and target completion."""

    name = "lifecycle"

    def __init__(self) -> None:
        super().__init__()
        self.selector_observations: list[int] = []
        self.data_views: list[StrategyView] = []
        self.changes: list[UniverseChange] = []
        self.warmup_completions = 0
        self.rebalances: list[StrategyView] = []

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        assert len(initialization.instruments) == 2

        def select(view: StrategyView) -> Iterable[str]:
            self.selector_observations.append(view.observations_seen)
            return ("asset-a",) if view.observations_seen == 1 else ("asset-b",)

        return StrategyConfiguration(
            history_capacity=2,
            warmup=WarmupPolicy(observations=3, security_observations=2),
            selector=select,
            selection_schedule=ObservationSchedule(every=2),
            rebalance_schedule=ObservationSchedule(every=2, start_at=3),
        )

    def on_data(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> Sequence[ScenarioIntent]:
        self.data_views.append(view)
        return (EmitMetricIntent("slice", str(market_slice.slice_sequence)),)

    def on_universe_changed(
        self,
        view: StrategyView,
        change: UniverseChange,
    ) -> Sequence[ScenarioIntent]:
        assert view.universe_change == change
        self.changes.append(change)
        return ()

    def on_warmup_completed(self, view: StrategyView) -> Sequence[ScenarioIntent]:
        assert not view.is_warming_up
        self.warmup_completions += 1
        return (EmitMetricIntent("warmup", "complete"),)

    def on_rebalance(self, view: StrategyView) -> Sequence[ScenarioIntent]:
        self.rebalances.append(view)
        return (view.target_quantities({"asset-b": 2}),)


class ForecastModel:
    """Return a stable caller-defined score for the ready universe."""

    requirements = ComponentRequirements(observations=3, security_observations=2)

    def __init__(self, name: str, scale: float) -> None:
        self.name = name
        self.scale = scale

    def update(self, view: StrategyView, market_slice: MarketSlice) -> StrategyForecast | None:
        if not view.universe:
            return None
        return StrategyForecast(
            self.name,
            pd.Series(
                {
                    instrument_id: (position + 1) * self.scale
                    for position, instrument_id in enumerate(view.universe)
                }
            ),
            market_slice.end_at,
        )


class ScoreConstructor:
    """Normalize positive combined scores into portfolio weights."""

    name = "score-constructor"
    requirements = ComponentRequirements()

    def construct(self, forecast: StrategyForecast, view: StrategyView) -> TargetPortfolio:
        del view
        normalized = forecast.values / forecast.values.sum()
        return TargetPortfolio(
            {
                instrument_id: Decimal(str(value)).quantize(Decimal("0.000001"))
                for instrument_id, value in normalized.items()
            }
        )


class HalfExposureOverlay:
    """Reserve half of portfolio equity as residual cash."""

    name = "half-exposure"
    requirements = ComponentRequirements()

    def apply(self, target: TargetPortfolio, view: StrategyView) -> TargetPortfolio:
        del view
        return TargetPortfolio(
            {
                key: (Decimal(str(value)) * Decimal("0.5")).quantize(Decimal("0.000001"))
                for key, value in target.weights.items()
            }
        )


def test_base_strategy_coordinates_warmup_history_universe_and_schedules() -> None:
    strategy = LifecycleStrategy()
    strategy.initialize(_initialization())

    first = strategy.on_event(_context(1), _market_event(1))
    second = strategy.on_event(_context(2), _market_event(2))
    third = strategy.on_event(_context(3), _market_event(3))

    assert [item.value for item in first if isinstance(item, EmitMetricIntent)] == ["1"]
    assert [item.value for item in second if isinstance(item, EmitMetricIntent)] == ["2"]
    assert strategy.selector_observations == [1, 3]
    assert [view.is_warming_up for view in strategy.data_views] == [True, True, False]
    assert [view.universe for view in strategy.data_views] == [(), ("asset-a",), ("asset-b",)]
    assert strategy.changes == [
        UniverseChange(added=("asset-a",)),
        UniverseChange(added=("asset-b",), removed=("asset-a",)),
    ]
    assert strategy.warmup_completions == 1
    assert len(strategy.rebalances) == 1
    target = next(item for item in third if isinstance(item, TargetQuantitiesIntent))
    assert [(item.instrument_id, item.quantity) for item in target.targets] == [
        ("asset-a", Decimal(0)),
        ("asset-b", Decimal(2)),
    ]
    history = strategy.data_views[-1].history
    assert [item.slice_sequence for item in history.observations("asset-a")] == [2, 3]
    assert history.latest("asset-a") is not None
    assert history.frame("asset-a").index.tolist() == [
        _market_slice(2).end_at,
        _market_slice(3).end_at,
    ]
    assert history.securities == ("asset-a", "asset-b")
    with pytest.raises(KeyError, match="missing"):
        history.observations("missing")


def test_composite_strategy_builds_one_traced_target_after_aggregated_warmup() -> None:
    strategy = CompositeStrategy(
        "composite",
        alpha_models=(ForecastModel("first", 1.0), ForecastModel("second", 2.0)),
        combiner=WeightedForecastCombiner({"first": 1.0, "second": 3.0}),
        portfolio_constructor=ScoreConstructor(),
        overlays=(HalfExposureOverlay(),),
        configuration=StrategyConfiguration(history_capacity=1),
    )
    strategy.initialize(_initialization())

    assert strategy.on_event(_context(1), _market_event(1)) == ()
    assert strategy.on_event(_context(2), _market_event(2)) == ()
    intents = strategy.on_event(_context(3), _market_event(3))

    assert len(intents) == 1
    target = cast("TargetWeightsIntent", intents[0])
    assert [(item.instrument_id, item.weight) for item in target.targets] == [
        ("asset-a", Decimal("0.166666")),
        ("asset-b", Decimal("0.333334")),
    ]
    assert strategy.last_decision is not None
    assert strategy.last_decision.forecast_sources == ("first", "second")
    assert strategy.last_decision.combined_source == "weighted-forecast"
    assert [stage.name for stage in strategy.last_decision.stages] == [
        "score-constructor",
        "half-exposure",
    ]
    assert strategy.last_decision.emitted


def test_composite_strategy_validates_models_and_forecast_combination() -> None:
    with pytest.raises(ValueError, match="positive sum"):
        WeightedForecastCombiner({"first": 0.0})
    with pytest.raises(ValueError, match="unique"):
        CompositeStrategy(
            "duplicate",
            alpha_models=(ForecastModel("same", 1.0), ForecastModel("same", 2.0)),
            combiner=WeightedForecastCombiner({"same": 1.0}),
            portfolio_constructor=ScoreConstructor(),
        )

    combiner = WeightedForecastCombiner({"first": 1.0, "second": 1.0})
    view = StrategyView(
        initialization=_initialization(),
        context=_context(1),
        history=StrategyHistory({"asset-a": (), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a", "asset-b"),
        universe=("asset-a", "asset-b"),
    )
    first = StrategyForecast("first", pd.Series({"asset-a": 1.0}), view.context.now)
    assert combiner.combine((first,), view) is None
    second = StrategyForecast("second", pd.Series({"asset-b": 1.0}), view.context.now)
    with pytest.raises(ValueError, match="identical"):
        combiner.combine((first, second), view)


def test_strategy_forecast_enforces_engine_timestamp_contract() -> None:
    values = pd.Series({"asset-a": 1.0})
    local = StrategyForecast(
        "alpha",
        values,
        pd.Timestamp("2026-01-02T09:30:00.123456-05:00"),
    )
    microsecond = StrategyForecast(
        "alpha",
        values,
        pd.Timestamp("2026-01-02T14:30:00.000001Z"),
    )

    assert local.as_of == pd.Timestamp("2026-01-02T14:30:00.123456Z")
    assert microsecond.as_of == pd.Timestamp("2026-01-02T14:30:00.000001Z")
    with pytest.raises(ValueError, match="timezone-aware"):
        StrategyForecast("alpha", values, pd.Timestamp("2026-01-02T14:30:00"))
    with pytest.raises(TypeError, match="pandas Timestamp"):
        StrategyForecast("alpha", values, cast("Any", pd.NaT))
    with pytest.raises(TypeError, match="pandas Timestamp"):
        StrategyForecast("alpha", values, cast("Any", "2026-01-02T14:30:00Z"))
    with pytest.raises(ValueError, match="microsecond precision"):
        StrategyForecast(
            "alpha",
            values,
            pd.Timestamp("2026-01-02T14:30:00.000000001Z"),
        )


def test_composite_strategy_rejects_future_alpha_and_combined_forecasts() -> None:
    class FutureModel(ForecastModel):
        def update(
            self,
            view: StrategyView,
            market_slice: MarketSlice,
        ) -> StrategyForecast:
            del market_slice
            return StrategyForecast(
                self.name,
                pd.Series({"asset-a": 1.0}),
                view.context.now + pd.Timedelta(microseconds=1),
            )

    class FutureCombiner:
        name = "future-combiner"
        requirements = ComponentRequirements()

        def combine(
            self,
            forecasts: tuple[StrategyForecast, ...],
            view: StrategyView,
        ) -> StrategyForecast:
            del forecasts
            return StrategyForecast(
                self.name,
                pd.Series({"asset-a": 1.0}),
                view.context.now + pd.Timedelta(microseconds=1),
            )

    view = StrategyView(
        initialization=_initialization(),
        context=_context(1),
        history=StrategyHistory({"asset-a": (), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a", "asset-b"),
        universe=("asset-a", "asset-b"),
    )
    future_alpha = CompositeStrategy(
        "future-alpha",
        alpha_models=(FutureModel("future", 1.0),),
        combiner=WeightedForecastCombiner({"future": 1.0}),
        portfolio_constructor=ScoreConstructor(),
    )
    with pytest.raises(StrategyLifecycleError, match=r"alpha model.*future-dated"):
        future_alpha.on_data(view, _market_slice(1))

    future_combined = CompositeStrategy(
        "future-combined",
        alpha_models=(ForecastModel("alpha", 1.0),),
        combiner=FutureCombiner(),
        portfolio_constructor=ScoreConstructor(),
    )
    with pytest.raises(StrategyLifecycleError, match=r"combiner.*future-dated"):
        future_combined.on_rebalance(view)


def test_rebalance_guards_use_completed_targets_and_authoritative_context() -> None:
    view = StrategyView(
        initialization=_initialization(),
        context=_context(1),
        history=StrategyHistory({"asset-a": (), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a", "asset-b"),
        universe=("asset-a", "asset-b"),
        _catalog=("asset-a", "asset-b"),
    )
    target = view.target_weights({"asset-a": "0.05"})
    change = MinimumTargetChangeGuard(0.1).evaluate(target, view)
    assert not change.approved
    assert "below minimum" in change.reason

    unavailable = replace(
        view, context=replace(view.context, portfolio=_portfolio(weights_available=False))
    )
    assert not MinimumTargetChangeGuard(0.0).evaluate(target, unavailable).approved
    working = replace(view, context=replace(view.context, working_orders=cast("Any", (object(),))))
    assert not OutstandingOrdersGuard().evaluate(target, working).approved
    assert OutstandingOrdersGuard().evaluate(target, view).approved


def test_composite_strategy_records_suppressed_rebalance() -> None:
    strategy = CompositeStrategy(
        "guarded",
        alpha_models=(ForecastModel("first", 1.0),),
        combiner=WeightedForecastCombiner({"first": 1.0}),
        portfolio_constructor=ScoreConstructor(),
        rebalance_guards=(MinimumTargetChangeGuard(0.9),),
    )
    strategy.initialize(_initialization())
    strategy.on_event(_context(1), _market_event(1))
    strategy.on_event(_context(2), _market_event(2))

    assert strategy.on_event(_context(3), _market_event(3)) == ()
    assert strategy.last_decision is not None
    assert not strategy.last_decision.emitted
    assert [item.guard for item in strategy.last_decision.guard_decisions] == [
        "minimum-target-change"
    ]


def test_base_strategy_forbids_order_changes_during_warmup_but_allows_metrics() -> None:
    class InvalidWarmupStrategy(BaseStrategy):
        name = "invalid-warmup"

        def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
            del initialization
            return StrategyConfiguration(warmup=WarmupPolicy(observations=2))

        def on_data(
            self,
            view: StrategyView,
            market_slice: MarketSlice,
        ) -> Sequence[ScenarioIntent]:
            del market_slice
            return (view.target_quantities({}),)

    strategy = InvalidWarmupStrategy()
    strategy.initialize(_initialization())
    with pytest.raises(StrategyLifecycleError, match="forbidden during warmup"):
        strategy.on_event(_context(1), _market_event(1))


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("liquidate", Decimal(0)),
        ("retain", Decimal("0.02")),
    ],
)
def test_weight_target_helper_applies_removal_policy(policy: str, expected: Decimal) -> None:
    initialization = _initialization()
    context = _context(1, held_asset_a=True)
    view = StrategyView(
        initialization=initialization,
        context=context,
        history=StrategyHistory({"asset-a": (), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a", "asset-b"),
        universe=("asset-b",),
        _catalog=("asset-a", "asset-b"),
        _removal_policy=cast("Any", policy),
    )

    intent = view.target_weights({"asset-b": "0.5"})

    assert isinstance(intent, TargetWeightsIntent)
    assert [(item.instrument_id, item.weight) for item in intent.targets] == [
        ("asset-a", expected),
        ("asset-b", Decimal("0.5")),
    ]
    with pytest.raises(ValueError, match="not in the universe"):
        view.target_weights({"asset-a": 0})
    with pytest.raises(TypeError, match="must be a mapping"):
        view.target_weights(cast("Any", []))


def test_target_helpers_reject_held_removals_and_unavailable_retain_weights() -> None:
    base = StrategyView(
        initialization=_initialization(),
        context=_context(1, held_asset_a=True),
        history=StrategyHistory({"asset-a": (), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a", "asset-b"),
        universe=("asset-b",),
        _catalog=("asset-a", "asset-b"),
        _removal_policy="error",
    )
    with pytest.raises(StrategyLifecycleError, match="nonzero position"):
        base.target_quantities({"asset-b": 1})
    with pytest.raises(StrategyLifecycleError, match="nonzero position"):
        base.target_weights({"asset-b": 1})

    unavailable_portfolio = StrategyPortfolio(
        base_currency="USD",
        cash=-200,
        net_market_value=200,
        long_market_value=200,
        short_market_value=0,
        gross_exposure=200,
        equity=0,
        weights_available=False,
        cash_weight=None,
        cash_balances=(StrategyCashBalance("USD", -200, 1, -200),),
        positions=(
            StrategyPosition("asset-a", 2, 100, 200, None),
            StrategyPosition("asset-b", 0, 200, 0, None),
        ),
    )
    unavailable_context = replace(base.context, portfolio=unavailable_portfolio)
    retain = replace(base, context=unavailable_context, _removal_policy="retain")
    with pytest.raises(StrategyLifecycleError, match="positive portfolio equity"):
        retain.target_weights({"asset-b": 1})
    quantity_target = retain.target_quantities({"asset-b": 1})
    assert quantity_target.targets[0].quantity == 2


def test_elapsed_schedule_security_filter_and_configuration_validation() -> None:
    first = pd.Timestamp("2026-01-01T00:00:00Z")
    schedule = ElapsedSchedule("1D", run_immediately=False)
    assert not schedule.is_due(ScheduleState(1, first, first, None))
    assert schedule.is_due(ScheduleState(2, first + pd.Timedelta(days=1), first, None))
    assert not schedule.is_due(
        ScheduleState(3, first + pd.Timedelta(days=1), first, first + pd.Timedelta(hours=12))
    )
    assert ElapsedSchedule("1D").is_due(ScheduleState(1, first, first, None))
    with pytest.raises(ValueError, match="positive"):
        ElapsedSchedule("0s")
    with pytest.raises(TypeError, match="boolean"):
        ElapsedSchedule("1D", run_immediately=cast("Any", 1))
    with pytest.raises(ValueError, match="nonnegative"):
        WarmupPolicy(elapsed="-1s")
    with pytest.raises(ValueError, match="positive"):
        WarmupPolicy(security_observations=0)
    with pytest.raises(ValueError, match="removal_policy"):
        StrategyConfiguration(removal_policy=cast("Any", "ignore"))
    with pytest.raises(TypeError, match="selector"):
        StrategyConfiguration(selector=cast("Any", 1))
    with pytest.raises(TypeError, match="selection_schedule"):
        StrategyConfiguration(selection_schedule=cast("Any", object()))
    with pytest.raises(TypeError, match="warmup must"):
        StrategyConfiguration(warmup=cast("Any", object()))

    observation = BarObservation(
        1,
        first,
        first + pd.Timedelta(hours=1),
        first + pd.Timedelta(hours=1),
        first + pd.Timedelta(hours=1),
        _bars(1)[0],
    )
    view = StrategyView(
        initialization=_initialization(),
        context=_context(1),
        history=StrategyHistory({"asset-a": (observation,), "asset-b": ()}),
        observations_seen=1,
        is_warming_up=False,
        ready_securities=("asset-a",),
        universe=("asset-a",),
        _catalog=("asset-a", "asset-b"),
    )
    selector = security_filter(
        lambda instrument_id, latest, _view: instrument_id == "asset-a" and latest is not None
    )
    assert tuple(selector(view)) == ("asset-a",)
    invalid_filter = security_filter(lambda _instrument_id, _latest, _view: cast("Any", 1))
    with pytest.raises(TypeError, match="predicate must return"):
        tuple(invalid_filter(view))


def test_specialized_hooks_and_lifecycle_guards() -> None:
    class HookStrategy(BaseStrategy):
        name = "hooks"

        def __init__(self) -> None:
            super().__init__()
            self.events: list[str] = []

        def on_fill(
            self,
            view: StrategyView,
            fill: StrategyFill,
        ) -> Sequence[ScenarioIntent]:
            assert not view.is_warming_up
            self.events.append(fill.fill_id)
            return ()

        def on_order_updated(
            self,
            view: StrategyView,
            order: StrategyOrder,
        ) -> Sequence[ScenarioIntent]:
            del view
            self.events.append(order.order_id)
            return ()

        def on_intent_rejected(
            self,
            view: StrategyView,
            reason: str,
        ) -> Sequence[ScenarioIntent]:
            del view
            self.events.append(reason)
            return ()

        def on_shutdown(self) -> None:
            self.events.append("shutdown")

    context = _context(1)
    strategy = HookStrategy()
    with pytest.raises(StrategyLifecycleError, match="not initialized"):
        strategy.on_event(context, IntentRejectedEvent("early"))
    strategy.initialize(_initialization())
    strategy.on_event(context, _market_event(1))
    order = StrategyOrder(
        "order-1",
        "asset-a",
        "buy",
        2,
        "market",
        None,
        "target_rebalance",
        "event-1",
        "event-1",
        1,
        context.now,
        1,
        0,
        0,
        "working",
        None,
    )
    fill = StrategyFill(
        "fill-1",
        "order-1",
        "asset-a",
        "USD",
        "buy",
        2,
        100,
        200,
        0,
        context.now,
        1,
    )
    assert strategy.on_event(context, FillReceivedEvent(fill)) == ()
    assert strategy.on_event(context, OrderUpdatedEvent(order)) == ()
    assert strategy.on_event(context, IntentRejectedEvent("risk limit")) == ()
    strategy.shutdown()
    assert strategy.events == ["fill-1", "order-1", "risk limit", "shutdown"]
    with pytest.raises(StrategyLifecycleError, match="already shut down"):
        strategy.shutdown()
    with pytest.raises(StrategyLifecycleError, match="shut down"):
        strategy.on_event(context, IntentRejectedEvent("late"))


def test_base_strategy_rejects_invalid_configuration_selection_and_hook_results() -> None:
    class InvalidConfiguration(BaseStrategy):
        name = "invalid-configuration"

        def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
            del initialization
            return cast("Any", object())

    with pytest.raises(TypeError, match="configure must return"):
        InvalidConfiguration().initialize(_initialization())

    class InvalidSelector(BaseStrategy):
        name = "invalid-selector"

        def __init__(self, selected: object) -> None:
            super().__init__()
            self.selected = selected

        def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
            del initialization
            return StrategyConfiguration(selector=lambda view: cast("Any", self.selected))

    for selected, message in [
        ("asset-a", "iterable"),
        (("unknown",), "unknown security"),
        (("asset-a", "asset-a"), "duplicate security"),
    ]:
        strategy = InvalidSelector(selected)
        strategy.initialize(_initialization())
        with pytest.raises((TypeError, ValueError), match=message):
            strategy.on_event(_context(1), _market_event(1))

    class InvalidHook(BaseStrategy):
        name = "invalid-hook"

        def on_rebalance(self, view: StrategyView) -> Sequence[ScenarioIntent]:
            del view
            return cast("Any", "invalid")

    strategy = InvalidHook()
    strategy.initialize(_initialization())
    with pytest.raises(TypeError, match="must return a sequence"):
        strategy.on_event(_context(1), _market_event(1))

    with pytest.raises(StrategyLifecycleError, match="already initialized"):
        strategy.initialize(_initialization())

    class InvalidSchedule:
        def is_due(self, state: ScheduleState) -> bool:
            del state
            return cast("Any", 1)

    class InvalidScheduledStrategy(BaseStrategy):
        name = "invalid-schedule"

        def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
            del initialization
            return StrategyConfiguration(selection_schedule=InvalidSchedule())

    invalid_schedule = InvalidScheduledStrategy()
    invalid_schedule.initialize(_initialization())
    with pytest.raises(TypeError, match="must return a boolean"):
        invalid_schedule.on_event(_context(1), _market_event(1))
