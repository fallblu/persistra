"""Dependency-free immutable primitives shared by every Persistra subsystem."""

from persistra.domain.assets import AssetClass
from persistra.domain.events import DomainEvent, EventType
from persistra.domain.identity import ContentId, EntityId, EventId, QualifiedName, SchemaVersion
from persistra.domain.numbers import (
    Currency,
    Money,
    NonNegativeQuantity,
    NumericKind,
    Price,
    Quantity,
    Rate,
    RoundingMode,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.domain.seeds import SeedSpec
from persistra.domain.time import (
    AvailabilityQuality,
    Clock,
    Duration,
    EffectiveInterval,
    FixedClock,
    SystemClock,
    TimeInterval,
    utc_now,
    validate_instant,
)

__all__ = [
    "AssetClass",
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
    "SourceNumeric",
    "SourceNumericKind",
    "SystemClock",
    "TimeInterval",
    "Unit",
    "UnitSpec",
    "utc_now",
    "validate_instant",
]
