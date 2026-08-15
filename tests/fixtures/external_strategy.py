"""External strategy fixture used by the real Trading Engine acceptance test."""

from __future__ import annotations

from typing import TYPE_CHECKING

from persistra.integrations.trading_engine import (
    EmitMetricIntent,
    MarketSliceClosedEvent,
    TargetQuantitiesIntent,
    TargetQuantity,
    serve_strategy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.integrations.trading_engine import (
        ScenarioIntent,
        StrategyContext,
        StrategyEvent,
        StrategyInitialization,
    )


class FixtureStrategy:
    """Request two units after the first completed market slice."""

    name = "persistra-fixture"
    version: str | None = "1"

    def __init__(self) -> None:
        self.instrument_id: str | None = None
        self.requested = False

    def initialize(self, initialization: StrategyInitialization) -> None:
        self.instrument_id = initialization.instruments[0].instrument_id

    def on_event(
        self,
        context: StrategyContext,
        event: StrategyEvent,
    ) -> Sequence[ScenarioIntent]:
        del context
        if isinstance(event, MarketSliceClosedEvent) and not self.requested:
            assert self.instrument_id is not None
            self.requested = True
            return (
                TargetQuantitiesIntent((TargetQuantity(self.instrument_id, 2),)),
                EmitMetricIntent("external_signal", "2"),
            )
        return ()

    def shutdown(self) -> None:
        pass


serve_strategy(FixtureStrategy())
