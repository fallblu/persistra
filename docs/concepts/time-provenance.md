# Time and provenance

Time fields answer different questions. Persistra keeps them separate so a retrieval time is
not mistaken for a market event, and a calendar period is not forced into an arbitrary
instant.

## Calendar labels and instants

Daily and lower-frequency bars use the timezone-naive `date` column. Intraday bars use the
UTC-aware `timestamp` column. Exactly one applies to each bar row.

```python
from persistra.data import synthetic

daily = synthetic.bars("DAILY", interval="daily")
intraday = synthetic.bars("INTRADAY", interval="5min")

assert daily.frame["date"].notna().all()
assert daily.frame["timestamp"].isna().all()
assert intraday.frame["timestamp"].notna().all()
assert intraday.frame["date"].isna().all()
```

For intraday bars, `source_timezone` retains the provider's timezone and
`timestamp_position` records what the provider label means. Normalized timestamps are UTC
instants.

## Scalar period labels

Commodity and economic series retain the provider's `period_label`. `period_start` and
`period_end` remain missing unless the source gives enough information to populate them
without inference.

This matters for labels such as a month, quarter, or semiannual period: choosing a start,
end, publication date, or midpoint would change the meaning.

```python
from persistra.data import synthetic

series = synthetic.series("CPI", frequency="monthly")
print(series.frame[["period_label", "period_start", "period_end"]].tail())
```

## Observation time

`observed_at` is the event or snapshot time attached to an observation when one applies. A
latest daily quote may instead have a calendar `latest_trading_day`. These fields are part of
the result schema and can be missing when the provider does not supply them.

## Provider as-of time

`provider_as_of` records the provider's stated as-of time. It appears in result metadata and,
where row-level meaning is needed, in normalized frames. It must be timezone-aware when
present.

Persistra does not substitute retrieval time when provider as-of time is absent.

## Retrieval time

`retrieved_at` records when Persistra obtained the source response or created deterministic
synthetic provenance. It answers, "When did this system observe the data?"

```python
result = synthetic.bars("DEMO")

print(result.metadata.retrieved_at)
print(result.frame["retrieved_at"].head())
```

Retrieval time supports reproducibility, cache diagnostics, and DuckDB revisions. It does not
claim that the observation occurred at that instant.

## Entitlement and cache provenance

`ResultMetadata.entitlement` records historical, delayed, realtime, or nonapplicable access.
`cache_status` records whether the raw response was a hit, miss, refresh, offline read, or not
used.

These fields belong in analysis inputs and reports when freshness or access mode can affect
interpretation.

## Retrieval-time revisions

`DuckDBStore` identifies snapshots by normalized content within a family and scope. Identical
content updates its last-seen time. Changed content creates another first-seen revision.

A `retrieved_before` query asks for the latest content Persistra had first observed by a
timezone-aware cutoff:

```python
from datetime import UTC, datetime

from persistra.data import DuckDBStore

cutoff = datetime(2025, 2, 1, tzinfo=UTC)

with DuckDBStore.open("research.duckdb", read_only=True) as store:
    result = store.load_bars(
        instrument_id,
        retrieved_before=cutoff,
    )
```

This supports observation-history reconstruction. It is not the same as provider-native
vintage data and does not recover a revision that Persistra never observed.

## As-of joins require a staleness limit

Backward as-of matching can make an old value look current unless its age is visible.
`asof_align` therefore requires `maximum_staleness` and returns `matched_label` plus
`matched_age`:

```python
import pandas as pd

from persistra.data import asof_align

aligned = asof_align(
    left_frame,
    right_frame,
    maximum_staleness=pd.Timedelta(days=3),
)
```

Choose the limit from the meaning and expected cadence of the right-hand data, not merely to
maximize matched rows.

## Questions to ask before combining data

Before a join, resample, or return calculation, identify:

1. Is each label a calendar date, period label, or instant?
2. Which timezone defines an intraday bucket?
3. Does the provider label the start or end of an interval?
4. How old may a matched observation be?
5. Is a missing value absent, not applicable, or explicitly reported as missing?
6. Does retrieval time constrain what the system knew, or only when it downloaded a payload?

Persistra exposes the fields needed to answer these questions but leaves the research policy
to the caller.
