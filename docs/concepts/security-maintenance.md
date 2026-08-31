# Security maintenance

Persistra combines GitHub security settings, bounded dependency proposals, code analysis, and
review policy. These controls identify changes for a maintainer to assess. They do not replace the
complete verification gate or the human-controlled release process.

Report an undisclosed vulnerability through the private channel in the
[security policy](https://github.com/fallblu/persistra/security/policy).

## Dependency updates

Dependabot checks Python and GitHub Actions dependencies every Monday. Python patch and minor
updates are grouped by runtime or development scope. Action patch and minor updates form one
group. Major updates remain separate so their compatibility impact is visible. At most five
version-update pull requests per ecosystem remain open at once.

Version-update pull requests target `develop`. GitHub always targets Dependabot security-update
pull requests at the repository's default branch, which is `main`; `target-branch` cannot change
that behavior. Treat such a pull request as a security warning and hotfix input. Do not merge it
directly as an ordinary feature change. Reproduce the dependency and lockfile change through the
documented hotfix or `develop` integration flow, then use the human-controlled release process.

Review every `pyproject.toml` and `uv.lock` change together. A dependency update must pass the
complete repository gate and `uv lock --check`. CI also resolves and tests the `lowest-direct` and
`highest` dependency bands. A lower-bound change must pass `lowest-direct`; all changes must pass
both bands before merge.

Dependabot configuration lives on `develop` until the next human release carries it to `main`,
where GitHub reads `.github/dependabot.yml`. Repository vulnerability alerts and automatic
security-fix proposals are enabled independently through GitHub security settings.

## Code and dependency analysis

CodeQL analyzes Python on pull requests and pushes to `develop` and `main`, on a weekly schedule,
and when started manually. It uses the `security-extended` query suite and interpreted-language
`none` build mode. The workflow checks out source without credentials and does not install the
project or execute repository code.

Dependency review runs on pull requests to `develop` and `main`. It rejects newly introduced
runtime, development, or unknown-scope dependencies with vulnerabilities of moderate severity or
higher. It checks vulnerabilities only; dependency license policy remains part of normal review.
The workflow reads the dependency graph without installing or executing pull-request code.

## Serialized input boundaries

Provider responses, raw cache entries, acquisition plans and checkpoints, research manifests,
Trading Engine schemas, scenarios, results, diagnostics, transcripts, journals, and persisted
store payloads use strict JSON decoding. Duplicate object fields are invalid at every nesting
level; Persistra never relies on a decoder's first-value or last-value behavior. Each public
boundary returns a validated typed result, raises its documented validation exception, or records
a structured store-verification finding.

Bounded Hypothesis tests exercise portable JSON, duplicate fields, malformed scalars, extreme
sizes, timestamps, decimals, and identifiers. The normal test gate limits generated examples so
these checks remain deterministic in cost. A minimized case that exposes a defect becomes an
explicit regression test in the repository.

## Findings and suppressions

Investigate each CodeQL or dependency-review finding against the affected code path and supported
dependency range. Prefer a code fix, dependency update, or constraint change. Record the evidence
and affected versions in the pull request or a linked issue.

Do not add broad query exclusions or advisory allowlists. A narrow suppression requires maintainer
review, a linked tracking issue, a reason such as confirmed false positive or unreachable test
code, and a condition for removal. Use GitHub's finding dismissal controls for CodeQL so the reason
and reviewer remain auditable. Any future dependency-review advisory exception must name one GHSA
and follow the same review rules. Re-run the affected workflow after a fix or suppression change.
