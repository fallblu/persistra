# ADR 0001: adopt Streamlit behind a bounded read-only adapter

- Status: accepted for v3
- Decision: `adopt_with_bounded_adapter_changes`

## Context

V3 requires eight local interactive result/analysis pages without introducing another metric
engine, result schema, connection lifecycle, or persistence surface. The prototype must keep
Streamlit outside base imports and preserve loopback, read-only, resource, accessibility, and
determinism boundaries.

## Decision

Adopt Streamlit 1.x only through `persistra.dashboard.app` and the hardened launcher.
Configuration, source verification, cache keys, page results, and public launch contracts do
not contain Streamlit types. Streamlit and Plotly import lazily at application invocation.

Each live/backup page query opens a thread-owned `ProjectMode.READ_ONLY` scope, materializes
bounded public result/analysis values, and closes the scope. Portable exports reopen through
the public verified export reader. The cache accepts detached frames and serialized figures
only; it never stores a project, service, DuckDB connection, or mutable managed state.

The launcher validates the source before starting the child, binds to loopback by default,
uses an owner-readable one-use request file, preserves XSRF/CORS, disables static serving,
file watching, telemetry, and automatic browser opening, and exposes no upload, arbitrary
path, SQL, HTML, JavaScript, or write control.

## Evidence and consequences

Contract tests cover all eight page keys, immutable-root cache invalidation, cache detachment,
non-loopback rejection, public project and portable-export queries, warning/unavailable
states, Plotly reuse, report/offline closure, and zero dashboard mutations. Strict imports
prove base and non-dashboard namespaces do not import Streamlit.

Streamlit API churn is localized to the application shell. Hosted/LAN deployment remains
unsupported. Backup browsing creates only ephemeral launcher configuration and the normal
advisory shared-lease evidence; it never alters database bytes. If future framework behavior
weakens these controls, this ADR must be revisited before expanding the dashboard.
