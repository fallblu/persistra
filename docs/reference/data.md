# Data access and storage

The data package provides normalized acquisition capabilities, deterministic synthetic data,
raw response caching, explicit DuckDB storage, and pandas transforms.

## Public data namespace

::: persistra.data
    options:
      members: true

## Synthetic data

::: persistra.data.synthetic
    options:
      members: true

## DuckDB storage

::: persistra.data.store.DuckDBStore
    options:
      members: true

::: persistra.data.store.StoredDataset
    options:
      members: true

::: persistra.data.store.StoredSnapshot
    options:
      members: true

::: persistra.data.store.StoredPage
    options:
      members: true

::: persistra.data.store.StoredOptionSnapshot
    options:
      members: true

::: persistra.data.store.SnapshotDiff
    options:
      members: true

::: persistra.data.store.SnapshotRow
    options:
      members: true

::: persistra.data.store.SnapshotValueChange
    options:
      members: true

## Columnar exports

::: persistra.data.export
    options:
      members: true

::: persistra.data.verification.StoreVerification
    options:
      members: true

::: persistra.data.verification.verify_store
    options:
      show_root_heading: true

## Raw response cache

::: persistra.data.cache
    options:
      members: true

## Transforms

::: persistra.data.utils
    options:
      members: true

## Capability protocols

::: persistra.data.protocols
    options:
      members: true
