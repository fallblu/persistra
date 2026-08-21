# Create a Persistra project

The initializer creates a standard non-packaged uv research application. Install Persistra,
then supply an explicit target directory:

```console
persistra init example-project
cd example-project
uv sync
uv run python main.py
uv run persistra inspect .
```

Use `--name NAME` when the distribution name should differ from the directory name. Persistra
strips surrounding whitespace and normalizes periods, underscores, and repeated hyphens to one
lowercase hyphen. It prints the normalized name and absolute project root.

Initialization does not prompt, access the network, run Git or uv, create an environment, or
resolve dependencies. The target must be absent or an existing empty directory. Its parent must
exist. Persistra refuses symlink targets, nonempty directories, files, and path collisions. A
failed or cancelled initialization closes an opened store and then attempts to remove every path
created by that invocation. Database creation uses a private staging directory, so partial main
files and database sidecars are part of the same rollback. `KeyboardInterrupt` retains its
original cancellation semantics; the CLI prints `persistra: cancelled` without a traceback and
returns status 130.

Rollback identifies created paths by their filesystem device and inode. It preserves paths that
existed before initialization, untracked paths added concurrently, and replacements moved into a
tracked location. Those concurrent paths can leave an otherwise empty target directory behind.
Cleanup failures are supplemental cancellation notes and do not replace the original
`KeyboardInterrupt` or `SystemExit`. These guarantees apply to failures delivered to the running
process. They cannot recover from `SIGKILL`, power loss, or filesystem corruption.

When Persistra is installed from a local directory, the initializer adds an absolute
`tool.uv.sources` path for Persistra to the generated `pyproject.toml`. It also retains editable
installation status. This mapping makes `uv sync` use the same checkout instead of querying a
package index. Registry installations do not add the mapping. Update or remove the absolute path
if you move the checkout or share the generated project with another machine.

## Standard layout

Format version 1 creates this fixed tree:

```text
example-project/
├── .gitignore
├── .python-version
├── README.md
├── persistra.toml
├── pyproject.toml
├── main.py
├── data.duckdb
├── cache/
│   └── responses/
├── artifacts/
│   ├── research/
│   └── trading-engine/
├── notebooks/
└── tests/
    └── test_project.py
```

Marker files retain intentionally empty standard directories in Git. The generated application
has no build backend or package directory. uv creates `uv.lock` and `.venv` only when you run
`uv sync`. A project initialized from an editable local checkout includes this source mapping:

```toml
[tool.uv.sources]
persistra = { path = "/absolute/path/to/persistra", editable = true }
```

A noneditable local installation omits `editable = true`.

`data.duckdb` is an initialized `DuckDBStore`. Additional root-level `*.duckdb` files are also
available to [the local inspector](inspection.md) without recursive discovery.

## Use paths explicitly

Open the project from a path your application owns. Existing Persistra APIs do not search the
current directory or parent directories:

```python
from pathlib import Path

from persistra.data import FredClient
from persistra.project import PersistraProject

project = PersistraProject.open(Path(__file__).resolve().parent)

client = FredClient.from_env(
    cache_directory=project.raw_cache_directory,
)
```

Use these fixed paths for format version 1:

| Path property | Purpose |
|---|---|
| `store_path` | Primary normalized `DuckDBStore` at `data.duckdb` |
| `raw_cache_directory` | Raw provider responses passed explicitly to clients |
| `research_artifact_directory` | Research manifests and caller-selected research output |
| `trading_engine_artifact_directory` | Scenarios, journals, manifests, transcripts, and replay bundles |
| `notebook_directory` | Caller-owned notebooks |

Pass a run-specific child of `trading_engine_artifact_directory` to `run_scenario`. Persistra
does not route caches, stores, or artifacts from the process working directory.

## Understand the project manifest

`persistra.toml` identifies only the project and fixed layout:

```toml
format_version = 1

[project]
name = "example-project"
```

Version 1 accepts exactly those fields. It does not allow path overrides. Missing, unknown,
mistyped, malformed, and unsupported fields fail with an actionable error.

The project manifest does not record datasets, parameters, environments, executions, or hashes.
`ResearchManifest` and Trading Engine manifests retain those separate responsibilities. Raw
cache entries, normalized stores, research manifests, and replay artifacts never share one
representation.

## Choose retention and version-control policies

The generated `.gitignore` excludes raw response contents, DuckDB files, generated research and
Trading Engine outputs, Python and tool caches, notebook checkpoints, `.env` files, and local
secret keys. It retains directory markers and does not ignore `uv.lock`, project manifests,
source, tests, README files, or notebooks.

Generated data and artifacts are ignored by default, not backed up. You own their retention,
backup, access-control, and deletion policies. Commit selected reproducibility manifests
deliberately after checking them for credentials and sensitive data. Put replay or research
inputs that should be versioned outside ignored generated-output directories.

The raw response cache supports offline replay but does not replace normalized storage. The
primary store does not replace research manifests. Trading Engine bundles remain separate from
both. This separation keeps provenance and retention decisions explicit.
