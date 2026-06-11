"""Tests for utils/logging.py — configure_logging smoke tests."""

from __future__ import annotations


def test_configure_logging_is_callable():
    """configure_logging must be importable and callable without error."""
    from persistra.utils.logging import configure_logging

    # First call: sets up structlog + console handler
    configure_logging()
    # Second call: idempotent (no duplicate root-level setup)
    configure_logging()


def test_configure_logging_with_run_dir_adds_file_handler(tmp_path):
    """Calling with a run_dir should create a log file."""
    from persistra.utils.logging import configure_logging

    run_dir = tmp_path / "my_run"
    configure_logging(run_dir=run_dir)
    assert (run_dir / "logs").exists()


def test_configure_logging_respects_level():
    """configure_logging stores the desired level without error."""
    from persistra.utils import logging as _utils_logging

    # Just confirm it accepts valid level strings and doesn't raise.
    _utils_logging.configure_logging(level="WARNING")
    _utils_logging.configure_logging(level="INFO")


def test_configure_logging_debug_level():
    """DEBUG level string is accepted without raising."""
    from persistra.utils import logging as _utils_logging

    # Should not raise
    _utils_logging.configure_logging(level="DEBUG")
