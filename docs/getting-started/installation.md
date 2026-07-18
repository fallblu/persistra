# Installation

Persistra requires Python 3.12, 3.13, or 3.14 on Linux. All runtime capabilities —
research, search, optimization, visualization, and the dashboard — are required
dependencies of the base package; there are no optional capability extras.

```bash
uv add persistra
```

or, inside this repository for development:

```bash
uv sync --extra dev --extra docs
make lint type test docs-check
make docs-build
```

The `dev` extra carries the verification toolchain (ruff, pyright, pytest, hypothesis,
pre-commit) and `docs` carries the MkDocs toolchain. Static image/PDF rendering is an
unimplemented extension point; self-contained offline HTML and checksum-closed report
directories are the supported presentation outputs.

## Verify the installation

```bash
persistra --version
persistra project init my-project --name my-project
persistra project inspect my-project
```

`project init` creates a `persistra.toml` and a managed `.persistra/` state directory
with a research database. Continue with the
[first project tutorial](first-project.md).
