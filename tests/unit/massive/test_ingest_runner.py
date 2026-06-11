"""Tests for massive/ingest_runner.py — Checkpoint and pure helpers (no network)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

import persistra.providers.massive.ingest_runner as ingest_runner
from persistra.providers.massive.ingest_runner import (
    Checkpoint,
    _is_retryable,
    _retry,
    run_ingest,
)

# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def test_checkpoint_starts_empty(tmp_path):
    cp = Checkpoint(tmp_path / "cp.json")
    assert cp.n_completed == 0
    assert cp.n_failed == 0
    assert not cp.is_done("AAPL::1d")


def test_mark_completed_flushes_to_disk(tmp_path):
    path = tmp_path / "cp.json"
    cp = Checkpoint(path)
    cp.mark_completed("AAPL::1d")
    assert cp.is_done("AAPL::1d")
    assert cp.n_completed == 1
    data = json.loads(path.read_text())
    assert "AAPL::1d" in data["completed"]


def test_mark_failed_flushes_to_disk(tmp_path):
    path = tmp_path / "cp.json"
    cp = Checkpoint(path)
    cp.mark_failed("AAPL::1d")
    assert cp.is_done("AAPL::1d")
    assert cp.n_failed == 1
    data = json.loads(path.read_text())
    assert "AAPL::1d" in data["failed"]


def test_checkpoint_loads_existing_state(tmp_path):
    path = tmp_path / "cp.json"
    # Pre-populate the file as a prior run would
    path.write_text(json.dumps({"completed": ["AAPL::1d", "MSFT::1d"], "failed": ["BAD::1d"]}))
    cp = Checkpoint(path)
    assert cp.n_completed == 2
    assert cp.n_failed == 1
    assert cp.is_done("AAPL::1d")
    assert cp.is_done("BAD::1d")
    assert not cp.is_done("GOOG::1d")


def test_checkpoint_marks_complete_and_failed_independently(tmp_path):
    cp = Checkpoint(tmp_path / "cp.json")
    cp.mark_completed("A::1d")
    cp.mark_failed("B::1d")
    assert cp.n_completed == 1
    assert cp.n_failed == 1


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------


def test_is_retryable_false_for_value_error():
    assert not _is_retryable(ValueError("bad input"))


def test_is_retryable_false_for_keyboard_interrupt():
    assert not _is_retryable(KeyboardInterrupt())


def test_is_retryable_true_for_connection_error():
    assert _is_retryable(ConnectionError("reset by peer"))


def test_is_retryable_true_for_timeout_in_message():
    class FakeHTTPError(Exception):
        pass

    assert _is_retryable(FakeHTTPError("timeout occurred"))


def test_is_retryable_true_for_429_status_code():
    class RateLimitError(Exception):
        status_code = 429

    assert _is_retryable(RateLimitError())


def test_is_retryable_true_for_500_status_code():
    class ServerError(Exception):
        status_code = 503

    assert _is_retryable(ServerError())


# ---------------------------------------------------------------------------
# _retry
# ---------------------------------------------------------------------------


def test_retry_returns_result_on_first_success():
    calls = []

    def ok():
        calls.append(1)
        return 42

    assert _retry(ok, max_retries=3) == 42
    assert len(calls) == 1


def test_retry_raises_immediately_for_non_retryable():
    def boom():
        raise ValueError("not retryable")

    with pytest.raises(ValueError, match="not retryable"):
        _retry(boom, max_retries=5)


def test_retry_exhausts_and_raises(monkeypatch):
    """After max_retries retryable failures it must raise the original error."""
    import time

    monkeypatch.setattr(time, "sleep", lambda _: None)  # skip real delays

    attempts = []

    def flaky():
        attempts.append(1)
        raise ConnectionError("network problem")

    with pytest.raises(ConnectionError, match="network problem"):
        _retry(flaky, max_retries=2, base_delay=0.0)

    assert len(attempts) == 3  # 1 initial + 2 retries


# ---------------------------------------------------------------------------
# run_ingest
# ---------------------------------------------------------------------------


def test_run_ingest_updates_progress_before_submitting_all_pending(monkeypatch, tmp_path):
    submitted = 0
    submitted_at_update = []

    class CountingExecutor(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            nonlocal submitted
            submitted += 1
            return super().submit(*args, **kwargs)

    class RecordingTqdm:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def set_postfix(self, **kwargs):
            pass

        def update(self, n):
            submitted_at_update.append(submitted)

    def fake_ingest_one(*args, **kwargs):
        return None

    class NullStore:
        def write_bars(self, table: Any, timeframe: str) -> None:
            pass

        def write_corporate_actions(self, table: Any) -> None:
            pass

        def write_universe(self, table: Any) -> None:
            pass

    monkeypatch.setattr(ingest_runner, "ThreadPoolExecutor", CountingExecutor)
    monkeypatch.setattr(ingest_runner, "tqdm", RecordingTqdm)
    monkeypatch.setattr(ingest_runner, "ingest_one", fake_ingest_one)

    checkpoint = Checkpoint(tmp_path / "checkpoint.json")
    symbols = [f"S{i}" for i in range(8)]

    run_ingest(symbols, ["1d"], "2024-01-01", "2024-01-31", NullStore(), checkpoint, max_workers=1)

    assert submitted == 8
    assert submitted_at_update
    assert submitted_at_update[0] < submitted
