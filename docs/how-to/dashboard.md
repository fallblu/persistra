# Use the dashboard

The dashboard is a loopback-only, read-only Streamlit application over completed
results and analyses. It never computes or persists analysis; a missing immutable
analysis is shown as unavailable.

```bash
persistra dashboard --project /path/to/project
persistra dashboard --backup /path/to/research-backup.duckdb
persistra dashboard --export /path/to/run-export.duckdb
```

The launcher validates the source before starting the child process, binds to
`127.0.0.1:8501` by default, keeps XSRF/CORS protections enabled, disables telemetry,
static serving, and file watching, and exposes no upload, arbitrary path, SQL, HTML,
JavaScript, or write control. Backup sources must be verified published copies;
portable-export sources are re-verified through the public export reader.

Each live/backup page query opens a short-lived thread-owned `READ_ONLY` project scope,
materializes bounded public values, and closes the scope. The cache stores detached
frames and serialized figures only, keyed by source fingerprint, immutable result
root, page parameters, limits, and renderer version.

The eight pages cover run overview, performance, portfolio, execution, attribution,
diagnostics, studies, and provenance inspection.

Network-hosted dashboards, authentication, public binds, file uploads, arbitrary SQL,
and managed writes are outside the dashboard support boundary — see
[ADR 0001](../explanation/adr-0001-streamlit-dashboard.md).
