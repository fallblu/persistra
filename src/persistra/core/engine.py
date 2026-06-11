from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import pandas as pd
from tqdm import tqdm

from persistra.data.calendar import TradingCalendar

from ..strategy.context import StrategyContext
from .clock import Clock
from .events import BarCloseEvent, DividendEvent, SplitEvent
from .execution import ExecutionModel, IdealFill
from .history import HistoryView
from .result import Result
from .timeframe import timeframe_duration

if TYPE_CHECKING:
    import numpy as np
    import pyarrow as pa

    from persistra.data.store import MarketData

    from ..strategy.base import Strategy
    from .portfolio import Portfolio
    from .state import PortfolioState

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass
class BarUnit:
    """One (timeframe, bar_time) dispatch group — columnar OHLCV arrays.

    All arrays are parallel: ``symbols[i]`` corresponds to ``opens[i]``,
    ``closes[i]``, etc. ``eff_close`` and ``duration`` are pre-computed at
    construction time and used only for sort ordering in
    :func:`order_session_units`.
    """

    timeframe: str
    timestamp: pd.Timestamp
    eff_close: pd.Timestamp
    duration: pd.Timedelta
    symbols: list[str]
    opens: np.ndarray  # float64, shape (n_symbols,)
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    volumes: np.ndarray


def order_session_units(
    session_bars: dict[str, list[BarUnit]],
) -> list[BarUnit]:
    """Sort a session's BarUnits by effective close; ties break coarsest-last.

    Units are pre-formed by ``_index_bars``; this function only merges and
    sorts. Finer timeframes sort first on ties (smaller duration sorts earlier).
    """
    all_units = [u for units in session_bars.values() for u in units]
    all_units.sort(key=lambda u: (u.eff_close, u.duration))
    return all_units


def rebucket_to_sessions(
    by_date: dict[pd.Timestamp, list[_T]],
    sessions: pd.DatetimeIndex,
) -> tuple[dict[pd.Timestamp, list[_T]], list[pd.Timestamp]]:
    """Roll each date-bucket onto the next session >= its date.

    Generic over the bucket payload (BarUnit lists for bars, action-row dicts
    for corporate actions). Buckets already keyed on a session date pass through
    unchanged. Buckets on a non-session date are merged into the next session's
    bucket, ordered by original date so earlier-dated rows dispatch first. Dates
    with no following session are returned in ``dropped``.
    """
    out: dict[pd.Timestamp, list[_T]] = {}
    dropped: list[pd.Timestamp] = []
    for date in sorted(by_date):
        idx = int(sessions.searchsorted(date, side="left"))
        if idx >= len(sessions):
            dropped.append(date)
            continue
        target = pd.Timestamp(sessions[idx])
        out.setdefault(target, []).extend(by_date[date])
    return out, dropped


class Engine:
    """Multi-timeframe, single-strategy event-driven backtest engine.

    Loads bars per subscribed timeframe, iterates calendar sessions, and within
    each session dispatches corporate actions then bar-close units in
    effective-close order. ``on_bar`` fires once per ``(timeframe, timestamp)``
    unit (gated on the primary timeframe's warmup); target weights reconcile to
    market-on-close fills at that unit's bar closes. Equity is recorded on every
    bar of the finest subscribed timeframe.
    """

    def __init__(
        self,
        data: MarketData,
        strategy: Strategy,
        portfolio: Portfolio,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        calendar: str = "XNYS",
        history_max_bars: int = 1000,
        execution_model: ExecutionModel | None = None,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.portfolio = portfolio
        self.start = self._naive(start)
        self.end = self._naive(end)
        self._timeframes = tuple(strategy.timeframes)
        self._primary_tf = self._timeframes[0]
        self._durations = {tf: timeframe_duration(tf) for tf in self._timeframes}
        self._calendar = TradingCalendar(calendar)
        self._clock = Clock(self._calendar, timeframes=self._timeframes)
        self._finest_tf = self._clock.finest
        self._histories = {tf: HistoryView(max_bars=history_max_bars) for tf in self._timeframes}
        self._trade_rows: list[dict[str, Any]] = []
        self._position_rows: list[dict[str, Any]] = []
        self._diagnostic_rows: list[dict[str, Any]] = []
        self._priced: set[str] = set()
        self._execution_model: ExecutionModel = (
            execution_model if execution_model is not None else IdealFill()
        )

    @staticmethod
    def _naive(ts: str | pd.Timestamp) -> pd.Timestamp:
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            t = t.tz_convert("UTC").tz_localize(None)
        return t.normalize()

    def run(
        self,
        output_dir: str | Path | None = None,
        run_id: str | None = None,
        meta_extra: dict[str, Any] | None = None,
    ) -> Result:
        """Execute the full backtest and return a Result.

        Loads bars for every subscribed timeframe, iterates over trading
        sessions in the configured calendar, dispatches corporate actions then
        bar-close events in effective-close order, and records equity on every
        bar of the finest timeframe.  Calls ``strategy.on_start`` before the
        first session and ``strategy.on_finish`` after the last.

        Args:
            output_dir: If provided, persists the Result (equity curve, trades,
                metadata, data-hash) as Parquet files under this directory.
            run_id: Explicit run identifier; auto-generated from UTC timestamp
                and a run-hash prefix when ``None``.
            meta_extra: Additional key/value pairs merged into ``Result.meta``
                before writing (e.g. strategy hyper-parameters).

        Returns:
            :class:`~persistra.core.result.Result` containing the equity curve,
            trade log, position log, and metadata dict.
        """
        from persistra.data.store import ActionQuery, BarQuery, UniverseQuery

        symbols = sorted(self.data.universe(UniverseQuery(self.start, self.end)))
        sessions = self._clock.sessions(self.start, self.end)
        session_index = pd.DatetimeIndex(sessions)

        persist = output_dir is not None
        hash_tables: list[pa.Table] = []

        bars_by_tf: dict[str, dict[pd.Timestamp, list[BarUnit]]] = {}
        dropped_bars: list[tuple[str, pd.Timestamp]] = []
        for tf in self._timeframes:
            table = self.data.bars(BarQuery(tuple(symbols), self.start, self.end, timeframe=tf))
            if persist:
                hash_tables.append(table)
            rolled, dropped = rebucket_to_sessions(self._index_bars(table, tf), session_index)
            bars_by_tf[tf] = rolled
            dropped_bars.extend((tf, d) for d in dropped)

        actions_table = self.data.corporate_actions(
            ActionQuery(tuple(symbols), self.start, self.end)
        )
        if persist:
            hash_tables.append(actions_table)
        actions_by_date, dropped_actions = rebucket_to_sessions(
            self._index_actions(actions_table), session_index
        )
        self._warn_unrollable(dropped_bars, dropped_actions)

        self.strategy.on_start(self._make_ctx(self.start, frozenset(symbols)))

        n_active_sessions = 0
        for session in tqdm(sessions):
            session = pd.Timestamp(session)
            if self._process_session(session, bars_by_tf, actions_by_date):
                n_active_sessions += 1

        self.strategy.on_finish(self._make_ctx(self.end, frozenset(symbols)))

        meta: dict[str, Any] = {
            "n_sessions": n_active_sessions,
            "start": str(self.start),
            "end": str(self.end),
            "strategy_id": self.strategy.strategy_id,
        }
        result = Result(
            equity_curve=self.portfolio.equity_curve(),
            trades=self._trades_frame(),
            positions=self._positions_frame(),
            diagnostics=self._diagnostics_frame(),
            meta=meta,
        )
        if persist:
            self._write_run(result, symbols, output_dir, run_id, meta_extra, hash_tables)
        return result

    def sessions(self) -> pd.DatetimeIndex:
        """Return the trading sessions this engine will iterate over [start, end]."""
        return pd.DatetimeIndex(self._clock.sessions(self.start, self.end))

    def _write_run(
        self,
        result: Result,
        symbols: list[str],
        output_dir: str | Path,
        run_id: str | None,
        meta_extra: dict[str, Any] | None,
        hash_tables: list[pa.Table],
    ) -> None:
        import datetime as _dt

        from persistra.core import artifacts
        from persistra.utils import (
            captured_versions,
            configure_logging,
            data_hash,
            git_info,
            run_hash,
        )

        extra = dict(meta_extra or {})
        assert hash_tables, "persist path requires at least one loaded table"
        fingerprint = {
            "symbols": symbols,
            "start": str(self.start),
            "end": str(self.end),
            "timeframes": list(self._timeframes),
            "calendar": self._calendar.name,
            "strategy_id": self.strategy.strategy_id,
            **extra,
        }
        rhash = run_hash(fingerprint)
        if run_id is None:
            stamp = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H-%M-%S-%f")
            run_id = f"{stamp}-{rhash[:8]}"

        run_dir = Path(output_dir) / run_id
        configure_logging(run_dir)

        _git = git_info()
        result.meta.update(
            {
                **extra,
                "run_id": run_id,
                "run_hash": rhash,
                "data_hash": data_hash(*hash_tables),
                "git_sha": _git["git_sha"],
                "git_info": _git,
                "versions": captured_versions(),
            }
        )
        artifacts.save(result, run_dir)

    def _index_bars(self, table: pa.Table, timeframe: str) -> dict[pd.Timestamp, list[BarUnit]]:
        """Group one timeframe's already-loaded bars into BarUnits by (session, bar_time)."""
        out: dict[pd.Timestamp, list[BarUnit]] = {}
        if table.num_rows == 0:
            return out
        df = table.to_pandas()
        df["bar_time"] = pd.to_datetime(df["bar_time"])
        duration = self._durations[timeframe]
        for day, day_group in df.groupby(df["bar_time"].dt.normalize()):
            session_units: list[BarUnit] = []
            for bt, bt_group in day_group.groupby("bar_time"):
                bt = pd.Timestamp(bt)
                unit = BarUnit(
                    timeframe=timeframe,
                    timestamp=bt,
                    eff_close=bt + duration,
                    duration=duration,
                    symbols=list(bt_group["symbol"].astype(str)),
                    opens=bt_group["open"].to_numpy(dtype=float),
                    highs=bt_group["high"].to_numpy(dtype=float),
                    lows=bt_group["low"].to_numpy(dtype=float),
                    closes=bt_group["close"].to_numpy(dtype=float),
                    volumes=bt_group["volume"].to_numpy(dtype=float),
                )
                session_units.append(unit)
            out[pd.Timestamp(day)] = session_units
        return out

    def _index_actions(self, table: pa.Table) -> dict[pd.Timestamp, list[dict[str, Any]]]:
        out: dict[pd.Timestamp, list[dict[str, Any]]] = {}
        if table.num_rows == 0:
            return out
        df = table.to_pandas()
        df["date"] = pd.to_datetime(df["date"])
        columns = {name: df[name].to_numpy() for name in df.columns}
        rows = [{name: col[i] for name, col in columns.items()} for i in range(len(df))]
        for row in rows:
            day = pd.Timestamp(row["date"]).normalize()
            out.setdefault(day, []).append(row)
        return out

    def _warn_unrollable(
        self,
        dropped_bars: list[tuple[str, pd.Timestamp]],
        dropped_actions: list[pd.Timestamp],
    ) -> None:
        by_tf: dict[str, list[pd.Timestamp]] = {}
        for tf, date in dropped_bars:
            by_tf.setdefault(tf, []).append(date)
        for tf, dates in by_tf.items():
            logger.warning(
                "%s bars on dates with no following session dropped: %s",
                tf,
                [d.date().isoformat() for d in sorted(dates)],
            )
        if dropped_actions:
            logger.warning(
                "corporate actions on dates with no following session dropped: %s",
                [d.date().isoformat() for d in sorted(dropped_actions)],
            )

    def _process_session(
        self,
        session: pd.Timestamp,
        bars_by_tf: dict[str, dict[pd.Timestamp, list[BarUnit]]],
        actions_by_date: dict[pd.Timestamp, list[dict[str, Any]]],
    ) -> bool:
        """Apply this session's corporate actions, then dispatch its bar units.

        Returns True if any bar units existed for this session."""
        members = self.strategy.universe_on(session, self.data.active_universe(session))
        self._apply_actions(session, actions_by_date, members)

        session_bars: dict[str, list[BarUnit]] = {}
        for tf in self._timeframes:
            units = bars_by_tf[tf].get(session, [])
            if units:
                session_bars[tf] = units
        if not session_bars:
            return False

        for unit in order_session_units(session_bars):
            self._dispatch_unit(unit, members)
        return True

    def _apply_actions(
        self,
        session: pd.Timestamp,
        actions_by_date: dict[pd.Timestamp, list[dict[str, Any]]],
        members: frozenset[str],
    ) -> None:
        for row in actions_by_date.get(session, []):
            symbol = str(row["symbol"])
            if symbol not in members:
                continue
            action_type = str(row["action_type"])
            if action_type == "split":
                ratio = row.get("ratio")
                if ratio is None or pd.isna(ratio):
                    continue
                self.portfolio.on_split(
                    SplitEvent(timestamp=session, symbol=symbol, ratio=float(ratio))
                )
            elif action_type == "dividend":
                amount = row.get("amount")
                if amount is None or pd.isna(amount):
                    continue
                self.portfolio.on_dividend(
                    DividendEvent(timestamp=session, symbol=symbol, amount=float(amount))
                )

    def _dispatch_unit(self, unit: BarUnit, members: frozenset[str]) -> None:
        history = self._histories[unit.timeframe]
        unit_closes: dict[str, BarCloseEvent] = {}
        for i, sym in enumerate(unit.symbols):
            if sym not in members:
                continue
            event = BarCloseEvent(
                timestamp=unit.timestamp,
                symbol=sym,
                open=float(unit.opens[i]),
                high=float(unit.highs[i]),
                low=float(unit.lows[i]),
                close=float(unit.closes[i]),
                volume=float(unit.volumes[i]),
            )
            history.update(event)
            self.portfolio.on_bar_close(event)
            self._priced.add(sym)
            unit_closes[sym] = event

        if self._histories[self._primary_tf].available_bars() >= self.strategy.warmup:
            tradable = members & self._priced
            self._run_strategy(unit.timeframe, unit.timestamp, tradable, unit_closes)

        if unit.timeframe == self._finest_tf:
            snap = self.portfolio.snapshot()
            self.portfolio.record_equity(unit.timestamp, snap=snap)
            self._record_positions(unit.timestamp, snap=snap)

    def _run_strategy(
        self,
        timeframe: str,
        timestamp: pd.Timestamp,
        universe: frozenset[str],
        unit_closes: dict[str, BarCloseEvent],
    ) -> None:
        ctx = self._make_ctx(timestamp, universe, timeframe=timeframe)
        self.strategy.on_bar(ctx)
        self._diagnostic_rows.extend(ctx.recorded)
        weights = ctx.emitted_weights
        if weights is None:
            return
        for order in self.portfolio.target_orders(weights, timestamp, ctx.portfolio.equity):
            bar = unit_closes.get(order.symbol)
            if bar is None:
                continue
            fill = self._execution_model.fill(order, bar)
            self.portfolio.on_fill(fill)
            self._trade_rows.append(
                {
                    "timestamp": fill.timestamp,
                    "symbol": fill.symbol,
                    "quantity": float(fill.quantity),
                    "fill_price": float(fill.fill_price),
                    "commission": float(fill.commission),
                }
            )

    def _make_ctx(
        self,
        timestamp: pd.Timestamp,
        universe: frozenset[str],
        timeframe: str | None = None,
    ) -> StrategyContext:
        state: PortfolioState = self.portfolio.snapshot()
        return StrategyContext(
            timestamp=timestamp,
            timeframe=timeframe or self._primary_tf,
            histories=self._histories,
            portfolio=state,
            universe=universe,
        )

    def _record_positions(
        self, timestamp: pd.Timestamp, snap: PortfolioState | None = None
    ) -> None:
        if snap is None:
            snap = self.portfolio.snapshot()
        for sym, weight in snap.weights.items():
            if weight != 0.0:
                self._position_rows.append({"bar_time": timestamp, "symbol": sym, "weight": weight})

    def _positions_frame(self) -> pd.DataFrame:
        cols = ["bar_time", "symbol", "weight"]
        if not self._position_rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(self._position_rows, columns=cols)

    def _diagnostics_frame(self) -> pd.DataFrame:
        cols = ["bar_time", "timeframe", "name", "symbol", "value"]
        if not self._diagnostic_rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(self._diagnostic_rows, columns=cols)

    def _trades_frame(self) -> pd.DataFrame:
        cols = ["timestamp", "symbol", "quantity", "fill_price", "commission"]
        if not self._trade_rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(self._trade_rows, columns=cols)
