# Persistra

Persistra v3 is a greenfield, local-first Python library for point-in-time market
research, strategy development, and event-driven backtesting.

The v3 rewrite is implemented on the integration line and remains unreleased until the
human-controlled release process assigns version metadata. Python 3.12 or newer is
required. The [documentation](docs/index.md) covers installation, task-oriented how-to
guides, the generated API reference, and the design/assumptions explanation; the
[release governance page](docs/explanation/release-governance.md) is the single authority
for release readiness.

```bash
uv sync --extra dev --extra docs
make lint type test docs-check
make docs-build
```

All research, search, optimization, visualization, and dashboard capabilities install
with the base package; there are no optional capability extras. Static image/PDF
rendering remains an unimplemented extension point; self-contained offline HTML
and checksum-closed report directories are supported.
