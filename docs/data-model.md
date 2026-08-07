# Data model and storage

Persistra separates identity from observations. Instruments, listings, provider symbols,
option contracts, and scalar series have explicit identities. A provider-scoped identity
does not claim equivalence with another provider.

Each result contains an exact pandas frame and immutable acquisition metadata. Required
provenance never depends on `DataFrame.attrs`. Calendar dates remain separate from UTC
instants, and missing applicability remains distinct from zero.

`DuckDBStore` creates or opens one explicit database connection. Acquisition never writes
automatically. Repeated identical source values update their last-seen time. Changed values
create a new retrieval-time revision. A `retrieved_before` query reconstructs only what
Persistra had observed by that time. It does not claim provider point-in-time history.
