from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import numpy as np
import pandas as pd
from tqdm import tqdm

from persistra.data.calendar import TradingCalendar

from ..strategy.context import StrategyContext
from .clock import Clock
from .events import BarCloseEvent, DividendEvent, OrderEvent, OrderType, SplitEvent
from .execution import ExecutionModel, ExecutionTiming, IdealFill
from .history import HistoryView
from .result import Result
from .timeframe import timeframe_duration

if TYPE_CHECKING:
    import pyarrow as pa

    from persistra.data.store import MarketData

    from ..strategy.base import Strategy
    from .events import FillEvent
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


@dataclass
class PendingOrder:
    """Order waiting for a future bar under delayed execution timing."""

    order_id: str
    order: OrderEvent
    timeframe: str
    delay_required: int
    origin: str
    bars_seen: int = 0


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

    _STREAM_CHUNK_DAYS = 92

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
        execution_timing: ExecutionTiming | str = ExecutionTiming.SAME_CLOSE,
        delay_bars: int | None = None,
        universe_name: str = "default",
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
        self._order_rows: list[dict[str, Any]] = []
        self._order_row_by_id: dict[str, dict[str, Any]] = {}
        self._next_order_number = 1
        self._position_rows: list[dict[str, Any]] = []
        self._diagnostic_rows: list[dict[str, Any]] = []
        self._priced: set[str] = set()
        self._execution_model: ExecutionModel = (
            execution_model if execution_model is not None else IdealFill()
        )
        self._execution_timing = self._coerce_execution_timing(execution_timing)
        self._delay_bars = self._coerce_delay_bars(self._execution_timing, delay_bars)
        self._universe_name = str(universe_name)
        self._pending_orders: list[PendingOrder] = []
        self._stale_exit_order_ids: dict[str, str] = {}
        self._stale_detected: set[str] = set()
        self._has_run = False

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
        from persistra.data.store import StreamingMarketData, UniverseQuery

        if self._has_run:
            raise RuntimeError(
                "Engine.run() is single-use; create fresh Engine, Strategy, and "
                "Portfolio instances for each run"
            )
        self._has_run = True

        symbols = sorted(
            self.data.universe(UniverseQuery(self.start, self.end, self._universe_name))
        )
        sessions = self._clock.sessions(self.start, self.end)
        session_index = pd.DatetimeIndex(sessions)

        persist = output_dir is not None
        hash_tables: list[pa.Table] = []

        self.strategy.on_start(self._make_ctx(self.start, frozenset(symbols)))

        if isinstance(self.data, StreamingMarketData):
            n_active_sessions = self._run_streaming_sessions(
                symbols, sessions, session_index, persist, hash_tables
            )
        else:
            n_active_sessions = self._run_eager_sessions(
                symbols, sessions, session_index, persist, hash_tables
            )

        self.strategy.on_finish(self._make_ctx(self.end, frozenset(symbols)))
        self._mark_unfilled_orders(self.end, reason="no_future_matching_bar")

        meta: dict[str, Any] = {
            "n_sessions": n_active_sessions,
            "start": str(self.start),
            "end": str(self.end),
            "strategy_id": self.strategy.strategy_id,
            "execution_timing": self._execution_timing.value,
            "delay_bars": self._delay_bars,
        }
        result = Result(
            equity_curve=self.portfolio.equity_curve(),
            trades=self._trades_frame(),
            positions=self._positions_frame(),
            orders=self._orders_frame(),
            diagnostics=self._diagnostics_frame(),
            meta=meta,
        )
        if persist:
            self._write_run(result, symbols, output_dir, run_id, meta_extra, hash_tables)
        return result

    @staticmethod
    def _coerce_execution_timing(timing: ExecutionTiming | str) -> ExecutionTiming:
        if isinstance(timing, ExecutionTiming):
            return timing
        try:
            return ExecutionTiming(str(timing))
        except ValueError as exc:
            allowed = ", ".join(t.value for t in ExecutionTiming)
            raise ValueError(f"execution_timing must be one of: {allowed}") from exc

    @staticmethod
    def _coerce_delay_bars(timing: ExecutionTiming, delay_bars: int | None) -> int:
        if timing == ExecutionTiming.DELAY_BARS:
            if delay_bars is None:
                raise ValueError("delay_bars is required when execution_timing='delay_bars'")
            if delay_bars < 1:
                raise ValueError(f"delay_bars must be >= 1, got {delay_bars}")
            return int(delay_bars)
        if delay_bars is not None:
            raise ValueError("delay_bars is only valid when execution_timing='delay_bars'")
        return 0

    def _run_eager_sessions(
        self,
        symbols: list[str],
        sessions: pd.DatetimeIndex,
        session_index: pd.DatetimeIndex,
        persist: bool,
        hash_tables: list[pa.Table],
    ) -> int:
        from persistra.data.store import ActionQuery, BarQuery

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

        n_active_sessions = 0
        for session in tqdm(sessions):
            session = pd.Timestamp(session)
            if self._process_session(session, bars_by_tf, actions_by_date):
                n_active_sessions += 1
        return n_active_sessions

    def _run_streaming_sessions(
        self,
        symbols: list[str],
        sessions: pd.DatetimeIndex,
        session_index: pd.DatetimeIndex,
        persist: bool,
        hash_tables: list[pa.Table],
    ) -> int:
        from persistra.data.store import ActionQuery, BarQuery, StreamingMarketData

        data = self.data
        assert isinstance(data, StreamingMarketData)

        n_active_sessions = 0
        all_dropped_bars: list[tuple[str, pd.Timestamp]] = []
        all_dropped_actions: list[pd.Timestamp] = []
        previous_session: pd.Timestamp | None = None
        for window_sessions in self._session_windows(sessions):
            window_end = pd.Timestamp(window_sessions[-1])
            query_start = (
                self.start
                if previous_session is None
                else previous_session + pd.Timedelta(microseconds=1)
            )
            bars_by_tf: dict[str, dict[pd.Timestamp, list[BarUnit]]] = {}
            for tf in self._timeframes:
                tf_bars: dict[pd.Timestamp, list[BarUnit]] = {}
                for table in data.bar_chunks(
                    BarQuery(tuple(symbols), query_start, window_end, timeframe=tf),
                    chunk_days=self._STREAM_CHUNK_DAYS,
                ):
                    if persist:
                        hash_tables.append(table)
                    rolled, dropped = rebucket_to_sessions(
                        self._index_bars(table, tf), session_index
                    )
                    self._merge_indexed_units(tf_bars, rolled)
                    all_dropped_bars.extend((tf, d) for d in dropped)
                bars_by_tf[tf] = tf_bars

            actions_by_date: dict[pd.Timestamp, list[dict[str, Any]]] = {}
            for table in data.corporate_action_chunks(
                ActionQuery(tuple(symbols), query_start, window_end),
                chunk_days=self._STREAM_CHUNK_DAYS,
            ):
                if persist:
                    hash_tables.append(table)
                rolled, dropped = rebucket_to_sessions(self._index_actions(table), session_index)
                self._merge_indexed_rows(actions_by_date, rolled)
                all_dropped_actions.extend(dropped)

            for session in tqdm(pd.DatetimeIndex(window_sessions)):
                session = pd.Timestamp(session)
                if self._process_session(session, bars_by_tf, actions_by_date):
                    n_active_sessions += 1
            previous_session = window_end

        self._warn_unrollable(all_dropped_bars, all_dropped_actions)
        return n_active_sessions

    def _session_windows(self, sessions: pd.DatetimeIndex) -> list[pd.DatetimeIndex]:
        windows: list[pd.DatetimeIndex] = []
        start = 0
        while start < len(sessions):
            first = pd.Timestamp(sessions[start])
            limit = first + pd.Timedelta(days=self._STREAM_CHUNK_DAYS - 1)
            end = start
            while end + 1 < len(sessions) and pd.Timestamp(sessions[end + 1]) <= limit:
                end += 1
            windows.append(pd.DatetimeIndex(sessions[start : end + 1]))
            start = end + 1
        return windows

    @staticmethod
    def _merge_indexed_units(
        target: dict[pd.Timestamp, list[BarUnit]],
        source: dict[pd.Timestamp, list[BarUnit]],
    ) -> None:
        for key, value in source.items():
            target.setdefault(key, []).extend(value)

    @staticmethod
    def _merge_indexed_rows(
        target: dict[pd.Timestamp, list[dict[str, Any]]],
        source: dict[pd.Timestamp, list[dict[str, Any]]],
    ) -> None:
        for key, value in source.items():
            target.setdefault(key, []).extend(value)

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
        table = table.select(["bar_time", "symbol", "open", "high", "low", "close", "volume"])
        duration = self._durations[timeframe]
        columns = table.to_pydict()
        grouped: dict[pd.Timestamp, dict[pd.Timestamp, list[int]]] = {}
        for i, raw_bar_time in enumerate(columns["bar_time"]):
            bar_time = pd.Timestamp(raw_bar_time)
            day = bar_time.normalize()
            grouped.setdefault(day, {}).setdefault(bar_time, []).append(i)

        for day in sorted(grouped):
            session_units = []
            for bar_time in sorted(grouped[day]):
                indices = grouped[day][bar_time]
                unit = BarUnit(
                    timeframe=timeframe,
                    timestamp=bar_time,
                    eff_close=bar_time + duration,
                    duration=duration,
                    symbols=[str(columns["symbol"][i]) for i in indices],
                    opens=np.asarray([columns["open"][i] for i in indices], dtype=float),
                    highs=np.asarray([columns["high"][i] for i in indices], dtype=float),
                    lows=np.asarray([columns["low"][i] for i in indices], dtype=float),
                    closes=np.asarray([columns["close"][i] for i in indices], dtype=float),
                    volumes=np.asarray([columns["volume"][i] for i in indices], dtype=float),
                )
                session_units.append(unit)
            out[day] = session_units
        return out

    def _index_actions(self, table: pa.Table) -> dict[pd.Timestamp, list[dict[str, Any]]]:
        out: dict[pd.Timestamp, list[dict[str, Any]]] = {}
        if table.num_rows == 0:
            return out
        columns = table.to_pydict()
        for i in range(table.num_rows):
            row = {name: values[i] for name, values in columns.items()}
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
        members = self.strategy.universe_on(
            session,
            self.data.active_universe(session, self._universe_name),
        )
        self._apply_actions(session, actions_by_date, members)
        self._record_stale_holding_diagnostics(session, members)
        self._ensure_stale_exit_orders(session, members)

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
            event = BarCloseEvent(
                timestamp=unit.timestamp,
                symbol=sym,
                open=float(unit.opens[i]),
                high=float(unit.highs[i]),
                low=float(unit.lows[i]),
                close=float(unit.closes[i]),
                volume=float(unit.volumes[i]),
            )
            self._fill_pending_orders(unit.timeframe, event)
            if sym not in members:
                continue
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
            if self._execution_timing == ExecutionTiming.SAME_CLOSE:
                order_id = self._record_order(order, timeframe=timeframe, origin="strategy")
                self._execute_order(
                    order_id,
                    order,
                    bar,
                    use_open=False,
                    timeframe=timeframe,
                )
            else:
                order_id = self._record_order(order, timeframe=timeframe, origin="strategy")
                self._pending_orders.append(
                    PendingOrder(
                        order_id=order_id,
                        order=order,
                        timeframe=timeframe,
                        delay_required=self._delay_required(),
                        origin="strategy",
                    )
                )

    def _fill_pending_orders(self, timeframe: str, bar: BarCloseEvent) -> None:
        if not self._pending_orders:
            return
        remaining: list[PendingOrder] = []
        for pending in self._pending_orders:
            if pending.timeframe != timeframe or pending.order.symbol != bar.symbol:
                remaining.append(pending)
                continue
            pending.bars_seen += 1
            if self._pending_order_is_ready(pending):
                self._execute_order(
                    pending.order_id,
                    pending.order,
                    bar,
                    use_open=(
                        pending.origin == "strategy"
                        and self._execution_timing == ExecutionTiming.NEXT_OPEN
                    ),
                    timeframe=timeframe,
                )
            else:
                remaining.append(pending)
        self._pending_orders = remaining

    def _pending_order_is_ready(self, pending: PendingOrder) -> bool:
        if pending.origin == "engine_universe_exit":
            return pending.bars_seen >= 1
        if self._execution_timing in (ExecutionTiming.NEXT_OPEN, ExecutionTiming.NEXT_CLOSE):
            return pending.bars_seen >= 1
        if self._execution_timing == ExecutionTiming.DELAY_BARS:
            return pending.bars_seen >= self._delay_bars
        return False

    def _execute_order(
        self,
        order_id: str,
        order: OrderEvent,
        bar: BarCloseEvent,
        *,
        use_open: bool,
        timeframe: str,
    ) -> None:
        execution_bar = replace(bar, close=bar.open) if use_open else bar
        fill = self._execution_model.fill(order, execution_bar)
        order_timestamp = (
            fill.order_timestamp if fill.order_timestamp is not None else order.timestamp
        )
        if fill.timestamp != bar.timestamp or fill.order_timestamp is None:
            fill = replace(fill, timestamp=bar.timestamp, order_timestamp=order_timestamp)
        if not fill.order_ref:
            fill = replace(fill, order_ref=order_id)
        decision = self.portfolio.on_fill(fill)
        if not decision.accepted:
            self._mark_order_rejected(order_id, fill, decision)
            self._record_rejected_fill(timeframe, fill, decision)
            return
        self._mark_order_filled(order_id, fill)
        self._trade_rows.append(
            {
                "order_timestamp": order_timestamp,
                "timestamp": fill.timestamp,
                "symbol": fill.symbol,
                "quantity": float(fill.quantity),
                "fill_price": float(fill.fill_price),
                "commission": float(fill.commission),
            }
        )

    def _delay_required(self) -> int:
        if self._execution_timing in (ExecutionTiming.NEXT_OPEN, ExecutionTiming.NEXT_CLOSE):
            return 1
        if self._execution_timing == ExecutionTiming.DELAY_BARS:
            return self._delay_bars
        return 0

    def _next_order_id(self) -> str:
        order_id = f"order_{self._next_order_number:08d}"
        self._next_order_number += 1
        return order_id

    def _record_order(
        self,
        order: OrderEvent,
        *,
        timeframe: str,
        origin: str,
        execution_timing: ExecutionTiming | None = None,
        delay_required: int | None = None,
    ) -> str:
        timing = execution_timing or self._execution_timing
        required = self._delay_required() if delay_required is None else int(delay_required)
        order_id = self._next_order_id()
        row = {
            "order_id": order_id,
            "order_timestamp": order.timestamp,
            "terminal_timestamp": pd.NaT,
            "timeframe": timeframe,
            "symbol": order.symbol,
            "quantity": float(order.quantity),
            "execution_timing": timing.value,
            "delay_required": required,
            "bars_seen": 0,
            "status": "",
            "reason": "",
            "fill_timestamp": pd.NaT,
            "fill_price": pd.NA,
            "commission": pd.NA,
            "portfolio_constraint": pd.NA,
            "origin": origin,
        }
        self._order_rows.append(row)
        self._order_row_by_id[order_id] = row
        return order_id

    def _mark_order_filled(self, order_id: str, fill: FillEvent) -> None:
        row = self._order_row_by_id[order_id]
        row.update(
            {
                "terminal_timestamp": fill.timestamp,
                "bars_seen": self._bars_seen_for_order(order_id),
                "status": "filled",
                "reason": "filled",
                "fill_timestamp": fill.timestamp,
                "fill_price": float(fill.fill_price),
                "commission": float(fill.commission),
            }
        )

    def _mark_order_rejected(self, order_id: str, fill: FillEvent, decision: Any) -> None:
        row = self._order_row_by_id[order_id]
        row.update(
            {
                "terminal_timestamp": fill.timestamp,
                "bars_seen": self._bars_seen_for_order(order_id),
                "status": "rejected",
                "reason": "portfolio_constraint",
                "fill_timestamp": fill.timestamp,
                "fill_price": float(fill.fill_price),
                "commission": float(fill.commission),
                "portfolio_constraint": float(decision.constraint),
            }
        )

    def _bars_seen_for_order(self, order_id: str) -> int:
        for pending in self._pending_orders:
            if pending.order_id == order_id:
                return pending.bars_seen
        return 0

    def _mark_unfilled_orders(self, timestamp: pd.Timestamp, *, reason: str) -> None:
        if not self._pending_orders:
            return
        for pending in self._pending_orders:
            row = self._order_row_by_id[pending.order_id]
            if row["status"]:
                continue
            pending_reason = (
                "stale_holding_no_price"
                if pending.origin == "engine_universe_exit"
                else reason
            )
            row.update(
                {
                    "terminal_timestamp": timestamp,
                    "bars_seen": pending.bars_seen,
                    "status": "unfilled",
                    "reason": pending_reason,
                }
            )
        self._pending_orders = []

    def _record_stale_holding_diagnostics(
        self,
        timestamp: pd.Timestamp,
        members: frozenset[str],
    ) -> None:
        snap = self.portfolio.snapshot()
        stale_symbols = sorted(
            sym for sym, qty in snap.positions.items() if qty != 0 and sym not in members
        )
        for symbol in stale_symbols:
            rows = {
                "holding_stale": 1.0,
                "holding_stale_weight": float(snap.weights.get(symbol, 0.0)),
            }
            if symbol not in self._stale_detected:
                rows["universe_exit"] = 1.0
                self._stale_detected.add(symbol)
            for name, value in rows.items():
                self._diagnostic_rows.append(
                    {
                        "bar_time": timestamp,
                        "timeframe": self._primary_tf,
                        "name": name,
                        "symbol": symbol,
                        "value": value,
                    }
                )

    def _ensure_stale_exit_orders(
        self,
        timestamp: pd.Timestamp,
        members: frozenset[str],
    ) -> None:
        snap = self.portfolio.snapshot()
        for symbol, quantity in sorted(snap.positions.items()):
            if quantity == 0 or symbol in members:
                continue
            existing = self._stale_exit_order_ids.get(symbol)
            if existing is not None and not self._order_row_by_id[existing]["status"]:
                continue
            order = OrderEvent(
                timestamp=timestamp,
                symbol=symbol,
                order_type=OrderType.MOC,
                quantity=-float(quantity),
            )
            order_id = self._record_order(
                order,
                timeframe=self._primary_tf,
                origin="engine_universe_exit",
                execution_timing=ExecutionTiming.SAME_CLOSE,
                delay_required=0,
            )
            self._stale_exit_order_ids[symbol] = order_id
            self._pending_orders.append(
                PendingOrder(
                    order_id=order_id,
                    order=order,
                    timeframe=self._primary_tf,
                    delay_required=0,
                    origin="engine_universe_exit",
                )
            )

    def _record_rejected_fill(self, timeframe: str, fill: FillEvent, decision: Any) -> None:
        rows = {
            "portfolio_order_rejected": 1.0,
            "portfolio_rejection_constraint": float(decision.constraint),
            "portfolio_requested_quantity": float(decision.requested_quantity),
            "portfolio_post_cash": float(decision.post_cash),
            "portfolio_post_gross_exposure": float(decision.post_gross_exposure),
            "portfolio_post_net_exposure": float(decision.post_net_exposure),
        }
        for name, value in rows.items():
            self._diagnostic_rows.append(
                {
                    "bar_time": fill.timestamp,
                    "timeframe": timeframe,
                    "name": name,
                    "symbol": fill.symbol,
                    "value": value,
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
        cols = ["order_timestamp", "timestamp", "symbol", "quantity", "fill_price", "commission"]
        if not self._trade_rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(self._trade_rows, columns=cols)

    def _orders_frame(self) -> pd.DataFrame:
        cols = [
            "order_id",
            "order_timestamp",
            "terminal_timestamp",
            "timeframe",
            "symbol",
            "quantity",
            "execution_timing",
            "delay_required",
            "bars_seen",
            "status",
            "reason",
            "fill_timestamp",
            "fill_price",
            "commission",
            "portfolio_constraint",
            "origin",
        ]
        if not self._order_rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(self._order_rows, columns=cols)
