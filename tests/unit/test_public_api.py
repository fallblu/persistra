from __future__ import annotations

from importlib.resources import files

import persistra
import persistra.domain as domain
import persistra.sources.alphavantage as alphavantage
from persistra.cli import main
from persistra.errors import DomainValidationError, PersistraError


def test_public_exports_are_intentionally_small() -> None:
    assert persistra.__all__ == ["Project", "ProjectMode", "ProjectOverrides", "__version__"]
    assert set(domain.__all__) == {
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
    }
    assert issubclass(DomainValidationError, PersistraError)
    assert files("persistra").joinpath("py.typed").is_file()


def test_alphavantage_package_exports_client_and_entry_points() -> None:
    assert set(alphavantage.__all__) == {
        "ALPHAVANTAGE_SOURCE",
        "API_KEY_ENVIRONMENT_VARIABLE",
        "DEFAULT_BASE_URL",
        "DEFAULT_REQUESTS_PER_MINUTE",
        "AlphaVantageClient",
        "AlphaVantageIngestor",
        "IngestReport",
        "ParsedFamilyBatch",
        "TokenBucketRateLimiter",
        "TransportResponse",
        "crypto_pair_instrument",
        "fx_pair_instrument",
        "register_alphavantage",
        "utc_day_sessions",
    }
    for name in alphavantage.__all__:
        assert getattr(alphavantage, name) is not None


def test_cli_shell(capsys: object) -> None:
    assert main([]) == 0
