"""Run Trading Engine through a safe subprocess and artifact boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, cast

from persistra.integrations.trading_engine._scalars import exact_fields, identifier
from persistra.integrations.trading_engine.journal import read_journal
from persistra.integrations.trading_engine.model import (
    EngineCapabilities,
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

if TYPE_CHECKING:
    from collections.abc import Sequence

type _VcsProvenance = dict[str, str | bool | None]

_CAPABILITY_FIELDS = {
    "engine_version",
    "scenario_contract_versions",
    "journal_contract_versions",
    "scenario_formats",
    "journal_formats",
    "execution_models",
}


def run_scenario(
    scenario: TradingEngineScenario | str | Path,
    *,
    executable: str | Path,
    output_directory: str | Path | None = None,
    journal_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    timeout: float = 300.0,
) -> EngineRunResult:
    """Validate, replay, reconcile, and bundle one deterministic scenario."""
    checked_timeout = _timeout(timeout)
    executable_path = _executable(executable)
    (
        scenario_model,
        scenario_path,
        scenario_requires_write,
        source_scenario_hash,
        scenario_format,
    ) = (
        _scenario_artifact(
            scenario,
            output_directory=output_directory,
            journal_path=journal_path,
            manifest_path=manifest_path,
        )
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
    partial_journal = output_journal.with_name(f"{output_journal.name}.partial")
    engine_staging_journal = partial_journal.with_name(f"{partial_journal.name}.partial")
    _preflight_artifacts(
        scenario_path,
        output_journal,
        partial_journal,
        engine_staging_journal,
        output_manifest,
        scenario_requires_write=scenario_requires_write,
    )
    executable_hash = _sha256(executable_path)
    capabilities = _engine_capabilities(executable_path, timeout=checked_timeout)
    if _sha256(executable_path) != executable_hash:
        raise ValueError("trading-engine executable changed during capability discovery")
    _require_compatible_engine(
        capabilities,
        contract_version=scenario_model.contract_version,
        scenario_format=scenario_format,
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
    replay_command = (
        str(executable_path),
        "--input",
        str(scenario_path),
        "--input-format",
        scenario_format,
        "--journal",
        str(partial_journal),
    )
    try:
        replay_process = _run_process(
            replay_command,
            timeout=checked_timeout,
            stage="scenario replay",
            journal_path=partial_journal,
        )
    except TradingEngineProcessError as error:
        diagnostic = engine_staging_journal if engine_staging_journal.exists() else partial_journal
        raise TradingEngineProcessError(
            error.message,
            error.command,
            error.returncode,
            error.stdout,
            error.stderr,
            diagnostic,
        ) from error
    if not partial_journal.is_file():
        raise TradingEngineProcessError(
            "trading-engine replay succeeded without creating its journal",
            replay_command,
            replay_process.returncode,
            replay_process.stdout,
            replay_process.stderr,
            partial_journal,
        )
    if _sha256(scenario_path) != scenario_hash:
        raise ValueError("scenario artifact changed during validation or replay")
    if _sha256(executable_path) != executable_hash:
        raise ValueError("trading-engine executable changed during validation or replay")
    journal_hash = _sha256(partial_journal)
    replay = read_journal(
        partial_journal,
        scenario=scenario_path,
        scenario_sha256=scenario_hash,
    )
    if _sha256(partial_journal) != journal_hash:
        raise ValueError("journal artifact changed during reconciliation")
    _finalize_journal(
        partial_journal,
        output_journal,
        expected_sha256=journal_hash,
    )
    _write_manifest(
        output_manifest,
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
    )
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
    *,
    scenario_requires_write: bool,
) -> None:
    outputs = [journal_path, partial_journal, engine_staging_journal, manifest_path]
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


def _finalize_journal(
    partial_path: Path,
    final_path: Path,
    *,
    expected_sha256: str,
) -> None:
    """Expose a validated journal without replacing an existing artifact."""
    document = partial_path.read_bytes()
    if hashlib.sha256(document).hexdigest() != expected_sha256:
        raise ValueError("journal artifact changed before it was finalized")
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{final_path.name}.",
        suffix=".staging",
        dir=final_path.parent,
    )
    staging_path = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        if _sha256(staging_path) != expected_sha256:
            raise ValueError("private journal staging changed while it was written")
        try:
            os.link(staging_path, final_path)
        except FileExistsError:
            raise FileExistsError(f"journal path already exists: {final_path}") from None
        except OSError as error:
            raise OSError(f"could not finalize journal {final_path}: {error}") from error
        if _sha256(final_path) != expected_sha256:
            final_path.unlink()
            raise ValueError("journal artifact changed while it was finalized")
        partial_path.unlink()
    finally:
        staging_path.unlink(missing_ok=True)


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
) -> None:
    metadata = cast("Mapping[str, object]", _json_copy(scenario.metadata))
    document = {
        "run_id": scenario.run_id,
        "contract": {"version": scenario.contract_version},
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
        "artifacts": {
            "scenario": {
                "path": _relative_artifact_path(scenario_path, manifest=path),
                "sha256": scenario_sha256,
                "format": scenario_format,
            },
            "journal": {
                "path": _relative_artifact_path(journal_path, manifest=path),
                "sha256": journal_sha256,
            },
        },
        "scenario_metadata": metadata,
    }
    encoded = json.dumps(
        document,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{encoded}\n")


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
        payload = exact_fields(raw, _CAPABILITY_FIELDS, name="engine capabilities")
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
    contract_version: str,
    scenario_format: str,
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
        ("completed_bar_v1" in capabilities.execution_models, "completed-bar v1 execution"),
    )
    missing = [description for supported, description in requirements if not supported]
    if missing:
        raise ValueError(
            "incompatible trading-engine capabilities: missing " + ", ".join(missing)
        )


def _capability_values(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a JSON array")
    return tuple(identifier(item, name=name) for item in cast("list[object]", value))


def _capabilities_dictionary(capabilities: EngineCapabilities) -> dict[str, object]:
    return {
        "engine_version": capabilities.engine_version,
        "scenario_contract_versions": list(capabilities.scenario_contract_versions),
        "journal_contract_versions": list(capabilities.journal_contract_versions),
        "scenario_formats": list(capabilities.scenario_formats),
        "journal_formats": list(capabilities.journal_formats),
        "execution_models": list(capabilities.execution_models),
    }


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
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            encoding="utf-8",
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise TradingEngineProcessError(
            f"trading-engine {stage} timed out after {timeout:g} seconds",
            tuple(command),
            None,
            _process_text(error.stdout),
            _process_text(error.stderr),
            journal_path,
        ) from error
    except OSError as error:
        raise TradingEngineProcessError(
            f"could not start trading-engine {stage}: {error}",
            tuple(command),
            None,
            journal_path=journal_path,
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        suffix = "" if not detail else f": {detail}"
        raise TradingEngineProcessError(
            f"trading-engine {stage} failed with exit code {result.returncode}{suffix}",
            tuple(command),
            result.returncode,
            result.stdout,
            result.stderr,
            journal_path,
        )
    return result


def _process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
