# Trading Engine integration

Import the public surface from `persistra.integrations.trading_engine`. Trading Engine is a
separate executable and the authority for execution semantics. Persistra supports only the
current v1 contract.

## Shared models

::: persistra.integrations.trading_engine.model
    options:
      members: true

## Contract schemas

::: persistra.integrations.trading_engine.contracts
    options:
      members: true

## Initial portfolio state

::: persistra.integrations.trading_engine.initial_state
    options:
      members: true

## Risk, fees, financing, and settlement

::: persistra.integrations.trading_engine.risk_financing
    options:
      members: true

## Venue and lifecycle replay

::: persistra.integrations.trading_engine.lifecycle_replay
    options:
      members: true

## Market-data replay

::: persistra.integrations.trading_engine.market_data_replay
    options:
      members: true

## Diagnostics and structured results

::: persistra.integrations.trading_engine.diagnostics
    options:
      members: true

::: persistra.integrations.trading_engine.automation
    options:
      members: true
