# Persistra

Persistra provides exact, typed contracts for primary market and economic data.
It keeps acquisition, normalized storage, analysis, and plotting separate.

Version 4 is an intentional clean break from the earlier research and backtesting platform.
It focuses on primary observations. It does not include fundamental, ownership, textual,
provider-analytics, realtime-options, or topological-data-analysis features.

Use the maintained guides in this order:

1. [Getting started](getting-started.md) introduces offline and provider-backed work.
2. [Data model and storage](data-model.md) explains identity, time, provenance, and revisions.
3. [Alpha Vantage acquisition](acquisition.md) lists the endpoint boundary and operational rules.
4. [Analysis and visualization](analysis.md) documents explicit calculations and plots.
5. The two executable notebooks demonstrate [cross-asset research](notebooks/01-cross-asset.ipynb)
   and [historical options](notebooks/02-historical-options.ipynb).

The [public API reference](reference/api.md) is generated from the installed package.
