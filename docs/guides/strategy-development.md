# Develop a strategy

Persistra provides two related abstractions for Python strategies executed by Trading Engine:

- `BaseStrategy` manages one strategy's lifecycle, history, warm-up, selection, schedules, and
  typed event dispatch.
- `CompositeStrategy` adds a signal-to-target pipeline made of alpha models, a forecast combiner,
  a portfolio constructor, optional target overlays, and rebalance guards.

Both implement the synchronous external-strategy protocol. Trading Engine supplies one immutable
event context at a time and waits for the response before continuing.

## Choose the smallest useful abstraction

Subclass `BaseStrategy` when a few lifecycle hooks express the behavior clearly. Use
`CompositeStrategy` when signal estimation, forecast combination, portfolio construction, and
risk overlays should be replaceable and testable independently.

Use the lower-level `ExternalStrategy` protocol only when the application must own all event
dispatch and state policy. It is not required for ordinary strategies.

## Configure lifecycle policy

Return a `StrategyConfiguration` from `configure`. Configuration is fixed for the initialized
run and receives the engine's complete instrument catalog, cash, risk, and execution policy.

```python
from persistra.integrations.trading_engine import (
    BaseStrategy,
    ObservationSchedule,
    StrategyConfiguration,
    StrategyInitialization,
    WarmupPolicy,
)


class ScheduledStrategy(BaseStrategy):
    name = "scheduled-strategy"
    version = "1"

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        assert initialization.instruments
        return StrategyConfiguration(
            history_capacity=120,
            warmup=WarmupPolicy(
                observations=60,
                elapsed="5h",
                security_observations=40,
            ),
            selection_schedule=ObservationSchedule(every=10),
            rebalance_schedule=ObservationSchedule(every=5, start_at=60),
            removal_policy="liquidate",
        )
```

`history_capacity` is the maximum retained bars per catalog security. Make it at least as large
as the longest calculation window. It bounds memory; it does not define readiness by itself.

Warm-up completes only when all configured conditions pass:

- the strategy has seen at least `observations` completed slices;
- at least `elapsed` market time has passed since the first slice end;
- a security needs `security_observations` bars before it can enter the effective universe.

Global warm-up and per-security readiness solve different problems. A late or intermittently
missing security can remain excluded after global warm-up while ready securities continue.

## Choose observation or elapsed schedules

`ObservationSchedule` uses one-based completed-slice counts:

```python
from persistra.integrations.trading_engine import ObservationSchedule

every_fifth = ObservationSchedule(every=5)
after_warmup = ObservationSchedule(every=5, start_at=60)
```

`ElapsedSchedule` uses market-slice end times and can run immediately or after one complete
interval:

```python
from persistra.integrations.trading_engine import ElapsedSchedule

hourly = ElapsedSchedule("1h")
delayed_hourly = ElapsedSchedule("1h", run_immediately=False)
```

Selection and rebalancing have separate schedules. A selection run updates the eligible catalog
subset. A rebalance run asks the strategy for intents only after warm-up.

## Filter the fixed catalog

Filtering never adds instruments to a scenario. It chooses from the catalog supplied during
initialization. A selector receives the current `StrategyView` and returns instrument IDs:

```python
from collections.abc import Iterable

from persistra.integrations.trading_engine import StrategyView


def liquid_catalog(view: StrategyView) -> Iterable[str]:
    for instrument in view.initialization.instruments:
        latest = view.history.latest(instrument.instrument_id)
        if latest is not None and latest.bar.volume >= 10_000:
            yield instrument.instrument_id
```

For a per-security predicate, use `security_filter`:

```python
from persistra.integrations.trading_engine import security_filter

positive_price = security_filter(
    lambda instrument_id, latest, view: (
        latest is not None and latest.bar.close > 0 and instrument_id in view.ready_securities
    )
)
```

The effective universe is the intersection of selected and ready securities. Unknown IDs and
non-Boolean filter results fail immediately.

Choose how to handle a held security removed by filtering:

| Policy | Complete target behavior |
|---|---|
| `liquidate` | Target zero for the removed security |
| `retain` | Carry its authoritative filled position or weight forward |
| `error` | Reject target completion while a removed position is nonzero |

`retain` uses actual engine state, not the last requested target. Retained weight targets require
positive equity and available realized weights.

## Read bounded causal history

Every completed market slice is ingested before `on_data`, universe, warm-up, and rebalance hooks
run. A `BarObservation` retains the slice sequence and all four causal clocks with its bar.

```python
from persistra.integrations.trading_engine import StrategyView


def trailing_return(view: StrategyView, instrument_id: str, window: int) -> float | None:
    observations = view.history.observations(instrument_id)
    if len(observations) < window:
        return None
    first = float(observations[-window].bar.close)
    last = float(observations[-1].bar.close)
    return last / first - 1.0
```

Use `history.frame(instrument_id)` when pandas operations are clearer. The frame includes slice
clocks and normalized bar values. Treat it as a snapshot: callbacks cannot mutate lifecycle
history.

## Implement focused hooks

`BaseStrategy` dispatches typed callbacks in causal order:

| Hook | Purpose |
|---|---|
| `on_initialize` | Allocate strategy-owned state after configuration |
| `on_data` | Observe every completed slice after history ingestion |
| `on_universe_changed` | React to added and removed effective securities |
| `on_warmup_completed` | React exactly once when global warm-up ends |
| `on_rebalance` | Produce scheduled strategy intents |
| `on_fill` | React to an applied fill |
| `on_order_updated` | Observe order lifecycle changes |
| `on_intent_rejected` | React to an engine-rejected intent |
| `on_shutdown` | Release strategy-owned resources |

Order-changing intents are forbidden during warm-up. Metrics remain available for observing the
warm-up process.

```python
from persistra.integrations.trading_engine import (
    EmitMetricIntent,
    MarketSlice,
    ScenarioIntent,
    StrategyView,
    UniverseChange,
)


class ObservableStrategy(ScheduledStrategy):
    name = "observable-strategy"

    def on_data(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> tuple[ScenarioIntent, ...]:
        return (EmitMetricIntent("universe-size", str(len(view.universe))),)

    def on_universe_changed(
        self,
        view: StrategyView,
        change: UniverseChange,
    ) -> tuple[ScenarioIntent, ...]:
        del view
        return (EmitMetricIntent("universe-added", str(len(change.added))),)
```

## Emit complete targets

Prefer the helpers on `StrategyView` for portfolio targets:

```python
from decimal import Decimal

from persistra.integrations.trading_engine import ScenarioIntent, StrategyView


def equal_weight_target(view: StrategyView) -> tuple[ScenarioIntent, ...]:
    if not view.universe:
        return (view.target_weights({}),)
    weight = Decimal(1) / Decimal(len(view.universe))
    return (
        view.target_weights(
            {instrument_id: weight for instrument_id in view.universe}
        ),
    )
```

`target_weights` and `target_quantities` expand an active-universe mapping to the complete fixed
catalog according to the removal policy. Do not hand-build a partial target and assume the
engine will infer the remainder.

The event context is authoritative. It includes marked cash, equity, exposures, positions,
working orders, and latest bars. Persistra verifies that realized cash and position weights
equal their marked values divided by positive equity, truncated toward zero to six decimal
places. Requested targets are not filled positions.

## Compose a decision pipeline

`CompositeStrategy` establishes one decision path:

```text
alpha models -> forecast combiner -> portfolio constructor -> overlays -> guards -> one target
```

An alpha model updates one named `StrategyForecast` from completed data. Returning `None` keeps
its previous forecast. The combiner can decline to construct a target until all required
forecasts are available. A constructor converts the combined forecast into `TargetPortfolio`.
Overlays transform the target in sequence. Guards approve or suppress the completed fixed-catalog
intent. Every forecast `as_of` must be a timezone-aware pandas timestamp with no more than
microsecond precision. Persistra normalizes it to UTC and rejects future-dated alpha and combined
forecasts before portfolio construction.

Every component declares `ComponentRequirements`. The composite raises history capacity and
warm-up requirements to satisfy the largest declaration:

```python
from persistra.integrations.trading_engine import ComponentRequirements

requirements = ComponentRequirements(observations=60, security_observations=40)
```

Use `WeightedForecastCombiner` for a normalized nonnegative blend:

```python
from persistra.integrations.trading_engine import WeightedForecastCombiner

combiner = WeightedForecastCombiner({"value": 0.4, "momentum": 0.6})
```

The built-in guards cover two common cases:

```python
from persistra.integrations.trading_engine import (
    MinimumTargetChangeGuard,
    OutstandingOrdersGuard,
)

guards = (
    OutstandingOrdersGuard(),
    MinimumTargetChangeGuard(0.01),
)
```

Guard order is meaningful. Evaluation stops at the first suppression. `last_decision` records the
forecast sources, combined source, every constructor and overlay target, every evaluated guard,
and whether a target was emitted.

See [Composite strategy examples](../examples/composite-strategies.md) for a complete pipeline
that calls the portfolio optimizer.

## Separate research state from execution state

A strategy commonly maintains three kinds of state:

- lifecycle state owned by `BaseStrategy`, such as history, readiness, and schedule timestamps;
- research state owned by components, such as fitted coefficients or current forecasts;
- execution state supplied by Trading Engine, such as filled positions and working orders.

Do not replace engine state with locally predicted fills. Recompute turnover and rebalance guards
from the authoritative context. If a model or configuration file can change strategy behavior,
declare it as a `StrategyProcess` artifact so the run manifest binds its bytes.

## Serve and replay the strategy

Put protocol serving in a small executable module:

```python
from persistra.integrations.trading_engine import serve_strategy

# Import an application strategy here.
# serve_strategy(ApplicationStrategy())
```

Standard output belongs exclusively to protocol messages. Write diagnostics to standard error.
The engine invokes the program directly without a shell, and process supervision is not a
sandbox.

Build an empty-schedule scenario, pass the strategy through `StrategyProcess`, and keep every
behavior-changing artifact. See [Replay with Trading Engine](trading-engine.md) for the full
runner contract and [Trading Engine replay examples](../examples/trading-engine-replay.md) for
copyable patterns.

## Test at three levels

Test components as ordinary Python objects first. Then drive `BaseStrategy.initialize`,
`on_event`, and `shutdown` with typed contexts to verify warm-up and target behavior. Finally,
replay a small deterministic scenario through the actual executable and assert journal outcomes.

Keep each level focused:

- component tests validate forecast and target mathematics;
- lifecycle tests validate dispatch, history, selection, and scheduling;
- replay tests validate order, fill, fee, risk, and accounting behavior.
