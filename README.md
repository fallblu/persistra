# persistra

![coverage](https://img.shields.io/badge/coverage-%E2%89%A585%25-brightgreen)

**Tooling for market research, strategy development, and event-driven backtesting.**

## Install

Requires Python 3.11+.

```bash
uv sync --extra dev --extra docs
```

Or with pip:

```bash
pip install -e ".[dev,docs]"
```

Optional extras:

```bash
pip install -e ".[dev,docs,tda,bayes]"
```

## Quickstart

The repository includes a small sample Parquet dataset under `examples/sample_data`, so
you can run a backtest without an API key.

```python
from persistra import Engine, EqualWeightRebalance, ParquetMarketData, Portfolio
from persistra.metrics import benchmark_free_summary

result = Engine(
    data=ParquetMarketData("examples/sample_data"),
    strategy=EqualWeightRebalance(every=21),
    portfolio=Portfolio(initial_capital=1_000_000.0),
    start="2022-01-03",
    end="2023-12-29",
).run()

print(benchmark_free_summary(result.equity_curve["equity"]))
```

## Documentation

The MkDocs site is the main documentation surface:

```bash
uv run mkdocs serve
```

## Local Validation

Use the Makefile targets for the same checks CI runs:

```bash
make lint
make type
make test
make docs-check
make docs-build
make build
```

In restricted environments where the default uv cache is not writable, prefix
commands with `UV_CACHE_DIR=.uv-cache`.

## License

MIT. See [LICENSE](LICENSE).
