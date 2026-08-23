"""Schema-backed Trading Engine contract validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pandas as pd
from jsonschema import FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry, Resource

from persistra.integrations.trading_engine._journal_parsing import (
    freeze_payload,
    iter_json_records,
)

_SCHEMA_FILES = (
    "scenario.schema.json",
    "scenario-stream.schema.json",
    "journal.schema.json",
)
_EXECUTION_PRICE_COLUMNS = (
    "engine_sequence",
    "order_id",
    "instrument_id",
    "side",
    "reference_price",
    "spread_adjustment",
    "impact_adjustment",
    "final_price",
)


class TradingEngineContractError(ValueError):
    """A structural contract failure with artifact and schema-path context."""


@dataclass(frozen=True, slots=True)
class SchemaReplayResult:
    """Schema-verified replay envelope and model-specific execution-price evidence."""

    contract_version: str
    run_id: str
    execution_model: str
    scenario_sha256: str
    journal_records: int
    execution_prices: pd.DataFrame
    events: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_prices", self.execution_prices.copy(deep=True))
        object.__setattr__(
            self,
            "events",
            tuple(
                cast("Mapping[str, object]", freeze_payload(dict(event))) for event in self.events
            ),
        )


@dataclass(frozen=True, slots=True)
class TradingEngineContractSchemas:
    """One immutable, fingerprinted Trading Engine contract schema set."""

    version: str
    directory: Path
    schemas: Mapping[str, Mapping[str, object]]
    sha256: str
    execution_models: tuple[str, ...]

    @classmethod
    def load(cls, directory: str | Path) -> TradingEngineContractSchemas:
        """Load and verify the authoritative schemas in one version directory."""
        root = Path(directory).resolve()
        if not root.is_dir():
            raise ValueError("Trading Engine contract directory does not exist")
        if not root.name.startswith("v") or not root.name[1:].isdigit():
            raise ValueError("Trading Engine contract directory must be named vN")
        version = root.name[1:]
        loaded: dict[str, Mapping[str, object]] = {}
        canonical: list[bytes] = []
        resources: list[tuple[str, Resource[Any]]] = []
        for name in _SCHEMA_FILES:
            path = root / name
            if not path.is_file():
                raise ValueError(f"Trading Engine contract is missing {name}")
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TradingEngineContractError(f"invalid contract schema {name}") from error
            if not isinstance(value, dict):
                raise TradingEngineContractError(f"contract schema {name} must be an object")
            schema = cast("dict[str, object]", value)
            identifier = schema.get("$id")
            if not isinstance(identifier, str) or f"/contracts/v{version}/" not in identifier:
                raise TradingEngineContractError(
                    f"contract schema {name} does not declare version {version}"
                )
            validator = validator_for(schema)
            try:
                validator.check_schema(schema)
            except SchemaError as error:
                raise TradingEngineContractError(f"invalid contract schema {name}") from error
            loaded[name] = MappingProxyType(schema)
            resources.append((identifier, Resource.from_contents(schema)))
            canonical.append(
                name.encode("utf-8")
                + b"\0"
                + json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
        registry = Registry[Any]().with_resources(resources)
        for name, schema in loaded.items():
            validator_for(schema)(schema, registry=registry, format_checker=FormatChecker())
            _check_references(schema, registry, name=name)
        digest = hashlib.sha256(b"\0".join(canonical)).hexdigest()
        models = tuple(sorted(_execution_models(loaded["scenario.schema.json"])))
        if not models:
            raise TradingEngineContractError("scenario schema declares no execution models")
        return cls(
            version=version,
            directory=root,
            schemas=MappingProxyType(loaded),
            sha256=digest,
            execution_models=models,
        )

    def validate_scenario(self, value: object) -> None:
        """Validate one batch scenario structurally."""
        self._validate("scenario.schema.json", value, artifact="scenario")

    def validate_stream_record(self, value: object, *, line_number: int) -> None:
        """Validate one scenario-stream record structurally."""
        self._validate(
            "scenario-stream.schema.json",
            value,
            artifact=f"scenario stream line {line_number}",
        )

    def validate_journal_record(self, value: object, *, line_number: int) -> None:
        """Validate one journal record structurally."""
        self._validate("journal.schema.json", value, artifact=f"journal line {line_number}")

    def validate_journal(self, path: str | Path) -> int:
        """Stream and validate a journal, returning its record count."""
        count = 0
        for line_number, record in iter_json_records(path):
            self.validate_journal_record(record, line_number=line_number)
            count += 1
        return count

    def read_replay(
        self, scenario_path: str | Path, journal_path: str | Path
    ) -> SchemaReplayResult:
        """Validate and reconcile a schema-versioned replay without older semantic adapters."""
        scenario_file = Path(scenario_path)
        try:
            scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TradingEngineContractError("invalid scenario JSON") from error
        self.validate_scenario(scenario)
        if not isinstance(scenario, dict):
            raise TradingEngineContractError("scenario must be an object")
        scenario_item = cast("dict[str, object]", scenario)
        run_id = scenario_item.get("run_id")
        execution = scenario_item.get("execution")
        if not isinstance(run_id, str) or not isinstance(execution, dict):
            raise TradingEngineContractError("scenario omits replay identity")
        model = cast("dict[str, object]", execution).get("model")
        if not isinstance(model, str) or model not in self.execution_models:
            raise TradingEngineContractError("scenario uses an unsupported execution model")
        scenario_digest = hashlib.sha256(scenario_file.read_bytes()).hexdigest()
        records: list[Mapping[str, object]] = []
        price_rows: list[dict[str, object]] = []
        expected_sequence = 1
        for line_number, record in iter_json_records(journal_path):
            self.validate_journal_record(record, line_number=line_number)
            if record.get("contract_version") != self.version:
                raise TradingEngineContractError(
                    f"journal line {line_number} contract version differs from schemas"
                )
            if record.get("run_id") != run_id:
                raise TradingEngineContractError(
                    f"journal line {line_number} run_id differs from scenario"
                )
            sequence = record.get("engine_sequence")
            if sequence != str(expected_sequence):
                raise TradingEngineContractError(
                    f"journal line {line_number} breaks engine sequence"
                )
            expected_sequence += 1
            if record.get("event_type") == "execution_price_selected":
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    raise TradingEngineContractError(
                        f"journal line {line_number} execution price payload is invalid"
                    )
                price_rows.append(
                    {
                        "engine_sequence": sequence,
                        **cast("dict[str, object]", payload),
                    }
                )
            records.append(record)
        if not records:
            raise TradingEngineContractError("journal must not be empty")
        self._reconcile_terminal_events(
            records,
            model=model,
            scenario_sha256=scenario_digest,
        )
        return SchemaReplayResult(
            contract_version=self.version,
            run_id=run_id,
            execution_model=model,
            scenario_sha256=scenario_digest,
            journal_records=len(records),
            execution_prices=pd.DataFrame(price_rows).reindex(columns=_EXECUTION_PRICE_COLUMNS),
            events=tuple(records),
        )

    def _reconcile_terminal_events(
        self,
        records: list[Mapping[str, object]],
        *,
        model: str,
        scenario_sha256: str,
    ) -> None:
        first = records[0]
        last = records[-1]
        if first.get("event_type") != "run_started":
            raise TradingEngineContractError("journal must begin with run_started")
        if last.get("event_type") != "run_completed":
            raise TradingEngineContractError("journal must end with run_completed")
        for label, record in (("run_started", first), ("run_completed", last)):
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                raise TradingEngineContractError(f"{label} payload is invalid")
            payload_item = cast("Mapping[object, object]", payload)
            if payload_item.get("execution_model") != model:
                raise TradingEngineContractError(f"{label} execution model differs from scenario")
            if payload_item.get("scenario_sha256") != scenario_sha256:
                raise TradingEngineContractError(f"{label} scenario hash differs")

    def _validate(self, name: str, value: object, *, artifact: str) -> None:
        schema = self.schemas[name]
        resources = [
            (cast("str", item["$id"]), Resource.from_contents(item))
            for item in self.schemas.values()
        ]
        registry = Registry[Any]().with_resources(resources)
        validator = validator_for(schema)(schema, registry=registry, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(cast("Any", value)),
            key=lambda error: (
                -len(error.absolute_path),
                [str(item) for item in error.absolute_path],
            ),
        )
        if not errors:
            return
        error = errors[0]
        path = "/".join(str(item) for item in error.absolute_path) or "<root>"
        raise TradingEngineContractError(
            f"{artifact} violates contract v{self.version} at {path}: "
            f"failed {error.validator} validation"
        ) from error


def _check_references(schema: Mapping[str, object], registry: Registry[Any], *, name: str) -> None:
    identifier = cast("str", schema["$id"])
    resolver = registry.resolver(identifier)
    for reference in _string_values_for_key(schema, "$ref"):
        try:
            resolver.lookup(reference)
        except Exception as error:
            raise TradingEngineContractError(
                f"contract schema {name} has unresolved reference {reference!r}"
            ) from error


def _string_values_for_key(value: object, key: str) -> set[str]:
    results: set[str] = set()
    if isinstance(value, Mapping):
        item = cast("Mapping[object, object]", value)
        candidate = item.get(key)
        if isinstance(candidate, str):
            results.add(candidate)
        elif key == "model" and isinstance(candidate, Mapping):
            model_schema = cast("Mapping[object, object]", candidate)
            enum = model_schema.get("enum")
            if isinstance(enum, list):
                results.update(
                    entry for entry in cast("list[object]", enum) if isinstance(entry, str)
                )
            const = model_schema.get("const")
            if isinstance(const, str):
                results.add(const)
        for child in item.values():
            results.update(_string_values_for_key(child, key))
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            results.update(_string_values_for_key(child, key))
    return results


def _execution_models(value: object) -> set[str]:
    results: set[str] = set()
    if isinstance(value, Mapping):
        item = cast("Mapping[object, object]", value)
        execution = item.get("execution")
        if isinstance(execution, Mapping):
            results.update(_models_in_execution(cast("Mapping[object, object]", execution)))
        for child in item.values():
            results.update(_execution_models(child))
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            results.update(_execution_models(child))
    return results


def _models_in_execution(value: Mapping[object, object]) -> set[str]:
    results: set[str] = set()
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        model = cast("Mapping[object, object]", properties).get("model")
        if isinstance(model, Mapping):
            model_schema = cast("Mapping[object, object]", model)
            const = model_schema.get("const")
            if isinstance(const, str):
                results.add(const)
            enum = model_schema.get("enum")
            if isinstance(enum, list):
                results.update(
                    entry for entry in cast("list[object]", enum) if isinstance(entry, str)
                )
    for keyword in ("oneOf", "anyOf", "allOf"):
        branches = value.get(keyword)
        if isinstance(branches, list):
            for branch in cast("list[object]", branches):
                if isinstance(branch, Mapping):
                    results.update(_models_in_execution(cast("Mapping[object, object]", branch)))
    return results
