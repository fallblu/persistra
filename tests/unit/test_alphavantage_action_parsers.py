from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.errors import SourceResponseError
from persistra.market import CorporateActionKind, CorporateActionStatus
from persistra.reference import InstrumentId, SecurityId
from persistra.sources.alphavantage.equity import parse_dividends, parse_splits

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_SECURITY = SecurityId.new()
_INSTRUMENT = InstrumentId.new()
_AVAILABLE = datetime(2026, 1, 10, tzinfo=UTC)
_SESSIONS = {
    date(2026, 1, 6): (
        datetime(2026, 1, 6, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 6, 21, 0, tzinfo=UTC),
    ),
    date(2026, 1, 8): (
        datetime(2026, 1, 8, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 8, 21, 0, tzinfo=UTC),
    ),
}


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_split_parser_maps_factors_to_split_kinds() -> None:
    actions = parse_splits(
        _fixture("splits.json"),
        security_id=_SECURITY,
        instrument_id=_INSTRUMENT,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    assert [action.kind for action in actions] == [
        CorporateActionKind.SPLIT,
        CorporateActionKind.REVERSE_SPLIT,
    ]
    split = actions[0]
    assert split.share_ratio == Decimal("2.0")
    assert split.status is CorporateActionStatus.COMPLETED
    assert split.effective_at == _SESSIONS[date(2026, 1, 6)][0]
    assert split.effective_date == date(2026, 1, 6)
    assert split.source_action_key == "alphavantage:IBM:split:2026-01-06"
    reverse = actions[1]
    assert reverse.share_ratio == Decimal("0.5")
    assert reverse.effective_at == datetime(2018, 3, 15, tzinfo=UTC)


def test_split_parser_is_deterministic_for_identical_payloads() -> None:
    first = parse_splits(
        _fixture("splits.json"),
        security_id=_SECURITY,
        instrument_id=_INSTRUMENT,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    second = parse_splits(
        _fixture("splits.json"),
        security_id=_SECURITY,
        instrument_id=_INSTRUMENT,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    assert [action.action_id for action in first] == [
        action.action_id for action in second
    ]


def test_dividend_parser_emits_cash_dividends_and_skips_zero_amounts() -> None:
    actions = parse_dividends(
        _fixture("dividends.json"),
        security_id=_SECURITY,
        instrument_id=_INSTRUMENT,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    assert len(actions) == 1
    dividend = actions[0]
    assert dividend.kind is CorporateActionKind.ORDINARY_CASH_DIVIDEND
    assert dividend.cash_per_subject_unit == Decimal("1.0")
    assert dividend.currency == "USD"
    assert dividend.ex_at == _SESSIONS[date(2026, 1, 8)][0]
    assert dividend.ex_date == date(2026, 1, 8)
    assert dividend.payable_date == date(2026, 1, 20)


def test_action_parsers_reject_malformed_payloads() -> None:
    with pytest.raises(SourceResponseError):
        parse_splits(
            {"data": []},
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_splits(
            {"symbol": "IBM", "data": "nope"},
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_splits(
            {
                "symbol": "IBM",
                "data": [{"effective_date": "bad", "split_factor": "2"}],
            },
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_splits(
            {
                "symbol": "IBM",
                "data": [{"effective_date": "2026-01-06", "split_factor": "0"}],
            },
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_dividends(
            {
                "symbol": "IBM",
                "data": [{"ex_dividend_date": "nope", "amount": "1"}],
            },
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_dividends(
            {
                "symbol": "IBM",
                "data": [
                    {
                        "ex_dividend_date": "2026-01-08",
                        "payment_date": "bad",
                        "amount": "1",
                    }
                ],
            },
            security_id=_SECURITY,
            instrument_id=_INSTRUMENT,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
