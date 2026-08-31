"""Bounded property tests for untrusted serialized input boundaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING

import duckdb
import pytest
from hypothesis import given

from persistra.data import (
    AcquisitionCachePolicy,
    AcquisitionFamily,
    AcquisitionPlan,
    AcquisitionRequest,
    AcquisitionRunner,
    DuckDBStore,
    acquisition_plan_from_json,
    acquisition_plan_to_json,
    synthetic,
    verify_store,
)
from persistra.data.cache import RawCacheEntry, RawResponseCache
from persistra.errors import CacheError, DataValidationError
from persistra.integrations.trading_engine import (
    TradingEngineContractError,
    TradingEngineContractSchemas,
    TradingEngineDiagnostic,
    TradingEngineSuccessSummary,
    trading_engine_diagnostic_from_json,
    trading_engine_success_from_json,
)
from persistra.integrations.trading_engine._journal_parsing import json_record
from persistra.research import (
    ResearchManifest,
    create_research_manifest,
    manifest_from_json,
    manifest_to_json,
)
from persistra.research.model import ArtifactIdentity, DatasetScope
from tests._serialized_strategies import (
    FILE_FUZZ_SETTINGS,
    FUZZ_SETTINGS,
    decimal_strings,
    duplicate_field_documents,
    extreme_sizes,
    identifier_strings,
    malformed_identifiers,
    malformed_scalars,
    portable_json,
    portable_mappings,
    timestamp_strings,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path


def _journal_record(document: str) -> dict[str, object]:
    return json_record(document, line_number=1)


_DECODERS: tuple[tuple[Callable[[str], object], type[object]], ...] = (
    (acquisition_plan_from_json, AcquisitionPlan),
    (manifest_from_json, ResearchManifest),
    (trading_engine_success_from_json, TradingEngineSuccessSummary),
    (trading_engine_diagnostic_from_json, TradingEngineDiagnostic),
    (_journal_record, dict),
)


def _plan(
    scope: Mapping[str, object] | None = None,
    parameters: Mapping[str, object] | None = None,
) -> AcquisitionPlan:
    return AcquisitionPlan(
        "fuzz-plan",
        (
            AcquisitionRequest(
                "request",
                "provider",
                "operation",
                {} if scope is None else scope,
                {} if parameters is None else parameters,
                AcquisitionCachePolicy.DEFAULT,
                AcquisitionFamily.SERIES,
            ),
        ),
    )


@pytest.mark.parametrize(("decoder", "expected_type"), _DECODERS)
@FUZZ_SETTINGS
@given(portable_json)
def test_json_decoders_return_typed_values_or_public_validation_errors(
    decoder: Callable[[str], object], expected_type: type[object], value: object
) -> None:
    document = json.dumps(value, allow_nan=False)

    try:
        result = decoder(document)
    except Exception as error:
        assert isinstance(error, (TypeError, ValueError))
    else:
        assert isinstance(result, expected_type)


@pytest.mark.parametrize(("decoder", "_expected_type"), _DECODERS)
@FUZZ_SETTINGS
@given(duplicate_field_documents)
def test_json_decoders_reject_duplicate_fields(
    decoder: Callable[[str], object], _expected_type: type[object], document: str
) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        decoder(document)


@FUZZ_SETTINGS
@given(scope=portable_mappings, parameters=portable_mappings)
def test_acquisition_plan_round_trip_is_canonical(
    scope: dict[str, object], parameters: dict[str, object]
) -> None:
    plan = _plan(scope, parameters)

    restored = acquisition_plan_from_json(acquisition_plan_to_json(plan, indent=None))

    assert restored == plan
    assert acquisition_plan_to_json(restored, indent=None) == acquisition_plan_to_json(
        plan, indent=None
    )


@FUZZ_SETTINGS
@given(parameters=portable_mappings)
def test_research_manifest_round_trip_is_canonical(parameters: dict[str, object]) -> None:
    manifest = create_research_manifest(
        [DatasetScope("dataset", parameters, "v1", snapshot_identity="snapshot")],
        feature_parameters=parameters,
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        environment={"persistra": "test"},
        include_runtime=False,
    )

    restored = manifest_from_json(manifest_to_json(manifest, indent=None))

    assert restored == manifest
    assert manifest_to_json(restored, indent=None) == manifest_to_json(manifest, indent=None)


@FUZZ_SETTINGS
@given(malformed_scalars)
def test_plan_version_rejects_malformed_scalars(value: object) -> None:
    document = json.loads(acquisition_plan_to_json(_plan()))
    assert isinstance(document, dict)
    document["format_version"] = value

    with pytest.raises(ValueError):
        acquisition_plan_from_json(json.dumps(document, allow_nan=False))


@FUZZ_SETTINGS
@given(extreme_sizes)
def test_manifest_artifact_sizes_have_stable_extreme_boundaries(size: int) -> None:
    document: dict[str, object] = {
        "manifest_version": 1,
        "datasets": [],
        "parameters": {
            "features": {},
            "labels": {},
            "splits": {},
            "benchmarks": {},
            "models": {},
        },
        "environment": {"persistra": "test"},
        "random_seeds": {},
        "execution": {
            "status": "succeeded",
            "artifacts": [{"name": "result", "sha256": "0" * 64, "size_bytes": size}],
        },
    }

    try:
        result = manifest_from_json(json.dumps(document))
    except ValueError:
        assert size < 0
    else:
        assert isinstance(result.artifacts[0], ArtifactIdentity)
        assert result.artifacts[0].size_bytes == size


@FUZZ_SETTINGS
@given(decimal_strings)
def test_diagnostic_decimal_quantities_are_typed_or_rejected(value: str) -> None:
    document = {
        "diagnostic_version": "1",
        "code": "strategy.protocol",
        "phase": "strategy",
        "message": "invalid response",
        "context": {"sequence": value},
        "cause": None,
    }

    try:
        result = trading_engine_diagnostic_from_json(json.dumps(document))
    except ValueError:
        return
    assert isinstance(result.context.sequence, int)
    assert result.context.sequence > 0


@FUZZ_SETTINGS
@given(identifier_strings | malformed_identifiers)
def test_plan_identifiers_are_typed_or_rejected(value: str) -> None:
    document = json.loads(acquisition_plan_to_json(_plan()))
    assert isinstance(document, dict)
    document["plan_id"] = value

    try:
        result = acquisition_plan_from_json(json.dumps(document))
    except ValueError:
        return
    assert isinstance(result, AcquisitionPlan)
    assert result.plan_id == value


@FILE_FUZZ_SETTINGS
@given(timestamp_strings)
def test_cache_timestamps_return_entries_or_cache_errors(tmp_path: Path, value: str) -> None:
    cache = RawResponseCache(tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    cache.put(RawCacheEntry(b"{}", "application/json", now, "provider", "operation", {}))
    path = next(tmp_path.rglob("*.json"))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["retrieved_at"] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    try:
        result = cache.get(
            "provider",
            "operation",
            {},
            now=now,
            max_age=timedelta(days=36500),
            offline=True,
        )
    except CacheError:
        return
    assert isinstance(result, RawCacheEntry)
    assert result.retrieved_at.tzinfo is not None


@FILE_FUZZ_SETTINGS
@given(duplicate_field_documents)
def test_cache_rejects_duplicate_fields_as_corruption(tmp_path: Path, document: str) -> None:
    cache = RawResponseCache(tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    cache.put(RawCacheEntry(b"{}", "application/json", now, "provider", "operation", {}))
    next(tmp_path.rglob("*.json")).write_text(document, encoding="utf-8")

    with pytest.raises(CacheError, match="corrupt"):
        cache.get("provider", "operation", {}, now=now, max_age=None, offline=True)


def test_checkpoint_rejects_duplicate_fields_as_validation_error(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"format_version":1,"format_version":1}', encoding="utf-8")
    runner = AcquisitionRunner(
        {("provider", "operation"): lambda _request: synthetic.series(periods=1)},
        checkpoint,
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(DataValidationError, match=r"unreadable.*duplicate JSON field"):
        runner.run(_plan())


def test_scenario_reader_rejects_nested_duplicate_fields(tmp_path: Path) -> None:
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        '{"run_id":"run","execution":{"model":"first","model":"second"}}',
        encoding="utf-8",
    )
    schema_values: dict[str, Mapping[str, object]] = {}
    schemas = TradingEngineContractSchemas(
        "1",
        tmp_path,
        MappingProxyType(schema_values),
        "0" * 64,
        (),
    )

    with pytest.raises(TradingEngineContractError, match="invalid scenario JSON"):
        schemas.read_replay(scenario, tmp_path / "journal.jsonl")


def test_store_verification_rejects_duplicate_payload_fields(tmp_path: Path) -> None:
    path = tmp_path / "data.duckdb"
    DuckDBStore.create(path).close()
    connection = duckdb.connect(str(path))
    connection.execute(
        "INSERT INTO acquisition_snapshots VALUES ('bad', 'series', 'scope', 'hash', ?, 1)",
        ['{"frame":[],"frame":[{}]}'],
    )
    connection.close()

    findings = verify_store(path).findings

    payload_findings = [item for item in findings if item.code == "store.snapshot.payload"]
    assert payload_findings
    assert "duplicate JSON field" in payload_findings[0].message
