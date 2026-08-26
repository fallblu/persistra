# Repository management

Persistra uses structured intake, stable planning labels, and the GitHub issue state. These
controls organize evidence without assigning a release, date, or delivery promise.

## Issue and pull-request intake

Use the bug form for reproducible incorrect behavior and the feature form for a new capability.
Use the general form when neither focused form fits. Each form asks for a component, scope, data or
provenance implications, and verification expectations. Never include credentials, customer data,
proprietary strategies, or licensed data.

Pull requests retain the required `Summary` and `Test plan` sections. The summary states the
behavior and any data or provenance impact. The test plan lists exact checks and relevant failure
or compatibility evidence.

## Label taxonomy

Each open issue receives exactly one component label:

| Label | Ownership boundary |
| --- | --- |
| `component: acquisition` | Providers, transport, raw caching, normalization, and acquisition plans |
| `component: storage` | DuckDB persistence, queries, projects, schemas, and stored artifacts |
| `component: research` | Transforms, point-in-time features, analysis, factors, and validation |
| `component: portfolio` | Portfolio construction, optimization, accounting, and backtesting |
| `component: engine` | Trading Engine schemas, scenarios, policies, and reconciliation |
| `component: visualization` | Plots, reports, browser inspection, and interactive rendering |
| `component: documentation` | Guides, examples, API reference, schemas, and documentation tooling |
| `component: operations` | CI, packaging, releases, security, governance, and repository tooling |

Component boundaries are exclusive for planning. Choose the component that owns the change, even
when another component consumes its result.

Priority uses four levels: `critical` for immediate security, correctness, or data-integrity
impact; `high` for work selected ahead of the normal backlog; `medium` for normal explicitly
triaged work; and `low` for useful work with no current urgency. Effort uses `small` for a narrow
verification surface, `medium` for moderate multi-file work, and `large` for work that should be
split into reviewed increments.

Priority and effort labels are assigned only during explicit triage. They do not promise a date or
release. The maintainer owns label definitions in `.github/labels.json`; changes require review.

The existing `bug`, `enhancement`, `documentation`, and `question` labels remain the useful type
labels. `good first issue` and `help wanted` remain maintainer-assigned contribution signals. Do not
create workflow-status labels. GitHub's open and closed states, close reasons, pull requests, and
linked dependencies already represent status.

## Repository profile

The public description, documentation homepage, discovery topics, and maintained repository
surfaces live in `.github/repository.json` and must agree with `pyproject.toml` and the README.
Issues remain the public work tracker. The unused repository wiki and classic Projects surface are
disabled; maintained documentation lives in the repository and on the documentation site.

## Branch and merge governance

Both long-lived branches require pull requests, an up-to-date head, resolved review conversations,
and these successful checks before merge:

- `verify (3.12)`, `verify (3.13)`, and `verify (3.14)`;
- `dependency-bands (lowest-direct)` and `dependency-bands (highest)`;
- `trading-engine-integration`.

`develop` additionally requires `Analyze Python` from CodeQL and `Review dependency changes`.
Those workflows have not reached the release-only `main` branch yet, so requiring their contexts
there would prevent a hotfix branch created from `main` from merging. Add those requirements to
`main` after its next release integration brings both workflows across.

The protections block branch deletion and force pushes and apply to administrators without a
bypass. Persistra currently has one maintainer, so the rules require zero approving reviews;
requiring approval would prevent the author from merging otherwise valid work. Stale-approval
dismissal, code-owner review, and last-push approval are consequently disabled. Revisit that choice
when a second regular reviewer is available.

Rebase merging is available for feature work, while merge commits remain available for the
documented release and hotfix integrations. Squash merging is disabled, linear history is not
required, and merged head branches are deleted automatically. The reviewed settings live in
`.github/branch-protection.json` and `.github/repository.json`.
