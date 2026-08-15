"""Boundary validation tests for exact engine values and typed models."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine._scalars import (
    INT64_MAX,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    quantity_value,
)
from persistra.integrations.trading_engine.model import (
    BarClockPolicy,
    ExecutionPolicy,
    ScenarioBar,
    SizingPolicy,
    TargetDecision,
)


@pytest.mark.parametrize(
    ("value", "error", "message", "options"),
    [
        (True, TypeError, "decimal number", {}),
        (object(), TypeError, "decimal number", {}),
        (".", ValueError, "decimal number", {}),
        ("NaN", ValueError, "finite", {}),
        ("1.0000001", ValueError, "at most six", {}),
        (0, ValueError, "positive", {"positive": True}),
        (-1, ValueError, "nonnegative", {"nonnegative": True}),
        (Decimal(INT64_MAX) + 1, ValueError, "supported range", {}),
    ],
)
def test_decimal_value_rejects_unsupported_engine_values(
    value: object,
    error: type[Exception],
    message: str,
    options: dict[str, bool],
) -> None:
    with pytest.raises(error, match=message):
        decimal_value(value, name="value", **options)


def test_decimal_value_and_string_use_exact_canonical_micros() -> None:
    assert decimal_value(Decimal("1.250000"), name="value") == Decimal("1.250000")
    assert decimal_value(2.5, name="value") == Decimal("2.5")
    assert decimal_string(Decimal("1.250000")) == "1.25"
    assert decimal_string(Decimal("-0.000000")) == "0"


@pytest.mark.parametrize(
    ("value", "error", "message", "positive"),
    [
        (True, TypeError, "whole number", False),
        (Decimal("1.5"), ValueError, "whole number", False),
        (1.5, ValueError, "whole number", False),
        ("", ValueError, "whole number", False),
        ("no", ValueError, "whole number", False),
        ("01", ValueError, "canonical", False),
        (object(), TypeError, "whole number", False),
        (-1, ValueError, "nonnegative", False),
        (0, ValueError, "positive", True),
        (INT64_MAX + 1, ValueError, "supported range", False),
    ],
)
def test_quantity_value_rejects_unsupported_engine_values(
    value: object,
    error: type[Exception],
    message: str,
    positive: bool,
) -> None:
    with pytest.raises(error, match=message):
        quantity_value(value, name="quantity", positive=positive)


def test_quantity_value_accepts_integral_decimal_float_and_string() -> None:
    assert quantity_value(Decimal(2), name="quantity") == 2
    assert quantity_value(3.0, name="quantity") == 3
    assert quantity_value("4", name="quantity") == 4


@pytest.mark.parametrize(
    ("value", "error", "message"),
    [
        (1, TypeError, "string"),
        (" padded", ValueError, "empty or padded"),
        ("line\nbreak", ValueError, "whitespace or control"),
    ],
)
def test_identifier_rejects_nonportable_values(
    value: object,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        identifier(value, name="identifier")


def test_exact_fields_requires_an_exact_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        exact_fields([], {"value"}, name="item")
    with pytest.raises(ValueError, match=r"missing=.*value.*extra=.*other"):
        exact_fields({"other": 1}, {"value"}, name="item")


def valid_bar() -> ScenarioBar:
    """Return a directly constructed valid exact bar."""
    return ScenarioBar(
        source_sequence=1,
        instrument_id="asset-a",
        source_timestamp=pd.Timestamp("2026-01-02T14:30:00Z"),
        start_at=pd.Timestamp("2026-01-02T14:30:00Z"),
        end_at=pd.Timestamp("2026-01-02T14:35:00Z"),
        available_at=pd.Timestamp("2026-01-02T14:35:00Z"),
        received_at=pd.Timestamp("2026-01-02T14:35:00Z"),
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        close=Decimal("100"),
        volume=100,
    )


def test_policy_models_reject_each_unsupported_setting() -> None:
    with pytest.raises(ValueError, match="start or end"):
        BarClockPolicy(cast("Any", "middle"), timedelta(1), timedelta(0), timedelta(0))
    with pytest.raises(ValueError, match="availability_delay"):
        BarClockPolicy("start", timedelta(1), timedelta(microseconds=-1), timedelta(0))
    with pytest.raises(ValueError, match="receipt_delay"):
        BarClockPolicy("start", timedelta(1), timedelta(0), timedelta(microseconds=-1))
    with pytest.raises(ValueError, match="initial_cash equity"):
        SizingPolicy(equity_basis=cast("Any", "current_equity"))
    with pytest.raises(ValueError, match="decision_close"):
        SizingPolicy(reference_price=cast("Any", "open"))
    with pytest.raises(ValueError, match="down_to_lot"):
        SizingPolicy(quantity_rounding=cast("Any", "nearest"))
    with pytest.raises(ValueError, match="fee_bps"):
        ExecutionPolicy(participation_bps=1, fee_bps=10_001)
    with pytest.raises(ValueError, match="nonnegative"):
        ExecutionPolicy(participation_bps=1, fixed_fee=-1)


def test_bar_and_target_models_enforce_exact_causal_values() -> None:
    bar = valid_bar()
    assert bar.volume == 100
    with pytest.raises(ValueError, match="timestamps"):
        replace(bar, end_at=bar.start_at)
    with pytest.raises(ValueError, match="OHLC"):
        replace(bar, low=Decimal("100.5"))
    with pytest.raises(ValueError, match="nonnegative"):
        replace(bar, volume=-1)
    with pytest.raises(TypeError, match="pandas Timestamp"):
        replace(bar, source_timestamp=cast("Any", "2026-01-02T14:30:00Z"))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(bar, source_timestamp=pd.Timestamp("2026-01-02T14:30:00"))
    with pytest.raises(ValueError, match="microsecond precision"):
        replace(bar, source_timestamp=pd.Timestamp("2026-01-02T14:30:00.000000001Z"))

    with pytest.raises(ValueError, match="between zero and one"):
        TargetDecision(
            after_bar_sequence=1,
            decision_at=bar.received_at,
            instrument_id="asset-a",
            quantity=1,
            reference_close=Decimal(100),
            target_weight=1.1,
        )
