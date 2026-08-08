# Persistra

Persistra is a typed Python library for acquiring, storing, analyzing, and plotting primary
market and economic data. Its provider-neutral pandas contracts cover bars, quotes,
top-of-book snapshots, historical option chains, scalar series, exchange rates, commodity
spot quotes, and reference data.

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO", periods=30)
print(bars.frame[["date", "close", "volume"]].tail())
```

Synthetic data uses the same normalized contracts as provider data, so examples and tests
run without credentials or network access. Alpha Vantage supplies primary market datasets.
FRED and ALFRED supply source-level economic observations and revision histories. Explicit
raw caching and DuckDB storage keep acquisition and persistence separate. Persistra requires
Python 3.12 or later. Point-in-time research transforms select available vintages, preserve
feature provenance, construct separate forward labels, evaluate cross-sectional equity signals,
generate purged and embargoed temporal splits, and record portable research manifests.

Start with the [installation guide](docs/getting-started/installation.md) and
[quickstart](docs/getting-started/quickstart.md). The documentation also includes complete
tutorials, task-focused guides, a [snippet cookbook](docs/examples/snippets.md), and a
module-level [API reference](docs/reference/index.md). Contributors should read
[CONTRIBUTING.md](CONTRIBUTING.md).
