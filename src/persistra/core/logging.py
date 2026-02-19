"""
src/persistra/core/logging.py

Structured logging for Persistra with rotating file handler and console output.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".persistra" / "logs"


def setup_logging(level=logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("persistra")
    root_logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root_logger.addHandler(console)

    # File handler (rotating, 5MB max, 3 backups)
    file_handler = RotatingFileHandler(
        LOG_DIR / "persistra.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(logging.DEBUG)  # Always capture DEBUG to file
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    ))
    root_logger.addHandler(file_handler)

    return root_logger
