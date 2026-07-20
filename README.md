# Persistra

Persistra v3 is a local-first Python library for point-in-time market research, strategy
development, and event-driven backtesting. Python 3.12+. All research, search,
optimization, visualization, and dashboard capabilities install with the base package;
there are no optional extras. The API reference is in [`docs/`](docs/index.md).

## Commands

```bash
uv sync --extra dev --extra docs   # set up
make lint type test docs-check     # ruff, pyright (strict), pytest+coverage, doc checks
make docs-build                    # strict mkdocs build
```

## Releases

Version changes, builds, tags, pushes, and publication are human-controlled; a branch is
pre-release until those steps are performed, and no code infers release state from the
branch name. Release readiness requires the mechanical gate to pass on Python 3.12–3.14:
`make lint type test docs-check docs-build schema-check`, `uv lock --check`, and a clean
install of the built package. The coverage floor is 85% (`--cov-fail-under`) and only
ratchets upward. Human release steps: inspect wheel/sdist content and license, update the
version in `pyproject.toml`, then build, sign, tag, push, and publish.

## Assumptions and limitations

Read before interpreting simulation, scenario, metric, or reuse output.

- **Information timing.** Decisions consume only facts whose persisted availability is at
  or before the decision cutoff; complete bars become observable at their interval end;
  label/retrospective ancestry is ineligible for decisions.
- **Vectorized simulation.** A research approximation: synthetic fractional fills under a
  declared capacity/cost policy, no order book or intrabar path, T0 settlement.
- **Event simulation.** Replays a predeclared order set against completed bars under a
  coarse observation clock (market-on-open/close select bar references, not tick/intrabar
  claims) with a deterministic settlement proxy; no stateful strategy callback or full
  corporate-action entitlement engine.
- **Scenarios and search.** Historical, hypothetical, Monte Carlo, and bootstrap
  transformations are assumptions, not forecasts. Bayesian search is seeded Optuna TPE;
  managed final-holdout protection is not yet available.
- **Metrics and models.** Results carry state, unit, population, and warning evidence;
  drawdowns are computed on the compounded time-weighted-return index. Direct forecasts
  are transforms, not fitted estimators; risk models are covariance estimators, not a full
  factor-risk system.
- **Currency.** The accounting/results layer is single-reporting-currency (USD). Non-USD
  market data and research are supported, but feeding non-USD pair instruments into
  simulation or accounting is not.
- **Alpha Vantage.** Latest snapshots only (no vintages or as-reported history), so every
  ingested family carries `ingestion_bounded` availability. Fundamentals are not ingested,
  index coverage is thin, spot FX bars are volume-less, and crypto/FX pairs use synthetic
  issuers and calendars; stablecoin-quoted pairs (e.g. BTC/USDT) cannot be represented.
- **Logging.** Structured logs apply key-based redaction only; a secret stored under an
  innocuous key is not detected.
- **Reproducibility.** Semantic identities exclude allocated IDs, paths, PIDs, and
  completion time; exact replay depends on the execution facts each component records.
  Results carrying unknown material code, unsafe input overrides, compatibility reuse, or
  fidelity limitations retain those findings and must not be treated as clean evidence.
