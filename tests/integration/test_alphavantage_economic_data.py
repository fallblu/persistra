from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from persistra import Project, ProjectMode
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import (
    MacroQuery,
    MacroVintageMode,
    RiskFreeQuery,
    Tenor,
)
from persistra.market.economic_models import MacroSeriesRef, RiskFreeCurveRef
from persistra.reference import AsOfContext, CalendarDefinition, CalendarRef, VenueId
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    ParsedFamilyBatch,
)
from persistra.sources.alphavantage.macro import (
    macro_series_definition,
    parse_macro_release,
)
from persistra.sources.alphavantage.rates import (
    FED_FUNDS_CURVE_NAME,
    TREASURY_CURVE_NAME,
    fed_funds_curve_definition,
    parse_federal_funds_rate,
    parse_treasury_yields,
    treasury_curve_definition,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)
FETCHED_AT = datetime(2026, 1, 10, tzinfo=UTC)
CALENDAR_NAME = QualifiedName("persistra.calendar.xnys")


def _project(tmp_path: Path) -> Path:
    layout = Project.init(tmp_path / "project")
    market = layout.state_path / "market.duckdb"
    create_database_file(
        market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(NOW),
    )
    with layout.config_path.open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.primary]\npath = ".persistra/market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    return layout.root


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_alphavantage_macro_rate_commodity_round_trip(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.reference.calendars.register(
            CalendarDefinition(
                CALENDAR_NAME,
                1,
                VenueId.new(),
                "XNYS",
                "America/New_York",
                date(2025, 12, 20),
                date(2026, 2, 1),
                AVAILABLE,
            )
        )
        calendar = CalendarRef(CALENDAR_NAME, 1)
        gdp_payload = _fixture("real_gdp.json")
        gdp_series = project.services.market.macro.register(
            macro_series_definition("REAL_GDP", gdp_payload)
        )
        gdp_release = parse_macro_release(
            gdp_payload,
            function="REAL_GDP",
            series=gdp_series,
            available_at=FETCHED_AT,
        )
        wti_payload = _fixture("wti.json")
        wti_series = project.services.market.macro.register(
            macro_series_definition("WTI", wti_payload)
        )
        wti_release = parse_macro_release(
            wti_payload,
            function="WTI",
            series=wti_series,
            available_at=FETCHED_AT,
        )
        treasury_curve = project.services.market.risk_free_curves.register(
            treasury_curve_definition(calendar=calendar)
        )
        treasury_points = parse_treasury_yields(
            _fixture("treasury_yield_10year.json"),
            curve=treasury_curve,
            maturity="10year",
            available_at=FETCHED_AT,
        )
        fed_curve = project.services.market.risk_free_curves.register(
            fed_funds_curve_definition(calendar=calendar)
        )
        fed_points = parse_federal_funds_rate(
            _fixture("federal_funds_rate.json"),
            curve=fed_curve,
            available_at=FETCHED_AT,
        )
        report = AlphaVantageIngestor(project).ingest(
            ParsedFamilyBatch(
                macro_releases=(gdp_release, wti_release),
                risk_free_points=treasury_points + fed_points,
            )
        )
        assert report.macro_releases == 2
        assert report.risk_free_points == 4
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 12, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        gdp_rows = project.services.market.macro.query(
            MacroQuery(
                MacroSeriesRef(QualifiedName("alphavantage.macro.real_gdp"), 1),
                date(2025, 1, 1),
                date(2026, 1, 1),
                MacroVintageMode.LATEST_KNOWN,
                context,
            )
        )
        assert len(gdp_rows) == 3
        assert gdp_rows["vintage_completeness"].unique().tolist() == ["latest_only"]
        assert gdp_rows["safety_status"].unique().tolist() == ["unsafe"]
        wti_rows = project.services.market.macro.query(
            MacroQuery(
                MacroSeriesRef(QualifiedName("alphavantage.commodity.wti"), 1),
                date(2026, 1, 1),
                date(2026, 1, 31),
                MacroVintageMode.LATEST_KNOWN,
                context,
            )
        )
        assert len(wti_rows) >= 2
        treasury_rows = project.services.market.rates.points(
            RiskFreeQuery(
                RiskFreeCurveRef(TREASURY_CURVE_NAME, 1),
                date(2026, 1, 8),
                date(2026, 1, 9),
                (Tenor.months(120),),
                context,
            )
        )
        assert len(treasury_rows) == 2
        assert float(
            project.services.market.rates.require(
                curve=RiskFreeCurveRef(TREASURY_CURVE_NAME, 1),
                effective_date=date(2026, 1, 9),
                tenor=Tenor.months(120),
                context=context,
            )
        ) == 0.0428
        fed_rows = project.services.market.rates.points(
            RiskFreeQuery(
                RiskFreeCurveRef(FED_FUNDS_CURVE_NAME, 1),
                date(2025, 11, 1),
                date(2025, 12, 31),
                (Tenor.days(1),),
                context,
            )
        )
        assert len(fed_rows) == 2
