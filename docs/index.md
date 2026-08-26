# Persistra

Persistra is a typed Python toolkit for reproducible, point-in-time financial research. It keeps
data acquisition, local storage, feature and factor research, portfolio construction, backtesting,
and execution inputs explicit and inspectable.

## Start here

1. [Install Persistra](getting-started/installation.md).
2. Follow the offline [quickstart](getting-started/quickstart.md).
3. [Create a project](guides/projects.md) when you want a standard local layout.
4. Choose a data source: [Alpha Vantage](getting-started/alpha-vantage.md) or
   [FRED and ALFRED](getting-started/fred.md).

## Main workflows

- [Acquire and cache data](guides/acquisition.md).
- [Store and inspect results](guides/storage.md).
- [Build point-in-time datasets and factor models](guides/research.md).
- [Construct and backtest portfolios](guides/portfolio.md).
- [Run Monte Carlo research](guides/monte-carlo.md).
- [Build and reconcile Trading Engine v1 scenarios](guides/trading-engine.md).

The [examples](examples/index.md) provide complete offline workflows. The
[API reference](reference/index.md) documents every public package.

## Scope

Persistra is an offline research library. It does not connect to brokers, place live orders, or
infer missing point-in-time assumptions. Trading Engine is a separate deterministic executable;
Persistra validates and assembles its current v1 contract but does not implement execution
semantics.
