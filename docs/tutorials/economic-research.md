# Tutorial: study economic series

This tutorial works with normalized scalar series. You will compare commodity and economic
levels, calculate growth and rate changes, construct observed Treasury curves, and visualize
the results without interpolation.

## 1. Create normalized series

```python
from persistra.data import synthetic
from persistra.model import SeriesKind

production = synthetic.series(
    "PRODUCTION",
    periods=36,
    frequency="monthly",
    kind=SeriesKind.ECONOMIC,
    unit="index",
)
commodity = synthetic.series(
    "COMMODITY",
    periods=36,
    frequency="monthly",
    kind=SeriesKind.COMMODITY,
    unit="USD",
)

print(production.definition)
print(production.frame.tail())
```

A `SeriesSet` contains a `SeriesDefinition`, an exact observation frame, and
`ResultMetadata`. Native frequency, unit, geography, seasonal adjustment, and maturity stay
attached to the series rather than being inferred downstream.

## 2. Pivot compatible series

```python
from persistra.data import pivot_series

levels = pivot_series([production, commodity])
levels.columns = ["Production", "Commodity"]

print(levels.tail())
```

`pivot_series` requires one frequency across the inputs. It preserves the provider's period
labels and does not invent period boundaries.

## 3. Calculate growth

`growth_rate` returns fractional growth over an explicit positive lag:

```python
from persistra.analysis import growth_rate, summary_statistics

monthly_growth = growth_rate(levels, lag=1)
annual_growth = growth_rate(levels, lag=12)

print(monthly_growth.tail())
print(summary_statistics(annual_growth).round(4))
```

The function does not annualize monthly growth or fill missing levels. The lag defines the
comparison directly.

## 4. Calculate basis-point changes

Create deterministic Treasury series and pivot them into a wide rate frame:

```python
from persistra.analysis import basis_point_change
from persistra.data import pivot_series, synthetic

treasuries = synthetic.treasury_curve(periods=18)
rates = pivot_series(treasuries)
rates.columns = [series.definition.maturity for series in treasuries]

rate_changes = basis_point_change(
    rates,
    rate_unit="percent",
    periods=1,
)

print(rate_changes.tail())
```

The input unit is required because a one-unit change means different things for percentage
points and decimal rates. Use `rate_unit="percent"` for values such as `4.25` percent and
`rate_unit="decimal"` for values such as `0.0425`.

## 5. Construct observed yield curves

Build one curve at an actual period label and a history table across all labels:

```python
from persistra.analysis import yield_curve, yield_curve_history

period_label = treasuries[0].frame["period_label"].iloc[-1]
curve = yield_curve(treasuries, period_label=period_label)
history = yield_curve_history(treasuries)

print(curve)
print(history.tail())
```

The functions do not interpolate a missing maturity. The curve contains only observed
values, and the history retains missing cells.

## 6. Visualize levels, changes, and curves

```python
import matplotlib.pyplot as plt

from persistra.viz import (
    plot_scalar_series,
    plot_series_change,
    plot_yield_curve,
    plot_yield_curve_history,
)

figure, axes = plt.subplots(2, 2, figsize=(12, 8))

plot_scalar_series(production, ax=axes[0, 0])
axes[0, 0].set_title("Production level")

plot_series_change(annual_growth, ylabel="12-month growth", ax=axes[0, 1])
plot_yield_curve(curve, ax=axes[1, 0])
plot_yield_curve_history(history, ax=axes[1, 1])

figure.tight_layout()
plt.show()
```

The history heatmap is noninterpolated. It shows missing observations rather than smoothing
over them.

## 7. Store the normalized series

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore

with TemporaryDirectory() as directory:
    path = Path(directory) / "economics.duckdb"
    with DuckDBStore.create(path) as store:
        store.save(production)
        restored = store.load_series(production.definition.series_id)
        recent = store.query_series(
            production.definition.series_id,
            start_label="2025-01",
        )

    assert restored is not None
    print(recent)
```

Period-label filters are inclusive string filters applied inside DuckDB. Use labels that
match the normalized source frequency and format.

For provider-backed economic and commodity series, continue with
[Acquire data](../guides/acquisition.md).
