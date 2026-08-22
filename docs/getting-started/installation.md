# Install Persistra

Persistra requires Python 3.12 or later and supports Linux. Choose the smallest installation
boundary that matches the application:

| Installation | Includes |
|---|---|
| `persistra` | Data, analysis, research, portfolios, projects, and Trading Engine contracts |
| `persistra[viz]` | Base package plus Matplotlib visualization and image support |
| `persistra[inspect]` | Base package plus visualization and the Panel browser inspector |

Provider credentials and the Trading Engine executable remain optional. Importing
`persistra.viz` without visualization support reports the required extra instead of exposing a
low-level missing-module error.

## Create a project with uv

Use the Persistra initializer to create a standard project:

```bash
persistra init systematic-strategy
cd systematic-strategy
uv sync
```

If the initializer runs from a local Persistra checkout, it writes that absolute checkout path
under `tool.uv.sources` in the new project. `uv sync` then installs Persistra from the same local
source. Move or remove the mapping when the checkout location changes or the project should use a
registry release instead.

Confirm the installation with deterministic synthetic data:

```bash
uv run python -c "from persistra.data import synthetic; print(len(synthetic.bars(periods=5).frame))"
```

If you do not use `uv`, create a virtual environment and install with `pip`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install persistra
```

Install visualization helpers without the browser application when needed:

```bash
uv add "persistra[viz]"
```

Install the optional local browser inspector when needed:

```bash
uv add "persistra[inspect]"
```

Then run `uv run persistra inspect DIRECTORY`. See [Inspect local stores](../guides/inspection.md)
for discovery rules and the read-only safety boundary.

The base installation can produce a noninteractive inventory without Panel:

```console
uv run persistra inspect DIRECTORY --list --json
```

The source distribution intentionally contains the source package, tests and fixtures,
documentation, verification scripts, lockfile, and build policy needed to reproduce and verify a
wheel. Hatch also requires the root `.gitignore` as source-archive metadata. The archive excludes
repository automation, agent instructions, and local contributor tooling that do not participate
in a source build. `make package-check` enforces this policy, rebuilds a wheel from only the source
archive, and tests base, visualization, and inspector installations in clean environments.

## Verify the research stack

This check touches normalized data, returns, and portfolio construction without network or file
access:

```python
from persistra.analysis import simple_returns
from persistra.data import pivot_bars, synthetic

first = synthetic.bars("FIRST", periods=20, seed=1)
second = synthetic.bars("SECOND", periods=20, seed=2)
prices = pivot_bars([first, second], field="close")
returns = simple_returns(prices)

assert prices.shape == (20, 2)
assert returns.shape == (20, 2)
print(returns.tail())
```

See [Create a Persistra project](../guides/projects.md) for the fixed layout and retention
policies. Continue with the [strategy quickstart](quickstart.md). It uses only the installed
package.

## Add Trading Engine when needed

Persistra can build and inspect scenarios without the engine binary. Install Trading Engine when
you want deterministic order, fill, fee, margin, and accounting replay. Keep it in a separate
checkout; Persistra communicates with it only through versioned artifacts and a subprocess.

Follow [Set up Trading Engine](trading-engine.md) after the offline quickstart.

## Provider credentials are optional

Synthetic data is sufficient for examples, tests, and initial strategy development. Configure
[Alpha Vantage](alpha-vantage.md) or [FRED and ALFRED](fred.md) only when the strategy needs those
sources. Never put provider keys in source files, committed environment files, or notebooks.

## Install a contributor checkout

```bash
git clone https://github.com/fallblu/persistra.git
cd persistra
uv sync --group dev --group docs
make pre-commit-install
```

Run the complete gate before committing:

```bash
make lint type test docs-check
make docs-build
make package-check
uv lock --check
```

See the [contributor guide](https://github.com/fallblu/persistra/blob/develop/CONTRIBUTING.md) for
the branch, commit, and verification workflow.
