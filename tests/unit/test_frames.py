"""Versioned dataframe contract registry, coercion, and validation contracts."""

from __future__ import annotations

import datetime as dt

import pytest

from persistra.domain.frames import (
    FRAME_REGISTRY,
    ColumnDtype,
    ColumnSpec,
    FrameContract,
    FrameContractRegistry,
    build_frame,
    validate_frame,
)
from persistra.domain.identity import QualifiedName, SchemaVersion
from persistra.errors import FrameContractError

_CONTRACT = FrameContract(
    name=QualifiedName("persistra.dataframe.sample"),
    version=SchemaVersion(1),
    columns=(
        ColumnSpec("instrument_id", ColumnDtype.STRING),
        ColumnSpec("observed_at", ColumnDtype.INSTANT),
        ColumnSpec("session_date", ColumnDtype.DATE),
        ColumnSpec("trade_count", ColumnDtype.INT),
        ColumnSpec("halted", ColumnDtype.BOOL),
        ColumnSpec("close", ColumnDtype.FLOAT),
        ColumnSpec("reason_codes", ColumnDtype.JSON),
    ),
    ordering=("observed_at", "instrument_id"),
)


def _row(instrument: str, observed: dt.datetime) -> dict[str, object]:
    return {
        "instrument_id": instrument,
        "observed_at": observed,
        "session_date": dt.date(2026, 7, 15),
        "trade_count": 3,
        "halted": False,
        "close": 12.5,
        "reason_codes": ["ok"],
    }


def test_build_frame_produces_contract_dtypes_and_order() -> None:
    frame = build_frame(_CONTRACT, [_row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))])
    assert list(frame.columns) == list(_CONTRACT.column_names)
    assert str(frame["instrument_id"].dtype) == "string"
    assert str(frame["observed_at"].dtype) == "datetime64[us, UTC]"
    assert str(frame["session_date"].dtype) == "object"
    assert str(frame["trade_count"].dtype) == "Int64"
    assert str(frame["halted"].dtype) == "boolean"
    assert str(frame["close"].dtype) == "float64"
    assert str(frame["reason_codes"].dtype) == "string"
    assert frame["reason_codes"].iloc[0] == '["ok"]'
    validate_frame(_CONTRACT, frame)


def test_empty_frame_keeps_full_schema() -> None:
    frame = build_frame(_CONTRACT, [])
    assert list(frame.columns) == list(_CONTRACT.column_names)
    assert len(frame) == 0
    assert str(frame["observed_at"].dtype) == "datetime64[us, UTC]"
    assert str(frame["trade_count"].dtype) == "Int64"
    validate_frame(_CONTRACT, frame)


def test_ordering_is_deterministic_and_stable() -> None:
    early = dt.datetime(2026, 7, 15, 9, tzinfo=dt.UTC)
    late = dt.datetime(2026, 7, 15, 16, tzinfo=dt.UTC)
    frame = build_frame(
        _CONTRACT,
        [_row("B", late), _row("A", late), _row("Z", early)],
    )
    assert list(frame["instrument_id"]) == ["Z", "A", "B"]


def test_schema_identity() -> None:
    assert _CONTRACT.schema_id == "persistra.dataframe.sample@1"


def test_registry_register_get_and_conflict() -> None:
    registry = FrameContractRegistry()
    registry.register(_CONTRACT)
    assert registry.get("persistra.dataframe.sample@1") is _CONTRACT
    assert "persistra.dataframe.sample@1" in registry.identities()
    registry.register(_CONTRACT)  # idempotent for an identical contract
    conflicting = FrameContract(
        name=QualifiedName("persistra.dataframe.sample"),
        version=SchemaVersion(1),
        columns=(ColumnSpec("x", ColumnDtype.STRING),),
    )
    with pytest.raises(FrameContractError):
        registry.register(conflicting)
    with pytest.raises(FrameContractError):
        registry.get("persistra.dataframe.missing@1")


def test_global_registry_is_shared() -> None:
    assert isinstance(FRAME_REGISTRY, FrameContractRegistry)


def test_contract_rejects_duplicate_and_bad_ordering() -> None:
    with pytest.raises(FrameContractError):
        FrameContract(
            name=QualifiedName("persistra.dataframe.dup"),
            version=SchemaVersion(1),
            columns=(ColumnSpec("a", ColumnDtype.STRING), ColumnSpec("a", ColumnDtype.INT)),
        )
    with pytest.raises(FrameContractError):
        FrameContract(
            name=QualifiedName("persistra.dataframe.order"),
            version=SchemaVersion(1),
            columns=(ColumnSpec("a", ColumnDtype.STRING),),
            ordering=("missing",),
        )
    with pytest.raises(FrameContractError):
        FrameContract(
            name=QualifiedName("persistra.dataframe.order"),
            version=SchemaVersion(1),
            columns=(ColumnSpec("a", ColumnDtype.JSON),),
            ordering=("a",),
        )
    with pytest.raises(FrameContractError):
        FrameContract(
            name=QualifiedName("persistra.dataframe.empty"),
            version=SchemaVersion(1),
            columns=(),
        )


def test_coercion_rejections() -> None:
    naive = _row("A", dt.datetime(2026, 7, 15, 14))
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [naive])
    bad_date = _row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))
    bad_date["session_date"] = dt.datetime(2026, 7, 15, tzinfo=dt.UTC)
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [bad_date])
    bad_int = _row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))
    bad_int["trade_count"] = True
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [bad_int])
    bad_float = _row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))
    bad_float["close"] = float("inf")
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [bad_float])
    bad_json = _row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))
    bad_json["reason_codes"] = "{not json"
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [bad_json])


def test_row_column_mismatch_rejected() -> None:
    good = _row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))
    missing = dict(good)
    del missing["close"]
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [missing])
    extra = dict(good)
    extra["surprise"] = 1
    with pytest.raises(FrameContractError):
        build_frame(_CONTRACT, [extra])


def test_validate_frame_detects_divergence() -> None:
    frame = build_frame(_CONTRACT, [_row("A", dt.datetime(2026, 7, 15, 14, tzinfo=dt.UTC))])
    renamed = frame.rename(columns={"close": "price"})
    with pytest.raises(FrameContractError):
        validate_frame(_CONTRACT, renamed)
    retyped = frame.copy()
    retyped["trade_count"] = retyped["trade_count"].astype("float64")
    with pytest.raises(FrameContractError):
        validate_frame(_CONTRACT, retyped)


def test_json_accepts_dict_and_canonicalizes_keys() -> None:
    contract = FrameContract(
        name=QualifiedName("persistra.dataframe.jsononly"),
        version=SchemaVersion(1),
        columns=(ColumnSpec("payload", ColumnDtype.JSON),),
    )
    frame = build_frame(contract, [{"payload": {"b": 1, "a": 2}}])
    assert frame["payload"].iloc[0] == '{"a":2,"b":1}'
    validate_frame(contract, frame)
