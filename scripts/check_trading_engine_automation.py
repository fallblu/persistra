"""Verify Persistra automation contracts against pinned Trading Engine v1."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from persistra.integrations.trading_engine import (
    TradingEngineDiagnostic,
    TradingEngineProcessError,
    bind_engine_status_manifest,
    structured_engine_failure,
    trading_engine_diagnostic_from_json,
    trading_engine_success_from_json,
    verify_trading_engine_success,
)


def main() -> None:
    """Cross-check versioned success and failure output from Trading Engine v1."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_trading_engine_automation.py CONTRACT_DIRECTORY EXECUTABLE")
    contracts = Path(sys.argv[1]).resolve(strict=True)
    executable = Path(sys.argv[2]).resolve(strict=True)
    fixture = contracts / "fixtures/demo.scenario.json"
    with tempfile.TemporaryDirectory(prefix="persistra-automation-") as raw_directory:
        directory = Path(raw_directory)
        journal = directory / "journal.jsonl"
        replay = subprocess.run(
            (
                str(executable),
                "--input",
                str(fixture),
                "--input-format",
                "json",
                "--journal",
                str(journal),
                "--output-format",
                "json",
                "--diagnostic-format",
                "json",
            ),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        success = trading_engine_success_from_json(replay.stdout)
        verify_trading_engine_success(success, fixture, journal_path=journal)
        manifest = bind_engine_status_manifest({"run_id": success.run_id}, success)
        if manifest["status"]["status"] != "success":
            raise SystemExit("structured success status was not attached")

        invalid = directory / "invalid.scenario.json"
        document = json.loads(fixture.read_text(encoding="utf-8"))
        document["unexpected"] = True
        invalid.write_text(json.dumps(document), encoding="utf-8")
        failure = subprocess.run(
            (
                str(executable),
                "--input",
                str(invalid),
                "--input-format",
                "json",
                "--output-format",
                "json",
                "--diagnostic-format",
                "json",
                "--validate-only",
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if failure.returncode == 0:
            raise SystemExit("invalid v1 scenario unexpectedly passed validation")
        diagnostic = trading_engine_diagnostic_from_json(failure.stderr)
        status = structured_engine_failure(
            TradingEngineProcessError(
                message="validation failed",
                command=tuple(failure.args),
                returncode=failure.returncode,
                stdout=failure.stdout,
                stderr=failure.stderr,
                diagnostic=diagnostic,
            )
        )
        if status.code != diagnostic.code or status.context != diagnostic_context(diagnostic):
            raise SystemExit("structured failure status lost diagnostic identity or context")
    print(
        f"Trading Engine automation v{success.version}: "
        f"{success.counts.audits} audits, {success.counts.orders} orders, "
        f"failure code {diagnostic.code}"
    )


def diagnostic_context(diagnostic: TradingEngineDiagnostic) -> dict[str, object]:
    """Return the nonempty public context fields expected in failure status."""
    return {
        name: value
        for name, value in {
            "json_path": diagnostic.context.json_path,
            "line": diagnostic.context.line,
            "sequence": diagnostic.context.sequence,
            "event_id": diagnostic.context.event_id,
            "order_id": diagnostic.context.order_id,
            "causation_ids": list(diagnostic.context.causation_ids),
        }.items()
        if value not in (None, [])
    }


if __name__ == "__main__":
    main()
