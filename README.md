# Persistra

Persistra v3 is a greenfield, local-first Python library for point-in-time market
research, strategy development, and event-driven backtesting.

The v3 rewrite is implemented on the integration line and remains unreleased until the
human-controlled release process assigns version metadata. Python 3.12 or newer is
required. The [documentation](docs/index.md), [migration guide](docs/migration-guide.md),
and [normative design](docs/v3/v3-spec.md) describe the supported surface.

```bash
uv sync --extra dev --extra docs --extra all
make lint type test docs-check
make docs-build
```

The base package is intentionally small. Install `research`, `search`, `optimize`, `viz`,
or `dashboard` capabilities explicitly, or install `persistra[all]`. Static image/PDF
rendering remains a guarded, unimplemented extension point; self-contained offline HTML
and checksum-closed report directories are supported.
