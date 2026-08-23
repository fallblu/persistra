"""Offline verification and deterministic comparison of replay bundles."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

import pandas as pd

from persistra.integrations.trading_engine._journal_parsing import freeze_payload
from persistra.integrations.trading_engine.journal import read_journal
from persistra.integrations.trading_engine.scenario import (
    read_scenario,
    read_scenario_stream,
)
from persistra.integrations.trading_engine.strategy import (
    StrategyIdentity,
    StrategyTranscript,
    read_strategy_transcript,
)

if TYPE_CHECKING:
    from persistra.integrations.trading_engine.model import ExecutionReplayResult

_HASH = re.compile(r"[0-9a-f]{64}")
_INPUT_LAYERS = (
    "scenario",
    "contract",
    "capabilities",
    "strategy_identity",
    "strategy_artifacts",
)
_OUTPUT_FRAMES = ("orders", "fills", "valuations", "metrics")


class ReplayBundleError(ValueError):
    """A replay bundle is unsafe, incomplete, tampered with, or inconsistent."""


@dataclass(frozen=True, slots=True)
class ReplayBundleVerification:
    """Fully checked offline replay bundle and its parsed execution artifacts."""

    manifest_path: Path
    manifest_sha256: str
    run_id: str
    contract_version: str
    execution_model: str
    engine_version: str
    scenario_path: Path
    journal_path: Path
    strategy_transcript_path: Path | None
    artifact_sha256: Mapping[str, str]
    capabilities: Mapping[str, object]
    strategy_identity: StrategyIdentity | None
    replay: ExecutionReplayResult
    transcript: StrategyTranscript | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))
        object.__setattr__(self, "scenario_path", Path(self.scenario_path))
        object.__setattr__(self, "journal_path", Path(self.journal_path))
        if self.strategy_transcript_path is not None:
            object.__setattr__(
                self, "strategy_transcript_path", Path(self.strategy_transcript_path)
            )
        object.__setattr__(
            self,
            "artifact_sha256",
            MappingProxyType(dict(self.artifact_sha256)),
        )
        object.__setattr__(
            self,
            "capabilities",
            cast(
                "Mapping[str, object]",
                freeze_payload(dict(self.capabilities)),
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a stable machine-readable verification summary."""
        return {
            "status": "verified",
            "manifest": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "run_id": self.run_id,
            "contract_version": self.contract_version,
            "execution_model": self.execution_model,
            "engine_version": self.engine_version,
            "artifacts": dict(self.artifact_sha256),
            "strategy": (
                None
                if self.strategy_identity is None
                else {
                    "name": self.strategy_identity.name,
                    "version": self.strategy_identity.version,
                }
            ),
            "journal_records": len(self.replay.events),
            "completed": True,
        }


@dataclass(frozen=True, slots=True)
class ReplayBundleComparison:
    """Layered comparison of two independently verified replay bundles."""

    identical: bool
    input_changes: tuple[str, ...]
    output_changes: tuple[str, ...]
    first_divergence: str | None
    aggregate_differences: Mapping[str, Mapping[str, int | float]]

    def __post_init__(self) -> None:
        frozen = {
            layer: MappingProxyType(dict(values))
            for layer, values in self.aggregate_differences.items()
        }
        object.__setattr__(self, "aggregate_differences", MappingProxyType(frozen))

    def to_dict(self) -> dict[str, object]:
        """Return a stable machine-readable comparison summary."""
        return {
            "status": "identical" if self.identical else "different",
            "identical": self.identical,
            "input_changes": list(self.input_changes),
            "output_changes": list(self.output_changes),
            "first_divergence": self.first_divergence,
            "aggregate_differences": {
                layer: dict(values) for layer, values in self.aggregate_differences.items()
            },
        }


def verify_replay_bundle(path: str | Path) -> ReplayBundleVerification:
    """Verify one existing bundle without invoking Trading Engine or a strategy."""
    manifest_path = _manifest_path(path)
    root = manifest_path.parent.resolve()
    document = _json_object(manifest_path, label="bundle manifest")
    run_id = _string(document.get("run_id"), name="manifest run_id")
    contract = _object(document.get("contract"), name="manifest contract")
    contract_version = _string(contract.get("version"), name="contract version")
    execution = _object(document.get("execution"), name="manifest execution")
    execution_model = _string(execution.get("model"), name="execution model")
    engine = _object(document.get("engine"), name="manifest engine")
    engine_version = _string(engine.get("version"), name="engine version")
    capabilities = _object(engine.get("capabilities"), name="engine capabilities")
    engine_executable = _object(engine.get("executable"), name="engine executable")
    _digest(engine_executable.get("sha256"), name="engine executable sha256")
    artifacts = _object(document.get("artifacts"), name="manifest artifacts")

    resolved: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for name, value in artifacts.items():
        descriptor = _object(value, name=f"artifact {name}")
        artifact_path, digest = _verify_artifact(
            root,
            descriptor,
            name=f"artifact {name}",
        )
        resolved[name] = artifact_path
        digests[name] = digest
    if set(resolved) not in (
        {"scenario", "journal"},
        {"scenario", "journal", "strategy_transcript"},
    ):
        raise ReplayBundleError(
            "manifest artifacts must declare scenario and journal only, "
            "with an optional strategy transcript"
        )

    scenario_format = _string(
        _object(artifacts["scenario"], name="scenario artifact").get("format"),
        name="scenario format",
    )
    if scenario_format not in {"json", "jsonl"}:
        raise ReplayBundleError("scenario artifact format is unsupported")
    _validate_capabilities(
        capabilities,
        engine_version=engine_version,
        contract_version=contract_version,
        execution_model=execution_model,
        scenario_format=scenario_format,
    )
    try:
        scenario = (
            read_scenario(resolved["scenario"])
            if scenario_format == "json"
            else read_scenario_stream(resolved["scenario"])
        )
    except (OSError, ValueError) as error:
        raise ReplayBundleError(f"scenario reconciliation failed: {error}") from error
    if scenario.run_id != run_id:
        raise ReplayBundleError("scenario run_id differs from manifest")
    if scenario.contract_version != contract_version:
        raise ReplayBundleError("scenario contract version differs from manifest")
    if scenario.execution.model != execution_model:
        raise ReplayBundleError("scenario execution model differs from manifest")
    metadata = _object(document.get("scenario_metadata"), name="scenario metadata")
    if scenario.metadata != metadata:
        raise ReplayBundleError("scenario metadata differs from manifest")

    transcript = None
    strategy_identity = None
    transcript_path = resolved.get("strategy_transcript")
    strategy_document = document.get("strategy")
    if transcript_path is None and strategy_document is not None:
        raise ReplayBundleError("manifest strategy requires a strategy transcript")
    if transcript_path is not None:
        strategy = _object(strategy_document, name="manifest strategy")
        strategy_executable = _object(strategy.get("executable"), name="strategy executable")
        _digest(strategy_executable.get("sha256"), name="strategy executable sha256")
        protocol = _string(strategy.get("protocol_version"), name="strategy protocol")
        if protocol not in _strings(
            capabilities.get("strategy_protocol_versions"),
            name="strategy protocol capabilities",
        ):
            raise ReplayBundleError("strategy protocol is not advertised by engine capabilities")
        identity = _object(strategy.get("identity"), name="strategy identity")
        strategy_identity = StrategyIdentity(
            _string(identity.get("name"), name="strategy name"),
            _optional_string(identity.get("version"), name="strategy version"),
        )
        for index, artifact in enumerate(
            _sequence(strategy.get("artifacts"), name="strategy artifacts")
        ):
            artifact_path, digest = _verify_artifact(
                root,
                _object(artifact, name=f"strategy artifact {index}"),
                name=f"strategy artifact {index}",
            )
            key = f"strategy_artifact:{index}:{artifact_path.name}"
            resolved[key] = artifact_path
            digests[key] = digest
        try:
            transcript = read_strategy_transcript(
                transcript_path,
                scenario_sha256=digests["scenario"],
                run_id=run_id,
            )
        except (OSError, ValueError) as error:
            raise ReplayBundleError(
                f"strategy transcript reconciliation failed: {error}"
            ) from error
        if transcript.identity != strategy_identity:
            raise ReplayBundleError("strategy transcript identity differs from manifest")
        initialization = transcript.initialization
        if initialization.engine_version != engine_version:
            raise ReplayBundleError("strategy transcript engine version differs from manifest")
        if initialization.scenario_contract_version != contract_version:
            raise ReplayBundleError("strategy transcript contract version differs from manifest")
        if initialization.execution.model != execution_model:
            raise ReplayBundleError("strategy transcript execution model differs from manifest")

    try:
        replay = read_journal(
            resolved["journal"],
            scenario=resolved["scenario"],
            scenario_sha256=digests["scenario"],
            strategy_transcript=transcript,
        )
    except (OSError, ValueError) as error:
        raise ReplayBundleError(f"journal reconciliation failed: {error}") from error
    for name, artifact_path in resolved.items():
        if _sha256(artifact_path) != digests[name]:
            raise ReplayBundleError(f"artifact {name} changed during verification")

    return ReplayBundleVerification(
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_path),
        run_id=run_id,
        contract_version=contract_version,
        execution_model=execution_model,
        engine_version=engine_version,
        scenario_path=resolved["scenario"],
        journal_path=resolved["journal"],
        strategy_transcript_path=transcript_path,
        artifact_sha256=digests,
        capabilities=capabilities,
        strategy_identity=strategy_identity,
        replay=replay,
        transcript=transcript,
    )


def compare_replay_bundles(
    left: str | Path | ReplayBundleVerification,
    right: str | Path | ReplayBundleVerification,
) -> ReplayBundleComparison:
    """Verify as needed and compare two bundles at stable execution layers."""
    left_bundle = left if isinstance(left, ReplayBundleVerification) else verify_replay_bundle(left)
    right_bundle = (
        right if isinstance(right, ReplayBundleVerification) else verify_replay_bundle(right)
    )
    input_values: dict[str, tuple[object, object]] = {
        "scenario": (
            left_bundle.artifact_sha256["scenario"],
            right_bundle.artifact_sha256["scenario"],
        ),
        "contract": (left_bundle.contract_version, right_bundle.contract_version),
        "capabilities": (left_bundle.capabilities, right_bundle.capabilities),
        "strategy_identity": (
            left_bundle.strategy_identity,
            right_bundle.strategy_identity,
        ),
        "strategy_artifacts": (
            _strategy_hashes(left_bundle),
            _strategy_hashes(right_bundle),
        ),
    }
    input_changes = tuple(
        layer for layer in _INPUT_LAYERS if input_values[layer][0] != input_values[layer][1]
    )
    output_changes: list[str] = []
    aggregate: dict[str, Mapping[str, int | float]] = {}
    first_divergence = None

    left_decisions = () if left_bundle.transcript is None else left_bundle.transcript.decisions
    right_decisions = () if right_bundle.transcript is None else right_bundle.transcript.decisions
    if left_decisions != right_decisions:
        output_changes.append("decisions")
        aggregate["decisions"] = {
            "left_count": len(left_decisions),
            "right_count": len(right_decisions),
        }
        first_divergence = _first_sequence_divergence("decisions", left_decisions, right_decisions)

    for layer in _OUTPUT_FRAMES:
        if layer == "valuations" and _fee_value(left_bundle.replay) != _fee_value(
            right_bundle.replay
        ):
            output_changes.append("fees")
            aggregate["fees"] = _fee_aggregate(left_bundle.replay, right_bundle.replay)
            if first_divergence is None:
                first_divergence = "fees"
        left_frame = cast("pd.DataFrame", getattr(left_bundle.replay, layer))
        right_frame = cast("pd.DataFrame", getattr(right_bundle.replay, layer))
        if left_frame.equals(right_frame):
            continue
        output_changes.append(layer)
        aggregate[layer] = _frame_aggregate(left_frame, right_frame)
        if first_divergence is None:
            first_divergence = _frame_first_divergence(layer, left_frame, right_frame)

    if _completion_value(left_bundle.replay) != _completion_value(right_bundle.replay):
        output_changes.append("completion")
        aggregate["completion"] = {"left_count": 1, "right_count": 1}
        if first_divergence is None:
            first_divergence = "completion"
    if first_divergence is None and input_changes:
        first_divergence = f"input:{input_changes[0]}"
    changes = tuple(output_changes)
    return ReplayBundleComparison(
        identical=not input_changes and not changes,
        input_changes=input_changes,
        output_changes=changes,
        first_divergence=first_divergence,
        aggregate_differences=aggregate,
    )


def _manifest_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_dir():
        manifests = sorted(path.glob("*.manifest.json"))
        if len(manifests) != 1:
            raise ReplayBundleError("bundle directory must contain exactly one *.manifest.json")
        path = manifests[0]
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ReplayBundleError("bundle manifest does not exist") from error
    if not resolved.is_file():
        raise ReplayBundleError("bundle manifest is not a regular file")
    return resolved


def _verify_artifact(
    root: Path, descriptor: Mapping[str, object], *, name: str
) -> tuple[Path, str]:
    relative = _string(descriptor.get("path"), name=f"{name} path")
    supplied = Path(relative)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise ReplayBundleError(f"{name} path is unsafe")
    try:
        path = (root / supplied).resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise ReplayBundleError(f"{name} path is missing or escapes the bundle") from error
    if not path.is_file():
        raise ReplayBundleError(f"{name} is not a regular file")
    expected = _digest(descriptor.get("sha256"), name=f"{name} sha256")
    actual = _sha256(path)
    if actual != expected:
        raise ReplayBundleError(f"{name} checksum differs")
    return path, actual


def _validate_capabilities(
    capabilities: Mapping[str, object],
    *,
    engine_version: str,
    contract_version: str,
    execution_model: str,
    scenario_format: str,
) -> None:
    if (
        _string(capabilities.get("engine_version"), name="capability engine version")
        != engine_version
    ):
        raise ReplayBundleError("engine capability version differs from manifest")
    claims = (
        ("scenario_contract_versions", contract_version),
        ("journal_contract_versions", contract_version),
        ("scenario_formats", scenario_format),
        ("journal_formats", "jsonl"),
        ("execution_models", execution_model),
    )
    for name, expected in claims:
        if expected not in _strings(capabilities.get(name), name=name):
            raise ReplayBundleError(f"engine capabilities do not advertise {name} claim")


def _strategy_hashes(bundle: ReplayBundleVerification) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (name, digest)
            for name, digest in bundle.artifact_sha256.items()
            if name.startswith("strategy_artifact:")
        )
    )


def _completion_value(replay: ExecutionReplayResult) -> Mapping[str, object]:
    value = cast("dict[str, object]", asdict(replay.completion))
    value.pop("scenario_sha256")
    return value


def _fee_value(replay: ExecutionReplayResult) -> tuple[object, ...]:
    fill_columns = tuple(
        column for column in replay.fills if isinstance(column, str) and "fee" in column
    )
    fill_fees = replay.fills.loc[:, fill_columns].to_json(
        orient="split", date_format="iso", date_unit="us"
    )
    borrow_fees = replay.borrow_fees.to_json(orient="split", date_format="iso", date_unit="us")
    completion = replay.completion
    return (
        fill_fees,
        borrow_fees,
        completion.execution_fees_micros,
        completion.borrow_fees_micros,
        completion.total_fees_micros,
    )


def _fee_aggregate(
    left: ExecutionReplayResult, right: ExecutionReplayResult
) -> Mapping[str, int | float]:
    return {
        "left_rows": len(left.fills) + len(left.borrow_fees),
        "right_rows": len(right.fills) + len(right.borrow_fees),
        "execution_fees_micros_delta": (
            right.completion.execution_fees_micros - left.completion.execution_fees_micros
        ),
        "borrow_fees_micros_delta": (
            right.completion.borrow_fees_micros - left.completion.borrow_fees_micros
        ),
        "total_fees_micros_delta": (
            right.completion.total_fees_micros - left.completion.total_fees_micros
        ),
    }


def _first_sequence_divergence(layer: str, left: Sequence[object], right: Sequence[object]) -> str:
    for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
        if left_item != right_item:
            return f"{layer}[{index}]"
    return f"{layer}[{min(len(left), len(right))}]"


def _frame_first_divergence(layer: str, left: pd.DataFrame, right: pd.DataFrame) -> str:
    identifiers = (
        "order_id",
        "fill_id",
        "metric_name",
        "instrument_id",
        "slice_sequence",
        "engine_sequence",
    )
    common = [name for name in identifiers if name in left.columns and name in right.columns]
    if common:
        left_rows = left.sort_values(common, kind="stable").reset_index(drop=True)
        right_rows = right.sort_values(common, kind="stable").reset_index(drop=True)
    else:
        left_rows = left.reset_index(drop=True)
        right_rows = right.reset_index(drop=True)
    limit = min(len(left_rows), len(right_rows))
    for index in range(limit):
        if not left_rows.iloc[index].equals(right_rows.iloc[index]):
            if common:
                identity = ",".join(f"{name}={left_rows.iloc[index][name]}" for name in common)
                return f"{layer}[{identity}]"
            return f"{layer}[{index}]"
    return f"{layer}[{limit}]"


def _frame_aggregate(left: pd.DataFrame, right: pd.DataFrame) -> Mapping[str, int | float]:
    result: dict[str, int | float] = {
        "left_rows": len(left),
        "right_rows": len(right),
    }
    for column in sorted(set(left.columns) & set(right.columns)):
        if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(
            right[column]
        ):
            result[f"{column}_delta"] = float(right[column].sum() - left[column].sum())
    return result


def _json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplayBundleError(f"{label} is not valid JSON") from error
    return dict(_object(value, name=label))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayBundleError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _object(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReplayBundleError(f"{name} must be an object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, *, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ReplayBundleError(f"{name} must be an array")
    return cast("list[object]", value)


def _strings(value: object, *, name: str) -> tuple[str, ...]:
    values = _sequence(value, name=name)
    result = tuple(_string(item, name=name) for item in values)
    if not result or len(result) != len(set(result)):
        raise ReplayBundleError(f"{name} must contain unique string values")
    return result


def _string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayBundleError(f"{name} must be a nonempty string")
    return value


def _optional_string(value: object, *, name: str) -> str | None:
    return None if value is None else _string(value, name=name)


def _digest(value: object, *, name: str) -> str:
    result = _string(value, name=name)
    if _HASH.fullmatch(result) is None:
        raise ReplayBundleError(f"{name} must be a lowercase SHA-256 digest")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
