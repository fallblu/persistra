from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import TYPE_CHECKING, Any

from tqdm import tqdm

from persistra.providers.massive.aggregates import fetch_aggregates
from persistra.providers.massive.client import make_client

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pyarrow as pa

    from persistra.data.store import MarketDataWriter

_log = logging.getLogger(__name__)

MAX_WORKERS: int = 30
MAX_RETRIES: int = 5
BASE_DELAY: float = 1.0
MAX_DELAY: float = 60.0

_thread_local = threading.local()


class Checkpoint:
    """Thread-safe checkpoint backed by an atomically-written JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        data: dict[str, list[str]] = {}
        if path.exists():
            data = json.loads(path.read_text())
        self._completed: set[str] = set(data.get("completed", []))
        self._failed: set[str] = set(data.get("failed", []))

    def is_done(self, key: str) -> bool:
        """Return True if the key has already been completed or permanently failed.

        Args:
            key: Checkpoint key, typically ``"<symbol>::<timeframe>"``.

        Returns:
            True if the key appears in either the completed or failed set.
        """
        return key in self._completed or key in self._failed

    def mark_completed(self, key: str) -> None:
        """Record a key as successfully completed and flush to disk.

        Thread-safe: acquires the internal lock before mutating state.

        Args:
            key: Checkpoint key to mark as completed.
        """
        with self._lock:
            self._completed.add(key)
            self._flush()

    def mark_failed(self, key: str) -> None:
        """Record a key as permanently failed and flush to disk.

        Thread-safe: acquires the internal lock before mutating state.

        Args:
            key: Checkpoint key to mark as failed.
        """
        with self._lock:
            self._failed.add(key)
            self._flush()

    @property
    def n_completed(self) -> int:
        """Number of keys that have been marked completed."""
        return len(self._completed)

    @property
    def n_failed(self) -> int:
        """Number of keys that have been marked as permanently failed."""
        return len(self._failed)

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(
                {"completed": sorted(self._completed), "failed": sorted(self._failed)},
                indent=2,
            )
        )
        os.replace(tmp, self.path)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (KeyboardInterrupt, SystemExit, ValueError, TypeError)):
        return False
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return True
    for attr in ("status_code", "status", "code"):
        code = getattr(exc, attr, None)
        if isinstance(code, int) and (code == 429 or code >= 500):
            return True
    msg = str(exc).lower()
    return any(kw in msg for kw in ("timeout", "connection", "network", "reset", "broken pipe"))


def _retry(
    fn: Callable[[], Any],
    *,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    max_delay: float = MAX_DELAY,
) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except BaseException as exc:
            if not _is_retryable(exc) or attempt == max_retries:
                raise
            delay = random.uniform(0.0, min(base_delay * (2**attempt), max_delay))
            _log.debug("Retry %d/%d for %s (sleeping %.2fs)", attempt + 1, max_retries, exc, delay)
            time.sleep(delay)


def _get_thread_client() -> Any:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = make_client()
    return _thread_local.client


def ingest_one(
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    store: MarketDataWriter,
    *,
    exchange: str = "XNYS",
) -> None:
    """Fetch and store bars for a single (symbol, timeframe) pair.

    Fetches aggregate bars from the Massive provider with automatic retries on
    transient errors, then writes non-empty results to ``store``. Intended to
    be called from a thread pool where each (symbol, timeframe) pair is owned
    by exactly one concurrent caller.

    Args:
        symbol: Ticker symbol to ingest (e.g. ``"AAPL"``).
        timeframe: Bar timeframe string accepted by ``fetch_aggregates``
            (e.g. ``"1d"``, ``"1h"``).
        start: ISO-8601 date string for the start of the fetch window
            (inclusive).
        end: ISO-8601 date string for the end of the fetch window
            (inclusive).
        store: Destination store; ``store.write_bars`` is called when the
            fetched table contains at least one row.
        exchange: Exchange calendar MIC used for the regular-hours filter.
            Defaults to ``"XNYS"``.
    """
    client = _get_thread_client()
    table: pa.Table = _retry(
        lambda: fetch_aggregates(client, symbol, timeframe, start, end, exchange=exchange)
    )
    if table.num_rows:
        # write_bars is thread-safe only when each (sym, tf) pair is owned by at most one
        # concurrent caller — guaranteed by run_ingest's unique-pair queue construction.
        store.write_bars(table, timeframe)


def run_ingest(
    symbols: list[str],
    timeframes: list[str],
    start: str,
    end: str,
    store: MarketDataWriter,
    checkpoint: Checkpoint,
    *,
    max_workers: int = MAX_WORKERS,
    exchange: str = "XNYS",
) -> None:
    """Concurrently ingest bars for all (symbol, timeframe) pairs.

    Skips pairs already recorded in ``checkpoint``, then dispatches the
    remaining work to a ``ThreadPoolExecutor``. Progress is displayed via a
    tqdm bar. Each completed or permanently failed pair is recorded in
    ``checkpoint`` so a re-run resumes from where it left off.

    Args:
        symbols: List of ticker symbols to ingest.
        timeframes: List of timeframe strings (e.g. ``["1d", "1h"]``).
        start: ISO-8601 date string for the start of the fetch window.
        end: ISO-8601 date string for the end of the fetch window.
        store: Destination ``MarketDataWriter`` for bar data.
        checkpoint: Mutable checkpoint used for skip-on-resume and
            success/failure tracking.
        max_workers: Maximum number of concurrent threads. Defaults to
            ``MAX_WORKERS`` (30).
        exchange: Exchange calendar MIC forwarded to each ``ingest_one``
            call for the regular-hours filter. Defaults to ``"XNYS"``.
    """
    all_pairs = [(sym, tf) for tf in timeframes for sym in sorted(symbols)]
    pending = [(sym, tf) for sym, tf in all_pairs if not checkpoint.is_done(f"{sym}::{tf}")]
    n_skipped = len(all_pairs) - len(pending)

    def submit_next(
        pairs: list[tuple[str, str]],
        index: int,
        executor: ThreadPoolExecutor,
        futures: dict[Any, tuple[str, str]],
    ) -> int:
        if index >= len(pairs):
            return index
        sym, tf = pairs[index]
        future = executor.submit(ingest_one, sym, tf, start, end, store, exchange=exchange)
        futures[future] = (sym, tf)
        return index + 1

    with tqdm(total=len(all_pairs), initial=n_skipped, unit="pair") as bar:
        bar.set_postfix(done=checkpoint.n_completed, failed=checkpoint.n_failed, skipped=n_skipped)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Any, tuple[str, str]] = {}
            next_index = 0
            max_in_flight = max_workers * 4
            while next_index < len(pending) and len(futures) < max_in_flight:
                next_index = submit_next(pending, next_index, executor, futures)

            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    sym, tf = futures.pop(future)
                    key = f"{sym}::{tf}"
                    try:
                        future.result()
                        checkpoint.mark_completed(key)
                    except Exception as exc:
                        _log.error("Permanent failure for %s: %s", key, exc)
                        checkpoint.mark_failed(key)
                    bar.update(1)
                    bar.set_postfix(
                        done=checkpoint.n_completed,
                        failed=checkpoint.n_failed,
                        skipped=n_skipped,
                    )
                    next_index = submit_next(pending, next_index, executor, futures)
