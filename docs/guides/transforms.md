# Reshape and align data

Persistra's transform utilities convert normalized result objects into research-ready pandas
objects while keeping policy choices explicit. They copy inputs and do not fill missing
observations.

## Pivot bars into a wide frame

Use `pivot_bars` for one normalized bar field across several `BarSet` objects:

```python
from persistra.data import pivot_bars, synthetic

first = synthetic.bars("FIRST", periods=30, seed=1)
second = synthetic.bars("SECOND", periods=30, seed=2)

closes = pivot_bars([first, second], field="close")
volumes = pivot_bars([first, second], field="volume")
```

Supported fields are `open`, `high`, `low`, `close`, `adjusted_close`, and `volume`.
Columns use `(provider, instrument_id)` labels so two providers do not silently collapse into
one identity. Each input identity must be unique. Choose one acquisition snapshot before
pivoting when several snapshots have the same provider and instrument identity.

Daily and intraday rows cannot be mixed in one pivot or inside one input because their temporal
identities differ.

## Pivot scalar series

```python
from persistra.data import pivot_series, synthetic

first_series = synthetic.series("FIRST", frequency="monthly")
second_series = synthetic.series("SECOND", frequency="monthly")

values = pivot_series([first_series, second_series])
```

All inputs must have the same frequency and a unique `(provider, series_id)` identity. Choose
one revision or acquisition snapshot for an identity before pivoting. Resample outside Persistra
when a research question requires a frequency conversion, then document the aggregation rule.

## Align by intersection or union

`align` accepts named pandas `Series` or `DataFrame` objects. Choose the label set directly:

```python
import pandas as pd

from persistra.data import align

first = pd.Series(
    [1.0, 2.0, 3.0],
    index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
)
second = pd.Series(
    [10.0, 20.0, 30.0],
    index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-04"]),
)

common = align({"first": first, "second": second}, how="intersection")
complete_calendar = align({"first": first, "second": second}, how="union")
```

Intersection retains only labels shared by every input. Union retains every observed label
and introduces missing cells where an input has no observation. Neither mode fills values. Every
input index must be unique because the shared output axis has no occurrence identity.

## Perform a bounded as-of alignment

Use `asof_align` when a left observation may match the most recent earlier right observation.
The maximum staleness is mandatory:

```python
import pandas as pd

from persistra.data import asof_align

trades = pd.DataFrame(
    {"price": [100.0, 101.0]},
    index=pd.to_datetime(
        ["2025-01-02 14:31:00Z", "2025-01-02 14:36:00Z"]
    ),
)
indicators = pd.DataFrame(
    {"signal": [0.2, 0.4]},
    index=pd.to_datetime(
        ["2025-01-02 14:30:00Z", "2025-01-02 14:35:00Z"]
    ),
)

matched = asof_align(
    trades,
    indicators,
    maximum_staleness=pd.Timedelta(minutes=2),
)

print(matched[["price", "signal", "matched_label", "matched_age"]])
```

The result records both the matched source label and its age. Values older than the limit
remain unmatched. Both inputs must have a `DatetimeIndex`; the function sorts copies before
matching. The right source index must be unique so a match does not depend on incidental row
order. Input columns cannot use the generated names `left_label`, `matched_label`, or
`matched_age`, or names that collide with `_left` and `_right` merge suffixes.

## Resample intraday bars

`resample_bars` requires a frequency, timezone, and selected sessions:

```python
import pandas as pd

from persistra.data import resample_bars, synthetic
from persistra.model import BarSet

intraday = synthetic.bars(
    "DEMO",
    periods=120,
    interval="5min",
    session="regular",
)

# Synthetic timestamps intentionally have unknown provider-label semantics. A real workflow
# can make this conversion only after establishing the provider convention.
intraday_frame = intraday.frame.copy()
intraday_frame["timestamp_position"] = pd.Series(
    ["start"] * len(intraday_frame), dtype="string"
)
intraday = BarSet(intraday.instrument, intraday_frame, intraday.metadata)

hourly = resample_bars(
    intraday,
    frequency="1h",
    timezone="America/New_York",
    sessions={"regular"},
)
```

The aggregation applies conventional OHLCV rules:

- `open`: first observation
- `high`: maximum observation
- `low`: minimum observation
- `close`: last observation
- `volume`: sum with missingness preserved when no value applies
- adjusted and corporate-action fields: field-specific last or sum behavior

Output timestamps are normalized back to UTC, while `source_timezone` records the timezone
used to form the buckets. Start-labeled sources use left-closed intervals. End-labeled sources
use right-closed intervals. Derived output labels always identify interval starts. Sources with
`provider_label` or mixed label conventions are ambiguous and must be normalized under an
explicit provider policy before resampling. The result metadata records both the source and
output timestamp positions and identifies the frame as a local derived result.

!!! note

    Synthetic intraday timestamps use daily-spaced labels even when the interval name is
    intraday. They test the contract and API, not a realistic exchange session schedule.

## Preserve gaps intentionally

Transforms are deliberately conservative. If a workflow needs forward filling,
interpolation, calendar expansion, winsorization, or another statistical policy, apply it in
ordinary pandas code after the explicit Persistra transform:

```python
union = align({"prices": closes, "volumes": volumes}, how="union")

# This is a caller-owned research choice, not a Persistra default.
filled_prices = union["prices"].ffill(limit=1)
```

Keep that choice close to the analysis that depends on it and test it against the missing-data
patterns expected in the dataset.
