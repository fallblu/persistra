"""Structured Trading Engine CLI success and failure artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.integrations.trading_engine._scalars import exact_fields, identifier, quantity_value
from persistra.integrations.trading_engine.model import (
    StrategyResponseRejection,
    TradingEngineDiagnostic,
    TradingEngineProcessError,
)

TRADING_ENGINE_RESULT_VERSION: Final = "1"
_HASH_FIELDS = {"scenario_sha256", "journal_sha256", "strategy_transcript_sha256"}
_COUNT_FIELDS = {
    "instruments",
    "schedule_batches",
    "slices",
    "audits",
    "orders",
    "active_orders",
    "filled_orders",
    "rejected_orders",
}


@dataclass(frozen=True, slots=True)
class TradingEngineSuccessHashes:
    """Content identities reported by one successful CLI operation."""

    scenario_sha256: str
    journal_sha256: str | None
    strategy_transcript_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_sha256", _sha256_text(self.scenario_sha256))
        for name in ("journal_sha256", "strategy_transcript_sha256"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _sha256_text(value))

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_sha256": self.scenario_sha256,
            "journal_sha256": self.journal_sha256,
            "strategy_transcript_sha256": self.strategy_transcript_sha256,
        }


@dataclass(frozen=True, slots=True)
class TradingEngineSuccessCounts:
    """Bounded nonnegative replay counts reported by Trading Engine."""

    instruments: int
    schedule_batches: int
    slices: int
    audits: int
    orders: int
    active_orders: int
    filled_orders: int
    rejected_orders: int

    def __post_init__(self) -> None:
        for name in _COUNT_FIELDS:
            object.__setattr__(self, name, quantity_value(getattr(self, name), name=name))
        if self.active_orders + self.filled_orders + self.rejected_orders > self.orders:
            raise ValueError("success order status counts exceed total orders")

    def to_dict(self) -> dict[str, int]:
        return {name: cast("int", getattr(self, name)) for name in sorted(_COUNT_FIELDS)}


@dataclass(frozen=True, slots=True)
class TradingEngineSuccessSummary:
    """Versioned machine-readable validation or replay success."""

    operation: Literal["validate", "replay"]
    run_id: str
    hashes: TradingEngineSuccessHashes
    counts: TradingEngineSuccessCounts
    valuation: Mapping[str, Any]
    artifacts: Mapping[str, str | None]
    version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        if self.version != TRADING_ENGINE_RESULT_VERSION:
            raise ValueError(f"unsupported Trading Engine result version: {self.version!r}")
        if self.operation not in {"validate", "replay"}:
            raise ValueError(f"unsupported Trading Engine result operation: {self.operation!r}")
        object.__setattr__(self, "run_id", identifier(self.run_id, name="result run_id"))
        object.__setattr__(
            self, "valuation", freeze_portable_mapping(self.valuation, name="result valuation")
        )
        artifacts = _optional_string_mapping(
            self.artifacts,
            fields={"journal", "strategy_transcript"},
            name="result artifacts",
        )
        object.__setattr__(
            self, "artifacts", freeze_portable_mapping(artifacts, name="result artifacts")
        )
        if self.operation == "validate":
            if any(
                (
                    self.hashes.journal_sha256,
                    self.hashes.strategy_transcript_sha256,
                    artifacts["journal"],
                    artifacts["strategy_transcript"],
                )
            ):
                raise ValueError("validation success must not declare replay artifacts")
        elif self.hashes.journal_sha256 is None or artifacts["journal"] is None:
            raise ValueError("replay success must declare its journal")

    def to_dict(self) -> dict[str, object]:
        return {
            "result_version": self.version,
            "status": "success",
            "operation": self.operation,
            "run_id": self.run_id,
            "hashes": self.hashes.to_dict(),
            "counts": self.counts.to_dict(),
            "valuation": thaw_portable_mapping(self.valuation),
            "artifacts": thaw_portable_mapping(self.artifacts),
        }


@dataclass(frozen=True, slots=True)
class StructuredEngineFailureStatus:
    """Safe manifest-ready status derived from a typed process failure."""

    code: str
    phase: str
    message: str
    context: Mapping[str, Any]
    cause: Mapping[str, Any] | None
    artifacts: Mapping[str, Any]
    rejection: Mapping[str, Any] | None = None
    diagnostic_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        if self.diagnostic_version != "1":
            raise ValueError(
                f"unsupported Trading Engine diagnostic version: {self.diagnostic_version!r}"
            )
        object.__setattr__(self, "code", identifier(self.code, name="diagnostic code"))
        if "." not in self.code:
            raise ValueError("diagnostic code must be namespaced")
        object.__setattr__(self, "phase", identifier(self.phase, name="diagnostic phase"))
        raw_message = cast("object", self.message)
        if not isinstance(raw_message, str) or not raw_message:
            raise ValueError("diagnostic message must be a nonempty string")
        object.__setattr__(
            self,
            "context",
            freeze_portable_mapping(self.context, name="failure context"),
        )
        if self.cause is not None:
            object.__setattr__(
                self, "cause", freeze_portable_mapping(self.cause, name="failure cause")
            )
        object.__setattr__(
            self,
            "artifacts",
            freeze_portable_mapping(self.artifacts, name="failure artifacts"),
        )
        if self.rejection is not None:
            object.__setattr__(
                self, "rejection", freeze_portable_mapping(self.rejection, name="failure rejection")
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "state": "failed",
            "diagnostic_version": self.diagnostic_version,
            "code": self.code,
            "phase": self.phase,
            "message": self.message,
            "context": thaw_portable_mapping(self.context),
            "cause": None if self.cause is None else thaw_portable_mapping(self.cause),
            "artifacts": thaw_portable_mapping(self.artifacts),
            "rejection": None if self.rejection is None else thaw_portable_mapping(self.rejection),
        }


def trading_engine_success_from_json(document: str) -> TradingEngineSuccessSummary:
    """Parse a strict CLI result v1 success document without matching prose."""
    if not isinstance(cast("object", document), str):
        raise TypeError("Trading Engine success document must be a string")
    try:
        raw = json.loads(document, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError(f"invalid Trading Engine success JSON: {error}") from error
    item = exact_fields(
        raw,
        {
            "result_version",
            "status",
            "operation",
            "run_id",
            "hashes",
            "counts",
            "valuation",
            "artifacts",
        },
        name="Trading Engine success",
    )
    if item["status"] != "success":
        raise ValueError("Trading Engine result status must be success")
    hashes = exact_fields(item["hashes"], _HASH_FIELDS, name="success hashes")
    counts = exact_fields(item["counts"], _COUNT_FIELDS, name="success counts")
    valuation = _mapping(item["valuation"], name="success valuation")
    artifacts = _mapping(item["artifacts"], name="success artifacts")
    return TradingEngineSuccessSummary(
        operation=_operation(item["operation"]),
        run_id=_string(item["run_id"], name="result run_id"),
        hashes=TradingEngineSuccessHashes(
            _string(hashes["scenario_sha256"], name="scenario_sha256"),
            _optional_string(hashes["journal_sha256"], name="journal_sha256"),
            _optional_string(
                hashes["strategy_transcript_sha256"], name="strategy_transcript_sha256"
            ),
        ),
        counts=TradingEngineSuccessCounts(**counts),
        valuation=valuation,
        artifacts=cast("Mapping[str, str | None]", artifacts),
        version=_result_version(item["result_version"]),
    )


def verify_trading_engine_success(
    summary: TradingEngineSuccessSummary,
    scenario_path: str | Path,
    *,
    journal_path: str | Path | None = None,
    strategy_transcript_path: str | Path | None = None,
) -> None:
    """Cross-check one success summary against immutable scenario and output artifacts."""
    scenario = Path(scenario_path).expanduser().resolve(strict=True)
    if _sha256_file(scenario) != summary.hashes.scenario_sha256:
        raise ValueError("success scenario hash differs from retained artifact")
    identity = _scenario_identity(scenario)
    expected = {
        "run_id": summary.run_id,
        "instruments": summary.counts.instruments,
        "schedule_batches": summary.counts.schedule_batches,
        "slices": summary.counts.slices,
    }
    for name, value in expected.items():
        if identity[name] != value:
            raise ValueError(f"success {name} differs from retained scenario")
    if summary.operation == "validate":
        if journal_path is not None or strategy_transcript_path is not None:
            raise ValueError("validation success cannot verify replay artifacts")
        return
    if journal_path is None:
        raise ValueError("replay success requires a retained journal")
    journal = Path(journal_path).expanduser().resolve(strict=True)
    if _sha256_file(journal) != summary.hashes.journal_sha256:
        raise ValueError("success journal hash differs from retained artifact")
    records = _json_lines(journal)
    if len(records) != summary.counts.audits:
        raise ValueError("success audit count differs from retained journal")
    journal_records = [_mapping(item, name="journal record") for item in records]
    completed = [item for item in journal_records if item.get("event_type") == "run_completed"]
    if len(completed) != 1:
        raise ValueError("retained journal does not have exactly one completion")
    payload = _mapping(completed[0].get("payload"), name="run completion payload")
    if not _contains_portable(payload.get("valuation"), summary.valuation):
        raise ValueError("success valuation differs from retained journal")
    order_counts = _mapping(payload.get("order_counts"), name="run completion order counts")
    for result_name, journal_name in (
        ("orders", "total"),
        ("active_orders", "active"),
        ("filled_orders", "filled"),
        ("rejected_orders", "rejected"),
    ):
        if getattr(summary.counts, result_name) != order_counts.get(journal_name):
            raise ValueError(f"success {result_name} differs from retained journal")
    _verify_optional_artifact(
        strategy_transcript_path,
        expected_hash=summary.hashes.strategy_transcript_sha256,
        name="strategy transcript",
    )


def structured_engine_failure(error: object) -> StructuredEngineFailureStatus:
    """Convert a process exception into bounded status without retaining stdout or stderr."""
    if not isinstance(error, TradingEngineProcessError):
        raise TypeError("error must be TradingEngineProcessError")
    diagnostic = error.diagnostic
    if diagnostic is None:
        raise ValueError("process error does not contain a structured diagnostic")
    artifacts = {
        "journal": _artifact_status(error.journal_path),
        "strategy_transcript": _artifact_status(error.strategy_transcript_path),
    }
    rejection = (
        None
        if error.strategy_rejection is None
        else _rejection_status(error.strategy_rejection, error.strategy_transcript_path)
    )
    return StructuredEngineFailureStatus(
        code=diagnostic.code,
        phase=diagnostic.phase,
        message=diagnostic.message,
        context=_diagnostic_context(diagnostic),
        cause=_diagnostic_cause(diagnostic),
        artifacts=artifacts,
        rejection=rejection,
        diagnostic_version=_result_version(diagnostic.version),
    )


def bind_engine_status_manifest(
    manifest: Mapping[str, Any],
    status: TradingEngineSuccessSummary | StructuredEngineFailureStatus,
) -> Mapping[str, Any]:
    """Attach one structured success or failure status to a replay manifest."""
    document = thaw_portable_mapping(freeze_portable_mapping(manifest, name="replay manifest"))
    if "status" in document:
        raise ValueError("replay manifest already contains status")
    document["status"] = status.to_dict()
    return freeze_portable_mapping(document, name="replay manifest")


def _diagnostic_context(diagnostic: TradingEngineDiagnostic) -> dict[str, object]:
    context = diagnostic.context
    return {
        name: value
        for name, value in {
            "json_path": context.json_path,
            "line": context.line,
            "sequence": context.sequence,
            "event_id": context.event_id,
            "order_id": context.order_id,
            "causation_ids": list(context.causation_ids),
        }.items()
        if value not in (None, [])
    }


def _diagnostic_cause(diagnostic: TradingEngineDiagnostic) -> dict[str, object] | None:
    cause = diagnostic.cause
    if cause is None:
        return None
    return {
        name: value
        for name, value in {
            "kind": cause.kind,
            "message": cause.message,
            "operation": cause.operation,
            "target": cause.target,
        }.items()
        if value is not None
    }


def _rejection_status(rejection: StrategyResponseRejection, path: Path | None) -> dict[str, object]:
    evidence = rejection.evidence
    return {
        "version": rejection.version,
        "transcript_sequence": rejection.transcript_sequence,
        "expected_strategy_sequence": rejection.expected_strategy_sequence,
        "prefix_sha256": hashlib.sha256(evidence.prefix).hexdigest(),
        "prefix_bytes": len(evidence.prefix),
        "observed_bytes": evidence.observed_bytes,
        "truncated": evidence.truncated,
        "transcript_sha256": None if path is None or not path.is_file() else _sha256_file(path),
    }


def _artifact_status(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    return {
        "path": str(resolved),
        "exists": resolved.is_file(),
        "sha256": _sha256_file(resolved) if resolved.is_file() else None,
    }


def _scenario_identity(path: Path) -> dict[str, object]:
    if path.suffix == ".jsonl":
        records = _json_lines(path)
        header = _mapping(
            _mapping(records[0], name="scenario header").get("payload"),
            name="scenario header payload",
        )
        scenario_records = [_mapping(item, name="scenario record") for item in records]
        slices = [item for item in scenario_records if item.get("record_type") == "market_slice"]
        schedule = sum(
            bool(_mapping(item.get("payload"), name="market slice payload").get("intents"))
            for item in slices
        )
        return {
            "run_id": header.get("run_id"),
            "instruments": len(cast("list[object]", header.get("instruments"))),
            "schedule_batches": schedule,
            "slices": len(slices),
        }
    document = _mapping(json.loads(path.read_text(encoding="utf-8")), name="scenario")
    return {
        "run_id": document.get("run_id"),
        "instruments": len(cast("list[object]", document.get("instruments"))),
        "schedule_batches": len(cast("list[object]", document.get("schedule"))),
        "slices": len(cast("list[object]", document.get("slices"))),
    }


def _verify_optional_artifact(
    path: str | Path | None, *, expected_hash: str | None, name: str
) -> None:
    if expected_hash is None:
        if path is not None:
            raise ValueError(f"success does not declare a {name}")
        return
    if path is None or _sha256_file(Path(path).expanduser().resolve(strict=True)) != expected_hash:
        raise ValueError(f"success {name} hash differs from retained artifact")


def _json_lines(path: Path) -> list[object]:
    try:
        return [
            json.loads(line, object_pairs_hook=_unique_object)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON Lines artifact: {path}") from error


def _optional_string_mapping(
    value: Mapping[str, str | None], *, fields: set[str], name: str
) -> dict[str, str | None]:
    item = exact_fields(value, fields, name=name)
    return {field: _optional_string(item[field], name=field) for field in fields}


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return dict(cast("Mapping[str, Any]", value))


def _contains_portable(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        actual_mapping = cast("Mapping[object, object]", actual)
        expected_mapping = cast("Mapping[object, object]", expected)
        return all(
            key in actual_mapping and _contains_portable(actual_mapping[key], value)
            for key, value in expected_mapping.items()
        )
    if isinstance(expected, tuple | list):
        expected_sequence = cast("tuple[object, ...] | list[object]", expected)
        if not isinstance(actual, tuple | list):
            return False
        actual_sequence = cast("tuple[object, ...] | list[object]", actual)
        if len(actual_sequence) != len(expected_sequence):
            return False
        return all(
            _contains_portable(actual_item, expected_item)
            for actual_item, expected_item in zip(actual_sequence, expected_sequence, strict=True)
        )
    return actual == expected


def _operation(value: object) -> Literal["validate", "replay"]:
    if value not in {"validate", "replay"}:
        raise ValueError(f"unsupported Trading Engine result operation: {value!r}")
    return cast("Literal['validate', 'replay']", value)


def _result_version(value: object) -> Literal["1"]:
    if value != TRADING_ENGINE_RESULT_VERSION:
        raise ValueError(f"unsupported Trading Engine result version: {value!r}")
    return "1"


def _string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_string(value: object, *, name: str) -> str | None:
    return None if value is None else _string(value, name=name)


def _sha256_text(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("content hash must be lowercase SHA-256")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate Trading Engine result field: {key!r}")
        result[key] = value
    return result
