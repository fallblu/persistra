# Contributing

Persistra requires Python 3.12 or later. Use [uv](https://docs.astral.sh/uv/) to manage
the project.

This document gives the development, verification, Git, and release instructions.
These instructions apply to human contributors and coding agents.

## Development setup

```bash
uv sync --group dev --group docs
make pre-commit-install
```

The first command creates `.venv` and installs the development and documentation
dependencies. The second command installs the pre-commit hooks.

The base package contains all runtime dependencies. The `dev` and `docs` groups contain
development tools only.

## Verification gate

Before each commit, make sure that the complete gate passes. Continuous integration
(CI) runs the gate on Python 3.12, 3.13, and 3.14.

```bash
make lint type test docs-check
make docs-build
make schema-check
uv lock --check
```

The commands run these checks:

- Ruff lint
- Strict Pyright type check
- Pytest tests and coverage check
- Documentation checks
- Strict MkDocs build
- Schema check
- Lockfile check

The minimum coverage is 85 percent (`--cov-fail-under=85`). Do not decrease this
value.

CI resolves the `lowest-direct` and `highest` dependency bands on Python 3.12. CI also
builds the wheel, installs it, and runs a CLI smoke test.

After a dependency lower-bound change, test the `lowest-direct` band:

```bash
uv pip install --resolution lowest-direct ".[dev,docs]"
```

## Git workflow

The project uses Git Flow with two long-lived branches:

- **`main`:** Contains the released history. Each commit is a tagged release
  (`vX.Y.Z`) and agrees with its latest tag.
- **`develop`:** Integrates changes for the next release.

Use these working rules:

- Create feature branches from `develop`.
- Use one of these prefixes: `feat/`, `fix/`, `docs/`, `chore/`, `test/`, or
  `refactor/`.
- Merge feature branches into `develop`.
- Use [Conventional Commits](https://www.conventionalcommits.org) with this subject
  format: `type: imperative summary`.
- Use one of these commit types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`,
  `perf`, `build`, or `ci`.
- Do not add a commit body, trailer, or attribution footer.
- Make each commit one coherent and working unit.
- Make sure that the gate passes before each commit.
- Open pull requests with `gh`.
- Add a **Summary** section and a **Test plan** section to the pull-request body.
- Make sure that CI passes.
- Use rebase-and-merge. Do not squash commits.
- Delete the feature branch after the merge.
- Add each user-facing change to `CHANGELOG.md` for the target version.

## Releases

Humans control version changes, builds, tags, pushes, and publication. The `main`
branch changes only through release and hotfix merges. Thus, `main` agrees with its
latest tag.

A branch name does not give the release state.

For a normal release, create `release/X.Y.Z` from `develop`. Change the version in this
branch. Then, update `pyproject.toml`, run `uv lock`, and add the changelog entry.

Merge the release branch into `main` and add tag `vX.Y.Z`. Then, merge the branch into
`develop`.

For a hotfix, create `hotfix/X.Y.Z` from `main`. Change the patch version in this
branch. Merge the branch into `main` and add the tag. Then, merge the branch into
`develop`.

Before a release, make sure that these conditions are true:

- The complete gate passes on Python 3.12, 3.13, and 3.14.
- `uv lock --check` passes.
- A clean installation of the built package passes.
- Test coverage is not less than 85 percent.

The human release operator examines the wheel, source distribution, and license. The
operator then builds, signs, tags, pushes, and publishes the release.
