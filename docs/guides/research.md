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
residual variance into a reconciled asset covariance matrix. Optional diagonal shrinkage remains
an explicit model parameter.

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
group-level signal means, forward returns, dispersion, ICs, and counts.

`quantile_portfolios` forms equal-weight portfolios without modeling execution:

```python
from persistra.research import quantile_portfolios

volume = pd.DataFrame(
    [[1_000_000.0, 800_000.0, 700_000.0, 500_000.0]] * len(dates),
    index=dates,
    columns=signals.columns,
)
quantiles = quantile_portfolios(
    ranks,
    equity_labels,
    quantiles=2,
    groups=groups,
    volumes=volume,
)

print(quantiles.returns)
print(quantiles.spread)
print(quantiles.turnover)
print(quantiles.capacity)
```

Assignments are made independently on each date and within each supplied group. Ties stay
together. A group with fewer assets than the requested quantile count remains unassigned.
Returns use available forward labels. Turnover measures one-way changes in equal membership
weights between adjacent formation dates. Capacity fields report observed volume count, total,
median, and minimum; they are diagnostics, not an execution or market-impact model. The result
also exposes assignments, asset counts, top-minus-bottom spreads, and aggregate summaries.

## Compare benchmarks and repeated searches

Compare one or more candidate return series with an aligned benchmark. The summary reports
pairwise counts, means, differences, tracking error, win rate, and correlation:

```python
from persistra.research import adjust_pvalues, compare_benchmark

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
```

`adjust_pvalues` supports Bonferroni family-wise error control and Benjamini-Hochberg false
discovery rate control. It adjusts supplied p-values; it does not infer a test or hide the number
of hypotheses searched.

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
    random_seeds={},
    execution_status="not-run",
)
write_research_manifest(manifest, "research-manifest.json")
```

`DatasetScope` requires a normalized schema version plus a content identity or stored snapshot
identity. `create_research_manifest` records Persistra and its direct runtime dependency versions
by default. Parameters and scopes must contain portable JSON values. For completed external
research, call `identify_artifact` on each output and record the identities with execution status
`succeeded` or `failed`. Each identity includes the artifact name, SHA-256 checksum, and byte size.
`manifest_from_json` and `read_research_manifest` reject unknown or incomplete schema fields.

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
