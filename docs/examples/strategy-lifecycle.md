# Strategy-lifecycle examples

`BaseStrategy` turns the low-level external protocol into focused hooks with bounded history,
warm-up, filtering, selection and rebalance schedules, and complete target helpers. These
examples run entirely in Python; the final section shows how to expose the same object to Trading
Engine.

## Implement a warm-up and rebalance policy

```python
from decimal import Decimal

from persistra.integrations.trading_engine import (
    BaseStrategy,
    EmitMetricIntent,
    MarketSlice,
    ObservationSchedule,
    ScenarioIntent,
    StrategyConfiguration,
    StrategyInitialization,
    StrategyView,
    WarmupPolicy,
    security_filter,
)


class MomentumStrategy(BaseStrategy):
    name = "warmup-momentum"
    version = "1"

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        assert initialization.instruments
        selector = security_filter(
            lambda instrument_id, latest, view: (
                latest is not None
                and latest.bar.volume >= Decimal("100")
                and instrument_id in view.ready_securities
            )
        )
        return StrategyConfiguration(
            history_capacity=5,
            warmup=WarmupPolicy(observations=3, security_observations=2),
            selector=selector,
            selection_schedule=ObservationSchedule(every=1),
            rebalance_schedule=ObservationSchedule(every=2, start_at=3),
            removal_policy="liquidate",
        )

    def on_data(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> tuple[ScenarioIntent, ...]:
        return (
            EmitMetricIntent(
                "observations-seen",
                str(view.observations_seen),
            ),
        )

    def on_rebalance(self, view: StrategyView) -> tuple[ScenarioIntent, ...]:
        scores: dict[str, Decimal] = {}
        for instrument_id in view.universe:
            history = view.history.observations(instrument_id)
            scores[instrument_id] = history[-1].bar.close / history[0].bar.close - 1
        leaders = [instrument_id for instrument_id, score in scores.items() if score > 0]
        weight = Decimal(1) / Decimal(len(leaders)) if leaders else Decimal(0)
        return (
            view.target_weights(
                {instrument_id: weight for instrument_id in leaders}
            ),
        )
```

History is ingested before `on_data` and `on_rebalance`. The filter can inspect the latest
observation, but a security enters the effective universe only after its per-security warm-up.
Order-changing intents are forbidden until global warm-up also completes.

## Drive the lifecycle without an engine binary

Build the same typed initialization and event objects the protocol host receives. This is useful
for fast lifecycle tests:

```python
import pandas as pd

from persistra.integrations.trading_engine import (
    CashBalance,
    ExecutionInstrument,
    ExecutionPolicy,
    FxRate,
    MarketSliceClosedEvent,
    RiskPolicy,
    ScenarioBar,
    StrategyCashBalance,
    StrategyContext,
    StrategyPortfolio,
    StrategyPosition,
    TargetWeightsIntent,
)

instrument = ExecutionInstrument("asset-a", "AAA", "USD", "0.01")
initialization = StrategyInitialization(
    engine_version="example-engine",
    scenario_contract_version="3",
    scenario_sha256="a" * 64,
    run_id="lifecycle-example",
    base_currency="USD",
    initial_cash=(CashBalance("USD", "10000"),),
    instruments=(instrument,),
    risk=RiskPolicy(
        "1000",
        "1000",
        "1000",
        "1000000",
        "2",
        5000,
        2500,
        0,
    ),
    execution=ExecutionPolicy(10000),
    metadata={},
)


def event_context(sequence: int) -> tuple[StrategyContext, MarketSliceClosedEvent]:
    start = pd.Timestamp("2026-01-01T14:30:00Z") + pd.Timedelta(days=sequence)
    end = start + pd.Timedelta(hours=6)
    bar = ScenarioBar(
        "asset-a",
        Decimal(99 + sequence),
        Decimal(102 + sequence),
        Decimal(98 + sequence),
        Decimal(100 + sequence),
        Decimal(1000),
    )
    market_slice = MarketSlice(
        slice_sequence=sequence,
        start_at=start,
        end_at=end,
        available_at=end + pd.Timedelta(seconds=1),
        received_at=end + pd.Timedelta(seconds=2),
        bars=(bar,),
        fx_rates=(FxRate("USD", 1),),
    )
    portfolio = StrategyPortfolio(
        base_currency="USD",
        cash=Decimal(10000),
        net_market_value=Decimal(0),
        long_market_value=Decimal(0),
        short_market_value=Decimal(0),
        gross_exposure=Decimal(0),
        equity=Decimal(10000),
        weights_available=True,
        cash_weight=Decimal(1),
        cash_balances=(
            StrategyCashBalance("USD", Decimal(10000), Decimal(1), Decimal(10000)),
        ),
        positions=(
            StrategyPosition("asset-a", Decimal(0), bar.close, Decimal(0), Decimal(0)),
        ),
    )
    context = StrategyContext(
        now=market_slice.received_at,
        portfolio=portfolio,
        working_orders=(),
        latest_bars=(bar,),
    )
    return context, MarketSliceClosedEvent(market_slice)


strategy = MomentumStrategy()
strategy.initialize(initialization)
responses = []
for sequence in range(1, 4):
    context, event = event_context(sequence)
    responses.extend(strategy.on_event(context, event))

assert any(isinstance(intent, TargetWeightsIntent) for intent in responses)
strategy.shutdown()
```

The engine remains authoritative in integration tests. A local lifecycle test can verify
dispatch and target formation, but it does not simulate fills, target persistence, fees, or
accounting.

## Select on multiple conditions

A selector can use instrument metadata, bounded history, and current portfolio state:

```python
from collections.abc import Iterable

from persistra.integrations.trading_engine import StrategyView


def price_and_volume_selector(view: StrategyView) -> Iterable[str]:
    held = {
        position.instrument_id
        for position in view.context.portfolio.positions
        if position.quantity != 0
    }
    for instrument in view.initialization.instruments:
        instrument_id = instrument.instrument_id
        latest = view.history.latest(instrument_id)
        if latest is None:
            continue
        liquid = latest.bar.volume >= Decimal("100000")
        priced = Decimal("5") <= latest.bar.close <= Decimal("500")
        if (liquid and priced) or instrument_id in held:
            yield instrument_id
```

Including held securities can make exit logic explicit. Alternatively, let filtering remove
them and choose `liquidate`, `retain`, or `error` as the removal policy.

## Use elapsed schedules

```python
from persistra.integrations.trading_engine import ElapsedSchedule


class HourlyStrategy(MomentumStrategy):
    name = "hourly-momentum"

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        configuration = super().configure(initialization)
        return StrategyConfiguration(
            history_capacity=configuration.history_capacity,
            warmup=WarmupPolicy(elapsed="2h", security_observations=2),
            selector=configuration.selector,
            selection_schedule=ElapsedSchedule("30min"),
            rebalance_schedule=ElapsedSchedule("1h", run_immediately=False),
            removal_policy=configuration.removal_policy,
        )
```

Elapsed schedules use market-slice end times, not wall-clock time spent running the replay.

## React to fills and rejections

Override only the hooks a strategy needs:

```python
from persistra.integrations.trading_engine import (
    StrategyFill,
    StrategyOrder,
)


class ReactiveStrategy(MomentumStrategy):
    name = "reactive-momentum"

    def on_fill(
        self,
        view: StrategyView,
        fill: StrategyFill,
    ) -> tuple[ScenarioIntent, ...]:
        del view
        return (EmitMetricIntent("last-fill", fill.fill_id),)

    def on_order_updated(
        self,
        view: StrategyView,
        order: StrategyOrder,
    ) -> tuple[ScenarioIntent, ...]:
        del view
        return (EmitMetricIntent("order-status", order.status),)

    def on_intent_rejected(
        self,
        view: StrategyView,
        reason: str,
    ) -> tuple[ScenarioIntent, ...]:
        del view
        return (EmitMetricIntent("intent-rejected", reason),)
```

Use `view.context.working_orders` and the marked portfolio to make follow-up decisions. Never
assume a requested target has filled.

## Create a service entry point

Put serving in a dedicated executable file so importing the strategy remains side-effect free:

```python
from persistra.integrations.trading_engine import serve_strategy

# from my_strategy import MomentumStrategy
# serve_strategy(MomentumStrategy())
```

Standard output belongs to protocol JSON Lines. Send diagnostics to standard error. Declare the
strategy file and every model, configuration, or data artifact in `StrategyProcess` before
replay.
