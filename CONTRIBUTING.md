# Contributing

Persistra requires Python 3.12 or later. Use [uv](https://docs.astral.sh/uv/) to manage
the project.

This document gives the development, verification, Git, and release instructions.
These instructions apply to human contributors and coding agents.

Report suspected vulnerabilities through the private channel in the
[security policy](.github/SECURITY.md), not through a public issue.

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
make package-check
uv lock --check
```

The commands run these checks:

- Ruff lint
- Strict Pyright type check
- Pytest tests and coverage check
- Documentation checks
- Strict MkDocs build
- Wheel and source-distribution build
- Clean wheel installation and public import smoke test
- Lockfile check

The minimum coverage is 90 percent (`--cov-fail-under=90`). Do not decrease this
value.

CI resolves the `lowest-direct` and `highest` dependency bands on Python 3.12. CI also
builds the wheel, installs it, and runs public import smoke tests.

After a dependency lower-bound change, test the `lowest-direct` band:

```bash
uv pip install --resolution lowest-direct ".[dev,docs,inspect]"
```

### Cross-repository compatibility

The required integration job checks out the full Trading Engine commit recorded as
`TRADING_ENGINE_COMPAT_REVISION` in `.github/workflows/ci.yml`. It never follows a branch or
repository variable. The job verifies the resolved checkout and writes the tested revision to its
log and job summary, so an unchanged Persistra commit always exercises the same engine source.

Advance the revision deliberately in a dedicated pull request:

1. Select a full commit from Trading Engine `develop` whose own required checks pass.
2. Build that exact checkout with `make bootstrap` and `make build`.
3. Run `tests/integration/test_trading_engine.py` against its binary and `contracts/v1` directory.
4. Replace the one workflow revision, describe compatibility changes since the previous pin, and
   require the complete Persistra CI matrix to pass.

Moving-head checks may be run as nonrequired canaries, but they must not replace or override this
reviewed compatibility gate. Before a Persistra release, confirm that the pinned engine revision
still represents the supported protocol and update it through the same process when necessary.

CI groups pull-request runs by PR number and push runs by exact branch or tag ref. A new run cancels
superseded work for that PR or unprotected branch. Tag and protected-branch runs are never canceled,
so release verification and integration-branch evidence always finish. Job names stay stable, and
required checks are reported by the newest run for a change.

## Intake and planning metadata

Use the focused bug or feature issue form when either applies. Use the general form for other
scoped requests. Pull requests retain the required `Summary` and `Test plan` sections.

Every issue has one component owner. Priority and effort labels are assigned only during explicit
triage; they do not promise a date or release. The reviewed definitions live in
`.github/labels.json`. See the [repository management guide](docs/concepts/repository-management.md)
for the component boundaries and label policy.

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
- Use rebase-and-merge for feature branches into `develop`. Do not squash commits.
- Use merge commits for release and hotfix integration as described below.
- GitHub deletes the feature branch automatically after the merge; verify that it is gone.
- Add each user-facing change to `CHANGELOG.md` for the target version.

Pull requests into `main` and `develop` must be current with their base, resolve all review
conversations, and pass the protected checks documented in the
[repository management guide](docs/concepts/repository-management.md). The protections apply to
administrators and block force pushes and branch deletion. They currently require no approval
because Persistra has one maintainer; this avoids making self-authored changes impossible to land.

## Releases

Humans control version changes, builds, tags, pushes, and publication. The `main`
branch changes only through release and hotfix merges. Thus, `main` agrees with its
latest tag.

A branch name does not give the release state.

For a normal release, create `release/X.Y.Z` from `develop`. Change the version in this
branch. Then, update `pyproject.toml`, run `uv lock`, and add the changelog entry.

Open a pull request from the release branch into `main`. Merge it with a merge commit and
add tag `vX.Y.Z` to that merge commit. Then, merge `main` into `develop` with a merge
commit. Do not rebase either integration because that rewrites shared history.

For a hotfix, create `hotfix/X.Y.Z` from `main`. Change the patch version in this
branch. Open a pull request from the hotfix branch into `main`. Merge it with a merge
commit and add the tag to that merge commit. Then, merge `main` into `develop` with a
merge commit. Do not rebase either integration.

Before a release, make sure that these conditions are true:

- The complete gate passes on Python 3.12, 3.13, and 3.14.
- `uv lock --check` passes.
- A clean installation of the built package passes.
- Test coverage is not less than 90 percent.

The human release operator examines the wheel, source distribution, and license. Run the
human-triggered release-evidence workflow from the exact version-matched release ref, verify its
SBOM, checksums, and signed provenance, and retain that evidence with the published distributions.
The operator then tags, pushes, and publishes the release. See the
[release-evidence guide](docs/concepts/release-evidence.md) for the commands and retention policy.
