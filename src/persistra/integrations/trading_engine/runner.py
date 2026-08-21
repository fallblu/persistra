"""Run Trading Engine through a safe subprocess and artifact boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import signal
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, cast

from persistra._files import (
    FileIdentity,
    atomic_write_bytes,
    file_identity,
    unlink_if_identity,
)
from persistra.integrations.trading_engine._scalars import exact_fields, identifier
from persistra.integrations.trading_engine.journal import read_journal
from persistra.integrations.trading_engine.model import (
    EngineCapabilities,
    EngineResourceLimits,
    EngineRunResult,
    TradingEngineProcessError,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.scenario import (
    scenario_from_json,
    scenario_from_jsonl,
    write_scenario,
    write_scenario_stream,
)
from persistra.integrations.trading_engine.strategy import (
    TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION,
    StrategyArtifact,
    StrategyProcess,
    StrategyRunResult,
    read_strategy_transcript,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

type _VcsProvenance = dict[str, str | bool | None]

_REQUIRED_CAPABILITY_FIELDS = {
    "engine_version",
    "scenario_contract_versions",
    "journal_contract_versions",
    "scenario_formats",
    "journal_formats",
    "execution_models",
    "strategy_protocol_versions",
}
_RESOURCE_LIMIT_FIELDS = {
    "version",
    "scenario_record_bytes",
    "strategy_message_bytes",
    "internal_events",
    "catalog_instruments",
    "intents_per_batch",
    "artifact_record_bytes",
}
_PROCESS_TERMINATION_GRACE_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class _PreparedStrategy:
    command: tuple[str, ...]
    executable: Path
    executable_sha256: str
    artifacts: tuple[StrategyArtifact, ...]
    response_timeout: float


@dataclass(frozen=True, slots=True)
class _StagedArtifact:
    partial_path: Path
    final_path: Path
    staging_path: Path
    expected_sha256: str
    label: str
    partial_identity: FileIdentity
    staging_identity: FileIdentity


def run_scenario(
    scenario: TradingEngineScenario | str | Path,
    *,
    executable: str | Path,
    output_directory: str | Path | None = None,
    journal_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    strategy: StrategyProcess | None = None,
    strategy_transcript_path: str | Path | None = None,
    timeout: float = 300.0,
) -> EngineRunResult:
    """Validate, replay, reconcile, and bundle one deterministic scenario."""
    checked_timeout = _timeout(timeout)
    executable_path = _executable(executable)
    if strategy is None and strategy_transcript_path is not None:
        raise ValueError("strategy_transcript_path requires a strategy process")
    prepared_strategy = None if strategy is None else _prepare_strategy(strategy)
    (
        scenario_model,
        scenario_path,
        scenario_requires_write,
        source_scenario_hash,
        scenario_format,
    ) = _scenario_artifact(
        scenario,
        output_directory=output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    output_journal = _journal_artifact(
        scenario_model,
        output_directory=output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    output_manifest = _manifest_artifact(
        scenario_model,
        output_directory=output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    output_strategy_transcript = (
        None
        if prepared_strategy is None
        else _strategy_transcript_artifact(
            scenario_model,
            output_directory=output_directory,
            journal_path=journal_path,
            manifest_path=manifest_path,
            strategy_transcript_path=strategy_transcript_path,
        )
    )
    if prepared_strategy is not None and scenario_model.schedule:
        raise ValueError("external strategy replay requires an empty scenario schedule")
    partial_journal = output_journal.with_name(f"{output_journal.name}.partial")
    engine_staging_journal = partial_journal.with_name(f"{partial_journal.name}.partial")
    partial_manifest = output_manifest.with_name(f"{output_manifest.name}.partial")
    partial_strategy_transcript = (
        None
        if output_strategy_transcript is None
        else output_strategy_transcript.with_name(f"{output_strategy_transcript.name}.partial")
    )
    engine_staging_strategy_transcript = (
        None
        if partial_strategy_transcript is None
        else partial_strategy_transcript.with_name(f"{partial_strategy_transcript.name}.partial")
    )
    strategy_outputs = tuple(
        path
        for path in (
            output_strategy_transcript,
            partial_strategy_transcript,
            engine_staging_strategy_transcript,
        )
        if path is not None
    )
    _preflight_artifacts(
        scenario_path,
        output_journal,
        partial_journal,
        engine_staging_journal,
        output_manifest,
        partial_manifest,
        scenario_requires_write=scenario_requires_write,
        additional_outputs=strategy_outputs,
    )
    executable_hash = _sha256(executable_path)
    capabilities = _engine_capabilities(executable_path, timeout=checked_timeout)
    if _sha256(executable_path) != executable_hash:
        raise ValueError("trading-engine executable changed during capability discovery")
    _require_compatible_engine(
        capabilities,
        scenario=scenario_model,
        contract_version=scenario_model.contract_version,
        scenario_format=scenario_format,
        execution_model=scenario_model.execution.model,
        strategy_protocol_version=(
            None if prepared_strategy is None else TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION
        ),
    )
    persistra_vcs = _vcs_provenance(Path(__file__).resolve())
    engine_vcs = _vcs_provenance(executable_path)
    if scenario_requires_write:
        if scenario_format == "jsonl":
            write_scenario_stream(scenario_model, scenario_path)
        else:
            write_scenario(scenario_model, scenario_path)
        scenario_hash = _sha256(scenario_path)
    else:
        scenario_hash = source_scenario_hash
        if _sha256(scenario_path) != scenario_hash:
            raise ValueError("scenario artifact changed before validation")
    validation_command = (
        str(executable_path),
        "--input",
        str(scenario_path),
        "--input-format",
        scenario_format,
        "--validate-only",
    )
    validation = _run_process(
        validation_command,
        timeout=checked_timeout,
        stage="scenario validation",
    )
    replay_arguments = [
        str(executable_path),
        "--input",
        str(scenario_path),
        "--input-format",
        scenario_format,
        "--journal",
        str(partial_journal),
    ]
    if prepared_strategy is not None:
        assert partial_strategy_transcript is not None
        replay_arguments.extend(
            [
                "--strategy-executable",
                prepared_strategy.command[0],
            ]
        )
        for argument in prepared_strategy.command[1:]:
            replay_arguments.append(f"--strategy-arg={argument}")
        replay_arguments.extend(
            [
                "--strategy-timeout",
                f"{prepared_strategy.response_timeout:g}",
                "--strategy-transcript",
                str(partial_strategy_transcript),
            ]
        )
    replay_command = tuple(replay_arguments)
    try:
        replay_process = _run_process(
            replay_command,
            timeout=checked_timeout,
            stage="scenario replay",
            journal_path=partial_journal,
            strategy_transcript_path=partial_strategy_transcript,
        )
    except TradingEngineProcessError as error:
        diagnostic = engine_staging_journal if engine_staging_journal.exists() else partial_journal
        strategy_diagnostic = (
            engine_staging_strategy_transcript
            if engine_staging_strategy_transcript is not None
            and engine_staging_strategy_transcript.exists()
            else partial_strategy_transcript
        )
        raise TradingEngineProcessError(
            error.message,
            error.command,
            error.returncode,
            error.stdout,
            error.stderr,
            diagnostic,
            strategy_diagnostic,
        ) from error
    if not partial_journal.is_file():
        raise TradingEngineProcessError(
            "trading-engine replay succeeded without creating its journal",
            replay_command,
            replay_process.returncode,
            replay_process.stdout,
            replay_process.stderr,
            partial_journal,
            partial_strategy_transcript,
        )
    if partial_strategy_transcript is not None and not partial_strategy_transcript.is_file():
        raise TradingEngineProcessError(
            "trading-engine replay succeeded without creating its strategy transcript",
            replay_command,
            replay_process.returncode,
            replay_process.stdout,
            replay_process.stderr,
            partial_journal,
            partial_strategy_transcript,
        )
    if _sha256(scenario_path) != scenario_hash:
        raise ValueError("scenario artifact changed during validation or replay")
    if _sha256(executable_path) != executable_hash:
        raise ValueError("trading-engine executable changed during validation or replay")
    if prepared_strategy is not None:
        _require_unchanged_strategy(prepared_strategy)
    journal_hash = _sha256(partial_journal)
    transcript = None
    transcript_hash = None
    if prepared_strategy is not None:
        assert partial_strategy_transcript is not None
        transcript_hash = _sha256(partial_strategy_transcript)
        transcript = read_strategy_transcript(
            partial_strategy_transcript,
            scenario_sha256=scenario_hash,
            run_id=scenario_model.run_id,
        )
        if _sha256(partial_strategy_transcript) != transcript_hash:
            raise ValueError("strategy transcript changed during validation")
        _require_unchanged_strategy(prepared_strategy)
    replay = read_journal(
        partial_journal,
        scenario=scenario_path,
        scenario_sha256=scenario_hash,
        strategy_transcript=transcript,
    )
    if _sha256(partial_journal) != journal_hash:
        raise ValueError("journal artifact changed during reconciliation")
    strategy_result: StrategyRunResult | None = None
    finalized_artifacts: list[tuple[Path, Path, str, str]] = [
        (partial_journal, output_journal, journal_hash, "journal")
    ]
    if prepared_strategy is not None:
        assert partial_strategy_transcript is not None
        assert output_strategy_transcript is not None
        assert transcript_hash is not None
        assert transcript is not None
        strategy_result = StrategyRunResult(
            identity=transcript.identity,
            executable=prepared_strategy.executable,
            executable_sha256=prepared_strategy.executable_sha256,
            artifacts=prepared_strategy.artifacts,
            transcript_path=output_strategy_transcript,
            transcript_sha256=transcript_hash,
            event_count=transcript.event_count,
            response_timeout=prepared_strategy.response_timeout,
        )
        finalized_artifacts.append(
            (
                partial_strategy_transcript,
                output_strategy_transcript,
                transcript_hash,
                "strategy transcript",
            )
        )
    manifest_identity: FileIdentity | None = None
    try:
        _write_manifest(
            partial_manifest,
            scenario=scenario_model,
            scenario_path=scenario_path,
            journal_path=output_journal,
            executable=executable_path,
            scenario_format=scenario_format,
            scenario_sha256=scenario_hash,
            journal_sha256=journal_hash,
            executable_sha256=executable_hash,
            capabilities=capabilities,
            persistra_vcs=persistra_vcs,
            engine_vcs=engine_vcs,
            strategy=strategy_result,
        )
        manifest_identity = file_identity(partial_manifest)
        manifest_hash = _sha256(partial_manifest)
        if file_identity(partial_manifest) != manifest_identity:
            raise ValueError("manifest staging changed before bundle publication")
        finalized_artifacts.append(
            (
                partial_manifest,
                output_manifest,
                manifest_hash,
                "manifest",
            )
        )
        _finalize_artifacts(finalized_artifacts)
    finally:
        if manifest_identity is not None:
            unlink_if_identity(partial_manifest, manifest_identity)
    return EngineRunResult(
        executable=executable_path,
        executable_sha256=executable_hash,
        capabilities=capabilities,
        scenario_path=scenario_path,
        journal_path=output_journal,
        manifest_path=output_manifest,
        scenario_sha256=scenario_hash,
        journal_sha256=journal_hash,
        validation_stdout=validation.stdout,
        validation_stderr=validation.stderr,
        stdout=replay_process.stdout,
        stderr=replay_process.stderr,
        replay=replay,
        strategy=strategy_result,
    )


def _scenario_artifact(
    scenario: TradingEngineScenario | str | Path,
    *,
    output_directory: str | Path | None,
    journal_path: str | Path | None,
    manifest_path: str | Path | None,
) -> tuple[TradingEngineScenario, Path, bool, str, str]:
    if isinstance(scenario, TradingEngineScenario):
        directory = _output_directory(
            output_directory,
            journal_path=journal_path,
            manifest_path=manifest_path,
        )
        path = (directory / f"{_artifact_stem(scenario.run_id)}.scenario.jsonl").resolve()
        return scenario, path, True, "", "jsonl"
    path = Path(scenario).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"scenario path is not a regular file: {path}")
    document = path.read_bytes()
    scenario_format = _scenario_format(path)
    parser = scenario_from_jsonl if scenario_format == "jsonl" else scenario_from_json
    model = parser(document.decode("utf-8"))
    return model, path, False, hashlib.sha256(document).hexdigest(), scenario_format


def _journal_artifact(
    scenario: TradingEngineScenario,
    *,
    output_directory: str | Path | None,
    journal_path: str | Path | None,
    manifest_path: str | Path | None,
) -> Path:
    if journal_path is not None:
        path = Path(journal_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    directory = _output_directory(
        output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    return (directory / f"{_artifact_stem(scenario.run_id)}.journal.jsonl").resolve()


def _manifest_artifact(
    scenario: TradingEngineScenario,
    *,
    output_directory: str | Path | None,
    journal_path: str | Path | None,
    manifest_path: str | Path | None,
) -> Path:
    if manifest_path is not None:
        path = Path(manifest_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    directory = _output_directory(
        output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    return (directory / f"{_artifact_stem(scenario.run_id)}.manifest.json").resolve()


def _strategy_transcript_artifact(
    scenario: TradingEngineScenario,
    *,
    output_directory: str | Path | None,
    journal_path: str | Path | None,
    manifest_path: str | Path | None,
    strategy_transcript_path: str | Path | None,
) -> Path:
    if strategy_transcript_path is not None:
        path = Path(strategy_transcript_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    directory = _output_directory(
        output_directory,
        journal_path=journal_path,
        manifest_path=manifest_path,
    )
    return (directory / f"{_artifact_stem(scenario.run_id)}.strategy.jsonl").resolve()


def _output_directory(
    output_directory: str | Path | None,
    *,
    journal_path: str | Path | None,
    manifest_path: str | Path | None,
) -> Path:
    if output_directory is None:
        location = journal_path if journal_path is not None else manifest_path
        if location is None:
            raise ValueError("provide output_directory, journal_path, or manifest_path")
        directory = Path(location).expanduser().parent
    else:
        directory = Path(output_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"output_directory is not a directory: {directory}")
    return directory.resolve()


def _preflight_artifacts(
    scenario_path: Path,
    journal_path: Path,
    partial_journal: Path,
    engine_staging_journal: Path,
    manifest_path: Path,
    partial_manifest: Path,
    *,
    scenario_requires_write: bool,
    additional_outputs: Sequence[Path] = (),
) -> None:
    outputs = [
        journal_path,
        partial_journal,
        engine_staging_journal,
        manifest_path,
        partial_manifest,
        *additional_outputs,
    ]
    if scenario_requires_write:
        outputs.append(scenario_path)
    if len(set(outputs)) != len(outputs) or (
        not scenario_requires_write and scenario_path in outputs
    ):
        raise ValueError("scenario, journal staging files, and manifest paths must differ")
    collisions = [path for path in outputs if path.exists()]
    if collisions:
        rendered = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"artifact path already exists: {rendered}")


def _finalize_journal(  # pyright: ignore[reportUnusedFunction]
    partial_path: Path,
    final_path: Path,
    *,
    expected_sha256: str,
) -> None:
    """Expose a validated journal without replacing an existing artifact."""
    _finalize_artifacts([(partial_path, final_path, expected_sha256, "journal")])


def _finalize_artifacts(artifacts: Sequence[tuple[Path, Path, str, str]]) -> None:
    """Expose a checked artifact group without replacing existing paths."""
    staged: list[_StagedArtifact] = []
    linked: list[tuple[Path, FileIdentity]] = []
    published = False
    try:
        for partial_path, final_path, expected_sha256, label in artifacts:
            partial_identity = file_identity(partial_path)
            document = partial_path.read_bytes()
            if (
                file_identity(partial_path) != partial_identity
                or hashlib.sha256(document).hexdigest() != expected_sha256
            ):
                raise ValueError(f"{label} artifact changed before it was finalized")
            descriptor, staging_name = tempfile.mkstemp(
                prefix=f".{final_path.name}.",
                suffix=".staging",
                dir=final_path.parent,
            )
            staging_path = Path(staging_name)
            staging_identity = file_identity(staging_path)
            staged.append(
                _StagedArtifact(
                    partial_path,
                    final_path,
                    staging_path,
                    expected_sha256,
                    label,
                    partial_identity,
                    staging_identity,
                )
            )
            try:
                stream = os.fdopen(descriptor, "wb")
                descriptor = -1
                with stream:
                    stream.write(document)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if (
                file_identity(staging_path) != staging_identity
                or _sha256(staging_path) != expected_sha256
            ):
                raise ValueError(f"private {label} staging changed while it was written")
        for artifact in staged:
            try:
                os.link(artifact.staging_path, artifact.final_path)
            except FileExistsError:
                raise FileExistsError(
                    f"{artifact.label} path already exists: {artifact.final_path}"
                ) from None
            except OSError as error:
                raise OSError(
                    f"could not finalize {artifact.label} {artifact.final_path}: {error}"
                ) from error
            linked.append((artifact.final_path, artifact.staging_identity))
        for artifact in staged:
            if (
                file_identity(artifact.final_path) != artifact.staging_identity
                or _sha256(artifact.final_path) != artifact.expected_sha256
                or file_identity(artifact.final_path) != artifact.staging_identity
            ):
                raise ValueError(f"{artifact.label} artifact changed while it was finalized")
        for artifact in staged:
            unlink_if_identity(artifact.partial_path, artifact.partial_identity)
        published = True
    except Exception:
        if not published:
            for path, identity in reversed(linked):
                unlink_if_identity(path, identity)
        raise
    finally:
        for artifact in staged:
            unlink_if_identity(artifact.staging_path, artifact.staging_identity)


def _write_manifest(
    path: Path,
    *,
    scenario: TradingEngineScenario,
    scenario_path: Path,
    journal_path: Path,
    executable: Path,
    scenario_format: str,
    scenario_sha256: str,
    journal_sha256: str,
    executable_sha256: str,
    capabilities: EngineCapabilities,
    persistra_vcs: _VcsProvenance,
    engine_vcs: _VcsProvenance,
    strategy: StrategyRunResult | None,
) -> None:
    metadata = cast("Mapping[str, object]", _json_copy(scenario.metadata))
    artifacts: dict[str, object] = {
        "scenario": {
            "path": _relative_artifact_path(scenario_path, manifest=path),
            "sha256": scenario_sha256,
            "format": scenario_format,
        },
        "journal": {
            "path": _relative_artifact_path(journal_path, manifest=path),
            "sha256": journal_sha256,
        },
    }
    document: dict[str, object] = {
        "run_id": scenario.run_id,
        "contract": {"version": scenario.contract_version},
        "execution": {"model": scenario.execution.model},
        "environment": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "platform": f"{platform.system()}-{platform.machine()}",
        },
        "persistra": {
            "version": version("persistra"),
            "vcs": persistra_vcs,
        },
        "engine": {
            "version": capabilities.engine_version,
            "capabilities": _capabilities_dictionary(capabilities),
            "executable": {
                "name": executable.name,
                "sha256": executable_sha256,
            },
            "vcs": engine_vcs,
        },
        "artifacts": artifacts,
        "scenario_metadata": metadata,
    }
    if strategy is not None:
        artifacts["strategy_transcript"] = {
            "path": _relative_artifact_path(strategy.transcript_path, manifest=path),
            "sha256": strategy.transcript_sha256,
            "format": "jsonl",
        }
        document["strategy"] = {
            "protocol_version": TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION,
            "identity": {
                "name": strategy.identity.name,
                "version": strategy.identity.version,
            },
            "response_timeout_seconds": strategy.response_timeout,
            "executable": {
                "name": strategy.executable.name,
                "sha256": strategy.executable_sha256,
            },
            "artifacts": [
                {
                    "path": _relative_artifact_path(item.path, manifest=path),
                    "sha256": item.sha256,
                }
                for item in strategy.artifacts
            ],
        }
    encoded = json.dumps(
        document,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_bytes(path, f"{encoded}\n".encode())


def _json_copy(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("scenario metadata keys must be strings")
            result[key] = _json_copy(item)
        return result
    if isinstance(value, tuple | list):
        return [_json_copy(item) for item in cast("tuple[object, ...] | list[object]", value)]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise TypeError("scenario metadata must contain JSON-compatible values")


def _executable(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"trading-engine executable does not exist: {path}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError(f"trading-engine executable is not an executable file: {resolved}")
    return resolved


def _prepare_strategy(strategy: StrategyProcess) -> _PreparedStrategy:
    executable = _strategy_executable(strategy.command[0])
    command = (str(executable), *(str(part) for part in strategy.command[1:]))
    artifacts: list[StrategyArtifact] = []
    seen: set[Path] = set()
    for value in strategy.artifacts:
        try:
            path = value.resolve(strict=True)
        except FileNotFoundError as error:
            raise ValueError(f"strategy artifact does not exist: {value}") from error
        if not path.is_file():
            raise ValueError(f"strategy artifact is not a regular file: {path}")
        if path in seen:
            raise ValueError(f"strategy artifacts must not contain duplicates: {path}")
        seen.add(path)
        artifacts.append(StrategyArtifact(path, _sha256(path)))
    return _PreparedStrategy(
        command=command,
        executable=executable,
        executable_sha256=_sha256(executable),
        artifacts=tuple(artifacts),
        response_timeout=strategy.response_timeout,
    )


def _strategy_executable(value: str | Path) -> Path:
    supplied = Path(value).expanduser()
    path = Path(os.path.abspath(supplied))
    if not path.exists():
        raise ValueError(f"strategy executable does not exist: {supplied}")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"strategy executable is not an executable file: {path}")
    return path


def _require_unchanged_strategy(strategy: _PreparedStrategy) -> None:
    if _sha256(strategy.executable) != strategy.executable_sha256:
        raise ValueError("strategy executable changed during replay")
    for artifact in strategy.artifacts:
        if _sha256(artifact.path) != artifact.sha256:
            raise ValueError(f"strategy artifact changed during replay: {artifact.path}")


def _scenario_format(path: Path) -> str:
    if path.suffix == ".jsonl":
        return "jsonl"
    if path.suffix == ".json":
        return "json"
    raise ValueError("scenario path must end in .json or .jsonl")


def _engine_capabilities(executable: Path, *, timeout: float) -> EngineCapabilities:
    command = (str(executable), "--capabilities")
    result = _run_process(
        command,
        timeout=timeout,
        stage="capability discovery",
    )
    try:
        raw = json.loads(result.stdout, object_pairs_hook=_unique_json_object)
        if not isinstance(raw, dict):
            raise TypeError("engine capabilities must be a JSON object")
        payload = cast("dict[str, object]", raw)
        missing = sorted(_REQUIRED_CAPABILITY_FIELDS.difference(payload))
        if missing:
            raise ValueError(f"engine capabilities fields are missing: {missing}")
        capabilities = EngineCapabilities(
            engine_version=identifier(payload["engine_version"], name="engine_version"),
            scenario_contract_versions=_capability_values(
                payload["scenario_contract_versions"],
                name="scenario_contract_versions",
            ),
            journal_contract_versions=_capability_values(
                payload["journal_contract_versions"],
                name="journal_contract_versions",
            ),
            scenario_formats=_capability_values(
                payload["scenario_formats"],
                name="scenario_formats",
            ),
            journal_formats=_capability_values(
                payload["journal_formats"],
                name="journal_formats",
            ),
            execution_models=_capability_values(
                payload["execution_models"],
                name="execution_models",
            ),
            strategy_protocol_versions=_capability_values(
                payload["strategy_protocol_versions"],
                name="strategy_protocol_versions",
            ),
            resource_limits=(
                _resource_limits(payload["resource_limits"])
                if "resource_limits" in payload
                else None
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise TradingEngineProcessError(
            f"trading-engine capability discovery returned an invalid document: {error}",
            command,
            result.returncode,
            result.stdout,
            result.stderr,
        ) from error
    return capabilities


def _require_compatible_engine(
    capabilities: EngineCapabilities,
    *,
    scenario: TradingEngineScenario,
    contract_version: str,
    scenario_format: str,
    execution_model: str,
    strategy_protocol_version: str | None = None,
) -> None:
    requirements = (
        (
            contract_version in capabilities.scenario_contract_versions,
            f"scenario contract_version {contract_version!r}",
        ),
        (
            contract_version in capabilities.journal_contract_versions,
            f"journal contract_version {contract_version!r}",
        ),
        (
            scenario_format in capabilities.scenario_formats,
            f"{scenario_format.upper()} scenarios",
        ),
        ("jsonl" in capabilities.journal_formats, "JSON Lines journals"),
        (
            execution_model in capabilities.execution_models,
            f"execution model {execution_model!r}",
        ),
    )
    if strategy_protocol_version is not None:
        requirements += (
            (
                strategy_protocol_version in capabilities.strategy_protocol_versions,
                f"strategy protocol version {strategy_protocol_version!r}",
            ),
        )
    missing = [description for supported, description in requirements if not supported]
    if missing:
        raise ValueError("incompatible trading-engine capabilities: missing " + ", ".join(missing))
    limits = capabilities.resource_limits
    if limits is None:
        return
    if limits.version != "1":
        raise ValueError(f"unsupported engine resource limit version: {limits.version!r}")
    exceeded: list[str] = []
    if scenario.max_internal_events > limits.internal_events:
        exceeded.append("max_internal_events")
    if len(scenario.instruments) > limits.catalog_instruments:
        exceeded.append("instrument catalog")
    if any(len(item.intents) > limits.intents_per_batch for item in scenario.schedule):
        exceeded.append("intent batch")
    if exceeded:
        raise ValueError("scenario exceeds engine resource limits: " + ", ".join(exceeded))


def _capability_values(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a JSON array")
    return tuple(identifier(item, name=name) for item in cast("list[object]", value))


def _resource_limits(value: object) -> EngineResourceLimits:
    payload = exact_fields(value, _RESOURCE_LIMIT_FIELDS, name="engine resource limits")
    return EngineResourceLimits(
        version=identifier(payload["version"], name="resource limit version"),
        scenario_record_bytes=_positive_limit(
            payload["scenario_record_bytes"], name="scenario_record_bytes"
        ),
        strategy_message_bytes=_positive_limit(
            payload["strategy_message_bytes"], name="strategy_message_bytes"
        ),
        internal_events=_positive_limit(payload["internal_events"], name="internal_events"),
        catalog_instruments=_positive_limit(
            payload["catalog_instruments"], name="catalog_instruments"
        ),
        intents_per_batch=_positive_limit(payload["intents_per_batch"], name="intents_per_batch"),
        artifact_record_bytes=_positive_limit(
            payload["artifact_record_bytes"], name="artifact_record_bytes"
        ),
    )


def _positive_limit(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _capabilities_dictionary(capabilities: EngineCapabilities) -> dict[str, object]:
    document: dict[str, object] = {
        "engine_version": capabilities.engine_version,
        "scenario_contract_versions": list(capabilities.scenario_contract_versions),
        "journal_contract_versions": list(capabilities.journal_contract_versions),
        "scenario_formats": list(capabilities.scenario_formats),
        "journal_formats": list(capabilities.journal_formats),
        "execution_models": list(capabilities.execution_models),
        "strategy_protocol_versions": list(capabilities.strategy_protocol_versions),
    }
    if capabilities.resource_limits is not None:
        limits = capabilities.resource_limits
        document["resource_limits"] = {
            "version": limits.version,
            "scenario_record_bytes": limits.scenario_record_bytes,
            "strategy_message_bytes": limits.strategy_message_bytes,
            "internal_events": limits.internal_events,
            "catalog_instruments": limits.catalog_instruments,
            "intents_per_batch": limits.intents_per_batch,
            "artifact_record_bytes": limits.artifact_record_bytes,
        }
    return document


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _vcs_provenance(path: Path) -> _VcsProvenance:
    location = path if path.is_dir() else path.parent
    root = _git_output(location, "rev-parse", "--show-toplevel")
    if root is None:
        return {"revision": None, "dirty": None}
    root_path = Path(root)
    revision = _git_output(root_path, "rev-parse", "HEAD")
    status = _git_output(
        root_path,
        "status",
        "--porcelain=v1",
        "--untracked-files=no",
    )
    return {
        "revision": revision,
        "dirty": None if status is None else bool(status),
    }


def _git_output(directory: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _relative_artifact_path(path: Path, *, manifest: Path) -> str:
    relative = os.path.relpath(path, start=manifest.parent)
    return Path(relative).as_posix()


def _timeout(value: float) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be a positive finite number")
    return float(value)


def _artifact_stem(run_id: str) -> str:
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id cannot contain path separators or dot path components")
    return run_id


def _run_process(
    command: Sequence[str],
    *,
    timeout: float,
    stage: str,
    journal_path: Path | None = None,
    strategy_transcript_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = list(command)
    try:
        process = subprocess.Popen(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            shell=False,
            start_new_session=True,
        )
    except OSError as error:
        raise TradingEngineProcessError(
            f"could not start trading-engine {stage}: {error}",
            tuple(command),
            None,
            journal_path=journal_path,
            strategy_transcript_path=strategy_transcript_path,
        ) from error
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stdout, stderr = _terminate_process_group(process)
        raise TradingEngineProcessError(
            f"trading-engine {stage} timed out after {timeout:g} seconds",
            tuple(command),
            None,
            stdout,
            stderr,
            journal_path,
            strategy_transcript_path,
        ) from error
    returncode = process.returncode
    assert returncode is not None
    if returncode != 0:
        detail = stderr.strip() or stdout.strip()
        suffix = "" if not detail else f": {detail}"
        raise TradingEngineProcessError(
            f"trading-engine {stage} failed with exit code {returncode}{suffix}",
            tuple(command),
            returncode,
            stdout,
            stderr,
            journal_path,
            strategy_transcript_path,
        )
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def _terminate_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    """Terminate an isolated process group and drain its captured output."""
    _signal_process_group(process, signal.SIGTERM)
    try:
        return process.communicate(timeout=_PROCESS_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_process_group(process, signal.SIGKILL)
        return process.communicate()


def _signal_process_group(process: subprocess.Popen[str], group_signal: signal.Signals) -> None:
    """Signal a process group that may already have exited."""
    try:
        os.killpg(process.pid, group_signal)
    except ProcessLookupError:
        pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
