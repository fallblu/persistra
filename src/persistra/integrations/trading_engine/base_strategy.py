"""Reusable lifecycle policy for Trading Engine strategies."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import identifier, quantity_value
from persistra.integrations.trading_engine.model import (
    CancelOrderIntent,
    EmitMetricIntent,
    MarketSlice,
    ScenarioBar,
    ScenarioIntent,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetQuantity,
    TargetWeight,
    TargetWeightsIntent,
)
from persistra.integrations.trading_engine.strategy import (
    FillReceivedEvent,
    MarketSliceClosedEvent,
    OrderUpdatedEvent,
    StrategyContext,
    StrategyEvent,
    StrategyFill,
    StrategyInitialization,
    StrategyOrder,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import timedelta

type RemovalPolicy = Literal["liquidate", "retain", "error"]
type TargetValue = Decimal | str | int | float

_INTENT_TYPES = (
    TargetWeightsIntent,
    TargetQuantitiesIntent,
    SubmitOrderIntent,
    CancelOrderIntent,
    EmitMetricIntent,
)


class StrategyLifecycleError(RuntimeError):
    """The reusable strategy lifecycle was used in an invalid state."""


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """Immutable inputs for one strategy schedule decision."""

    observation: int
    now: pd.Timestamp
    first_observed_at: pd.Timestamp
    last_run_at: pd.Timestamp | None


class StrategySchedule(Protocol):
    """Decide whether a scheduled strategy hook is due."""

    def is_due(self, state: ScheduleState) -> bool:
        """Return whether the hook is due at this market observation."""

        ...


@dataclass(frozen=True, slots=True)
class ObservationSchedule:
    """Run on a fixed cadence of completed market observations."""

    every: int = 1
    start_at: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "every",
            quantity_value(self.every, name="schedule every", positive=True),
        )
        object.__setattr__(
            self,
            "start_at",
            quantity_value(self.start_at, name="schedule start_at", positive=True),
        )

    def is_due(self, state: ScheduleState) -> bool:
        """Return whether this observation lies on the configured cadence."""
        return state.observation >= self.start_at and (
            state.observation - self.start_at
        ) % self.every == 0


@dataclass(frozen=True, slots=True)
class ElapsedSchedule:
    """Run after a fixed amount of completed-market time."""

    interval: pd.Timedelta | timedelta | str
    run_immediately: bool = True

    def __post_init__(self) -> None:
        interval = pd.Timedelta(self.interval)
        if pd.isna(interval) or interval <= pd.Timedelta(0):
            raise ValueError("schedule interval must be positive")
        if not isinstance(cast("object", self.run_immediately), bool):
            raise TypeError("run_immediately must be a boolean")
        object.__setattr__(self, "interval", interval)

    def is_due(self, state: ScheduleState) -> bool:
        """Return whether the configured elapsed interval has passed."""
        interval = cast("pd.Timedelta", self.interval)
        if state.last_run_at is not None:
            return state.now - state.last_run_at >= interval
        return self.run_immediately or state.now - state.first_observed_at >= interval


@dataclass(frozen=True, slots=True)
class WarmupPolicy:
    """Require observations, elapsed market time, and per-security history."""

    observations: int = 0
    elapsed: pd.Timedelta | timedelta | str = "0s"
    security_observations: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observations",
            quantity_value(self.observations, name="warmup observations"),
        )
        elapsed = pd.Timedelta(self.elapsed)
        if pd.isna(elapsed) or elapsed < pd.Timedelta(0):
            raise ValueError("warmup elapsed time must be nonnegative")
        object.__setattr__(self, "elapsed", elapsed)
        object.__setattr__(
            self,
            "security_observations",
            quantity_value(
                self.security_observations,
                name="security warmup observations",
                positive=True,
            ),
        )


class SecuritySelector(Protocol):
    """Choose strategy securities from the initialized engine catalog."""

    def __call__(self, view: StrategyView) -> Iterable[str]:
        """Return catalog instrument identifiers to select."""

        ...


@dataclass(frozen=True, slots=True)
class StrategyConfiguration:
    """Lifecycle, history, filtering, and schedule policy for a base strategy."""

    history_capacity: int = 252
    warmup: WarmupPolicy = field(default_factory=WarmupPolicy)
    selector: SecuritySelector | None = None
    selection_schedule: StrategySchedule = field(default_factory=ObservationSchedule)
    rebalance_schedule: StrategySchedule = field(default_factory=ObservationSchedule)
    removal_policy: RemovalPolicy = "liquidate"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "history_capacity",
            quantity_value(self.history_capacity, name="history_capacity", positive=True),
        )
        if not isinstance(cast("object", self.warmup), WarmupPolicy):
            raise TypeError("warmup must be WarmupPolicy")
        if self.selector is not None and not callable(self.selector):
            raise TypeError("selector must be callable")
        for name in ("selection_schedule", "rebalance_schedule"):
            if not callable(getattr(getattr(self, name), "is_due", None)):
                raise TypeError(f"{name} must implement is_due")
        if self.removal_policy not in {"liquidate", "retain", "error"}:
            raise ValueError("removal_policy must be liquidate, retain, or error")


@dataclass(frozen=True, slots=True)
class BarObservation:
    """One bounded historical bar and its causal market-slice clocks."""

    slice_sequence: int
    start_at: pd.Timestamp
    end_at: pd.Timestamp
    available_at: pd.Timestamp
    received_at: pd.Timestamp
    bar: ScenarioBar


class StrategyHistory:
    """Immutable bounded bar history visible to one strategy callback."""

    __slots__ = ("_observations",)

    def __init__(self, observations: Mapping[str, tuple[BarObservation, ...]]) -> None:
        self._observations = dict(observations)

    @property
    def securities(self) -> tuple[str, ...]:
        """Return catalog identifiers in deterministic order."""
        return tuple(self._observations)

    def observations(self, instrument_id: str) -> tuple[BarObservation, ...]:
        """Return the retained observations for one security."""
        checked_id = identifier(instrument_id, name="instrument_id")
        try:
            return self._observations[checked_id]
        except KeyError as error:
            raise KeyError(checked_id) from error

    def latest(self, instrument_id: str) -> BarObservation | None:
        """Return the latest retained observation, if one exists."""
        observations = self.observations(instrument_id)
        return observations[-1] if observations else None

    def frame(self, instrument_id: str) -> pd.DataFrame:
        """Return a new end-time-indexed OHLCV frame for one security."""
        observations = self.observations(instrument_id)
        frame = pd.DataFrame(
            [
                {
                    "slice_sequence": item.slice_sequence,
                    "open": item.bar.open,
                    "high": item.bar.high,
                    "low": item.bar.low,
                    "close": item.bar.close,
                    "volume": item.bar.volume,
                    "available_at": item.available_at,
                    "received_at": item.received_at,
                }
                for item in observations
            ],
            index=pd.DatetimeIndex(
                [item.end_at for item in observations],
                name="end_at",
            ),
        )
        return frame


@dataclass(frozen=True, slots=True)
class UniverseChange:
    """Securities added to or removed from the effective strategy universe."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Return whether the effective universe changed."""
        return bool(self.added or self.removed)


@dataclass(frozen=True, slots=True)
class StrategyView:
    """One lifecycle-aware view of engine context, history, and universe state."""

    initialization: StrategyInitialization
    context: StrategyContext
    history: StrategyHistory
    observations_seen: int
    is_warming_up: bool
    ready_securities: tuple[str, ...]
    universe: tuple[str, ...]
    universe_change: UniverseChange = field(default_factory=UniverseChange)
    _catalog: tuple[str, ...] = field(default=(), repr=False)
    _removal_policy: RemovalPolicy = field(default="liquidate", repr=False)

    def target_weights(self, weights: Mapping[str, TargetValue]) -> TargetWeightsIntent:
        """Build a complete fixed-catalog target under the removal policy."""
        checked = self._checked_targets(weights, name="weights")
        active = set(self.universe)
        portfolio = self.context.portfolio
        targets: list[TargetWeight] = []
        for instrument_id in self._catalog:
            position = portfolio.position(instrument_id)
            if instrument_id in checked:
                value: TargetValue = checked[instrument_id]
            elif instrument_id in active or self._removal_policy == "liquidate":
                value = Decimal(0)
            elif self._removal_policy == "error":
                if position.quantity != 0:
                    raise StrategyLifecycleError(
                        f"removed security {instrument_id!r} has a nonzero position"
                    )
                value = Decimal(0)
            elif position.quantity == 0:
                value = Decimal(0)
            elif not portfolio.weights_available or position.weight is None:
                raise StrategyLifecycleError(
                    "retaining removed weight targets requires positive portfolio equity"
                )
            else:
                value = position.weight
            targets.append(TargetWeight(instrument_id, value))
        return TargetWeightsIntent(tuple(targets))

    def target_quantities(self, quantities: Mapping[str, TargetValue]) -> TargetQuantitiesIntent:
        """Build a complete fixed-catalog quantity target under the removal policy."""
        checked = self._checked_targets(quantities, name="quantities")
        active = set(self.universe)
        targets: list[TargetQuantity] = []
        for instrument_id in self._catalog:
            position = self.context.portfolio.position(instrument_id)
            if instrument_id in checked:
                value: TargetValue = checked[instrument_id]
            elif instrument_id in active or self._removal_policy == "liquidate":
                value = Decimal(0)
            elif self._removal_policy == "error":
                if position.quantity != 0:
                    raise StrategyLifecycleError(
                        f"removed security {instrument_id!r} has a nonzero position"
                    )
                value = Decimal(0)
            else:
                value = position.quantity
            targets.append(TargetQuantity(instrument_id, value))
        return TargetQuantitiesIntent(tuple(targets))

    def _checked_targets(
        self,
        values: Mapping[str, TargetValue],
        *,
        name: str,
    ) -> dict[str, TargetValue]:
        if not isinstance(cast("object", values), Mapping):
            raise TypeError(f"{name} must be a mapping")
        result: dict[str, TargetValue] = {}
        active = set(self.universe)
        for raw_id, value in values.items():
            instrument_id = identifier(raw_id, name="instrument_id")
            if instrument_id not in active:
                raise ValueError(f"target security {instrument_id!r} is not in the universe")
            result[instrument_id] = value
        return result


class BaseStrategy:
    """Implement strategy lifecycle policy while exposing focused subclass hooks."""

    name: str
    version: str | None = None

    def __init__(self) -> None:
        self._initialization: StrategyInitialization | None = None
        self._configuration: StrategyConfiguration | None = None
        self._history: dict[str, deque[BarObservation]] = {}
        self._observation_counts: dict[str, int] = {}
        self._catalog: tuple[str, ...] = ()
        self._selected: set[str] = set()
        self._universe: set[str] = set()
        self._observations_seen = 0
        self._first_observed_at: pd.Timestamp | None = None
        self._last_selection_at: pd.Timestamp | None = None
        self._last_rebalance_at: pd.Timestamp | None = None
        self._warmup_completed = False
        self._shutdown = False

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        """Return immutable lifecycle policy for this initialized run."""
        del initialization
        return StrategyConfiguration()

    def initialize(self, initialization: StrategyInitialization) -> None:
        """Configure the strategy and initialize bounded catalog history."""
        if self._initialization is not None:
            raise StrategyLifecycleError("strategy is already initialized")
        configuration = self.configure(initialization)
        if not isinstance(cast("object", configuration), StrategyConfiguration):
            raise TypeError("configure must return StrategyConfiguration")
        catalog = tuple(instrument.instrument_id for instrument in initialization.instruments)
        self._initialization = initialization
        self._configuration = configuration
        self._catalog = catalog
        self._selected = set(catalog) if configuration.selector is None else set()
        self._history = {
            instrument_id: deque(maxlen=configuration.history_capacity)
            for instrument_id in catalog
        }
        self._observation_counts = dict.fromkeys(catalog, 0)
        self.on_initialize(initialization)

    def on_event(
        self,
        context: StrategyContext,
        event: StrategyEvent,
    ) -> Sequence[ScenarioIntent]:
        """Advance lifecycle state and dispatch one typed event to focused hooks."""
        if self._initialization is None or self._configuration is None:
            raise StrategyLifecycleError("strategy is not initialized")
        if self._shutdown:
            raise StrategyLifecycleError("strategy is shut down")
        if isinstance(event, MarketSliceClosedEvent):
            return self._on_market_slice(context, event.market_slice)
        view = self._view(context)
        if isinstance(event, FillReceivedEvent):
            return self._checked_intents(self.on_fill(view, event.fill), view, stage="on_fill")
        if isinstance(event, OrderUpdatedEvent):
            return self._checked_intents(
                self.on_order_updated(view, event.order),
                view,
                stage="on_order_updated",
            )
        return self._checked_intents(
            self.on_intent_rejected(view, event.reason),
            view,
            stage="on_intent_rejected",
        )

    def shutdown(self) -> None:
        """Run the subclass shutdown hook exactly once."""
        if self._initialization is None:
            raise StrategyLifecycleError("strategy is not initialized")
        if self._shutdown:
            raise StrategyLifecycleError("strategy is already shut down")
        self.on_shutdown()
        self._shutdown = True

    def on_initialize(self, initialization: StrategyInitialization) -> None:
        """Receive initialized state after lifecycle configuration."""
        del initialization

    def on_data(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> Sequence[ScenarioIntent]:
        """Observe each completed market slice after history ingestion."""
        del view, market_slice
        return ()

    def on_universe_changed(
        self,
        view: StrategyView,
        change: UniverseChange,
    ) -> Sequence[ScenarioIntent]:
        """React when filtering or readiness changes the effective universe."""
        del view, change
        return ()

    def on_warmup_completed(self, view: StrategyView) -> Sequence[ScenarioIntent]:
        """React once when all global warmup requirements are satisfied."""
        del view
        return ()

    def on_rebalance(self, view: StrategyView) -> Sequence[ScenarioIntent]:
        """Return intents when the configured rebalance schedule is due."""
        del view
        return ()

    def on_fill(
        self,
        view: StrategyView,
        fill: StrategyFill,
    ) -> Sequence[ScenarioIntent]:
        """React to one applied fill."""
        del view, fill
        return ()

    def on_order_updated(
        self,
        view: StrategyView,
        order: StrategyOrder,
    ) -> Sequence[ScenarioIntent]:
        """React to one order lifecycle update."""
        del view, order
        return ()

    def on_intent_rejected(
        self,
        view: StrategyView,
        reason: str,
    ) -> Sequence[ScenarioIntent]:
        """React when the engine rejects an intent."""
        del view, reason
        return ()

    def on_shutdown(self) -> None:
        """Release subclass resources at protocol shutdown."""

    def _on_market_slice(
        self,
        context: StrategyContext,
        market_slice: MarketSlice,
    ) -> tuple[ScenarioIntent, ...]:
        configuration = self._required_configuration()
        self._ingest(market_slice)
        schedule_state = self._schedule_state(market_slice.end_at, self._last_selection_at)
        if self._schedule_is_due(
            configuration.selection_schedule,
            schedule_state,
            name="selection_schedule",
        ):
            selector_view = self._view(context)
            selected: Iterable[str] = (
                self._catalog
                if configuration.selector is None
                else configuration.selector(selector_view)
            )
            self._selected = self._checked_selection(selected)
            self._last_selection_at = market_slice.end_at
        previous_universe = self._universe
        ready = self._ready_securities()
        self._universe = self._selected.intersection(ready)
        change = UniverseChange(
            added=tuple(
                item for item in self._catalog if item in self._universe - previous_universe
            ),
            removed=tuple(
                item for item in self._catalog if item in previous_universe - self._universe
            ),
        )
        warming_up = self._is_warming_up(market_slice.end_at)
        completed_now = not warming_up and not self._warmup_completed
        if completed_now:
            self._warmup_completed = True
        view = self._view(context, change=change, warming_up=warming_up)
        intents: list[ScenarioIntent] = []
        intents.extend(
            self._checked_intents(
                self.on_data(view, market_slice),
                view,
                stage="on_data",
            )
        )
        if change.changed:
            intents.extend(
                self._checked_intents(
                    self.on_universe_changed(view, change),
                    view,
                    stage="on_universe_changed",
                )
            )
        if completed_now:
            intents.extend(
                self._checked_intents(
                    self.on_warmup_completed(view),
                    view,
                    stage="on_warmup_completed",
                )
            )
        rebalance_state = self._schedule_state(market_slice.end_at, self._last_rebalance_at)
        if not warming_up and self._schedule_is_due(
            configuration.rebalance_schedule,
            rebalance_state,
            name="rebalance_schedule",
        ):
            intents.extend(
                self._checked_intents(
                    self.on_rebalance(view),
                    view,
                    stage="on_rebalance",
                )
            )
            self._last_rebalance_at = market_slice.end_at
        return tuple(intents)

    def _ingest(self, market_slice: MarketSlice) -> None:
        self._observations_seen += 1
        if self._first_observed_at is None:
            self._first_observed_at = market_slice.end_at
        bars = {bar.instrument_id: bar for bar in market_slice.bars}
        if set(bars) != set(self._catalog):
            raise StrategyLifecycleError("market slice must cover the initialized catalog")
        for instrument_id in self._catalog:
            self._history[instrument_id].append(
                BarObservation(
                    slice_sequence=market_slice.slice_sequence,
                    start_at=market_slice.start_at,
                    end_at=market_slice.end_at,
                    available_at=market_slice.available_at,
                    received_at=market_slice.received_at,
                    bar=bars[instrument_id],
                )
            )
            self._observation_counts[instrument_id] += 1

    def _checked_selection(self, values: Iterable[str]) -> set[str]:
        if isinstance(values, str | bytes):
            raise TypeError("selector must return an iterable of instrument identifiers")
        selected: set[str] = set()
        catalog = set(self._catalog)
        for raw_id in values:
            instrument_id = identifier(raw_id, name="selected instrument_id")
            if instrument_id not in catalog:
                raise ValueError(f"selector returned unknown security {instrument_id!r}")
            if instrument_id in selected:
                raise ValueError(f"selector returned duplicate security {instrument_id!r}")
            selected.add(instrument_id)
        return selected

    def _ready_securities(self) -> set[str]:
        required = self._required_configuration().warmup.security_observations
        return {
            instrument_id
            for instrument_id, count in self._observation_counts.items()
            if count >= required
        }

    def _is_warming_up(self, now: pd.Timestamp) -> bool:
        policy = self._required_configuration().warmup
        if self._first_observed_at is None:
            return True
        elapsed = cast("pd.Timedelta", policy.elapsed)
        return self._observations_seen < policy.observations or (
            now - self._first_observed_at < elapsed
        )

    def _schedule_state(
        self,
        now: pd.Timestamp,
        last_run_at: pd.Timestamp | None,
    ) -> ScheduleState:
        if self._first_observed_at is None:
            raise StrategyLifecycleError("schedule evaluated before market data")
        return ScheduleState(
            observation=self._observations_seen,
            now=now,
            first_observed_at=self._first_observed_at,
            last_run_at=last_run_at,
        )

    def _view(
        self,
        context: StrategyContext,
        *,
        change: UniverseChange | None = None,
        warming_up: bool | None = None,
    ) -> StrategyView:
        initialization = self._required_initialization()
        configuration = self._required_configuration()
        history = StrategyHistory(
            {
                instrument_id: tuple(self._history[instrument_id])
                for instrument_id in self._catalog
            }
        )
        is_warming_up = (
            not self._warmup_completed if warming_up is None else warming_up
        )
        return StrategyView(
            initialization=initialization,
            context=context,
            history=history,
            observations_seen=self._observations_seen,
            is_warming_up=is_warming_up,
            ready_securities=tuple(
                item for item in self._catalog if item in self._ready_securities()
            ),
            universe=tuple(item for item in self._catalog if item in self._universe),
            universe_change=UniverseChange() if change is None else change,
            _catalog=self._catalog,
            _removal_policy=configuration.removal_policy,
        )

    def _checked_intents(
        self,
        values: Sequence[ScenarioIntent],
        view: StrategyView,
        *,
        stage: str,
    ) -> tuple[ScenarioIntent, ...]:
        raw_values = cast("object", values)
        if isinstance(raw_values, str | bytes) or not isinstance(raw_values, Sequence):
            raise TypeError(f"{stage} must return a sequence of strategy intents")
        intents = tuple(cast("Sequence[object]", values))
        if not all(isinstance(item, _INTENT_TYPES) for item in intents):
            raise TypeError(f"{stage} returned a value that is not a strategy intent")
        typed = cast("tuple[ScenarioIntent, ...]", intents)
        if view.is_warming_up and any(not isinstance(item, EmitMetricIntent) for item in typed):
            raise StrategyLifecycleError("order-changing intents are forbidden during warmup")
        return typed

    @staticmethod
    def _schedule_is_due(
        schedule: StrategySchedule,
        state: ScheduleState,
        *,
        name: str,
    ) -> bool:
        result = schedule.is_due(state)
        if not isinstance(cast("object", result), bool):
            raise TypeError(f"{name}.is_due must return a boolean")
        return result

    def _required_initialization(self) -> StrategyInitialization:
        if self._initialization is None:
            raise StrategyLifecycleError("strategy is not initialized")
        return self._initialization

    def _required_configuration(self) -> StrategyConfiguration:
        if self._configuration is None:
            raise StrategyLifecycleError("strategy is not initialized")
        return self._configuration


def security_filter(
    predicate: Callable[[str, BarObservation | None, StrategyView], bool],
) -> SecuritySelector:
    """Build a catalog selector from a per-security predicate."""

    def select(view: StrategyView) -> Iterable[str]:
        for instrument in view.initialization.instruments:
            instrument_id = instrument.instrument_id
            selected = predicate(instrument_id, view.history.latest(instrument_id), view)
            if not isinstance(cast("object", selected), bool):
                raise TypeError("security filter predicate must return a boolean")
            if selected:
                yield instrument_id

    return select
