# Install

persistra requires Python 3.11 or newer.

## Recommended Setup

From the repository root:

```bash
uv sync --extra dev --extra docs
```

That installs the package, test tools, type checker, MkDocs, and documentation plugins.

## pip Setup

```bash
pip install -e ".[dev,docs]"
```

Optional extras:

```bash
pip install -e ".[dev,docs,tda,bayes]"
```

- `tda` installs optional topological-data-analysis feature transforms.
- `bayes` installs Optuna support for Bayesian parameter search.

## Check the Environment

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run mkdocs build --strict
```

For documentation changes, also execute runnable Markdown snippets:

```bash
uv run python scripts/check_doc_snippets.py
```

## Sample Data

The repository includes a small Parquet dataset under `examples/sample_data`. You do not
need an API key for the quickstart or first backtest.
