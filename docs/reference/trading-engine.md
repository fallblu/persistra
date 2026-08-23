# Trading Engine integration

Import the public scenario, runner, journal, and analysis surface from
`persistra.integrations.trading_engine`. Import replay plots from `persistra.viz`.

The integration supports synchronized market slices, portable portfolio targets, and typed
direct intents. Trading Engine remains a separate executable and the authority for execution
semantics.

## Scenario, policy, and result models

::: persistra.integrations.trading_engine.model
    options:
      members: true

## Scenario construction and serialization

::: persistra.integrations.trading_engine.scenario
    options:
      members: true

## Explicit initial portfolio state

::: persistra.integrations.trading_engine.initial_state
    options:
      members: true

## Risk, fees, financing, and settlement

::: persistra.integrations.trading_engine.risk_financing
    options:
      members: true

## Audit journal import

::: persistra.integrations.trading_engine.journal
    options:
      members: true

## Failure diagnostics

::: persistra.integrations.trading_engine.diagnostics
    options:
      members: true

## Subprocess runner

::: persistra.integrations.trading_engine.runner
    options:
      members: true

## External strategy host

::: persistra.integrations.trading_engine.strategy
    options:
      members: true

## Strategy lifecycle

::: persistra.integrations.trading_engine.base_strategy
    options:
      members: true

## Composite strategy pipeline

::: persistra.integrations.trading_engine.composite_strategy
    options:
      members: true

## Execution and performance analysis

::: persistra.integrations.trading_engine.analysis
    options:
      members: true

## Replay visualizations

::: persistra.viz.trading_engine
    options:
      members: true
