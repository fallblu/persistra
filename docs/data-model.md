# Data model and storage

Persistra separates identity from observations. Instruments, listings, provider symbols,
option contracts, and scalar series have explicit identities. A provider-scoped identity
does not claim equivalence with another provider.

Each result contains an exact pandas frame and immutable acquisition metadata. Required
provenance never depends on `DataFrame.attrs`. Calendar dates remain separate from UTC
instants, and missing applicability remains distinct from zero.

DuckDB storage will arrive in the next implementation checkpoint.
