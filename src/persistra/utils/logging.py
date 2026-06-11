from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

_structured: bool = False
_log_level: int = logging.INFO

_SHARED_PROCESSORS: list[Any] = [
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
]


def configure_logging(run_dir: Path | None = None, level: str = "INFO") -> None:
    """Wire structlog with a console sink and an optional per-run JSON file sink.

    Safe to call multiple times:
    - First call configures structlog and adds the console handler.
    - Subsequent calls with a non-None run_dir add a JSON file handler for that run.
    """
    global _structured, _log_level
    _log_level = getattr(logging, level.upper(), logging.INFO)

    if not _structured:
        _setup_structlog()
        _structured = True

    if run_dir is not None:
        _add_file_handler(run_dir)


def _setup_structlog() -> None:
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(_log_level)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(),
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )

    root = logging.getLogger()
    root.setLevel(_log_level)
    root.addHandler(console_handler)


def _add_file_handler(run_dir: Path) -> None:
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "run.log")
    file_handler.setLevel(_log_level)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )
    logging.getLogger().addHandler(file_handler)
