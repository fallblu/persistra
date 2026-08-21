"""Tests for acquisition metadata."""

from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

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


def test_metadata_deeply_freezes_and_redacts_portable_parameters() -> None:
    parameters: dict[str, Any] = {
        "symbols": ["AAA"],
        "options": {
            "region": "US",
            "api_key": "nested-secret",
            "requests": [{"APIKEY": "sequence-secret", "page": 1}],
        },
    }
    result = ResultMetadata(
        provider="demo",
        operation="request",
        request_parameters=parameters,
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    parameters["symbols"].append("BBB")
    parameters["options"]["region"] = "EU"

    assert result.request_parameters == {
        "symbols": ("AAA",),
        "options": {"region": "US", "requests": ({"page": 1},)},
    }
    with pytest.raises(AttributeError):
        result.request_parameters["symbols"].append("CCC")
    with pytest.raises(TypeError):
        result.request_parameters["options"]["region"] = "EU"


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf")])
def test_metadata_rejects_nonportable_parameters(value: object) -> None:
    with pytest.raises(ValueError, match="portable JSON"):
        ResultMetadata(
            provider="demo",
            operation="request",
            request_parameters={"unsupported": value},
            retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
        )


def test_metadata_rejects_cyclic_parameters() -> None:
    parameters: dict[str, Any] = {}
    parameters["cycle"] = parameters

    with pytest.raises(ValueError, match="portable JSON"):
        ResultMetadata(
            provider="demo",
            operation="request",
            request_parameters=parameters,
            retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
        )


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


@pytest.mark.parametrize("field", ["provider", "operation"])
def test_metadata_requires_nonblank_scope_fields(field: str) -> None:
    metadata = ResultMetadata(
        provider="provider",
        operation="operation",
        request_parameters={},
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match=field):
        replace(metadata, **{field: " \t"})
