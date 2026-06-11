from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .schema import BAR_SCHEMA, CORPORATE_ACTION_SCHEMA, UNIVERSE_MEMBERSHIP_SCHEMA


class AdjustmentPolicy(StrEnum):
    """Price adjustment policy for bar queries."""

    RAW = "raw"


@dataclass(frozen=True)
class BarQuery:
    """Engine-facing request for OHLCV bars."""

    symbols: tuple[str, ...]
    start: pd.Timestamp
    end: pd.Timestamp
    timeframe: str = "1d"
    fields: tuple[str, ...] | None = None
    adjustment: AdjustmentPolicy = AdjustmentPolicy.RAW


@dataclass(frozen=True)
class ActionQuery:
    """Request for corporate actions."""

    symbols: tuple[str, ...]
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class UniverseQuery:
    """Request for universe membership over an inclusive date range."""

    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class UniverseMembership:
    """One point-in-time universe membership interval."""

    symbol: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp | None = None


class MarketData(Protocol):
    """Read-side market data contract used by the engine."""

    def bars(self, query: BarQuery) -> pa.Table:
        """Return bars matching ``query`` sorted by ``(bar_time, symbol)``."""
        ...

    def corporate_actions(self, query: ActionQuery) -> pa.Table:
        """Return corporate actions matching ``query``."""
        ...

    def universe(self, query: UniverseQuery) -> list[str]:
        """Return symbols active at any point inside ``query``."""
        ...

    def active_universe(self, date: pd.Timestamp) -> frozenset[str]:
        """Return symbols active on one session date."""
        ...


class MarketDataWriter(Protocol):
    """Write-side contract used by provider adapters and fixtures."""

    def write_bars(self, table: pa.Table, timeframe: str) -> None:
        """Merge raw bars into storage."""
        ...

    def write_corporate_actions(self, table: pa.Table) -> None:
        """Merge corporate actions into storage."""
        ...

    def write_universe(self, table: pa.Table) -> None:
        """Replace universe membership storage."""
        ...


class ParquetMarketData(MarketData, MarketDataWriter):
    """Hive-partitioned Parquet market-data backend.

    Layout::

        root/bars/timeframe=<tf>/symbol=<sym>/year=<YYYY>/part-*.parquet
        root/actions/action_type=<type>/year=<YYYY>/part-*.parquet
        root/universe/membership.parquet
        root/_state/
    """

    def __init__(
        self,
        root: str | Path,
        *,
        symbols: Iterable[str] | None = None,
        timeframes: Iterable[str] | None = None,
    ) -> None:
        self.root = Path(root)
        self._bars_root = self.root / "bars"
        self._actions_root = self.root / "actions"
        self._universe_path = self.root / "universe" / "membership.parquet"
        self._symbols = (
            frozenset(str(symbol) for symbol in symbols) if symbols is not None else None
        )
        self._timeframes = (
            frozenset(str(timeframe) for timeframe in timeframes)
            if timeframes is not None
            else None
        )
        self._universe_cache: pd.DataFrame | None = None
        self._active_cache: dict[pd.Timestamp, frozenset[str]] = {}

    @property
    def state_dir(self) -> Path:
        """Directory reserved for ingest checkpoints and provider state."""
        return self.root / "_state"

    @staticmethod
    def _naive(ts: str | pd.Timestamp) -> pd.Timestamp:
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            t = t.tz_convert("UTC").tz_localize(None)
        return t

    @staticmethod
    def _date(ts: str | pd.Timestamp) -> pd.Timestamp:
        return pd.Timestamp(ParquetMarketData._naive(ts).date())

    @staticmethod
    def _table_from_df(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
        return pa.Table.from_pandas(df, schema=schema, preserve_index=False)

    @staticmethod
    def _empty_like(schema: pa.Schema, fields: tuple[str, ...] | None = None) -> pa.Table:
        if fields is None:
            return schema.empty_table()
        return schema.empty_table().select(list(fields))

    def bars(self, query: BarQuery) -> pa.Table:
        if query.adjustment != AdjustmentPolicy.RAW:
            raise ValueError(f"unsupported adjustment policy: {query.adjustment}")
        fields = self._bar_fields(query.fields)
        symbols = self._filter_symbols(query.symbols)
        if (
            (self._timeframes is not None and query.timeframe not in self._timeframes)
            or not symbols
            or not self._bars_root.exists()
        ):
            return self._empty_like(BAR_SCHEMA, fields)

        start = self._naive(query.start)
        end = self._naive(query.end)
        tables: list[pa.Table] = []
        for symbol in sorted(symbols):
            symbol_root = self._bars_root / f"timeframe={query.timeframe}" / f"symbol={symbol}"
            if not symbol_root.exists():
                continue
            dataset = ds.dataset(symbol_root, format="parquet")
            table = dataset.to_table()
            if table.num_rows == 0:
                continue
            df = table.to_pandas()
            df["bar_time"] = pd.to_datetime(df["bar_time"])
            mask = (df["bar_time"] >= start) & (df["bar_time"] <= end)
            df = df.loc[mask]
            if not df.empty:
                tables.append(self._table_from_df(df, BAR_SCHEMA).select(list(fields)))

        if not tables:
            return self._empty_like(BAR_SCHEMA, fields)
        return pa.concat_tables(tables).sort_by(
            [("bar_time", "ascending"), ("symbol", "ascending")]
        )

    def corporate_actions(self, query: ActionQuery) -> pa.Table:
        symbols = self._filter_symbols(query.symbols)
        if not symbols or not self._actions_root.exists():
            return CORPORATE_ACTION_SCHEMA.empty_table()
        dataset = ds.dataset(self._actions_root, format="parquet")
        table = dataset.to_table()
        if table.num_rows == 0:
            return CORPORATE_ACTION_SCHEMA.empty_table()
        df = table.to_pandas()
        df["date"] = pd.to_datetime(df["date"])
        start = self._date(query.start)
        end = self._date(query.end)
        mask = df["symbol"].isin(symbols) & (df["date"] >= start) & (df["date"] <= end)
        df = df.loc[mask].sort_values(["date", "symbol", "action_type"]).reset_index(drop=True)
        if df.empty:
            return CORPORATE_ACTION_SCHEMA.empty_table()
        df["date"] = df["date"].dt.date
        return self._table_from_df(df, CORPORATE_ACTION_SCHEMA)

    def universe(self, query: UniverseQuery) -> list[str]:
        df = self._load_universe()
        if df.empty:
            return []
        start = self._date(query.start)
        end = self._date(query.end)
        mask = (df["start_date"] <= end) & (df["end_date"].isna() | (df["end_date"] >= start))
        symbols = set(df.loc[mask, "symbol"].astype(str))
        return sorted(self._filter_symbols(symbols))

    def active_universe(self, date: pd.Timestamp) -> frozenset[str]:
        day = self._date(date)
        cached = self._active_cache.get(day)
        if cached is not None:
            return cached
        df = self._load_universe()
        if df.empty:
            result = frozenset[str]()
        else:
            mask = (df["start_date"] <= day) & (df["end_date"].isna() | (df["end_date"] >= day))
            result = frozenset(df.loc[mask, "symbol"].astype(str))
        result = frozenset(self._filter_symbols(result))
        self._active_cache[day] = result
        return result

    def write_bars(self, table: pa.Table, timeframe: str) -> None:
        self._raise_if_subsetted()
        if table.num_rows == 0:
            return
        df = table.cast(BAR_SCHEMA).to_pandas()
        df["bar_time"] = pd.to_datetime(df["bar_time"])
        df = df.sort_values(["symbol", "bar_time"]).reset_index(drop=True)
        groups = [df["symbol"].astype(str), df["bar_time"].dt.year]
        for (symbol, year), shard_df in df.groupby(groups):
            target_dir = (
                self._bars_root / f"timeframe={timeframe}" / f"symbol={symbol}" / f"year={year}"
            )
            self._merge_write(
                shard_df,
                target_dir,
                BAR_SCHEMA,
                dedupe=["bar_time", "symbol"],
                sort=["bar_time", "symbol"],
            )

    def write_corporate_actions(self, table: pa.Table) -> None:
        self._raise_if_subsetted()
        if table.num_rows == 0:
            return
        df = table.cast(CORPORATE_ACTION_SCHEMA).to_pandas()
        df["date"] = pd.to_datetime(df["date"])
        for (action_type, year), shard_df in df.groupby(
            [df["action_type"].astype(str), df["date"].dt.year]
        ):
            target_dir = self._actions_root / f"action_type={action_type}" / f"year={year}"
            out_df = shard_df.copy()
            out_df["date"] = out_df["date"].dt.date
            self._merge_write(
                out_df,
                target_dir,
                CORPORATE_ACTION_SCHEMA,
                dedupe=["date", "symbol", "action_type"],
                sort=["date", "symbol", "action_type"],
            )

    def write_universe(self, table: pa.Table) -> None:
        self._raise_if_subsetted()
        self._universe_cache = None
        self._active_cache = {}
        self._atomic_write(table.cast(UNIVERSE_MEMBERSHIP_SCHEMA), self._universe_path)

    def _filter_symbols(self, symbols: Iterable[str]) -> frozenset[str]:
        requested = frozenset(str(symbol) for symbol in symbols)
        if self._symbols is None:
            return requested
        return requested & self._symbols

    def _raise_if_subsetted(self) -> None:
        if self._symbols is not None or self._timeframes is not None:
            raise RuntimeError("subsetted ParquetMarketData instances are read-only")

    def _bar_fields(self, requested: tuple[str, ...] | None) -> tuple[str, ...]:
        if requested is None:
            return tuple(BAR_SCHEMA.names)
        fields = ("bar_time", "symbol", *requested)
        missing = [field for field in fields if field not in BAR_SCHEMA.names]
        if missing:
            raise ValueError(f"unknown bar field(s): {missing}")
        return tuple(dict.fromkeys(fields))

    def _load_universe(self) -> pd.DataFrame:
        if self._universe_cache is not None:
            return self._universe_cache
        if not self._universe_path.exists():
            df = UNIVERSE_MEMBERSHIP_SCHEMA.empty_table().to_pandas()
        else:
            df = pq.read_table(self._universe_path, schema=UNIVERSE_MEMBERSHIP_SCHEMA).to_pandas()
        if not df.empty:
            df["start_date"] = pd.to_datetime(df["start_date"])
            df["end_date"] = pd.to_datetime(df["end_date"])
        self._universe_cache = df
        return df

    def _merge_write(
        self,
        new_df: pd.DataFrame,
        target_dir: Path,
        schema: pa.Schema,
        *,
        dedupe: list[str],
        sort: list[str],
    ) -> None:
        frames = [new_df]
        if target_dir.exists():
            for path in sorted(target_dir.glob("*.parquet")):
                frames.append(pq.read_table(path, schema=schema).to_pandas())
        combined = pd.concat(frames, ignore_index=True)
        combined = (
            combined.drop_duplicates(subset=dedupe, keep="last")
            .sort_values(sort)
            .reset_index(drop=True)
        )
        if "transactions" in combined.columns:
            combined["transactions"] = combined["transactions"].astype("Int64")
        table = self._table_from_df(combined, schema)
        target = target_dir / "part.parquet"
        self._atomic_write(table, target)
        for stale in target_dir.glob("*.parquet"):
            if stale != target:
                stale.unlink()

    @staticmethod
    def _atomic_write(table: pa.Table, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        pq.write_table(table, tmp)
        os.replace(tmp, target)
