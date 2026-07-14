# persistra — agent instructions

Python library for market research, strategy development, and event-driven backtesting. Managed with uv; Python 3.11+.

## Commands

- Setup: `uv sync --extra dev --extra docs`
- Lint: `make lint` (ruff)
- Types: `make type` (pyright)
- Tests: `make test` (pytest)
- Docs checks: `make docs-check` (docstring + doc-snippet checks); `make docs-build` for a strict mkdocs build
- Pre-commit runs ruff, pyright, and docs-check; expect commits to fail if those don't pass.

## Verification gate

`make lint type test` must pass before any commit. Run `make docs-check` as well whenever docs or docstrings change.

## Workflow

- One feature branch per effort; atomic checkpoint commits in the repo's conventional style (`feat:`, `fix:`, `chore:` — subject only).
- Open PRs with `gh` (Summary + Test plan); branches land on main via rebase-and-merge.
- Releases are human-triggered only: never create `chore(release)` commits, bump versions in `pyproject.toml`, tag, run `uv build` for publishing, or push, unless explicitly asked.
