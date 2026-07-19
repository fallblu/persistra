from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast

from persistra import Project, ProjectMode
from persistra.catalog import CompositeSnapshotRef
from persistra.db import DatabaseName, DatabaseRole
from persistra.db.connection import create_database_file
from persistra.domain import AssetClass, FixedClock, QualifiedName
from persistra.reference import (
    FX_24X5_CALENDAR_NAME,
    SYNTHETIC_OTC_VENUE_ID,
    ActiveListings,
    AsOfContext,
    CalendarDefinition,
    CalendarRef,
    CutoffMode,
    InstrumentDefinition,
    InstrumentId,
    ListingId,
    ListingStatus,
    PublicCutoffPolicy,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    SessionDecisionAnchor,
    SessionDecisionSchedule,
    SessionSelection,
    UniverseDefinition,
    UniverseRef,
    market_convention_issuer_id,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
AVAILABLE = datetime(2025, 12, 1, tzinfo=UTC)


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


def _fx_pair() -> InstrumentDefinition:
    return InstrumentDefinition(
        market_convention_issuer_id(AssetClass.FX),
        SecurityId.new(),
        SYNTHETIC_OTC_VENUE_ID,
        ListingId.new(),
        InstrumentId.new(),
        "",
        "UTC",
        SecurityKind.FX_PAIR,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        "USD",
        AVAILABLE,
        available_at=AVAILABLE,
        base_currency="EUR",
        quote_currency="USD",
    )


def _crypto_pair() -> InstrumentDefinition:
    return InstrumentDefinition(
        market_convention_issuer_id(AssetClass.CRYPTO),
        SecurityId.new(),
        SYNTHETIC_OTC_VENUE_ID,
        ListingId.new(),
        InstrumentId.new(),
        "",
        "UTC",
        SecurityKind.CRYPTO_PAIR,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        "EUR",
        AVAILABLE,
        available_at=AVAILABLE,
        base_currency="BTC",
        quote_currency="EUR",
    )


def test_pair_instruments_round_trip_and_select_into_universes(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    fx = _fx_pair()
    crypto = _crypto_pair()
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        assert (
            project.services.reference.register_instrument(fx) == fx.instrument_id
        )
        assert (
            project.services.reference.register_instrument(crypto)
            == crypto.instrument_id
        )
        project.services.reference.calendars.register(
            CalendarDefinition.fx_24x5(
                coverage_start=date(2025, 12, 20),
                coverage_end=date(2026, 1, 15),
                available_at=AVAILABLE,
            )
        )
        snapshot = project.services.snapshots.create()

    context = AsOfContext(
        snapshot,
        datetime(2026, 1, 9, 21, tzinfo=UTC),
        datetime(2026, 1, 9, 21, tzinfo=UTC),
    )
    with Project.open(root, mode=ProjectMode.READ_ONLY, clock=FixedClock(NOW)) as project:
        frame = project.services.reference.instruments(
            context=context,
            instrument_ids=(fx.instrument_id, crypto.instrument_id),
        )
        assert len(frame) == 2
        by_kind = frame.set_index("security_kind")
        fx_row = cast("Any", by_kind.loc[SecurityKind.FX_PAIR.value])
        assert fx_row["asset_class"] == AssetClass.FX.value
        assert fx_row["base_currency"] == "EUR"
        assert fx_row["quote_currency"] == "USD"
        assert fx_row["currency"] == "USD"
        assert fx_row["mic"] == ""
        crypto_row = cast("Any", by_kind.loc[SecurityKind.CRYPTO_PAIR.value])
        assert crypto_row["asset_class"] == AssetClass.CRYPTO.value
        assert crypto_row["base_currency"] == "BTC"
        assert crypto_row["quote_currency"] == "EUR"
        assert crypto_row["currency"] == "EUR"
        assert (
            fx_row["issuer_id"]
            == str(market_convention_issuer_id(AssetClass.FX).value)
        )

    with Project.open(
        root,
        mode=ProjectMode.RESEARCH_WRITE,
        clock=FixedClock(NOW),
    ) as project:
        composite = project.services.snapshots.create_composite(
            {DatabaseName("primary"): snapshot}
        )
        assert isinstance(composite, CompositeSnapshotRef)
        project.services.universes.register(
            UniverseDefinition(
                QualifiedName("project.universe.pairs"),
                1,
                ActiveListings(
                    (SYNTHETIC_OTC_VENUE_ID,),
                    (SecurityKind.FX_PAIR, SecurityKind.CRYPTO_PAIR),
                ),
                allowed_security_kinds=(
                    SecurityKind.FX_PAIR,
                    SecurityKind.CRYPTO_PAIR,
                ),
            )
        )
        evaluation = project.services.universes.evaluate(
            definition=UniverseRef(QualifiedName("project.universe.pairs"), 1),
            composite_snapshot=composite,
            decisions=SessionDecisionSchedule(
                CalendarRef(FX_24X5_CALENDAR_NAME, 1),
                SessionDecisionAnchor.CLOSE,
                SessionSelection.EVERY_SESSION,
            ),
            start_at=datetime(2026, 1, 5, tzinfo=UTC),
            end_at=datetime(2026, 1, 9, tzinfo=UTC),
            cutoff_mode=CutoffMode.PUBLIC,
            public_cutoff_policy=PublicCutoffPolicy.at_decision(),
            market_database="primary",
        )
        eligibility = project.services.universes.eligibility(
            evaluation.universe_evaluation_id
        )
        assert eligibility["eligible"].all()
        assert set(eligibility["instrument_id"]) == {
            str(fx.instrument_id.value),
            str(crypto.instrument_id.value),
        }
