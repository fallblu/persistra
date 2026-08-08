"""Tests for acquisition metadata."""

from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from persistra.model import ResultMetadata


def test_metadata_redacts_key_and_copies_parameters() -> None:
    parameters: dict[str, object] = {
        "symbol": "IBM",
        "apikey": "secret",
        "APIKEY": "other-secret",
    }
    result = ResultMetadata(
        provider="alpha_vantage",
        operation="GLOBAL_QUOTE",
        request_parameters=parameters,
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    parameters["symbol"] = "CHANGED"
    assert dict(result.request_parameters) == {"symbol": "IBM"}
    assert isinstance(result.request_parameters, MappingProxyType)


def test_metadata_requires_aware_times() -> None:
    with pytest.raises(ValueError, match="retrieved_at"):
        ResultMetadata(
            provider="x",
            operation="y",
            request_parameters={},
            retrieved_at=datetime(2025, 1, 1),
        )
    with pytest.raises(ValueError, match="provider_as_of"):
        ResultMetadata(
            provider="x",
            operation="y",
            request_parameters={},
            retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
            provider_as_of=datetime(2025, 1, 1),
        )
