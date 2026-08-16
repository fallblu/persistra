# Composite-strategy examples

`CompositeStrategy` separates a strategy decision into replaceable stages while preserving one
lifecycle and at most one emitted target per scheduled rebalance:

```text
alpha models -> combiner -> constructor -> overlays -> guards -> target intent
```

The protocols describe behavior, not inheritance. Plain classes with the required methods and
`ComponentRequirements` are enough.

## Create an alpha model

An alpha model observes every completed slice and returns a named point-in-time cross-sectional
forecast. Returning `None` retains its previous forecast.

```python
import pandas as pd

from persistra.integrations.trading_engine import (
    ComponentRequirements,
    MarketSlice,
    StrategyForecast,
    StrategyView,
)


class TrailingReturnAlpha:
    name = "trailing-return"
    requirements = ComponentRequirements(observations=20, security_observations=20)

    def update(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> StrategyForecast | None:
        if not view.universe:
            return None
        values: dict[str, float] = {}
        for instrument_id in view.universe:
            observations = view.history.observations(instrument_id)
            first = float(observations[-20].bar.close)
            last = float(observations[-1].bar.close)
            values[instrument_id] = last / first - 1.0
        return StrategyForecast(
            source=self.name,
            values=pd.Series(values),
            as_of=market_slice.end_at,
        )
```

The forecast index may contain only current-universe securities. It cannot contain an unknown or
filtered-out ID, and `as_of` cannot be later than the engine context.

## Add a second alpha model

```python
class ShortReversalAlpha:
    name = "short-reversal"
    requirements = ComponentRequirements(observations=5, security_observations=5)

    def update(
        self,
        view: StrategyView,
        market_slice: MarketSlice,
    ) -> StrategyForecast | None:
        if not view.universe:
            return None
        values = {}
        for instrument_id in view.universe:
            observations = view.history.observations(instrument_id)
            first = float(observations[-5].bar.close)
            last = float(observations[-1].bar.close)
            values[instrument_id] = -(last / first - 1.0)
        return StrategyForecast(self.name, pd.Series(values), market_slice.end_at)
```

Component requirements are merged. In this pair, the composite needs at least 20 global and 20
per-security observations even if its base configuration asks for less.

## Combine forecasts

Use the built-in normalized weighted mean when every source should be present:

```python
from persistra.integrations.trading_engine import WeightedForecastCombiner

combiner = WeightedForecastCombiner(
    {
        "trailing-return": 0.75,
        "short-reversal": 0.25,
    }
)
```

The combiner returns `None` until all named inputs are available and aligned. A custom combiner
can implement confidence weighting, horizon selection, or a missing-source policy explicitly:

```python
from persistra.integrations.trading_engine import StrategyForecast


class LatestForecastCombiner:
    name = "latest-forecast"
    requirements = ComponentRequirements()

    def combine(
        self,
        forecasts: tuple[StrategyForecast, ...],
        view: StrategyView,
    ) -> StrategyForecast | None:
        del view
        if not forecasts:
            return None
        latest = max(forecasts, key=lambda forecast: forecast.as_of)
        return StrategyForecast(self.name, latest.values, latest.as_of, latest.confidence)
```

Document a custom missing-source rule. Silently changing the blend as models appear and
disappear can create unintended turnover.

## Construct a portfolio with the optimizer

The constructor translates forecast units into an explicit `PortfolioProblem`. This example uses
a diagonal risk estimate for brevity; a real constructor can use a current
`FactorPortfolioForecast` and its asset covariance.

```python
import numpy as np

from persistra.integrations.trading_engine import TargetPortfolio
from persistra.portfolio import (
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    TurnoverConstraint,
    WeightBounds,
    optimize_portfolio,
)


class OptimizingConstructor:
    name = "mean-variance"
    requirements = ComponentRequirements()

    def construct(
        self,
        forecast: StrategyForecast,
        view: StrategyView,
    ) -> TargetPortfolio:
        assets = forecast.values.index
        covariance = pd.DataFrame(
            np.eye(len(assets)) * 0.04,
            index=assets,
            columns=assets,
        )
        current = pd.Series(
            {
                instrument_id: float(
                    view.context.portfolio.position(instrument_id).weight or 0
                )
                for instrument_id in assets
            }
        )
        result = optimize_portfolio(
            PortfolioProblem(
                covariance=covariance,
                expected_returns=forecast.values,
                current_weights=current,
                objective=MeanVarianceObjective(risk_aversion=5.0),
                constraints=(
                    WeightBounds(0.0, 0.40),
                    NetExposureConstraint(1.0, 1.0),
                    TurnoverConstraint(0.30),
                ),
                as_of=forecast.as_of,
            )
        )
        return TargetPortfolio(
            {instrument_id: str(weight) for instrument_id, weight in result.weights.items()}
        )
```

Portfolio weights in `view.context` are authoritative filled weights. They may be unavailable
when equity is not positive; production constructors must state a policy for that case instead of
substituting the last requested target.

## Apply target overlays

Overlays are deterministic target-to-target transformations. This overlay reserves cash by
scaling risky weights:

```python
from decimal import Decimal


class CashReserveOverlay:
    name = "cash-reserve"
    requirements = ComponentRequirements()

    def __init__(self, reserve: str) -> None:
        self._multiplier = Decimal(1) - Decimal(reserve)

    def apply(self, target: TargetPortfolio, view: StrategyView) -> TargetPortfolio:
        del view
        return TargetPortfolio(
            {
                instrument_id: weight * self._multiplier
                for instrument_id, weight in target.weights.items()
            }
        )
```

Overlay order matters. Put transformations in the same order used during research and inspect
the recorded `TargetStage` values when debugging a decision.

## Add rebalance guards

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

The first guard suppresses a new target while any order is working. The second requires the
largest absolute change from authoritative marked weights to reach one percentage point. Guard
evaluation stops at the first suppression.

Custom guards return a named `RebalanceDecision` with an explanation:

```python
from persistra.integrations.trading_engine import (
    RebalanceDecision,
    TargetWeightsIntent,
)


class PositiveEquityGuard:
    name = "positive-equity"
    requirements = ComponentRequirements()

    def evaluate(
        self,
        target: TargetWeightsIntent,
        view: StrategyView,
    ) -> RebalanceDecision:
        del target
        approved = view.context.portfolio.equity > 0
        reason = "portfolio equity is positive" if approved else "portfolio equity is not positive"
        return RebalanceDecision(self.name, approved, reason)
```

## Assemble the composite

```python
from persistra.integrations.trading_engine import (
    CompositeStrategy,
    ObservationSchedule,
    StrategyConfiguration,
    WarmupPolicy,
)

composite = CompositeStrategy(
    "multi-alpha",
    version="1",
    alpha_models=(TrailingReturnAlpha(), ShortReversalAlpha()),
    combiner=combiner,
    portfolio_constructor=OptimizingConstructor(),
    overlays=(CashReserveOverlay("0.05"),),
    rebalance_guards=guards,
    configuration=StrategyConfiguration(
        history_capacity=60,
        warmup=WarmupPolicy(observations=10, security_observations=10),
        rebalance_schedule=ObservationSchedule(every=5, start_at=20),
    ),
)
```

The effective history and warm-up become 60, 20, and 20 in this example: base history capacity
is retained, while component observation requirements raise both warm-up dimensions.

## Inspect decision provenance

After a due rebalance, inspect `last_decision`:

```python
decision = composite.last_decision
if decision is not None:
    print(decision.forecast_sources)
    print(decision.combined_source)
    print([(stage.name, stage.target.weights) for stage in decision.stages])
    print([(item.guard, item.approved, item.reason) for item in decision.guard_decisions])
    print(decision.emitted)
```

The trace is process-local diagnostic state. The emitted target and resulting engine behavior
still appear in the strategy transcript and audit journal. If traces are required as durable run
artifacts, emit stable metrics or persist them through an application-owned declared artifact.

## Test components before replay

Test each alpha with a small `StrategyView`, test combination with aligned and missing sources,
test constructors against binding constraints, test overlays with signed targets, and test every
guard approval and suppression path. Then drive the assembled composite through lifecycle events
before running a small end-to-end engine replay.
