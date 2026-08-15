"""Run the trading engine through a safe subprocess boundary."""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from persistra.integrations.trading_engine.journal import read_journal
from persistra.integrations.trading_engine.model import (
    EngineRunResult,
    TradingEngineProcessError,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.scenario import read_scenario, write_scenario

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_scenario(
    scenario: TradingEngineScenario | str | Path,
    *,
    executable: str | Path,
    output_directory: str | Path | None = None,
    journal_path: str | Path | None = None,
    timeout: float = 300.0,
) -> EngineRunResult:
    """Validate and replay a scenario with an explicit executable and no shell."""
    checked_timeout = _timeout(timeout)
    executable_path = _executable(executable)
    scenario_model, scenario_path = _scenario_artifact(
        scenario,
        output_directory=output_directory,
        journal_path=journal_path,
    )
    output_journal = _journal_artifact(
        scenario_model,
        output_directory=output_directory,
        journal_path=journal_path,
    )
    if scenario_path == output_journal:
        raise ValueError("scenario and journal paths must differ")
    if output_journal.exists():
        raise FileExistsError(f"journal path already exists: {output_journal}")

    validation_command = (
        str(executable_path),
        "--input",
        str(scenario_path),
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
        "--journal",
        str(output_journal),
    )
    replay_process = _run_process(
        replay_command,
        timeout=checked_timeout,
        stage="scenario replay",
        journal_path=output_journal,
    )
    if not output_journal.is_file():
        raise TradingEngineProcessError(
            "trading-engine replay succeeded without creating its journal",
            replay_command,
            replay_process.returncode,
            replay_process.stdout,
            replay_process.stderr,
            output_journal,
        )
    replay = read_journal(output_journal, scenario=scenario_model)
    return EngineRunResult(
        executable=executable_path,
        scenario_path=scenario_path,
        journal_path=output_journal,
        scenario_sha256=_sha256(scenario_path),
        journal_sha256=_sha256(output_journal),
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
) -> tuple[TradingEngineScenario, Path]:
    if isinstance(scenario, TradingEngineScenario):
        directory = _output_directory(output_directory, journal_path=journal_path)
        path = (directory / f"{_artifact_stem(scenario.run_id)}.scenario.json").resolve()
        write_scenario(scenario, path)
        return scenario, path
    path = Path(scenario).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"scenario path is not a regular file: {path}")
    return read_scenario(path), path


def _journal_artifact(
    scenario: TradingEngineScenario,
    *,
    output_directory: str | Path | None,
    journal_path: str | Path | None,
) -> Path:
    if journal_path is not None:
        path = Path(journal_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    if output_directory is None:
        raise ValueError("provide output_directory or journal_path")
    directory = Path(output_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"output_directory is not a directory: {directory}")
    return (directory / f"{_artifact_stem(scenario.run_id)}.journal.jsonl").resolve()


def _output_directory(
    output_directory: str | Path | None,
    *,
    journal_path: str | Path | None,
) -> Path:
    if output_directory is None:
        if journal_path is None:
            raise ValueError("provide output_directory or journal_path")
        directory = Path(journal_path).expanduser().parent
    else:
        directory = Path(output_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"output_directory is not a directory: {directory}")
    return directory.resolve()


def _executable(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"trading-engine executable does not exist: {path}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError(f"trading-engine executable is not an executable file: {resolved}")
    return resolved


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
