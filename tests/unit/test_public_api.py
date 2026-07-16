from __future__ import annotations

import persistra
import persistra.domain as domain
from persistra.cli import main
from persistra.errors import DomainValidationError, PersistraError


def test_public_exports_are_intentionally_small() -> None:
    assert persistra.__all__ == ["Project", "ProjectMode", "ProjectOverrides", "__version__"]
    assert set(domain.__all__) == {
        "AvailabilityQuality",
        "Clock",
        "ContentId",
        "Currency",
        "DomainEvent",
        "Duration",
        "EffectiveInterval",
        "EntityId",
        "EventId",
        "EventType",
        "FixedClock",
        "Money",
        "NonNegativeQuantity",
        "NumericKind",
        "Price",
        "QualifiedName",
        "Quantity",
        "Rate",
        "RoundingMode",
        "SchemaVersion",
        "SeedSpec",
        "SystemClock",
        "TimeInterval",
        "Unit",
        "UnitSpec",
        "utc_now",
        "validate_instant",
    }
    assert issubclass(DomainValidationError, PersistraError)


def test_cli_shell(capsys: object) -> None:
    assert main([]) == 0
