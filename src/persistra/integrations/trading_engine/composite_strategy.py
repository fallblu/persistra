"""Composable signal-to-target strategy policy for Trading Engine."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np
import pandas as pd

from persistra.integrations.trading_engine._scalars import decimal_value, identifier, quantity_value
from persistra.integrations.trading_engine.base_strategy import (
    BaseStrategy,
    StrategyConfiguration,
    StrategyLifecycleError,
    StrategyView,
    TargetValue,
    WarmupPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from persistra.integrations.trading_engine.model import (
        MarketSlice,
        ScenarioIntent,
        TargetWeightsIntent,
    )
    from persistra.integrations.trading_engine.strategy import StrategyInitialization


@dataclass(frozen=True, slots=True)
class ComponentRequirements:
    """History and warmup required before a strategy component may construct targets."""

    observations: int = 0
    security_observations: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observations",
            quantity_value(self.observations, name="component observations"),
        )
        object.__setattr__(
            self,
            "security_observations",
            quantity_value(
                self.security_observations,
                name="component security observations",
                positive=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategyForecast:
    """One named, point-in-time cross-sectional forecast in caller-defined units."""

    source: str
    values: pd.Series
    as_of: pd.Timestamp
    confidence: pd.Series | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", identifier(self.source, name="forecast source"))
        values = _forecast_series(self.values, name="forecast values")
        confidence = self.confidence
        if confidence is not None:
            confidence = _forecast_series(confidence, name="forecast confidence")
            if not confidence.index.equals(values.index):
                raise ValueError("forecast confidence must use the forecast value index")
            if (confidence < 0.0).any() or (confidence > 1.0).any():
                raise ValueError("forecast confidence must be between zero and one")
        raw_as_of = cast("object", self.as_of)
        if not isinstance(raw_as_of, pd.Timestamp):
            raise TypeError("forecast as_of must be a pandas Timestamp")
        if pd.isna(raw_as_of) or raw_as_of.tzinfo is None:
            raise ValueError("forecast as_of must be timezone-aware")
        timestamp = raw_as_of.tz_convert("UTC")
        if timestamp.nanosecond % 1_000:
            raise ValueError("forecast as_of must not exceed microsecond precision")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "as_of", timestamp)


@dataclass(frozen=True, slots=True)
class TargetPortfolio:
    """One complete or partial universe target before lifecycle completion."""

    weights: Mapping[str, TargetValue]

    def __post_init__(self) -> None:
        checked: dict[str, TargetValue] = {}
        for raw_id, raw_weight in self.weights.items():
            instrument_id = identifier(raw_id, name="target instrument_id")
            checked[instrument_id] = decimal_value(raw_weight, name="target weight")
        object.__setattr__(self, "weights", MappingProxyType(checked))


@dataclass(frozen=True, slots=True)
class TargetStage:
    """One named target transformation in a composite decision."""

    name: str
    target: TargetPortfolio

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, name="target stage name"))


@dataclass(frozen=True, slots=True)
class StrategyDecisionTrace:
    """Inspectable provenance for the latest composite rebalance decision."""

    decided_at: pd.Timestamp
    forecast_sources: tuple[str, ...]
    combined_source: str | None
    stages: tuple[TargetStage, ...]
    emitted: bool
    guard_decisions: tuple[RebalanceDecision, ...] = ()


@dataclass(frozen=True, slots=True)
class RebalanceDecision:
    """One named guard decision for a completed portfolio target."""

    guard: str
    approved: bool
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "guard", identifier(self.guard, name="guard name"))
        if not isinstance(cast("object", self.approved), bool):
            raise TypeError("guard approval must be a boolean")
        if not self.reason:
            raise ValueError("guard reason must not be empty")


class AlphaModel(Protocol):
    """Update one named forecast from completed market data."""

    @property
    def name(self) -> str:
        """Return the unique forecast source name."""

        ...

    @property
    def requirements(self) -> ComponentRequirements:
        """Return this component's lifecycle requirements."""

        ...

    def update(self, view: StrategyView, market_slice: MarketSlice) -> StrategyForecast | None:
        """Return a replacement forecast, or retain the previous forecast with ``None``."""

        ...


class ForecastCombiner(Protocol):
    """Combine current component forecasts into one forecast."""

    @property
    def name(self) -> str:
        """Return the target-stage name."""

        ...

    @property
    def requirements(self) -> ComponentRequirements:
        """Return this component's lifecycle requirements."""

        ...

    def combine(
        self,
        forecasts: tuple[StrategyForecast, ...],
        view: StrategyView,
    ) -> StrategyForecast | None:
        """Return one combined forecast, or decline to construct a target."""

        ...


class PortfolioConstructor(Protocol):
    """Convert one combined forecast into portfolio weights."""

    @property
    def name(self) -> str:
        """Return the target-stage name."""

        ...

    @property
    def requirements(self) -> ComponentRequirements:
        """Return this component's lifecycle requirements."""

        ...

    def construct(self, forecast: StrategyForecast, view: StrategyView) -> TargetPortfolio:
        """Return proposed portfolio weights for the effective universe."""

        ...


class TargetOverlay(Protocol):
    """Apply one deterministic transformation to proposed portfolio weights."""

    @property
    def name(self) -> str:
        """Return the target-stage name."""

        ...

    @property
    def requirements(self) -> ComponentRequirements:
        """Return this component's lifecycle requirements."""

        ...

    def apply(self, target: TargetPortfolio, view: StrategyView) -> TargetPortfolio:
        """Return transformed portfolio weights."""

        ...


class RebalanceGuard(Protocol):
    """Approve or suppress one fully completed target portfolio."""

    @property
    def name(self) -> str:
        """Return the guard name."""

        ...

    @property
    def requirements(self) -> ComponentRequirements:
        """Return this component's lifecycle requirements."""

        ...

    def evaluate(
        self,
        target: TargetWeightsIntent,
        view: StrategyView,
    ) -> RebalanceDecision:
        """Return whether the completed target may be emitted."""

        ...


@dataclass(frozen=True, slots=True)
class WeightedForecastCombiner:
    """Combine aligned forecasts using normalized nonnegative source weights."""

    weights: Mapping[str, float]
    name: str = "weighted-forecast"
    requirements: ComponentRequirements = field(default_factory=ComponentRequirements)

    def __post_init__(self) -> None:
        checked: dict[str, float] = {}
        for raw_name, raw_weight in self.weights.items():
            source = identifier(raw_name, name="forecast weight source")
            value = float(raw_weight)
            if not np.isfinite(value) or value < 0.0:
                raise ValueError("forecast weights must be finite and nonnegative")
            checked[source] = value
        if not checked or sum(checked.values()) <= 0.0:
            raise ValueError("forecast weights must have a positive sum")
        object.__setattr__(self, "weights", MappingProxyType(checked))
        object.__setattr__(self, "name", identifier(self.name, name="combiner name"))

    def combine(
        self,
        forecasts: tuple[StrategyForecast, ...],
        view: StrategyView,
    ) -> StrategyForecast | None:
        """Return the normalized weighted mean of current aligned forecasts."""
        del view
        selected = [forecast for forecast in forecasts if forecast.source in self.weights]
        if not selected:
            return None
        if set(forecast.source for forecast in selected) != set(self.weights):
            return None
        index = selected[0].values.index
        if any(not forecast.values.index.equals(index) for forecast in selected[1:]):
            raise ValueError("combined forecasts must use identical security indexes")
        total = sum(self.weights[forecast.source] for forecast in selected)
        values = sum(
            forecast.values * (self.weights[forecast.source] / total) for forecast in selected
        )
        return StrategyForecast(
            source=self.name,
            values=cast("pd.Series", values),
            as_of=max(forecast.as_of for forecast in selected),
        )


@dataclass(frozen=True, slots=True)
class MinimumTargetChangeGuard:
    """Suppress targets whose largest absolute weight change is below a threshold."""

    minimum: float
    name: str = "minimum-target-change"
    requirements: ComponentRequirements = field(default_factory=ComponentRequirements)

    def __post_init__(self) -> None:
        value = float(self.minimum)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError("minimum target change must be finite and nonnegative")
        object.__setattr__(self, "minimum", value)

    def evaluate(
        self,
        target: TargetWeightsIntent,
        view: StrategyView,
    ) -> RebalanceDecision:
        """Compare the completed target with authoritative marked weights."""
        if not view.context.portfolio.weights_available:
            return RebalanceDecision(self.name, False, "portfolio weights are unavailable")
        changes: list[float] = []
        for item in target.targets:
            current = view.context.portfolio.position(item.instrument_id).weight
            if current is None:
                return RebalanceDecision(self.name, False, "portfolio weights are unavailable")
            changes.append(abs(float(item.weight) - float(current)))
        largest = max(changes, default=0.0)
        approved = largest >= self.minimum
        reason = (
            f"largest target change {largest:g} meets minimum {self.minimum:g}"
            if approved
            else f"largest target change {largest:g} is below minimum {self.minimum:g}"
        )
        return RebalanceDecision(self.name, approved, reason)


@dataclass(frozen=True, slots=True)
class OutstandingOrdersGuard:
    """Suppress portfolio targets while the engine reports working orders."""

    name: str = "outstanding-orders"
    requirements: ComponentRequirements = field(default_factory=ComponentRequirements)

    def evaluate(
        self,
        target: TargetWeightsIntent,
        view: StrategyView,
    ) -> RebalanceDecision:
        """Approve only when no working order remains."""
        del target
        approved = not view.context.working_orders
        reason = "no working orders" if approved else "working orders are present"
        return RebalanceDecision(self.name, approved, reason)


class CompositeStrategy(BaseStrategy):
    """Orchestrate alpha, combination, construction, and overlays under one lifecycle."""

    def __init__(
        self,
        name: str,
        *,
        alpha_models: Sequence[AlphaModel],
        combiner: ForecastCombiner,
        portfolio_constructor: PortfolioConstructor,
        overlays: Sequence[TargetOverlay] = (),
        rebalance_guards: Sequence[RebalanceGuard] = (),
        configuration: StrategyConfiguration | None = None,
        version: str | None = None,
    ) -> None:
        super().__init__()
        self.name = identifier(name, name="strategy name")
        self.version = version
        self._alpha_models = tuple(alpha_models)
        if not self._alpha_models:
            raise ValueError("composite strategy requires at least one alpha model")
        component_names = [model.name for model in self._alpha_models]
        if len(component_names) != len(set(component_names)):
            raise ValueError("alpha model names must be unique")
        self._combiner = combiner
        self._portfolio_constructor = portfolio_constructor
        self._overlays = tuple(overlays)
        self._rebalance_guards = tuple(rebalance_guards)
        self._base_configuration = configuration or StrategyConfiguration()
        self._forecasts: dict[str, StrategyForecast] = {}
        self._last_decision: StrategyDecisionTrace | None = None
        self._requirements = _combined_requirements(
            (
                *self._alpha_models,
                combiner,
                portfolio_constructor,
                *self._overlays,
                *self._rebalance_guards,
            )
        )

    @property
    def last_decision(self) -> StrategyDecisionTrace | None:
        """Return the latest immutable decision trace, if a rebalance was evaluated."""
        return self._last_decision

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        """Merge component requirements into the supplied lifecycle configuration."""
        del initialization
        base = self._base_configuration
        warmup = base.warmup
        required = self._requirements
        return replace(
            base,
            history_capacity=max(base.history_capacity, required.security_observations),
            warmup=WarmupPolicy(
                observations=max(warmup.observations, required.observations),
                elapsed=warmup.elapsed,
                security_observations=max(
                    warmup.security_observations,
                    required.security_observations,
                ),
            ),
        )

    def on_data(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> Sequence[ScenarioIntent]:
        """Update every alpha model without emitting competing intents."""
        for source, forecast in tuple(self._forecasts.items()):
            if set(forecast.values.index).difference(view.universe):
                del self._forecasts[source]
        for model in self._alpha_models:
            forecast = model.update(view, market_slice)
            if forecast is None:
                continue
            if forecast.source != model.name:
                raise StrategyLifecycleError(
                    f"alpha model {model.name!r} returned source {forecast.source!r}"
                )
            if forecast.as_of > view.context.now:
                raise StrategyLifecycleError("alpha model returned a future-dated forecast")
            unknown = set(forecast.values.index).difference(view.universe)
            if unknown:
                raise StrategyLifecycleError(
                    f"alpha model returned securities outside the universe: {sorted(unknown)!r}"
                )
            self._forecasts[model.name] = forecast
        return ()

    def on_rebalance(self, view: StrategyView) -> Sequence[ScenarioIntent]:
        """Build and emit at most one complete target portfolio."""
        forecasts = tuple(
            self._forecasts[model.name]
            for model in self._alpha_models
            if model.name in self._forecasts
        )
        combined = self._combiner.combine(forecasts, view)
        if combined is None:
            self._last_decision = StrategyDecisionTrace(
                decided_at=view.context.now,
                forecast_sources=tuple(item.source for item in forecasts),
                combined_source=None,
                stages=(),
                emitted=False,
            )
            return ()
        if combined.as_of > view.context.now:
            raise StrategyLifecycleError("forecast combiner returned a future-dated forecast")
        stages: list[TargetStage] = []
        target = self._portfolio_constructor.construct(combined, view)
        stages.append(TargetStage(self._portfolio_constructor.name, target))
        for overlay in self._overlays:
            target = overlay.apply(target, view)
            stages.append(TargetStage(overlay.name, target))
        intent = view.target_weights(target.weights)
        guard_decisions: list[RebalanceDecision] = []
        for guard in self._rebalance_guards:
            decision = guard.evaluate(intent, view)
            if decision.guard != guard.name:
                raise StrategyLifecycleError(
                    f"rebalance guard {guard.name!r} returned decision {decision.guard!r}"
                )
            guard_decisions.append(decision)
            if not decision.approved:
                break
        emitted = all(decision.approved for decision in guard_decisions)
        self._last_decision = StrategyDecisionTrace(
            decided_at=view.context.now,
            forecast_sources=tuple(item.source for item in forecasts),
            combined_source=combined.source,
            stages=tuple(stages),
            emitted=emitted,
            guard_decisions=tuple(guard_decisions),
        )
        return (intent,) if emitted else ()


def _forecast_series(values: pd.Series, *, name: str) -> pd.Series:
    if values.index.has_duplicates or values.index.hasnans:
        raise ValueError(f"{name} index must be unique and nonmissing")
    checked_index = pd.Index([identifier(item, name=f"{name} security") for item in values.index])
    try:
        checked = values.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(checked.to_numpy(dtype=float)).all():
        raise ValueError(f"{name} must be finite")
    checked.index = checked_index
    return checked.copy(deep=True)


def _combined_requirements(components: Sequence[object]) -> ComponentRequirements:
    requirements: list[ComponentRequirements] = []
    for component in components:
        value = getattr(component, "requirements", None)
        if not isinstance(value, ComponentRequirements):
            raise TypeError("strategy components must declare ComponentRequirements")
        requirements.append(value)
    return ComponentRequirements(
        observations=max(item.observations for item in requirements),
        security_observations=max(item.security_observations for item in requirements),
    )
