# Release governance

This page is the single authority for what "release ready" means. The design references
describe capabilities; any acceptance list elsewhere is non-authoritative and defers to
this page. The rewrite is pre-release code; version changes, build publication, tags, and
repository pushes remain human-controlled.

## Mechanical gate

All of the following must pass on the supported Linux / Python 3.12–3.14 matrix:

1. `make lint type test` — ruff, pyright (strict), and the full pytest suite with the
   coverage gate;
2. `make docs-check` and `make docs-build` (strict);
3. `make schema-check`;
4. `uv lock --check`;
5. clean installation of the package on each supported Python version.

CI runs these on every push. The coverage gate is enforced by `--cov-fail-under` and is
raised on a deliberate ratchet: it currently stands at **85%**, with **88%** and **90%**
as the next steps as the simulation-executor and service-layer branches gain targeted
tests. Do not lower it.

## Evidence items

- **Flagship reproduction.** The flagship momentum workflow must run from data snapshot
  through report with no private or notebook-only logic.
- **Determinism and safety.** Schema upgrade/downgrade, deterministic replay, fault and
  resource behavior, portable-export reopen, offline report relocation, and dashboard
  loopback smoke tests must pass.

## Descoped for v3.0

The following focused-spec ambitions are explicitly **not** required for the v3.0 release
and are recorded here so no acceptance list silently blocks it: nested selection and a
sealed final-holdout contamination ledger; fitted forecast estimators and factor risk
models; sector/factor/tracking-error/ADV constraint families; the stateful strategy
callback, intrabar clock, and full corporate-action entitlement engine; advanced
Brinson/factor attribution and full statistical inference; and a static PNG/SVG/PDF
renderer. The `static` extra concept is retired along with all optional extras; static
image/PDF output remains an unimplemented extension point and cannot fail release
acceptance.

## Human release steps

Releasing is a deliberate human operation, performed only after the gate and evidence
above are satisfied:

1. inspect wheel/sdist content and license;
2. update version metadata in `pyproject.toml` (still `2.0.0` on development branches);
3. build, sign, tag, push, and publish.

No database migration or API behavior may infer release state from the branch name.

## Toolchain watch items

- The mkdocs-material build prints a banner about MkDocs 2.0 breaking the plugin/theme
  system; `mkdocs-material` is pinned below 10 and the strict build guards against
  breakage. Revisit before adopting MkDocs 2.0.
- `pyright` is pinned to an exact version so a minor release cannot break the type gate
  unrelated to a change; bump it deliberately.
