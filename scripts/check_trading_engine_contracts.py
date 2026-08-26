"""Check Persistra expectations against a pinned Trading Engine schema directory."""

from __future__ import annotations

import json
import sys

from persistra.integrations.trading_engine import (
    TRADING_ENGINE_CONTRACT_VERSION,
    TradingEngineContractSchemas,
)


def main() -> None:
    """Validate canonical fixtures and Persistra's supported contract declaration."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_trading_engine_contracts.py CONTRACT_DIRECTORY")
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    if schemas.version != TRADING_ENGINE_CONTRACT_VERSION:
        raise SystemExit(
            "Persistra contract version differs from pinned Trading Engine schemas: "
            f"expected {TRADING_ENGINE_CONTRACT_VERSION}, found {schemas.version}"
        )
    if "completed_bar_v1" not in schemas.execution_models:
        raise SystemExit("pinned Trading Engine schema omits completed_bar_v1")
    fixture_directory = schemas.directory / "fixtures"
    scenario_path = fixture_directory / "demo.scenario.json"
    journal_path = fixture_directory / "demo.journal.jsonl"
    if not scenario_path.is_file() or not journal_path.is_file():
        raise SystemExit("pinned Trading Engine contract omits canonical demo fixtures")
    schemas.validate_scenario(json.loads(scenario_path.read_text(encoding="utf-8")))
    records = schemas.validate_journal(journal_path)
    if records == 0:
        raise SystemExit("canonical Trading Engine journal fixture must not be empty")
    print(
        f"Trading Engine contract v{schemas.version}: {schemas.sha256} "
        f"({records} journal records)"
    )


if __name__ == "__main__":
    main()
