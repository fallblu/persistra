# Build Trading Engine scenarios

Persistra provides typed adapters for Trading Engine's current v1 scenario, stream, journal,
diagnostic, and result contracts. Trading Engine remains a separate executable and the authority
for order handling, execution, financing, settlement, and accounting.

Persistra does not retain adapters for older contracts. A document with any version other than
`"1"` is rejected.

## Load the authoritative schemas

Load the contract directory from the Trading Engine checkout you intend to run:

```python
from persistra.integrations.trading_engine import TradingEngineContractSchemas

schemas = TradingEngineContractSchemas.load("../trading-engine/contracts/v1")
schemas.validate_scenario(scenario_document)
schemas.validate_journal("artifacts/run.journal.jsonl")
```

The loader checks all three schema files, their references, declared v1 identifiers, and a stable
fingerprint. `schemas.read_replay(scenario_path, journal_path)` additionally reconciles run
identity, sequence, scenario hash, terminal events, and execution-price evidence.

## Assemble one v1 scenario

The adapters operate on one current document. Start with an explicit portfolio and catalog, then
apply the policies needed by the replay.

### Initial portfolio

`InitialPortfolioState` records native-currency cash, signed positions, cost basis, realized and
dividend attribution, fees, marks, and FX rates. `build_initial_state_scenario` combines it with:

- `ExecutionInstrument` catalog entries;
- venue calendars;
- a `RiskFinancingRiskPolicy` with one policy per instrument;
- a current execution object;
- typed `FinancingPolicy` and `SettlementPolicy` values;
- the schedule and market slices.

The builder validates both the batch JSON document and the equivalent JSON Lines stream. Use
`write_initial_state_scenario(..., stream=True)` for the streaming form. Initial-state
reconciliation derives one exact exposure row for every declared risk group, including groups
with no opening positions.

### Risk, fees, financing, and settlement

Use these immutable policy models:

- `InstrumentRiskPolicy`, `RiskGroup`, and `RiskFinancingRiskPolicy`;
- `FeeComponent`, `InstrumentFeeSchedule`, and `FeeExecutionPolicy`;
- `FinancingPolicy`;
- `SettlementCalendar`, `SettlementRule`, and `SettlementPolicy`.

```python
from persistra.integrations.trading_engine import (
    FeeComponent,
    FeeExecutionPolicy,
    InstrumentFeeSchedule,
)

execution = FeeExecutionPolicy(
    participation_bps=5_000,
    fee_schedules=(
        InstrumentFeeSchedule(
            schedule_id="asset-a-fees-v1",
            instrument_id="asset-a",
            settlement_currency="USD",
            components=(
                FeeComponent(
                    name="broker",
                    currency="USD",
                    kind="fixed",
                    value="0.25",
                    rounding="up",
                ),
            ),
        ),
    ),
)
```

`build_risk_financing_scenario` replaces the four policy sections of a v1 base scenario, verifies
catalog and currency coverage, validates observations, and checks both serializations.

For next-open or adverse-touch bar execution, use `ConservativeBarExecutionPolicy`. It produces
the current `configuration.version == "1"` payload with explicit fee schedules, spread, impact,
and missing-volume policy.

### Venue and lifecycle events

`build_lifecycle_replay_scenario` adds explicit venue sessions and causally delivered corporate or
instrument lifecycle events. The typed surface covers splits, cash dividends, distributions,
halts, resumes, identifier changes, and terminal events. Every event carries source provenance and
must fall within its market slice's delivery bounds. Stock dividends deliver the source
instrument and allocate no basis. Rights and spin-offs deliver a distinct instrument. Halt and
delisting reasons are whitespace-free audit labels rather than display text.

### Quotes, trades, and order books

`build_market_data_replay_scenario` supports two current execution models:

- `quote_trade_v1` for causal bid/ask quotes and aggressor-classified trades;
- `order_book_v1` for bounded level-two snapshots, updates, deletes, and trades.

Use `require_market_data_capabilities` before writing the scenario. It verifies that the selected
engine advertises the v1 contract, configuration, format, and model data requirements.

## Run Trading Engine

Write the finished scenario, invoke Trading Engine directly, and retain its JSON Lines journal.
The setup guide shows a local build. A typical replay command is:

```bash
../trading-engine/_build/default/bin/main.exe \
  --input artifacts/run.scenario.json \
  --input-format json \
  --journal artifacts/run.journal.jsonl \
  --output-format json \
  --diagnostic-format json
```

Parse the successful stdout document with `trading_engine_success_from_json`, then call
`verify_trading_engine_success` to compare reported hashes and counts with the retained files.
Parse failures with `trading_engine_diagnostic_from_json`.

## Reconcile retained artifacts

Choose the reconciler matching the scenario features:

- `reconcile_initial_state_replay` verifies opening state and the first valuation;
- `reconcile_risk_financing_replay` verifies fees, financing, settlement, and risk evidence;
- `reconcile_lifecycle_replay` verifies delivered and applied lifecycle events;
- `reconcile_market_data_replay` matches fills to executable source liquidity.

Each reconciler validates the scenario and journal against the same schema set before applying its
semantic checks. The `bind_*_manifest` helpers attach scenario identities and policy provenance to
caller-owned replay manifests.

## Compatibility policy

Persistra CI pins one reviewed Trading Engine commit and runs the canonical v1 fixtures plus each
specialized adapter. Advance the pinned commit, schema set, adapters, and cross-repository tests
together whenever the contract changes.
