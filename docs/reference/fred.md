# FRED and ALFRED

Construct `FredClient` directly or with `from_env`, then use its `discovery` and `series`
namespaces. The adapter keeps provider discovery metadata separate from source-level observations.

## Client

::: persistra.data.fred.client.FredClient
    options:
      members: true

## Series

::: persistra.data.fred.series.SeriesNamespace
    options:
      members: true

## Discovery

::: persistra.data.fred.discovery
    options:
      members: true

## Transport

Most applications should use the configured client. `FredTransport` is public for controlled
tests, custom session setup, and integration diagnostics.

::: persistra.data.fred.transport.FredTransport
    options:
      members: true
