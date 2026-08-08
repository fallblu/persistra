# Alpha Vantage

Construct `AlphaVantageClient` directly or with `from_env`, then call methods on its
namespaced attributes. The namespace classes below document those methods.

## Client

::: persistra.data.alphavantage.client.AlphaVantageClient
    options:
      members: true

## Security bars

::: persistra.data.alphavantage.securities.SecuritiesNamespace
    options:
      members: true

## Quotes and top of book

::: persistra.data.alphavantage.quotes.QuotesNamespace
    options:
      members: true

## Indices

::: persistra.data.alphavantage.indices.IndicesNamespace
    options:
      members: true

## Historical options

::: persistra.data.alphavantage.options.OptionsNamespace
    options:
      members: true

## Fiat and crypto pairs

The client exposes separate instances of the same pair namespace as `client.fx` and
`client.crypto`.

::: persistra.data.alphavantage.pairs.PairNamespace
    options:
      members: true

## Commodities

::: persistra.data.alphavantage.commodities.CommoditiesNamespace
    options:
      members: true

## Economics

::: persistra.data.alphavantage.economics.EconomicsNamespace
    options:
      members: true

## Reference data

::: persistra.data.alphavantage.reference.ReferenceNamespace
    options:
      members: true

## Transport and rate limiting

Most applications should use the configured client. These classes are public for custom
transport setup, controlled tests, and integration diagnostics.

::: persistra.data.alphavantage.transport.TokenRateLimiter
    options:
      members: true

::: persistra.data.alphavantage.transport.AlphaVantageTransport
    options:
      members: true
