# Assumptions and limitations

## Information timing

Research decisions consume only facts whose persisted availability is at or before the
decision cutoff. Complete daily/bar facts become observable at their interval end. Label and
retrospective ancestry is structurally ineligible for portfolio or simulator decisions.
Opaque inputs require a content-addressed override and remain visibly tainted in downstream
results, exports and reports.

## Vectorized simulation

The vectorized engine is a research approximation. It converts precomputed targets into
synthetic fractional fills under its declared capacity/cost policy. It does not model an
order book or intrabar path, and it records that limitation in fidelity findings. Its current
settlement treatment is T0; use the event engine when later effective settlement is material.

## Event simulation

The event engine replays a complete, predeclared set of orders against completed bars. An
order cannot consume the bar that precedes its eligibility boundary. Market-on-open and
market-on-close names select a bar reference under this coarse observation clock; they are not
tick/intrabar claims. Settlement uses a deterministic later-observed-market-session proxy,
not a full venue/holiday settlement-calendar entitlement engine.

The event engine does not currently call a stateful strategy, expose observation/portfolio
contexts, resume strategy state, generate forced margin orders, or process the full corporate
action entitlement surface. These capabilities are unavailable rather than inferred from the
presence of event/order tables.

## Scenarios and search

Historical, hypothetical, Monte Carlo and bootstrap transformations are scenario assumptions,
not forecasts or causal facts. `apply_scenario` operates on the numeric input path supplied by
the worker. A worker must deliberately use the resolved scenario input; the coordinator never
silently mutates canonical market data.

Bayesian search uses seeded Optuna TPE ask/tell rounds. Only the previous persisted trial
objectives enter the next suggestion. Discrete duplicates are rejected and deterministically
replaced from the remaining declared grid. Objective callbacks are responsible for returning
an eligible validation/analysis value; final-holdout protection is not yet a managed
experiment capability.

## Metrics and models

Metric results include state, unit, population and warning evidence. Money-weighted return is
currently available only for runs without external cash flows; in that case it equals the
annualized time-weighted return and carries an assumption warning. Direct forecasts are
transforms, not fitted statistical estimators. Risk models are covariance estimators, not a
complete factor-risk system.

## Reproducibility

Semantic identities exclude allocated IDs, paths, PIDs and completion time. Exact replay still
depends on the execution facts recorded by each component. Results with unknown material code,
unsafe input overrides, compatibility reuse or fidelity limitations retain those findings and
must not be represented as clean exact evidence.
