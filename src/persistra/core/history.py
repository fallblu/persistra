from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from .events import BarCloseEvent

_FIELDS = ("open", "high", "low", "close", "volume")


class HistoryView:
    """Rolling window of bar data, exposed as per-field DataFrames.

    Backed by one preallocated NumPy 2D array per OHLCV field (rows = distinct
    bar timestamps, columns = symbols). The engine populates it bar-by-bar via
    :meth:`update`; strategies receive a reference and must not mutate it.

    Assumes ``update`` is called with monotonically non-decreasing timestamps.
    Distinct timestamps are capped at ``max_bars``; older rows are evicted.

    Symbol presence is tracked per-column via ``_last_present_row``: the row
    index of the most recent bar written for each column. A symbol is "live" in
    a window if ``_last_present_row[col] >= win_start``. This replaces the old
    O(n_bars × n_cols) boolean-matrix ``.any()`` scan with an O(n_cols) compare.

    Columns are also maintained in a sorted list (``_sorted_symbols``) via
    ``bisect.insort``, so ``_field_frame`` can produce sorted column output in
    O(n_live) without re-sorting on every call.
    """

    def __init__(self, max_bars: int = 1000) -> None:
        if max_bars < 1:
            raise ValueError(f"max_bars must be >= 1, got {max_bars}")
        self._max_bars = max_bars
        self._row_cap = max(2 * max_bars, 2)
        self._col_cap = 8
        self._n = 0
        self._timestamps: list[pd.Timestamp] = []
        self._symbols: list[str] = []  # insertion order; index == column
        self._sorted_symbols: list[str] = []  # same symbols, maintained sorted
        self._col_of: dict[str, int] = {}
        self._data: dict[str, np.ndarray] = {
            f: np.full((self._row_cap, self._col_cap), np.nan) for f in _FIELDS
        }
        # Per-column: row index of most recent bar for that symbol; -1 = never seen.
        self._last_present_row = np.full(self._col_cap, -1, dtype=np.intp)

    def update(self, event: BarCloseEvent) -> None:
        """Ingest a bar-close event into the rolling history window.

        Records the OHLCV data from ``event`` at the appropriate row for the
        event's timestamp.  If the buffer exceeds ``max_bars`` rows after the
        write, the oldest rows are evicted.  Timestamps must arrive in
        monotonically non-decreasing order.

        Args:
            event: The bar-close event whose data should be stored.
        """
        ts = event.timestamp
        if not self._timestamps or self._timestamps[-1] != ts:
            if self._n == self._row_cap:
                self._compact()
            self._timestamps.append(ts)
            self._n += 1
        row = self._n - 1
        col = self._column_for(event.symbol)
        for field in _FIELDS:
            self._data[field][row, col] = getattr(event, field)
        self._last_present_row[col] = row
        # Eagerly compact when buffer exceeds max_bars so _last_present_row
        # always reflects the actual retained window after each update.
        if self._n > self._max_bars:
            self._compact()

    def available_bars(self) -> int:
        """Return the number of bar timestamps currently held in the window.

        Returns:
            The count of distinct timestamps retained, capped at ``max_bars``.
        """
        return min(self._n, self._max_bars)

    def closes(self, lookback: int) -> pd.DataFrame:
        """Return closing prices for all live symbols over the last ``lookback`` bars.

        Args:
            lookback: Maximum number of bars to include, counting back from the
                most recent.  Clamped to the number of available bars.

        Returns:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` of bar timestamps and
            one column per symbol that has data in the current window, sorted
            alphabetically.  Missing values are ``NaN``.
        """
        return self._field_frame("close", lookback)

    def opens(self, lookback: int) -> pd.DataFrame:
        """Return opening prices for all live symbols over the last ``lookback`` bars.

        Args:
            lookback: Maximum number of bars to include, counting back from the
                most recent.  Clamped to the number of available bars.

        Returns:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` of bar timestamps and
            one column per symbol that has data in the current window, sorted
            alphabetically.  Missing values are ``NaN``.
        """
        return self._field_frame("open", lookback)

    def highs(self, lookback: int) -> pd.DataFrame:
        """Return high prices for all live symbols over the last ``lookback`` bars.

        Args:
            lookback: Maximum number of bars to include, counting back from the
                most recent.  Clamped to the number of available bars.

        Returns:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` of bar timestamps and
            one column per symbol that has data in the current window, sorted
            alphabetically.  Missing values are ``NaN``.
        """
        return self._field_frame("high", lookback)

    def lows(self, lookback: int) -> pd.DataFrame:
        """Return low prices for all live symbols over the last ``lookback`` bars.

        Args:
            lookback: Maximum number of bars to include, counting back from the
                most recent.  Clamped to the number of available bars.

        Returns:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` of bar timestamps and
            one column per symbol that has data in the current window, sorted
            alphabetically.  Missing values are ``NaN``.
        """
        return self._field_frame("low", lookback)

    def volumes(self, lookback: int) -> pd.DataFrame:
        """Return trading volumes for all live symbols over the last ``lookback`` bars.

        Args:
            lookback: Maximum number of bars to include, counting back from the
                most recent.  Clamped to the number of available bars.

        Returns:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` of bar timestamps and
            one column per symbol that has data in the current window, sorted
            alphabetically.  Missing values are ``NaN``.
        """
        return self._field_frame("volume", lookback)

    # -- internals -----------------------------------------------------

    def _column_for(self, symbol: str) -> int:
        idx = self._col_of.get(symbol)
        if idx is not None:
            return idx
        idx = len(self._symbols)
        if idx == self._col_cap:
            self._grow_columns()
        self._symbols.append(symbol)
        bisect.insort(self._sorted_symbols, symbol)
        self._col_of[symbol] = idx
        return idx

    def _grow_columns(self) -> None:
        new_cap = self._col_cap * 2
        for field in _FIELDS:
            grown = np.full((self._row_cap, new_cap), np.nan)
            grown[:, : self._col_cap] = self._data[field]
            self._data[field] = grown
        grown_lpr = np.full(new_cap, -1, dtype=np.intp)
        grown_lpr[: self._col_cap] = self._last_present_row
        self._last_present_row = grown_lpr
        self._col_cap = new_cap

    def _compact(self) -> None:
        """Drop all but the last ``max_bars`` rows in one slice copy."""
        assert self._n >= self._max_bars
        keep = self._max_bars
        start = self._n - keep
        for field in _FIELDS:
            arr = self._data[field]
            arr[:keep, :] = arr[start : self._n, :]
            arr[keep:, :] = np.nan
        # Shift row indices; entries that preceded the retained window become -1.
        self._last_present_row = np.where(
            self._last_present_row >= start,
            self._last_present_row - start,
            -1,
        )
        self._timestamps = self._timestamps[start:]
        self._n = keep

    def _field_frame(self, field: str, lookback: int) -> pd.DataFrame:
        window = min(self._n, self._max_bars)
        if window == 0 or not self._symbols:
            return pd.DataFrame(index=pd.DatetimeIndex([]))
        arr = self._data[field]
        n_cols = len(self._symbols)
        win_start = self._n - window
        # O(n_cols) live check — replaces former O(n_bars × n_cols) .any() scan.
        live = self._last_present_row[:n_cols] >= win_start
        live_syms = [s for s in self._sorted_symbols if live[self._col_of[s]]]
        take = max(0, min(lookback, window))
        take_start = self._n - take
        index = pd.DatetimeIndex(self._timestamps[take_start : self._n])
        if not live_syms:
            return pd.DataFrame(index=index)
        cols = [self._col_of[s] for s in live_syms]
        data = arr[take_start : self._n][:, cols]
        return pd.DataFrame(data, index=index, columns=live_syms)
