# Build point-in-time research datasets

The `persistra.research` package keeps information availability, feature construction, and
future outcomes separate. It accepts normalized vintage histories and ordinary pandas frames.
It does not choose feature definitions, regimes, models, or favorable results.

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

## Generate leakage-safe temporal splits

Expanding and rolling generators keep index order and never shuffle observations:

```python
from persistra.research import expanding_window_splits, rolling_window_splits

expanding = expanding_window_splits(
    labels,
    initial_train_size=15,
    evaluation_size=5,
)
rolling = rolling_window_splits(
    labels,
    train_size=15,
    evaluation_size=5,
)
```

The requested training size defines the candidate window before purging. A training row is
purged when its label end is on or after the first evaluation date. Each returned
`TemporalSplit` exposes `train_index`, `evaluation_index`, and `purged_index`.
`validate_temporal_split` rejects observation overlap, incomplete horizons, and training
labels that reach the evaluation period. A custom `step` must be at least the evaluation
size so evaluation blocks do not overlap.

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
