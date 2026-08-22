# Build point-in-time research datasets

The `persistra.research` package keeps information availability, feature construction, signal
evaluation, and future outcomes separate. It accepts normalized vintage histories and ordinary
pandas frames. It does not choose favorable results or claim that a supplied equity universe is
survivorship-free.

## Select versions known on one date

Use `select_vintage` to select the active source version of every observation on an explicit
calendar date:

```python
from persistra.data import synthetic
from persistra.research import select_vintage

history = synthetic.vintage_series("GDP", periods=12)
known = select_vintage(history, known_on="2023-06-01")

print(known.frame[["period_label", "available_from", "value"]])
```

Availability boundaries are inclusive. The knowledge date and vintage availability fields
are timezone-naive calendar dates because `VintageSeriesSet` has daily source availability.
Retrieval time remains provenance and never determines which version is selected.

Pass a whole-day publication lag only when it is part of the research policy:

```python
import pandas as pd

lagged = select_vintage(
    history,
    known_on="2023-06-01",
    publication_lag=pd.Timedelta(days=2),
)
```

The lag moves the effective knowledge cutoff backward by two days. The result retains the
original source intervals and records the chosen lag separately.

## Compare explicit vintage-content policies

Use `project_vintage_history` when a study needs to isolate revision policy. The real-time
projection preserves every provider interval. The first-release projection ignores later
revisions. The final-vintage projection deliberately exposes each last retained value from its
observation's first recorded release date:

```python
from persistra.research import project_vintage_history

real_time = project_vintage_history(history, "real_time")
first_release = project_vintage_history(history, "first_release")
final_vintage = project_vintage_history(history, "final_vintage")
```

The first-release and final-vintage projections make their selected versions open-ended. They
preserve present, missing, and deleted states and never replace them with an older present
value. Record the chosen policy in the research manifest. Final vintage is intentionally
lookahead-biased and is useful as a comparison, not as a causal feature history.

## Assemble a feature panel

Each `FeatureSpec` requires a maximum staleness limit. It also names the normalized calendar
field that defines observation age. Use `period_start` or `period_end`; do not substitute
availability or retrieval time for the observation date.

```python
import pandas as pd

from persistra.research import FeatureSpec, build_feature_panel

decisions = pd.date_range("2023-03-01", periods=10, freq="MS")
spec = FeatureSpec(
    name="gdp",
    source=history,
    maximum_staleness=pd.Timedelta(days=120),
    publication_lag=pd.Timedelta(days=1),
    observation_date_column="period_start",
)

features = build_feature_panel([spec], decision_dates=decisions)

print(features.frame)
print(features.provenance)
```

For every decision date, the builder first selects source versions available under the lag
policy. It then chooses the most recent eligible observation date and rejects a match older
than `maximum_staleness`. An explicitly missing or deleted latest observation remains
missing. The builder does not fall back to an older nonmissing value.

`FeaturePanel.provenance` has one row for every feature and decision date. Matched rows record
the source series identity, provider key, period label, observation date, source availability
interval, retrieval time, age, lag, staleness limit, deletion state, and selected value.
Unmatched rows retain the source and policy fields. `FeaturePanel.policies` records the same
source identity and policy once per feature.

## Construct future labels separately

`forward_returns` calculates simple returns after feature construction. Its horizon is an
explicit count of index observations:

```python
from persistra.data import pivot_bars
from persistra.research import forward_returns

bars = synthetic.bars("ASSET", periods=30)
prices = pivot_bars([bars], field="close")
labels = forward_returns(prices, horizon=5)

print(labels.frame)
print(labels.label_ends)
```

`label_ends` records the actual index label at the end of each horizon. The final rows remain
missing when the requested future horizon does not exist. Feature panels and labels are
different result types so future values cannot enter feature construction by convenience.

## Fit caller-defined factor regressions

Factor models accept supplied return and exposure panels. They do not define, download, or
interpret factors. Time-series regressions require date-by-asset returns and date-by-factor
returns with the same index:

```python
import pandas as pd

from persistra.research import fit_time_series_factor_model

factor_dates = pd.date_range("2025-01-01", periods=8)
factor_returns = pd.DataFrame(
    {
        "factor_a": [-0.02, 0.01, 0.03, -0.01, 0.02, 0.00, 0.01, -0.01],
        "factor_b": [0.01, -0.01, 0.00, 0.02, -0.02, 0.01, 0.02, -0.01],
    },
    index=factor_dates,
)
asset_returns = pd.DataFrame(
    {
        "AAA": 0.001 + 1.2 * factor_returns["factor_a"],
        "BBB": -0.001 + 0.8 * factor_returns["factor_b"],
    },
    index=factor_dates,
)
model = fit_time_series_factor_model(
    asset_returns,
    factor_returns,
    covariance="newey_west",
    hac_lags=2,
)

print(model.coefficients)
print(model.standard_errors)
print(model.diagnostics)
```

Each asset uses its pairwise-complete observations. OLS is the default. Supply a positive
date-by-asset weight panel for WLS. Rank-deficient designs retain their least-norm coefficients
but mark inference unavailable. The result keeps fitted values and residuals on the original
axes. Use `rolling_time_series_factor_model` with a positive observation window, or with
`window=None` for expanding estimates. An estimate dated `t` never uses a later observation.

Cross-sectional regressions use a sorted `(date, asset)` MultiIndex exposure frame. Its columns
are caller-defined factors:

```python
import pandas as pd

from persistra.research import fama_macbeth_regression, forward_returns

factor_dates = pd.date_range("2025-01-01", periods=6)
assets = ["AAA", "BBB", "CCC", "DDD"]
levels = pd.DataFrame(
    {
        "AAA": [100, 101, 103, 102, 104, 105],
        "BBB": [100, 99, 100, 101, 100, 102],
        "CCC": [100, 102, 101, 103, 105, 104],
        "DDD": [100, 100, 101, 100, 102, 103],
    },
    index=factor_dates,
)
equity_labels = forward_returns(levels, horizon=1)

exposures = pd.DataFrame(
    {
        "date": [factor_dates[0]] * 4,
        "asset": assets,
        "exposure_a": [-1.0, -0.5, 0.5, 1.0],
        "exposure_b": [0.2, -0.2, -0.2, 0.2],
    }
).set_index(["date", "asset"])
exposures = exposures.reindex(
    pd.MultiIndex.from_product(
        [equity_labels.frame.index, assets],
        names=["date", "asset"],
    )
).groupby(level="asset").ffill()

fama_macbeth = fama_macbeth_regression(
    equity_labels,
    exposures,
    hac_lags=1,
)
print(fama_macbeth.cross_sectional.factor_returns)
print(fama_macbeth.premia.statistics)
```

Passing `ForwardReturnLabels` preserves the prediction horizon and excludes rows without a
complete label end. `estimate_cross_sectional_factor_returns` exposes each period regression.
`summarize_factor_premia` applies classical or Newey-West inference to any supplied factor-return
history. `build_factor_risk_model` combines current exposures, factor-return covariance, and
residual variance into a reconciled asset covariance matrix. Factor and residual histories must
use the same ordered datetime index. The optional observation window selects one trailing sample
from that shared index before covariance estimation. Missing return values remain missing within
that temporal sample and follow each estimator's documented complete-observation requirements.

Choose `sample`, `diagonal_shrinkage`, `constant_correlation`, `ledoit_wolf`, or `ewma` as the
factor covariance estimator. Diagonal and constant-correlation policies take the explicit
`shrinkage` value. EWMA takes `ewma_decay`. Ledoit-Wolf estimates and records its shrinkage
intensity. A complete, symmetric, positive-semidefinite factor covariance `DataFrame` may be
supplied instead. Every `FactorRiskModel` retains the estimator identity, effective parameters,
factor and residual observation counts, and portable `manifest_parameters`.

The risk model defaults `as_of` to the final timestamp in the effective sample. An explicit
boundary must be nonmissing, use the same timezone awareness as the histories, and be no earlier
than that timestamp. A later compatible boundary is allowed. The builder rejects histories that
extend beyond the boundary; it never silently truncates them. Optional diagonal shrinkage remains
an explicit model parameter. `build_factor_portfolio_forecast` then combines that risk model with
caller-supplied factor premia and optional asset alpha. It records each asset's expected-return
decomposition without assuming a factor definition, return frequency, or annualization. Use
`attribute_factor_portfolio` with absolute weights, or with benchmark weights for active
attribution, to reconcile expected return and variance to factor and idiosyncratic components.

Build a dated research-to-portfolio path with only the histories available at each date:

```python
import numpy as np

from persistra.portfolio import (
    MeanVarianceObjective,
    NetExposureConstraint,
    PortfolioProblem,
    WeightBounds,
    optimize_portfolio,
)
from persistra.research import rolling_factor_portfolio_forecasts

risk_dates = pd.date_range("2025-02-01", periods=6)
risk_factors = pd.DataFrame(
    {
        "market": [-0.02, 0.01, 0.03, -0.01, 0.02, 0.01],
        "quality": [0.01, -0.01, 0.00, 0.02, -0.02, 0.01],
    },
    index=risk_dates,
)
risk_residuals = pd.DataFrame(
    {
        "AAA": [0.01, -0.01, 0.005, 0.0, -0.005, 0.01],
        "BBB": [-0.005, 0.0, 0.01, -0.01, 0.005, 0.0],
    },
    index=risk_dates,
)
risk_assets = pd.Index(["AAA", "BBB"], name="asset")
risk_exposures = pd.DataFrame(
    np.tile([[1.0, 0.2], [0.5, 1.0]], (len(risk_dates), 1)),
    index=pd.MultiIndex.from_product([risk_dates, risk_assets], names=["date", "asset"]),
    columns=risk_factors.columns,
)
risk_premia = pd.DataFrame(
    {"market": [0.01] * len(risk_dates), "quality": [0.005] * len(risk_dates)},
    index=risk_dates,
)
forecast_path = rolling_factor_portfolio_forecasts(
    risk_exposures,
    risk_factors,
    risk_residuals,
    risk_premia,
    window=4,
    minimum_observations=3,
    covariance="ledoit_wolf",
)
available_forecasts = [step.forecast for step in forecast_path.steps if step.status == "ok"]
latest_forecast = available_forecasts[-1]
portfolio = optimize_portfolio(
    PortfolioProblem(
        covariance=latest_forecast.asset_covariance,
        expected_returns=latest_forecast.expected_returns,
        objective=MeanVarianceObjective(risk_aversion=10.0),
        constraints=(WeightBounds(0.0, 1.0), NetExposureConstraint(1.0, 1.0)),
        as_of=latest_forecast.as_of,
    )
)
print(forecast_path.diagnostics)
print(portfolio.weights)
```

`window=None` selects expanding history. Early dates and dates with unavailable exposures,
premia, alpha, or insufficient return history remain in the ordered result as typed unavailable
steps with reasons. Successful steps carry the covariance policy into their forecast. Changing a
later input cannot change an earlier step.

## Transform cross-sectional equity signals

Cross-sectional functions accept a wide date-by-asset frame. The ordered columns are the
explicit fixed universe for that call. Keep the same columns even when an asset has no
observation; use a missing value instead of silently changing the universe.

```python
import numpy as np
import pandas as pd

from persistra.research import (
    clip_cross_section,
    neutralize_cross_section,
    rank_cross_section,
    standardize_cross_section,
)

dates = pd.date_range("2025-01-02", periods=3)
signals = pd.DataFrame(
    [[-2.0, 0.1, 0.4, 8.0], [-1.0, 0.2, 0.5, 4.0], [0.0, np.nan, 0.8, 2.0]],
    index=dates,
    columns=["AAA", "BBB", "CCC", "DDD"],
)

ranks = rank_cross_section(signals)
clipped = clip_cross_section(signals, lower_quantile=0.05, upper_quantile=0.95)
standardized = standardize_cross_section(clipped)
```

Ranking exposes its tie method, direction, and percentile choice. Clipping uses per-date
quantiles. Standardization uses the available cross-section on each date and leaves a constant
cross-section missing because it has no scale.

Neutralization performs a separate least-squares regression on each date. Supply a date-by-asset
group panel for time-varying sector or other trustworthy classifications. Named numeric exposure
panels must use the same axes:

```python
groups = pd.DataFrame(
    [["technology", "technology", "health", "health"]] * len(dates),
    index=dates,
    columns=signals.columns,
)
size = pd.DataFrame(
    [[10.0, 12.0, 8.0, 9.0]] * len(dates),
    index=dates,
    columns=signals.columns,
)

residual = neutralize_cross_section(
    signals,
    groups=groups,
    exposures={"log_market_value": size},
)
```

The regression includes an intercept and group fixed effects. It uses only complete rows. A date
without enough observations to estimate the requested controls remains missing.

## Evaluate signal ordering and quantile portfolios

Information coefficients require `ForwardReturnLabels`, so every result retains the explicit
label horizon. Pearson and rank ICs use the same pairwise-complete sample and report its count:

```python
from persistra.research import forward_returns, information_coefficients

levels = pd.DataFrame(
    [[100.0, 100.0, 100.0, 100.0], [99.0, 100.5, 101.0, 102.0], [98.5, 101.0, 102.0, 103.0]],
    index=dates,
    columns=signals.columns,
)
equity_labels = forward_returns(levels, horizon=1)
ic = information_coefficients(ranks, equity_labels, minimum_count=3)
print(ic.statistics[["count", "pearson", "rank"]])
```

The signal and label frames must have identical dates and asset columns. Pass the group panel to
calculate separate ICs for each observed date and classification. Use `summarize_groups` to report
group-level signal means, forward returns, dispersion, ICs, and counts. A valid panel may have an
empty date axis. `forward_returns` and the signal evaluators preserve that input as typed,
schema-correct empty output instead of treating the absence of evaluation dates as an error.

`quantile_portfolios` uses explicit equal weighting by default. Supply nonnegative date-by-asset
weights for market-value, liquidity, inverse-volatility, or other caller-defined weighting. The
following example also applies a five-basis-point linear cost per unit of absolute asset weight
traded:

```python
from persistra.research import quantile_portfolios

volume = pd.DataFrame(
    [[1_000_000.0, 800_000.0, 700_000.0, 500_000.0]] * len(dates),
    index=dates,
    columns=signals.columns,
)
portfolio_weights = volume.copy()
quantiles = quantile_portfolios(
    ranks,
    equity_labels,
    quantiles=2,
    groups=groups,
    volumes=volume,
    weights=portfolio_weights,
    costs=0.0005,
)

print(quantiles.returns)
print(quantiles.costs)
print(quantiles.net_returns)
print(quantiles.spread)
print(quantiles.net_spread)
print(quantiles.turnover)
print(quantiles.weight_diagnostics)
print(quantiles.capacity)
```

Assignments are made independently on each date and within each supplied group. Ties stay
together. A group with fewer assets than the requested quantile count remains unassigned.
Raw weights are normalized within each date, group, and quantile; active group sleeves receive
equal portfolio weight. Missing and zero weights remain visible in `weight_diagnostics` alongside
raw coverage and effective membership after missing labels. Turnover includes the initial move
from cash and subsequent one-way formation changes.

Costs may be one nonnegative scalar, an asset-indexed `Series`, or a date-by-asset `DataFrame`.
Each value is a decimal return charge per unit of absolute asset weight bought or sold on that
formation date. These linear research costs are not fills, spread, impact, or order-level
execution. The result reports gross returns, costs, net returns, gross and net top-minus-bottom
spreads, and reconciled spread costs. Its summary includes gross and net compounded returns only
for a one-observation horizon, where labels do not overlap. Capacity fields report observed
volume count, total, median, and minimum separately from modeled costs. For a zero-date panel,
the aggregate summary retains each portfolio row with a period count of zero.

## Compare benchmarks and repeated searches

Compare one or more candidate return series with an aligned benchmark. The summary reports
pairwise counts, means, differences, tracking error, win rate, and correlation:

```python
from persistra.research import (
    adjust_pvalues,
    compare_benchmark,
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)

candidates = pd.DataFrame({"momentum_spread": quantiles.spread})
equal_weight = equity_labels.frame.mean(axis="columns")
comparison = compare_benchmark(
    candidates,
    equal_weight,
    benchmark_name="fixed_universe_equal_weight",
)

pvalues = pd.Series({"momentum": 0.01, "volume_trend": 0.04, "reversal": 0.20})
corrected = adjust_pvalues(
    pvalues,
    method="benjamini-hochberg",
    alpha=0.05,
)

selected_returns = quantiles.net_spread.dropna()
psr = probabilistic_sharpe_ratio(
    selected_returns,
    periods_per_year=252,
    benchmark_sharpe=0.5,
    skewness=0.1,
    kurtosis=3.4,
)
dsr = deflated_sharpe_ratio(
    selected_returns,
    periods_per_year=252,
    trial_count=40,
    trial_sharpe_standard_deviation=0.35,
    skewness=0.1,
    kurtosis=3.4,
)
```

`adjust_pvalues` supports Bonferroni family-wise error control and Benjamini-Hochberg false
discovery rate control. It adjusts supplied p-values; it does not infer a test or hide the number
of hypotheses searched.

`probabilistic_sharpe_ratio` implements the nonnormality-aware sampling approximation from
[Bailey and López de Prado's Sharpe ratio efficient frontier paper](https://ssrn.com/abstract=1821643).
Supply the annualization frequency, annualized benchmark Sharpe, skewness, and Pearson kurtosis;
the function does not infer these research choices. The result reports the observed
sample count, mean, standard deviation, annualized observed and benchmark Sharpes, sampling
standard error, test statistic, and probability. Insufficient or constant returns produce a
typed unavailable result with a reason.

`deflated_sharpe_ratio` uses the expected maximum independent-trial benchmark from the original
[deflated Sharpe ratio paper](https://ssrn.com/abstract=2460551). Supply the count of every trial
searched and the standard deviation of their annualized Sharpe ratios, including unsuccessful or
unreported candidates. It returns the expected-maximum benchmark and the same intermediate
estimates. The approximation assumes independent and identically distributed observations at the
declared frequency and does not correct serial dependence or correlated trials.

Neither probability proves out-of-sample validity. Use these search-aware diagnostics alongside
the nested temporal splits below, inspect unavailable results, and reserve the outer evaluation
windows for performance estimates that did not influence selection.

## Generate leakage-safe temporal splits

Expanding and rolling generators keep index order and never shuffle observations:

```python
from persistra.research import expanding_window_splits, rolling_window_splits

expanding = expanding_window_splits(
    labels,
    initial_train_size=15,
    evaluation_size=5,
    embargo=1,
)
rolling = rolling_window_splits(
    labels,
    train_size=15,
    evaluation_size=5,
    embargo=1,
)
```

The requested training size defines the candidate window before purging. A training row is
purged when its label end is on or after the first evaluation date. The optional embargo then
removes the requested number of safe observations nearest the evaluation boundary. Observation
counts, rather than calendar durations, keep this rule consistent with label horizons and
irregular trading calendars. Each returned `TemporalSplit` exposes `train_index`,
`evaluation_index`, `purged_index`, and `embargoed_index`.
`validate_temporal_split` rejects observation overlap, incomplete horizons, and training labels
that reach the evaluation period. It also requires embargoed rows to remain separate. A custom
`step` must be at least the evaluation size so evaluation blocks do not overlap.

For model or hyperparameter selection, nest inner validation splits entirely inside each outer
training window:

```python
from persistra.research import nested_expanding_window_splits

nested = nested_expanding_window_splits(
    labels,
    outer_initial_train_size=15,
    outer_evaluation_size=5,
    inner_initial_train_size=7,
    inner_evaluation_size=2,
    outer_embargo=1,
    inner_embargo=1,
)
```

Use each `NestedTemporalSplit.inner` sequence to select a model, refit that choice on the
corresponding `outer.train_index`, and evaluate it once on `outer.evaluation_index`. The outer
evaluation observations are unavailable to every inner train, validation, purge, and embargo
index by construction. Both levels use observation counts, so expanding and rolling variants
also work with irregular calendars. Every retained, purged, and embargoed index remains explicit
and typed for leakage assertions and audit records.

## Align a time-varying universe

Represent membership as dated intervals instead of inferring it from the surviving columns of a
wide panel. Every interval declares a stable asset identity, an included, excluded, or delisted
state, and source provenance:

```python
from datetime import UTC, datetime

import pandas as pd

from persistra.research import (
    MissingMembershipPolicy,
    UniverseMembership,
    apply_universe,
)

membership_frame = pd.DataFrame(
    [
        ("A", "2024-01-01", None, "included", "committee", "2023-12-31", datetime(2024, 1, 2, tzinfo=UTC)),
        ("B", "2024-01-02", None, "included", "committee", "2024-01-01", datetime(2024, 1, 2, tzinfo=UTC)),
    ],
    columns=[
        "asset_id", "valid_from", "valid_through", "state", "source", "source_as_of", "retrieved_at"
    ],
)
universe = UniverseMembership("committee-history", membership_frame)
candidate_signals = pd.DataFrame(
    {"A": [0.2, 0.1], "B": [0.9, 0.3]},
    index=pd.date_range("2024-01-01", periods=2, freq="D"),
)
eligible_signals = apply_universe(
    candidate_signals,
    universe,
    missing=MissingMembershipPolicy.EXCLUDE,
)
```

The first-date value for B becomes missing even though B survives into the current dataset. This
controlled distinction prevents future membership from leaking backward. Alignment never forward
fills: `MissingMembershipPolicy.ERROR` requires complete history, while `EXCLUDE` makes uncovered
cells ineligible. `DelistingPolicy.ERROR` rejects a delisted interval; `EXCLUDE` masks it. Apply the
same universe to level inputs before `forward_returns`, signal or classification panels before
evaluation, and signals before `construct_portfolio`. Existing missing-value contracts then retain
the complete asset axes without treating nonmembers as unavailable observations.

Add `universe.dataset_scope()` to the datasets passed to `create_research_manifest`. Its stable
content identity hashes normalized intervals and provenance, binding the research run to the exact
membership history rather than only a current constituent list.

## Record a portable research manifest

Use a versioned JSON manifest to connect dataset identity, parameters, environment versions, and
external output checksums without an experiment database:

```python
from persistra.research import (
    DatasetScope,
    create_research_manifest,
    write_research_manifest,
)

dataset = DatasetScope(
    name="daily_equities",
    scope={
        "symbols": list(levels.columns),
        "start": str(levels.index.min().date()),
        "end": str(levels.index.max().date()),
        "survivorship_free": False,
    },
    schema_version="bars-v1",
    snapshot_identity="duckdb:snapshot-42",
)
manifest = create_research_manifest(
    [dataset],
    feature_parameters={"momentum": {"lookback": 20, "lag": 1}},
    label_parameters={"horizon": equity_labels.horizon},
    split_parameters={"initial_train_size": 252, "evaluation_size": 21, "embargo": 1},
    benchmark_parameters={"name": "fixed_universe_equal_weight"},
    model_parameters={"factor_risk": latest_forecast.manifest_parameters},
    manifest_version=2,
    random_seeds={},
    execution_status="not-run",
)
write_research_manifest(manifest, "research-manifest.json")
```

Manifest publication is exclusive by default. Persistra writes and fsyncs a private file in the
destination directory before exposing the complete manifest. Pass `overwrite=True` only when
replacing an existing manifest is intentional; replacement is atomic.

`DatasetScope` requires a normalized schema version plus a content identity or stored snapshot
identity. `create_research_manifest` records Persistra and every declared base runtime dependency
by default. It also records the Python implementation, Python version, and stable
`system-machine` platform descriptor. Pass `include_runtime=False` to omit those facts in a
privacy-sensitive context, or use `runtime_overrides` to replace selected values explicitly. Call
`environment_versions(extras=("viz",))` or
`environment_versions(extras=("inspect",))` and pass the result as `environment` when optional
visualization or inspector dependencies participate in a run. The installed Persistra metadata is
the authoritative dependency inventory, so packaging tests detect declaration drift. Feature,
label, split, benchmark, and v2 model parameters and scopes may contain strings, integers, finite
floats, booleans, nulls,
string-keyed mappings, and sequences. Constructors recursively copy these portable JSON values,
expose mappings as read-only mappings, and expose sequences as tuples. A validated dataset scope
or manifest therefore keeps the same serialized representation for its lifetime. For completed
external research, call `identify_artifact` on each output and record the identities with execution
status `succeeded` or `failed`. Each identity includes the artifact name, SHA-256 checksum, and byte
size. `manifest_from_json` and `read_research_manifest` reject unknown or incomplete schema fields.

Load a supported Draft 2020-12 schema with `research_manifest_schema(version)`. The packaged v1
schema, Python parser, serializer, and [maintained example](../examples/research-manifest-v1.json)
are checked together so their contracts cannot drift. Version 1 remains strict. Version 2 adds
the `models` parameter family used above; unknown or removed fields are still rejected.

Verify completed outputs under an explicit trusted artifact directory:

```python
from pathlib import Path

from persistra.research import verify_manifest_artifacts

artifact_root = Path("research-artifacts")
artifact_root.mkdir(exist_ok=True)
verification = verify_manifest_artifacts(manifest, artifact_root)
verification.raise_for_errors()
```

Verification streams each regular file while recomputing its SHA-256 and byte size. It does not
follow symlinks or allow absolute and parent-traversal names. Structured findings distinguish
missing, unexpected, unsafe, resized, and content-modified artifacts. Set
`report_unexpected=False` only when the trusted root intentionally contains unrelated files.

Keep notebooks, live data, caches, figures, credentials, and generated manifests outside the
repository. The library does not need a CLI because the Python API writes and verifies one file
directly.

## Validate across periods and fixed universes

Treat aggregate statistics as a starting point. Check economically motivated signals such as
lagged price momentum, reversal, or volume trends across multiple periods and multiple explicit
fixed-universe slices. Compare them with simple baselines and retain missing coverage and sample
counts. A positive aggregate IC does not establish stability.

The automated suite exercises momentum and volume-trend examples on deterministic controlled
panels across two periods and two universe slices. This verifies calculation and slicing behavior;
it is not empirical evidence. Live or notebook validation belongs in an external research
workspace. Never construct historical fundamental factors from present-day company snapshots.
Point-in-time fundamental research needs a separate design for filings, amendments, taxonomies,
availability, security identity, and a survivorship-aware universe.

## Summarize explicit regimes

Supply a regime label for every return index row:

```python
from persistra.research import summarize_regimes

regimes = pd.Series(
    ["expansion", "contraction"] * 15,
    index=labels.frame.index,
)
summary = summarize_regimes(
    labels.frame,
    regimes,
    periods_per_year=252,
)

print(summary.coverage)
print(summary.regime_statistics)
```

The statistics report observed count, within-regime coverage, arithmetic mean return,
sample volatility, and maximum drawdown for each regime and return column. Volatility is
annualized only when `periods_per_year` is present. Drawdown resets when the regime changes
or a return is missing, so separate regime episodes are never compounded into a fictitious
continuous path.

The summary describes supplied regimes. It does not infer them, estimate a hidden classifier,
or interpret association as causal evidence.

## Carry research into a strategy

Keep the factor definitions, estimation window, inference choice, feature provenance, label
horizon, split policy, and model `as_of` with the resulting forecast. Use
`build_factor_portfolio_forecast` to connect a `FactorRiskModel` and caller-supplied premia to the
portfolio optimizer without discarding contribution detail.

For runtime use, update a model only from completed observations in `StrategyView.history`, or
load a frozen model through a declared strategy artifact. Use
[Develop a strategy](strategy-development.md) for lifecycle policy and the
[factor-model examples](../examples/factor-models.md) for complete regression-to-attribution
patterns.
