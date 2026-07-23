"""This module contains the Alpha Vantage parse-to-ingest boundary.

Endpoint parsers return canonical domain objects in a :class:`ParsedFamilyBatch`. The
:class:`AlphaVantageIngestor` sends each family to its typed canonical service.

A future generic-pipeline projector can use this boundary without a change to a parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persistra.market import (
        Bar,
        CorporateActionObservation,
        QuoteObservation,
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
    """This class represents endpoint-parser domain objects in groups for each typed
    family."""

    bars: tuple[Bar, ...] = ()
    corporate_actions: tuple[CorporateActionObservation, ...] = ()
    trading_status: tuple[TradingStatusObservation, ...] = ()
    quotes: tuple[QuoteObservation, ...] = ()
    macro_releases: tuple[MacroRelease, ...] = ()
    risk_free_points: tuple[RiskFreePoint, ...] = ()
    benchmark_observations: tuple[BenchmarkSeriesObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestReport:
    """This class contains domain-object counts for each typed service."""

    bars: int = 0
    corporate_actions: int = 0
    trading_status: int = 0
    quotes: int = 0
    macro_releases: int = 0
    risk_free_points: int = 0
    benchmark_observations: int = 0


class AlphaVantageIngestor:
    """This class sends parsed domain objects to the typed services."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, parsed: ParsedFamilyBatch) -> IngestReport:
        """Ingest each populated family through its typed canonical service."""
        market = self._project.services.market
        if parsed.bars:
            market.bars.ingest(parsed.bars)
        if parsed.corporate_actions:
            market.actions.ingest(parsed.corporate_actions)
        if parsed.trading_status:
            market.status.ingest(parsed.trading_status)
        if parsed.quotes:
            market.quotes.ingest(parsed.quotes)
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
            quotes=len(parsed.quotes),
            macro_releases=len(parsed.macro_releases),
            risk_free_points=len(parsed.risk_free_points),
            benchmark_observations=len(parsed.benchmark_observations),
        )
