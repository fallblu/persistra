# Alpha Vantage acquisition

Alpha Vantage acquisition will cover the primary dataset boundary in the
[4.0 roadmap](roadmap.md). It will exclude fundamentals, ownership, provider analytics,
alternative data, and real-time option chains.

The client will read `PERSISTRA_ALPHAVANTAGE_API_KEY`. Shared transport already provides
atomic raw caching, offline reads, proactive rate control, typed errors, and bounded retries.
Normal tests and notebooks remain offline.
