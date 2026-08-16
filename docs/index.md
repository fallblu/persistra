# Persistra

Persistra connects systematic strategy research to deterministic execution replay. It gives you
typed Python contracts for preparing data, estimating factor models, constructing portfolios,
implementing event-driven strategies, building Trading Engine scenarios, and analyzing the
resulting audit journal.

The main workflow is explicit:

```text
normalized data -> point-in-time features -> forecasts -> target portfolio
                -> strategy lifecycle -> Trading Engine -> journal analysis
```

Persistra owns the research and integration layers. The separately installed Trading Engine owns
orders, fills, risk, accounting, target persistence, and event sequencing. That boundary lets a
strategy remain easy to inspect in Python while execution behavior stays deterministic and
auditable.

## Start with a strategy

Follow this path when you are new to the project:

1. [Install Persistra](getting-started/installation.md).
2. Complete the offline [strategy quickstart](getting-started/quickstart.md).
3. Learn the [strategy lifecycle](guides/strategy-development.md), including warm-up, bounded
   history, filtering, schedules, composition, and rebalance guards.
4. Develop a signal with [factor regressions](guides/research.md) and turn it into constrained
   targets with [portfolio optimization](guides/portfolio.md).
5. [Set up Trading Engine](getting-started/trading-engine.md) and
   [replay the strategy](guides/trading-engine.md).
6. Inspect the complete [examples by topic](examples/index.md).

All introductory research examples run without credentials, network access, or an engine binary.
Synthetic data follows the same normalized result contracts as provider-backed data. Install
Trading Engine only when you are ready to test order and fill behavior.

## Choose the right strategy abstraction

| Need | Start with |
|---|---|
| One strategy with lifecycle hooks | `BaseStrategy` |
| Warm-up and bounded history | `WarmupPolicy` and `StrategyHistory` |
| Scheduled universe or rebalance decisions | `ObservationSchedule` or `ElapsedSchedule` |
| Fixed-catalog security filtering | `security_filter` or a `SecuritySelector` |
| Separate alpha, construction, and overlay stages | `CompositeStrategy` |
| Multiple aligned forecasts | `WeightedForecastCombiner` |
| Suppress small or conflicting rebalances | `MinimumTargetChangeGuard` and `OutstandingOrdersGuard` |
| Precomputed target panels | `build_scenario` with `target_weights` |
| Decisions that react to fills and portfolio state | An external strategy process |

Read [Develop a strategy](guides/strategy-development.md) for the lifecycle and composition
contracts. The [strategy examples](examples/strategy-lifecycle.md) and
[composite examples](examples/composite-strategies.md) provide complete starting points.

## Research components

Persistra keeps the boundary between estimation and portfolio choice visible:

- Regression functions estimate caller-defined factor models; Persistra does not supply
  reference factors.
- Factor forecasts preserve per-factor expected-return contributions and an explicit `as_of`.
- Portfolio problems state their objective, constraints, covariance policy, current weights,
  and cost penalties.
- Rolling optimization carries realized targets forward and records explicit held or failed
  rebalance steps.
- Vectorized backtests model target timing and portfolio accounting; Trading Engine replay adds
  orders, partial fills, fees, margin, and a terminal journal.

Use the [factor-model examples](examples/factor-models.md),
[portfolio examples](examples/portfolio-optimization.md), and
[portfolio guide](guides/portfolio.md) together.

## Data and provenance

Provider adapters acquire data but never write it to storage. Normalized results keep stable
identity, observations, and acquisition metadata separate. Transforms do not silently fill or
repair missing values, and point-in-time tools require availability, lag, staleness, label
horizon, purge, and embargo choices to stay visible.

Connect [Alpha Vantage](getting-started/alpha-vantage.md) for market data or
[FRED and ALFRED](getting-started/fred.md) for economic observations and revisions. The how-to
guides cover [acquisition](guides/acquisition.md), [offline caching](guides/cache-offline.md),
[DuckDB storage](guides/storage.md), [alignment](guides/transforms.md),
[analysis](guides/analysis.md), and [visualization](guides/visualization.md).

## Important boundaries

Persistra is built for offline research and replay. It does not provide broker connectivity,
live market-data subscriptions, order routing, or production process orchestration. A Trading
Engine strategy subprocess runs with the same trust as its caller; process supervision is not a
sandbox.

The library rejects ambiguous temporal axes, misaligned panels, incomplete scenario artifacts,
and unsupported execution inputs rather than guessing. See [Architecture](concepts/architecture.md),
[Data model](concepts/data-model.md), and [Time and provenance](concepts/time-provenance.md) for
the rationale. The [API reference](reference/index.md) lists the complete public surface.
