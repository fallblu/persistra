# Assumptions and limitations

Read this before interpreting simulation, scenario, metric, log, or compatibility-reuse
output.

## Information timing

Research decisions consume only facts whose persisted availability is at or before the
decision cutoff. Complete daily/bar facts become observable at their interval end. Label
and retrospective ancestry is structurally ineligible for portfolio or simulator
decisions. Opaque inputs require a content-addressed override and remain visibly tainted
in downstream results, exports, and reports.

## Vectorized simulation

The vectorized engine is a research approximation. It converts precomputed targets into
synthetic fractional fills under its declared capacity/cost policy. It does not model an
order book or intrabar path, and it records that limitation in fidelity findings
(including `simulation.vectorized.no_orders`). Its settlement treatment is T0; use the
event engine when later effective settlement is material.

## Event simulation

The event engine replays a complete, predeclared set of orders against completed bars. An
order cannot consume the bar that precedes its eligibility boundary. Market-on-open and
market-on-close names select a bar reference under this coarse observation clock; they are
not tick/intrabar claims. Settlement uses a deterministic later-observed-market-session
proxy, not a full venue/holiday settlement-calendar entitlement engine. The engine does
not call a stateful strategy, expose observation/portfolio contexts, resume strategy
state, generate forced margin orders, or process the full corporate-action entitlement
surface.

## Scenarios and search

Historical, hypothetical, Monte Carlo, and bootstrap transformations are scenario
assumptions, not forecasts or causal facts. `apply_scenario` operates on the numeric input
path supplied by the worker; the coordinator never silently mutates canonical market data.
Bayesian search uses seeded Optuna TPE ask/tell rounds over only the previously persisted
trial objectives; discrete duplicates are rejected and deterministically replaced.
Final-holdout protection is not yet a managed experiment capability.

## Metrics and models

Metric results include state, unit, population, and warning evidence. `max_drawdown` and
`drawdown_duration` are computed on the compounded time-weighted-return index, so external
cash flows neither mask nor fabricate drawdowns. Money-weighted return solves the dated
root from initial/final NAV and normalized external cash flows. Turnover uses absolute
fill notional. `cost_total` is reported both in aggregate and per cost component.
Supplying misaligned optional metric input series (risk-free returns, benchmark returns,
eligible fill volumes) raises `AnalysisInputError` at request time; absent inputs yield
explicit `missing_input` states. Direct forecasts are transforms, not fitted estimators;
risk models are covariance estimators, not a complete factor-risk system.

## Alpha Vantage and multi-asset data

Alpha Vantage serves latest snapshots only: no vintages and no as-reported history.
Every family ingested through the bundled adapter therefore carries
`ingestion_bounded` availability quality — the persisted availability instant is the
ingestion time, not a source-published instant. Fundamentals are not ingested (the
pre-normalized Alpha Vantage feed does not fit the strict filing model), index
coverage is thin, and technical indicators are derived in research features rather
than ingested. Spot FX bars are volume-less (`BarState.NO_VOLUME`); crypto and FX
pair instruments use a synthetic market-convention issuer and synthetic 24×7/24×5
calendars. Pair quote currencies must be registered ISO 4217 codes, so
stablecoin-quoted markets (for example BTC/USDT) cannot be represented; re-fetching
unchanged macro data reproduces the same content-derived release identity, and
deduplication of identical releases is the ingestion service's concern. Non-USD
market data and research are supported, but the
accounting/results layer is single-reporting-currency (USD): feeding non-USD pair
instruments into simulation or accounting is unsupported.

## Logging and redaction

Structured run logs apply key-based redaction only: values under keys matching sensitive,
path, or payload fragments are replaced, and other values are bounded and truncated but
not content-scanned. A secret stored under an innocuous key is not detected. Long context
keys are truncated with a hash suffix so distinct keys cannot collide.

## Reproducibility

Semantic identities exclude allocated IDs, paths, PIDs, and completion time. Exact replay
still depends on the execution facts recorded by each component. Results carrying unknown
material code, unsafe input overrides, compatibility reuse, or fidelity limitations retain
those findings and must not be represented as clean exact evidence.
