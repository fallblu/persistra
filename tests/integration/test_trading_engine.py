"""Cross-repository checks for the current Trading Engine v1 contract."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from persistra.integrations.trading_engine import (
    INITIAL_STATE_CONTRACT_VERSION,
    LIFECYCLE_CONTRACT_VERSION,
    MARKET_DATA_CONTRACT_VERSION,
    RISK_FINANCING_CONTRACT_VERSION,
    TRADING_ENGINE_CONTRACT_VERSION,
    TradingEngineContractSchemas,
    trading_engine_success_from_json,
    verify_trading_engine_success,
)

_BINARY = os.environ.get("PERSISTRA_TRADING_ENGINE_BINARY")
_CONTRACT_DIRECTORY = os.environ.get("PERSISTRA_TRADING_ENGINE_CONTRACT_DIR")

pytestmark = pytest.mark.skipif(
    _BINARY is None or _CONTRACT_DIRECTORY is None,
    reason="Trading Engine integration paths are not configured",
)


def test_every_adapter_targets_the_single_v1_contract() -> None:
    assert {
        TRADING_ENGINE_CONTRACT_VERSION,
        INITIAL_STATE_CONTRACT_VERSION,
        RISK_FINANCING_CONTRACT_VERSION,
        LIFECYCLE_CONTRACT_VERSION,
        MARKET_DATA_CONTRACT_VERSION,
    } == {"1"}


def test_canonical_v1_fixture_replays_and_reconciles(tmp_path: Path) -> None:
    assert _BINARY is not None
    assert _CONTRACT_DIRECTORY is not None
    schemas = TradingEngineContractSchemas.load(_CONTRACT_DIRECTORY)
    scenario = schemas.directory / "fixtures" / "demo.scenario.json"
    document = json.loads(scenario.read_text(encoding="utf-8"))
    schemas.validate_scenario(document)

    journal = tmp_path / "demo.journal.jsonl"
    completed = subprocess.run(
        (
            str(Path(_BINARY).resolve(strict=True)),
            "--input",
            str(scenario),
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
    summary = trading_engine_success_from_json(completed.stdout)
    verify_trading_engine_success(summary, scenario, journal_path=journal)
    replay = schemas.read_replay(scenario, journal)

    assert replay.contract_version == "1"
    assert replay.run_id == document["run_id"]
    assert replay.journal_records == summary.counts.audits
