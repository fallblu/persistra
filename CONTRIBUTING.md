# Contributing

Persistra targets Python 3.12+ and is managed with [uv](https://docs.astral.sh/uv/).
This document is the source of truth for development setup, the verification gate, the
git workflow, and releases. It applies to human contributors and coding agents alike.

## Development setup

```bash
uv sync --group dev --group docs   # create .venv with all dev + docs dependencies
make pre-commit-install            # install the pre-commit hooks (ruff, pyright, docs-check)
```

Everything installs with the base package — there are no optional runtime extras. The
`dev` and `docs` dependency groups add tooling only.

## Verification gate

Every commit must leave the tree green under the full gate; CI runs it on Python
3.12, 3.13, and 3.14.

```bash
make lint type test docs-check   # ruff, pyright (strict), pytest+coverage, doc checks
make docs-build                  # strict mkdocs build
make schema-check                # schema validation
uv lock --check                  # lockfile is in sync with pyproject.toml
```

- **Coverage floor is 85%** (`--cov-fail-under=85`) and only ratchets upward.
- CI additionally resolves the dependency bands (`lowest-direct` and `highest`) on
  3.12 and runs a package smoke test (build the wheel, install it, exercise the CLI).
  When you change a dependency lower bound, verify the `lowest-direct` band still
  builds, imports, and passes: `uv pip install --resolution lowest-direct ".[dev,docs]"`.

## Git workflow

The project follows **git-flow** with two long-lived branches:

- **`main`** holds the released history — every commit is a tagged release (`vX.Y.Z`)
  and always matches its latest tag.
- **`develop`** is the integration branch for the next release.

Working conventions:

- **Feature branches** (`feat/…`, `fix/…`, `docs/…`, `chore/…`, `test/…`, `refactor/…`)
  branch off `develop` and merge back into `develop`.
- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org),
  subject-only: `type: imperative summary` (e.g. `feat: add plotly helpers`). No body,
  no trailers, no attribution footers. Types: `feat`, `fix`, `docs`, `chore`, `test`,
  `refactor`, `perf`, `build`, `ci`. Each commit is one coherent, working unit with the
  gate passing.
- **Pull requests** are opened with `gh`; the body has a **Summary** and a **Test plan**
  section. CI must be green. PRs land via **rebase-and-merge** so the atomic commits are
  preserved — never squash. Delete the branch after it merges.
- User-facing changes get a `CHANGELOG.md` entry under the target version.

## Releases

Version changes, builds, tags, pushes, and publication are **human-controlled**. `main`
only advances through release and hotfix merges, so it always matches its latest tag; no
code infers release state from the branch name.

- **Release branches** (`release/X.Y.Z`) are cut from `develop` to prepare a normal
  release. The version bump lives here — update `pyproject.toml`, refresh the lockfile
  (`uv lock`), and add the `CHANGELOG.md` entry — plus release-only stabilization. The
  branch then merges into `main` (tagged `vX.Y.Z`) and back into `develop`.
- **Hotfix branches** (`hotfix/X.Y.Z`) are cut from `main` to patch a released version.
  Bump the patch version there, then merge into `main` (tagged) and back into `develop`.

Release readiness requires the mechanical gate to pass on Python 3.12–3.14 —
`make lint type test docs-check docs-build schema-check`, `uv lock --check`, and a clean
install of the built package — plus the 85% coverage floor. Human release steps: inspect
wheel/sdist content and license, then build, sign, tag, push, and publish.
