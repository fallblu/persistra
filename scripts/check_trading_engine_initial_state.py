"""Verify explicit opening-state support against pinned Trading Engine v1 fixtures."""

from __future__ import annotations

import sys

from persistra.integrations.trading_engine import (
    INITIAL_STATE_CONTRACT_VERSION,
    TradingEngineContractSchemas,
    reconcile_initial_state_replay,
)


def main() -> None:
    """Validate and reconcile the canonical v1 opening portfolio replay."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_trading_engine_initial_state.py CONTRACT_DIRECTORY")
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    if schemas.version != INITIAL_STATE_CONTRACT_VERSION:
        raise SystemExit(
            "Persistra initial-state contract differs from pinned Trading Engine schemas: "
            f"expected {INITIAL_STATE_CONTRACT_VERSION}, found {schemas.version}"
        )
    fixture_directory = schemas.directory / "fixtures"
    result = reconcile_initial_state_replay(
        schemas,
        fixture_directory / "demo.scenario.json",
        fixture_directory / "demo.journal.jsonl",
    )
    print(
        f"Trading Engine initial state v{schemas.version}: "
        f"{result.portfolio_sha256} ({result.replay.journal_records} journal records)"
    )


if __name__ == "__main__":
    main()
