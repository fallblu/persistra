"""The Alpha Vantage parse-to-ingest boundary.

Endpoint parsers return canonical domain objects grouped in a
:class:`ParsedFamilyBatch`; the :class:`AlphaVantageIngestor` coordinator hands
each family to its typed canonical service. A future generic-pipeline projector
can slot in behind this boundary without rewriting any parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persistra.market import (
        CorporateActionObservation,
        DailyBar,
        TradingStatusObservation,
    )
    from persistra.market.economic_models import (
        BenchmarkSeriesObservation,
        MacroRelease,
        RiskFreePoint,
    )
    from persistra.project import Project


@dataclass(frozen=True, slots=True)
class ParsedFamilyBatch:
    """Domain objects produced by endpoint parsers, grouped per typed family."""

    bars: tuple[DailyBar, ...] = ()
    corporate_actions: tuple[CorporateActionObservation, ...] = ()
    trading_status: tuple[TradingStatusObservation, ...] = ()
    macro_releases: tuple[MacroRelease, ...] = ()
    risk_free_points: tuple[RiskFreePoint, ...] = ()
    benchmark_observations: tuple[BenchmarkSeriesObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Counts of domain objects handed to each typed service."""

    bars: int = 0
    corporate_actions: int = 0
    trading_status: int = 0
    macro_releases: int = 0
    risk_free_points: int = 0
    benchmark_observations: int = 0


class AlphaVantageIngestor:
    """Thin coordinator handing parsed domain objects to the typed services."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, parsed: ParsedFamilyBatch) -> IngestReport:
        """Ingest every populated family through its typed canonical service."""
        market = self._project.services.market
        if parsed.bars:
            market.bars.ingest(parsed.bars)
        if parsed.corporate_actions:
            market.actions.ingest(parsed.corporate_actions)
        if parsed.trading_status:
            market.status.ingest(parsed.trading_status)
        for release in parsed.macro_releases:
            market.macro.ingest(release)
        if parsed.risk_free_points:
            market.rates.ingest(parsed.risk_free_points)
        if parsed.benchmark_observations:
            market.benchmarks.ingest_series(parsed.benchmark_observations)
        return IngestReport(
            bars=len(parsed.bars),
            corporate_actions=len(parsed.corporate_actions),
            trading_status=len(parsed.trading_status),
            macro_releases=len(parsed.macro_releases),
            risk_free_points=len(parsed.risk_free_points),
            benchmark_observations=len(parsed.benchmark_observations),
        )
