from __future__ import annotations

import datetime as dt
import os
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
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
    universe_name: str = "default"


@dataclass(frozen=True)
class UniverseMembership:
    """One point-in-time universe membership interval."""

    symbol: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp | None = None
    universe_name: str = "default"


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

    def active_universe(self, date: pd.Timestamp, universe_name: str = "default") -> frozenset[str]:
        """Return symbols active on one session date."""
        ...


@runtime_checkable
class StreamingMarketData(MarketData, Protocol):
    """Optional read-side contract for bounded market data scans."""

    def bar_chunks(self, query: BarQuery, *, chunk_days: int) -> Iterator[pa.Table]:
        """Yield bars matching ``query`` in bounded date chunks."""
        ...

    def corporate_action_chunks(self, query: ActionQuery, *, chunk_days: int) -> Iterator[pa.Table]:
        """Yield corporate actions matching ``query`` in bounded date chunks."""
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
        self._active_cache: dict[tuple[str, pd.Timestamp], frozenset[str]] = {}

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
        fields = self._bar_fields(query.fields)
        tables = list(
            self.bar_chunks(query, chunk_days=self._query_span_days(query.start, query.end))
        )
        if not tables:
            return self._empty_like(BAR_SCHEMA, fields)
        return pa.concat_tables(tables).sort_by(
            [("bar_time", "ascending"), ("symbol", "ascending")]
        )

    def bar_chunks(self, query: BarQuery, *, chunk_days: int) -> Iterator[pa.Table]:
        if query.adjustment != AdjustmentPolicy.RAW:
            raise ValueError(f"unsupported adjustment policy: {query.adjustment}")
        fields = self._bar_fields(query.fields)
        symbols = self._filter_symbols(query.symbols)
        if (
            (self._timeframes is not None and query.timeframe not in self._timeframes)
            or not symbols
            or not self._bars_root.exists()
        ):
            return

        dataset = ds.dataset(self._bars_root, format="parquet", partitioning="hive")
        columns = list(dict.fromkeys((*fields, "timeframe", "year")))
        for start, end in self._date_windows(query.start, query.end, chunk_days=chunk_days):
            table = dataset.to_table(
                columns=columns,
                filter=self._bar_filter(query.timeframe, symbols, start, end),
            )
            if table.num_rows == 0:
                continue
            yield self._project_bar_table(table, fields)

    def corporate_actions(self, query: ActionQuery) -> pa.Table:
        tables = list(
            self.corporate_action_chunks(
                query, chunk_days=self._query_span_days(query.start, query.end)
            )
        )
        if not tables:
            return CORPORATE_ACTION_SCHEMA.empty_table()
        return pa.concat_tables(tables).sort_by(
            [("date", "ascending"), ("symbol", "ascending"), ("action_type", "ascending")]
        )

    def corporate_action_chunks(self, query: ActionQuery, *, chunk_days: int) -> Iterator[pa.Table]:
        symbols = self._filter_symbols(query.symbols)
        if not symbols or not self._actions_root.exists():
            return
        dataset = ds.dataset(self._actions_root, format="parquet", partitioning="hive")
        columns = list(dict.fromkeys((*CORPORATE_ACTION_SCHEMA.names, "year")))
        for start, end in self._date_windows(query.start, query.end, chunk_days=chunk_days):
            table = dataset.to_table(
                columns=columns,
                filter=self._action_filter(symbols, start, end),
            )
            if table.num_rows == 0:
                continue
            yield self._project_action_table(table)

    def universe(self, query: UniverseQuery) -> list[str]:
        df = self._load_universe()
        if df.empty:
            return []
        start = self._date(query.start)
        end = self._date(query.end)
        mask = (
            (df["universe_name"] == str(query.universe_name))
            & (df["start_date"] <= end)
            & (df["end_date"].isna() | (df["end_date"] >= start))
        )
        symbols = set(df.loc[mask, "symbol"].astype(str))
        return sorted(self._filter_symbols(symbols))

    def active_universe(self, date: pd.Timestamp, universe_name: str = "default") -> frozenset[str]:
        day = self._date(date)
        cache_key = (str(universe_name), day)
        cached = self._active_cache.get(cache_key)
        if cached is not None:
            return cached
        df = self._load_universe()
        if df.empty:
            result = frozenset[str]()
        else:
            mask = (
                (df["universe_name"] == str(universe_name))
                & (df["start_date"] <= day)
                & (df["end_date"].isna() | (df["end_date"] >= day))
            )
            result = frozenset(df.loc[mask, "symbol"].astype(str))
        result = frozenset(self._filter_symbols(result))
        self._active_cache[cache_key] = result
        return result

    def bars_df(
        self,
        symbols: list[str],
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        *,
        timeframe: str = "1d",
        fields: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        """Return matching bars as a pandas DataFrame for notebook workflows."""
        from persistra.data.views import bars_df

        return bars_df(
            self,
            symbols,
            pd.Timestamp(start),
            pd.Timestamp(end),
            timeframe=timeframe,
            fields=fields,
        )

    def prices(
        self,
        symbols: list[str],
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        *,
        timeframe: str = "1d",
        field: str = "close",
    ) -> pd.DataFrame:
        """Return a wide ``bar_time`` x ``symbol`` price frame."""
        from persistra.data.views import prices

        return prices(
            self,
            symbols,
            pd.Timestamp(start),
            pd.Timestamp(end),
            timeframe=timeframe,
            field=field,
        )

    def ohlcv(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        *,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        """Return one symbol's OHLCV as a pandas DataFrame."""
        from persistra.data.views import ohlcv

        return ohlcv(self, symbol, pd.Timestamp(start), pd.Timestamp(end), timeframe=timeframe)

    def actions_df(
        self,
        symbols: list[str],
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
    ) -> pd.DataFrame:
        """Return matching corporate actions as a pandas DataFrame."""
        from persistra.data.views import actions_df

        return actions_df(self, symbols, pd.Timestamp(start), pd.Timestamp(end))

    def universe_df(self, *, universe_name: str | None = None) -> pd.DataFrame:
        """Return universe membership rows as a pandas DataFrame."""
        df = self._load_universe()
        if df.empty:
            return pd.DataFrame(columns=UNIVERSE_MEMBERSHIP_SCHEMA.names)
        result = df.copy()
        if universe_name is not None:
            result = result[result["universe_name"] == str(universe_name)]
        if self._symbols is not None:
            result = result[result["symbol"].isin(self._symbols)]
        return result.sort_values(["universe_name", "symbol", "start_date"]).reset_index(drop=True)

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
        self._atomic_write(self._normalize_universe_table(table), self._universe_path)

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

    @staticmethod
    def _query_span_days(start: pd.Timestamp, end: pd.Timestamp) -> int:
        start_day = ParquetMarketData._date(start)
        end_day = ParquetMarketData._date(end)
        return max(1, int((end_day - start_day).days) + 1)

    @staticmethod
    def _date_windows(
        start: str | pd.Timestamp, end: str | pd.Timestamp, *, chunk_days: int
    ) -> Iterator[tuple[pd.Timestamp, pd.Timestamp]]:
        if chunk_days < 1:
            raise ValueError("chunk_days must be >= 1")
        cursor = ParquetMarketData._naive(start)
        final = ParquetMarketData._naive(end)
        while cursor <= final:
            window_end = min(
                cursor + pd.Timedelta(days=chunk_days) - pd.Timedelta(microseconds=1),
                final,
            )
            yield cursor, window_end
            cursor = pd.Timestamp(window_end) + pd.Timedelta(microseconds=1)

    @staticmethod
    def _years_between(start: pd.Timestamp, end: pd.Timestamp) -> list[int]:
        return list(range(start.year, end.year + 1))

    def _bar_filter(
        self,
        timeframe: str,
        symbols: frozenset[str],
        start: pd.Timestamp,
        end: pd.Timestamp,
    ):
        return (
            (pc.field("timeframe") == timeframe)
            & pc.field("symbol").isin(sorted(symbols))
            & pc.field("year").isin(self._years_between(start, end))
            & (pc.field("bar_time") >= start.to_pydatetime())
            & (pc.field("bar_time") <= end.to_pydatetime())
        )

    def _action_filter(
        self,
        symbols: frozenset[str],
        start: pd.Timestamp,
        end: pd.Timestamp,
    ):
        start_date = self._date(start).date()
        end_date = self._date(end).date()
        return (
            pc.field("symbol").isin(sorted(symbols))
            & pc.field("year").isin(self._years_between(self._date(start), self._date(end)))
            & (pc.field("date") >= dt.date(start_date.year, start_date.month, start_date.day))
            & (pc.field("date") <= dt.date(end_date.year, end_date.month, end_date.day))
        )

    @staticmethod
    def _project_bar_table(table: pa.Table, fields: tuple[str, ...]) -> pa.Table:
        schema = pa.schema([BAR_SCHEMA.field(field) for field in fields])
        return (
            table.select(list(fields))
            .cast(schema)
            .sort_by([("bar_time", "ascending"), ("symbol", "ascending")])
        )

    @staticmethod
    def _project_action_table(table: pa.Table) -> pa.Table:
        return (
            table.select(CORPORATE_ACTION_SCHEMA.names)
            .cast(CORPORATE_ACTION_SCHEMA)
            .sort_by([("date", "ascending"), ("symbol", "ascending"), ("action_type", "ascending")])
        )

    def _load_universe(self) -> pd.DataFrame:
        if self._universe_cache is not None:
            return self._universe_cache
        if not self._universe_path.exists():
            df = UNIVERSE_MEMBERSHIP_SCHEMA.empty_table().to_pandas()
        else:
            df = self._normalize_universe_table(pq.read_table(self._universe_path)).to_pandas()
        if not df.empty:
            df["universe_name"] = df["universe_name"].astype(str)
            df["symbol"] = df["symbol"].astype(str)
            df["start_date"] = pd.to_datetime(df["start_date"])
            df["end_date"] = pd.to_datetime(df["end_date"])
        self._universe_cache = df
        return df

    @staticmethod
    def _normalize_universe_table(table: pa.Table) -> pa.Table:
        df = table.to_pandas()
        if "universe_name" not in df.columns:
            df["universe_name"] = "default"
        if df.empty:
            return UNIVERSE_MEMBERSHIP_SCHEMA.empty_table()
        df = df[["universe_name", "symbol", "start_date", "end_date"]].copy()
        df["universe_name"] = df["universe_name"].fillna("default").astype(str)
        df["symbol"] = df["symbol"].astype(str)
        df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
        df["end_date"] = pd.to_datetime(df["end_date"]).dt.date
        return pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)

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
