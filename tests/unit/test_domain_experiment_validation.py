"""Validation-path coverage for domain numerics and experiment contracts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from persistra.domain import ContentId, Money
from persistra.domain.numbers import Currency, Quantity
from persistra.errors import (
    CurrencyMismatchError,
    DecimalOverflowError,
    ExperimentRequestError,
    InvalidCurrencyError,
    InvalidDecimalError,
)
from persistra.experiments import (
    CompatibilityField,
    CompatibilityPolicy,
    ParameterDomain,
    ParameterSet,
    ScenarioKind,
    ScenarioSpec,
    StudyExecutionPolicy,
    WorkerOutcome,
)


def test_currency_and_money_validation() -> None:
    assert Currency("usd").code == "USD"
    with pytest.raises(InvalidCurrencyError):
        Currency("US")
    with pytest.raises(InvalidCurrencyError):
        Currency("ZZZ")
    usd = Currency("USD")
    total = Money("1.00", usd) + Money("2.50", usd)
    assert total == Money("3.50", usd)
    assert (Money("5", usd) - Money("2", usd)) == Money("3", usd)
    assert Money.zero(usd).amount == Decimal("0")
    assert Money("1", usd).__add__(3) is NotImplemented
    assert Money("1", usd).__sub__(3) is NotImplemented
    with pytest.raises(CurrencyMismatchError):
        _ = Money("1", usd) + Money("1", Currency("EUR"))


def test_profile_decimal_input_validation() -> None:
    assert Quantity("1.25").value == Decimal("1.25")
    with pytest.raises(InvalidDecimalError):
        Quantity("not-a-number")
    with pytest.raises(InvalidDecimalError):
        Quantity(object())  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidDecimalError):
        Quantity(Decimal("nan"))
    with pytest.raises(DecimalOverflowError):
        Quantity("1" * 40)


def test_experiment_contract_validation() -> None:
    assert ParameterDomain("x", ("1", "2")).values == ("1", "2")
    with pytest.raises(ExperimentRequestError):
        ParameterDomain("", ("1",))
    with pytest.raises(ExperimentRequestError):
        ParameterDomain("x", ("1", "1"))

    assert ParameterSet((("a", "1"), ("b", "2"))).values[0] == ("a", "1")
    with pytest.raises(ExperimentRequestError):
        ParameterSet((("b", "2"), ("a", "1")))

    assert ScenarioSpec("baseline", ScenarioKind.BASELINE).name == "baseline"
    with pytest.raises(ExperimentRequestError):
        ScenarioSpec("mc", ScenarioKind.MONTE_CARLO)

    policy = CompatibilityPolicy(
        "reuse", 1, (CompatibilityField.ENVIRONMENT,), "documented"
    )
    assert policy.version == 1
    with pytest.raises(ExperimentRequestError):
        CompatibilityPolicy("reuse", 1, (), "documented")

    assert WorkerOutcome(ContentId.from_bytes(b"m"), Decimal("1")).row_count == 0
    with pytest.raises(ExperimentRequestError):
        WorkerOutcome(ContentId.from_bytes(b"m"), Decimal("1"), row_count=-1)

    assert StudyExecutionPolicy(workers=2).workers == 2
    with pytest.raises(ExperimentRequestError):
        StudyExecutionPolicy(workers=0)
    with pytest.raises(ExperimentRequestError):
        StudyExecutionPolicy(workers=65)
