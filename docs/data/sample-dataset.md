# Sample Dataset

The repository ships with `examples/sample_data` so you can run examples without an API
key.

The sample includes:

- daily bars for a small equity universe
- hourly bars for a subset
- split and dividend records
- point-in-time universe membership

It is intentionally small enough to keep in git and broad enough to exercise the engine,
strategy, metrics, plotting, and experiment paths.

## Use It

```python
from persistra import ParquetMarketData
from persistra.data import UniverseQuery
import pandas as pd

data = ParquetMarketData("examples/sample_data")
symbols = data.universe(UniverseQuery(pd.Timestamp("2022-01-03"), pd.Timestamp("2022-12-30")))
print(len(symbols) > 0)
```

## Rebuild It

The core package keeps the committed sample Parquet dataset for tests and
examples, but provider-specific ingestion code lives outside this repository.
Rebuild or extend the dataset with an external provider package or maintenance
workflow that writes the canonical `MarketDataWriter` tables described in
[Parquet Layout](parquet-layout.md).
