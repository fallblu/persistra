from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

from persistra import Project, ProjectMode
from persistra.conformance import OutcomeStatus, standard_provider_suite
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import FixedClock, QualifiedName
from persistra.market import BarQuery, BarSpecDefinition, BarSpecRef, MacroQuery, MacroVintageMode
from persistra.market.economic_models import MacroSeriesRef
from persistra.reference import (
    AsOfContext,
    CalendarDefinition,
    InstrumentDefinition,
    InstrumentId,
    IssuerId,
    ListingId,
    ListingStatus,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    VenueId,
)
from persistra.sources.alphavantage.equity import parse_daily_equity_bars
from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    ParsedFamilyBatch,
)
from persistra.sources.alphavantage.macro import (
    macro_series_definition,
    parse_macro_release,
)
from persistra.sources.alphavantage.pairs import (
    crypto_pair_instrument,
    fx_pair_instrument,
    parse_crypto_daily_bars,
    parse_fx_daily_bars,
    utc_day_sessions,
)
from persistra.sources.alphavantage.registration import register_alphavantage

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)
FETCHED_AT = datetime(2026, 1, 10, tzinfo=UTC)
SPEC_NAME = QualifiedName("persistra.bar.session.regular")


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


def _equity_sessions() -> dict[date, tuple[datetime, datetime]]:
    exchange = xcals.get_calendar("XNYS", start="2026-01-01", end="2026-01-12")
    sessions: dict[date, tuple[datetime, datetime]] = {}
    for label in exchange.schedule.index:
        row = cast("Any", exchange.schedule.loc[label])
        sessions[label.date()] = (
            row["open"].to_pydatetime(),
            row["close"].to_pydatetime(),
        )
    return sessions


class _AlphaVantageDescriptorAdapter:
    """Fixture adapter describing the declared Alpha Vantage source contract."""

    def adapter_identity(self) -> str:
        return "alphavantage.adapter@1.0"

    def capabilities(self) -> frozenset[str]:
        return frozenset(
            {
                "availability",
                "credentials",
                "idempotency",
                "identity",
                "licensing",
                "pagination",
                "quarantine",
                "retry",
                "revisions",
                "schema",
            }
        )

    def sample_records(self, capability: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        rows = {
            "availability": (
                ("available_at", "2026-01-10T00:00:00+00:00"),
                ("availability_quality", "ingestion_bounded"),
            ),
            "credentials": (("status", "redacted"),),
            "idempotency": (("source_record_key", "TIME_SERIES_DAILY.AAA.2026-01-09"),),
            "identity": (("identity", "alphavantage.adapter@1.0"),),
            "licensing": (
                ("licensing_class", "licensed_no_redistribution"),
                ("redistributable", "false"),
            ),
            "pagination": (("page", "0"),),
            "quarantine": (
                ("disposition", "quarantined"),
                ("reason_code", "alphavantage.response.malformed"),
            ),
            "retry": (
                ("submission_key", "TIME_SERIES_DAILY.AAA.compact"),
                ("status", "complete"),
            ),
            "revisions": (
                ("source_record_key", "TIME_SERIES_DAILY.AAA.2026-01-09"),
                ("source_revision_key", "ingested@2026-01-10T00:00:00+00:00"),
            ),
            "schema": (("session_date", "2026-01-09"), ("close", "54.0")),
        }
        return (rows[capability],)


def test_cross_asset_families_share_one_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    equity = InstrumentDefinition(
        IssuerId.new(),
        SecurityId.new(),
        VenueId.new(),
        ListingId.new(),
        InstrumentId.new(),
        "XNYS",
        "America/New_York",
        SecurityKind.COMMON_STOCK,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        "USD",
        AVAILABLE,
        available_at=AVAILABLE,
    )
    crypto = crypto_pair_instrument(
        "BTC", "EUR", valid_from=AVAILABLE, available_at=AVAILABLE
    )
    fx = fx_pair_instrument("EUR", "USD", valid_from=AVAILABLE, available_at=AVAILABLE)
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        register_alphavantage(project)
        for instrument in (equity, crypto, fx):
            project.services.reference.register_instrument(instrument)
        equity_calendar = project.services.reference.calendars.register(
            CalendarDefinition(
                QualifiedName("persistra.calendar.xnys"),
                1,
                equity.venue_id,
                "XNYS",
                "America/New_York",
                date(2025, 12, 20),
                date(2026, 2, 1),
                AVAILABLE,
            )
        )
        crypto_calendar = project.services.reference.calendars.register(
            CalendarDefinition.always_open(
                coverage_start=date(2025, 12, 20),
                coverage_end=date(2026, 2, 1),
                available_at=AVAILABLE,
            )
        )
        fx_calendar = project.services.reference.calendars.register(
            CalendarDefinition.fx_24x5(
                coverage_start=date(2025, 12, 20),
                coverage_end=date(2026, 2, 1),
                available_at=AVAILABLE,
            )
        )
        spec = project.services.market.bar_specs.register(BarSpecDefinition(SPEC_NAME))
        equity_bars = parse_daily_equity_bars(
            _fixture("time_series_daily.json"),
            instrument_id=equity.instrument_id,
            spec=spec,
            calendar=equity_calendar,
            sessions=_equity_sessions(),
            available_at=FETCHED_AT,
        )
        crypto_bars = parse_crypto_daily_bars(
            _fixture("digital_currency_daily.json"),
            instrument_id=crypto.instrument_id,
            spec=spec,
            calendar=crypto_calendar,
            sessions=utc_day_sessions(date(2026, 1, 1), date(2026, 1, 11)),
            available_at=FETCHED_AT,
            currency="EUR",
        )
        fx_bars = parse_fx_daily_bars(
            _fixture("fx_daily.json"),
            instrument_id=fx.instrument_id,
            spec=spec,
            calendar=fx_calendar,
            sessions=utc_day_sessions(
                date(2026, 1, 1), date(2026, 1, 11), weekdays_only=True
            ),
            available_at=FETCHED_AT,
            currency="USD",
        )
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
        report = AlphaVantageIngestor(project).ingest(
            ParsedFamilyBatch(
                bars=equity_bars + crypto_bars + fx_bars,
                macro_releases=(gdp_release,),
            )
        )
        assert report.bars == len(equity_bars) + len(crypto_bars) + len(fx_bars)
        assert report.macro_releases == 1
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 12, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        expectations = {
            equity.instrument_id: (6, "USD"),
            crypto.instrument_id: (4, "EUR"),
            fx.instrument_id: (5, "USD"),
        }
        for instrument_id, (count, currency) in expectations.items():
            frame = project.services.market.bars.query(
                BarQuery(
                    (instrument_id,),
                    BarSpecRef(SPEC_NAME, 1),
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 1, 10, tzinfo=UTC),
                    context,
                )
            )
            assert len(frame) == count
            assert set(frame["currency"]) == {currency}
            assert frame["availability_quality"].unique().tolist() == [
                "ingestion_bounded"
            ]
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


def test_alphavantage_descriptor_passes_the_provider_conformance_suite() -> None:
    report = standard_provider_suite().run(_AlphaVantageDescriptorAdapter())
    assert report.passed
    assert {outcome.status for outcome in report.outcomes} == {OutcomeStatus.PASSED}
    assert report.adapter_identity == "alphavantage.adapter@1.0"
