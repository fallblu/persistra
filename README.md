# Persistra

Persistra is a typed Python library for acquiring, storing, exploring, and plotting primary
market and economic data. Its provider-neutral pandas contracts cover bars, quotes,
top-of-book snapshots, historical option chains, scalar series, and reference data. The
first provider adapter supports the primary Alpha Vantage datasets available at the
150-request-per-minute tier.

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO", periods=30)
print(bars.frame[["date", "close", "volume"]].tail())
```

Synthetic data uses the same normalized contracts as provider data, so examples and tests
run without credentials or network access. Persistra requires Python 3.12 or later.

See the [documentation](docs/index.md) and [contributor guide](CONTRIBUTING.md).
