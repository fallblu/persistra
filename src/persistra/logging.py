"""Structured logging configuration with bounded, non-secret context."""

from __future__ import annotations

import logging
from typing import Any

import structlog


def configure_logging(*, json_output: bool = True, level: int = logging.INFO) -> None:
    """Configure deterministic structured logs for command-line workflows."""
    renderer: Any = structlog.processors.JSONRenderer(sort_keys=True)
    if not json_output:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
