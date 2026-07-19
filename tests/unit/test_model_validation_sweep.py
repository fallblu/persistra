"""Validation-path coverage for lightweight typed model contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from persistra.accounting import (
    AccountingOpening,
    AccrualFacts,
    AccrualKind,
    BorrowAuthorizationFacts,
    CashFlowFacts,
    DividendFacts,
    FillFacts,
    MarkFacts,
    SettlementFacts,
    SettlementObligationId,
    SplitFacts,
    TradeFillFacts,
)
from persistra.catalog import MarketSnapshotId, SnapshotRef
from persistra.db import DatabaseId
from persistra.domain import ContentId, QualifiedName
from persistra.errors import (
    AccountingRequestError,
    FigureInputError,
    InvalidIntervalError,
    PortfolioConstructionError,
    ReferenceDefinitionError,
    SignalDefinitionError,
)
from persistra.portfolio import (
    ConstructionRequest,
    ConstructorRef,
    EqualWeightConstructorDefinition,
    RankSignalDefinition,
    SignalMaterializationId,
)
from persistra.reference import InstrumentId
from persistra.reference.models import (
    AsOfContext,
    CutoffMode,
    InstrumentDefinition,
    IssuerId,
    ListingId,
    ListingStatus,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    VenueId,
)
from persistra.viz.models import (
    FigureConfig,
    FigureLimits,
    ThemeRef,
    VisualReductionPolicy,
)

_AT = datetime(2025, 1, 6, tzinfo=UTC)
_NAIVE = datetime(2025, 1, 6)
_CONTENT = ContentId.from_bytes(b"content")


def test_accounting_facts_reject_invalid_shapes() -> None:
    instrument = InstrumentId.new()
    AccountingOpening(_AT, Decimal("100"), _CONTENT)
    with pytest.raises(AccountingRequestError):
        AccountingOpening(_AT, Decimal("-1"), _CONTENT)
    with pytest.raises(AccountingRequestError):
        FillFacts(_CONTENT, instrument, _AT, "hold", Decimal("1"), Decimal("1"),
                  Decimal("0"), Decimal("0"))
    FillFacts(_CONTENT, instrument, _AT, "buy", Decimal("1"), Decimal("1"),
              Decimal("0"), Decimal("0"))
    with pytest.raises(AccountingRequestError):
        TradeFillFacts(_CONTENT, instrument, _AT, _AT - timedelta(days=1),
                       Decimal("1"), Decimal("1"))
    TradeFillFacts(_CONTENT, instrument, _AT, _AT, Decimal("1"), Decimal("1"))
    with pytest.raises(AccountingRequestError):
        CashFlowFacts(_CONTENT, _AT, Decimal("0"))
    with pytest.raises(AccountingRequestError):
        SettlementFacts(_CONTENT, _NAIVE, SettlementObligationId.new())
    with pytest.raises(AccountingRequestError):
        AccrualFacts(_CONTENT, _AT, AccrualKind.FINANCING, Decimal("0"))
    with pytest.raises(AccountingRequestError):
        BorrowAuthorizationFacts(_CONTENT, instrument, _AT, _AT, Decimal("1"))
    with pytest.raises(AccountingRequestError):
        MarkFacts(_CONTENT, instrument, _AT, _AT - timedelta(days=1), Decimal("1"))
    with pytest.raises(AccountingRequestError):
        SplitFacts(_CONTENT, instrument, _AT, Decimal("0"))
    with pytest.raises(AccountingRequestError):
        DividendFacts(_CONTENT, instrument, _AT, Decimal("-1"))


def test_portfolio_definitions_reject_invalid_shapes() -> None:
    RankSignalDefinition(QualifiedName("persistra.signal.momentum"), 1)
    with pytest.raises(SignalDefinitionError):
        RankSignalDefinition(QualifiedName("persistra.signal.momentum"), 0)
    EqualWeightConstructorDefinition(QualifiedName("persistra.constructor.top"), 1)
    with pytest.raises(PortfolioConstructionError):
        EqualWeightConstructorDefinition(
            QualifiedName("persistra.constructor.top"), 1, minimum_rank=1.5
        )
    materialization = SignalMaterializationId.new()
    ref = ConstructorRef(QualifiedName("persistra.constructor.top"), 1)
    ConstructionRequest(ref, materialization, start_at=_AT, end_at=_AT + timedelta(days=1))
    with pytest.raises(PortfolioConstructionError):
        ConstructionRequest(ref, materialization, start_at=_NAIVE)
    with pytest.raises(PortfolioConstructionError):
        ConstructionRequest(
            ref, materialization, start_at=_AT + timedelta(days=1), end_at=_AT
        )


def test_viz_configuration_rejects_invalid_shapes() -> None:
    ThemeRef()
    with pytest.raises(FigureInputError):
        ThemeRef(version=0)
    assert VisualReductionPolicy.none().kind.value == "none"
    with pytest.raises(FigureInputError):
        VisualReductionPolicy.min_max_envelope(0)
    with pytest.raises(FigureInputError):
        FigureLimits(max_traces=0)
    FigureConfig()
    with pytest.raises(FigureInputError):
        FigureConfig(title="")
    with pytest.raises(FigureInputError):
        FigureConfig(display_timezone="America/New_York")
    with pytest.raises(FigureInputError):
        FigureConfig(locale="fr_FR")


def _instrument(**overrides: object) -> InstrumentDefinition:
    values: dict[str, object] = {
        "issuer_id": IssuerId.new(),
        "security_id": SecurityId.new(),
        "venue_id": VenueId.new(),
        "listing_id": ListingId.new(),
        "instrument_id": InstrumentId.new(),
        "mic": "XNYS",
        "timezone_name": "America/New_York",
        "security_kind": SecurityKind.COMMON_STOCK,
        "security_status": SecurityStatus.ACTIVE,
        "listing_status": ListingStatus.ACTIVE,
        "currency": "USD",
        "valid_from": _AT,
    }
    values.update(overrides)
    return InstrumentDefinition(**values)  # pyright: ignore[reportArgumentType]


def test_reference_context_and_instrument_validation() -> None:
    snapshot = SnapshotRef(DatabaseId.new(), MarketSnapshotId.new(), 1, _CONTENT)
    AsOfContext(snapshot, _AT, _AT)
    with pytest.raises(ReferenceDefinitionError):
        AsOfContext(snapshot, _AT, _AT, project_cutoff_at=_AT)
    with pytest.raises(ReferenceDefinitionError):
        AsOfContext(snapshot, _AT, _AT, cutoff_mode=CutoffMode.PUBLIC_AND_PROJECT)

    assert _instrument().mic == "XNYS"
    with pytest.raises(ReferenceDefinitionError):
        _instrument(mic="nyse")
    with pytest.raises(ReferenceDefinitionError):
        _instrument(currency="ZZZ")
    with pytest.raises(InvalidIntervalError):
        _instrument(valid_from=_AT, valid_to=_AT - timedelta(days=1))
