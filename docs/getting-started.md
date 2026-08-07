# Getting started

Install Persistra in a Python 3.12 or later environment. Runtime support targets Linux.

```bash
python -m pip install persistra
```

Start offline with deterministic synthetic data. It uses the same result types and exact
pandas schemas as provider acquisition.

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO", periods=30)
print(bars.frame[["date", "close"]].tail())
```

Every result keeps observations, identity, and acquisition metadata separate:

```python
print(bars.instrument.instrument_id)
print(bars.metadata.provider)
print(bars.frame.dtypes)
```

For Alpha Vantage, put the key in the environment and construct the namespaced client:

```bash
export PERSISTRA_ALPHAVANTAGE_API_KEY="your-key"
```

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env(requests_per_minute=150)
result = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
)
```

Acquisition never writes to storage. Save only after inspecting the normalized result:

```python
from pathlib import Path

from persistra.data import DuckDBStore

with DuckDBStore.create(Path("research.duckdb")) as store:
    snapshot_id = store.save(result)
    restored = store.load_bars(result.instrument.instrument_id)
```

Use `DuckDBStore.open` for an existing database. Creation refuses to replace a file, and
opening refuses to migrate an unsupported schema. See [data model and storage](data-model.md)
before building a persistent dataset.
