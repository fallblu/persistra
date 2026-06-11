"""Single source of truth for the persistra real-data sample dataset.

Imported by ``scripts/build_sample_data.py`` (to ingest) and by the test suite
(to assert the committed dataset matches). Keep this list and the committed
``examples/sample_data`` in sync via ``python -m scripts.build_sample_data``.
"""

from __future__ import annotations

SAMPLE_SYMBOLS: list[str] = [
    "AAPL",
    "AMZN",
    "GOOGL",
    "JPM",
    "LLY",
    "MSFT",
    "NVDA",
    "TSLA",
    "V",
    "WMT",
]
# Note: META is intentionally excluded — the "META" ticker has reused history
# (a different company held it before Facebook's 2022-06-09 rename), which yields
# bogus pre-rename prices. V (Visa) is used instead for a clean, continuous series.

# Ingest windows (inclusive). Daily covers the full history; intraday starts
# later to keep the 1h tree a reasonable size.
DAILY_START: str = "2021-01-01"
DAILY_END: str = "2026-06-30"
INTRADAY_START: str = "2021-06-01"
INTRADAY_END: str = "2026-06-30"
