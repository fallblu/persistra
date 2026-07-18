# Design reference: data platform

This page describes the implemented behavior of the project, database, catalog,
reference, and market-data subsystems. It is a condensed reference, not a normative
specification; the code and the [implementation boundaries](../assumptions-and-limitations.md)
are authoritative.

## Projects and databases

A project is a directory holding `persistra.toml` and a `.persistra/` state directory.
Configuration is immutable at open time; `ProjectOverrides` adjusts resource limits
without editing the file. Databases have roles (`research`, `market`) and content-checked
identities; a project refuses to open databases whose role or identity does not match its
configuration, or that carry an unresolved migration recovery marker.

Leases are advisory Linux file locks recorded with owner metadata. Readers take shared
leases; writers take exclusive leases. Lease conflicts, stale ownership, and path
identity changes are detected and raise typed errors. Backups are verified published
copies with a sidecar manifest; restore and fork always target new destinations, and
market snapshot copies require `verify_copy_on_open` in the consuming configuration.

Migrations are numbered, contiguous, and checksum-verified. A migration records a
recovery marker while in flight so an interrupted migration is detected on the next open.
Pre-release schema steps may be amended in place because pre-release databases are
disposable.

## Catalog and ingestion

Sources and datasets are registered in the catalog. Ingestion stages batches, validates
records, and assigns an explicit disposition to every record; rejected records enter
quarantine with remediation linkage through child batches. Revisions and retractions
create new canonical revisions with their own availability instants rather than
overwriting facts, which is what makes revision-specific point-in-time queries possible.

Snapshots publish content-addressed catalog roots. Market snapshots pin a single market
database; composite snapshots combine several. A pinned reader observes exactly the
snapshot's root, so later ingestion is invisible to it.

## Reference data and market data

Reference data models issuer/security/venue/listing/instrument identities, external
identifiers, effective classifications and memberships, reviewed materialized exchange
calendars, and point-in-time universe evaluation with complete eligibility audits.

Canonical market families — bars, trades, quotes, trading status, corporate actions,
fundamentals, estimates, macro vintages, benchmarks, and risk-free curves — validate
their invariants at construction and carry explicit availability instants and
availability quality. Point-in-time adjustment views apply split and total-return
policies against an anchor without mutating stored bars. The `AsOfContext` carries the
snapshot binding, effective instant, public cutoff, optional project cutoff, and source
precedence that together define what a query may observe.
