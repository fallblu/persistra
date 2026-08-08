# FRED and ALFRED

Construct `FredClient` directly or with `from_env`, then use its `series` namespace. The
adapter requests source levels at their native frequency.

## Client

::: persistra.data.fred.client.FredClient
    options:
      members: true

## Series

::: persistra.data.fred.series.SeriesNamespace
    options:
      members: true

## Transport

Most applications should use the configured client. `FredTransport` is public for controlled
tests, custom session setup, and integration diagnostics.

::: persistra.data.fred.transport.FredTransport
    options:
      members: true
