# Installation

Persistra requires Python 3.12 or later and supports Linux. Install it into an isolated
environment so its NumPy, SciPy, pandas, Matplotlib, DuckDB, Requests, and platform-directory
dependencies do not conflict with another project.

## Install from PyPI

Create and activate a virtual environment with the standard library:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install persistra
```

Confirm the import and installed version:

```python
import persistra

print(persistra.__version__)
```

## Install with uv

If your project uses [uv](https://docs.astral.sh/uv/), add Persistra to the project:

```bash
uv add persistra
```

Run a short offline check:

```bash
uv run python -c "from persistra.data import synthetic; print(len(synthetic.bars().frame))"
```

## Install a development checkout

Clone the repository and synchronize the runtime, development, and documentation groups:

```bash
git clone https://github.com/fallblu/persistra.git
cd persistra
uv sync --group dev --group docs
make pre-commit-install
```

Run the complete local verification gate before contributing:

```bash
make verify
```

The gate runs linting, strict type checking, tests with coverage, documentation validation, a
strict MkDocs build, package builds, installation smoke tests, and a lockfile check. See the
[contributor guide](https://github.com/fallblu/persistra/blob/develop/CONTRIBUTING.md) for the
branch and commit workflow.

## Provider credentials are optional

The base install is enough for every synthetic-data example and all local analysis,
visualization, transformation, and storage features. You need the corresponding provider API
key only when you call an Alpha Vantage or FRED adapter.

Do not put keys in source files, notebooks, shell history, or committed environment files.
When you are ready to acquire data, continue to [Connect Alpha Vantage](alpha-vantage.md) or
[Connect FRED and ALFRED](fred.md).

## Verify the environment

This example exercises the normalized data and analysis layers without touching the network
or filesystem:

```python
from persistra.analysis import summary_statistics
from persistra.data import pivot_bars, synthetic

bars = synthetic.bars("CHECK", periods=10)
closes = pivot_bars([bars], field="close")
summary = summary_statistics(closes)

assert len(bars.frame) == 10
assert not summary.empty
print(summary)
```

If an import fails, confirm that the interpreter running the command is the one from the
environment where you installed Persistra.
