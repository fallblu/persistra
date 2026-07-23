# Persistra

Persistra v3 is a local-first Python library. Use it for point-in-time market research,
strategy development, and event-driven backtesting.

Python 3.12 or later is necessary. The base package contains all Persistra
capabilities. There are no optional runtime extras.

Refer to the [`docs/`](docs/index.md) directory for the API reference. Refer to
[`CONTRIBUTING.md`](CONTRIBUTING.md) for development and release instructions.

## Assumptions and limitations

Read these limitations before you interpret a simulation, scenario, metric, or reuse
result.

- **Information timing.** A decision uses only a fact that is available at or before
  the decision cutoff. A complete bar becomes available at its interval end. Label
  ancestry and retrospective ancestry are not permitted decision inputs.
- **Vectorized simulation.** Vectorized simulation is a research approximation. It uses
  synthetic fractional fills and a specified capacity and cost policy. It does not
  model an order book or an intrabar path. It uses T0 settlement.
- **Event simulation.** Event simulation replays a specified order set against complete
  bars. A coarse observation clock controls the replay. Market-on-open and
  market-on-close orders select bar references. They do not make tick or intrabar
  claims. A deterministic proxy controls settlement. The simulator does not have a
  stateful strategy callback or a complete corporate-action entitlement engine.
- **Scenarios and search.** Historical, hypothetical, Monte Carlo, and bootstrap
  transformations are assumptions. They are not forecasts. Optuna TPE uses a seed for
  Bayesian search. Managed final-holdout protection is not available.
- **Metrics and models.** Results contain state, unit, population, and warning evidence.
  The system calculates drawdowns on the compounded time-weighted-return index. Direct
  forecasts are transforms, not fitted estimators. Risk models are covariance
  estimators, not a complete factor-risk system.
- **Currency.** The accounting and results layer uses one reporting currency, USD.
  Persistra supports non-USD market data and research. Simulation and accounting do not
  accept non-USD pair instruments.
- **Alpha Vantage.** Alpha Vantage supplies latest snapshots only. It does not supply
  vintages or as-reported history. Thus, each ingested family has
  `ingestion_bounded` availability. Persistra does not ingest fundamentals. Index
  coverage is small, spot FX bars do not have volume, and crypto and FX pairs use
  synthetic issuers and calendars. Persistra cannot represent stablecoin-quoted pairs,
  for example, BTC/USDT.
- **Logging.** Structured logs use key-based redaction only. The system cannot find a
  secret that has an unrelated key.
- **Reproducibility.** Semantic identities exclude allocated IDs, paths, PIDs, and
  completion time. Exact replay depends on the execution facts that each component
  records. Some results contain findings about material code, input overrides, reuse,
  or fidelity limits. Do not treat these results as clean evidence.
