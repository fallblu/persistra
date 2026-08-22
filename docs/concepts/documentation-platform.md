# Documentation platform

The canonical Persistra documentation is published at
<https://fallblu.github.io/persistra/>. GitHub Pages serves a strict static build produced by the
repository workflow. The site does not use a generated branch or commit built files.

## Deployment boundary

Only a push to `develop` can deploy the site. Pull requests run the complete documentation checks
through CI but cannot request a Pages token or deployment. The `github-pages` environment also
allows only `develop` and disables administrator bypass, so manually dispatched or modified
workflows from another branch cannot publish.

The build job has read-only repository access. A separate deployment job receives only
`pages: write` and `id-token: write`, consumes the generated artifact, and publishes it. Every
third-party workflow action is pinned to a full commit. The workflow runs the link and example
checker plus `mkdocs build --strict` before it uploads an artifact.

The repository homepage, package metadata, and README use the canonical site URL. `site_url`
provides canonical page metadata, while `repo_url` and `edit_uri` connect each page to its source
on `develop`.

## Toolchain decision

Persistra remains on MkDocs 1.x and Material for MkDocs 9.7 during the ecosystem transition.
These versions support the current search index, Material navigation and theme, Python Markdown
extensions, and generated API reference through mkdocstrings. The dependency ranges explicitly
exclude MkDocs 2 and future Material major versions. The known MkDocs 2 notice is disabled only
after these bounds are installed; every other strict-build warning remains an error.

MkDocs 2 is not a migration target because its announced plugin and theme boundaries do not
support the current topology. Zensical is the preferred candidate because it preserves Material
content and navigation, but Persistra will not switch while its compatibility tracker still lists
mkdocstrings integration as unfinished. A temporary move to another generator would require a
second rewrite and is not justified.

Reconsider Zensical when all of these conditions hold:

- mkdocstrings is supported rather than listed as plugin-compatibility backlog;
- the existing navigation, search, extensions, and generated API pages build without content
  forks;
- canonical, repository, and edit metadata match the deployed site;
- the documentation checker and a strict production build pass from a clean environment.

Migration should change the generator and configuration in one tested step. Until those gates are
met, dependency updates stay within the recorded MkDocs 1.x, Material 9.7, mkdocstrings 0.x, and
PyMdown Extensions 11.x lines.

The decision follows the
[Material for MkDocs compatibility analysis](https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/)
and the current [Zensical plugin tracker](https://zensical.org/compatibility/plugins/).

## Link validation boundaries

`make docs-check` is deterministic and offline. It validates local targets, Python snippets,
executable examples, and every normalized schema table against the runtime frame contracts.
Column order, pandas dtype, required values, identity keys, sort order, and named invariants must
all agree before documentation can build.

External links use a separate pinned Lychee workflow each Monday and on manual request. Changes to
the workflow or its configuration also trigger one check after they reach `develop`; routine pull
requests and documentation edits do not depend on the network. The checker uses HTTPS only,
rejects insecure and private destinations, and bounds concurrency, redirects, request time, and
retries. Detailed output identifies both the source page and failing target.

The allowlist in `lychee.toml` begins empty. An exception must match an exact URL pattern, explain
why the target cannot be made checkable, and be reviewed with the configuration change. Whole-host
and credential-bearing exceptions are not allowed.
