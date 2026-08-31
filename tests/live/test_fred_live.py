"""Opt-in, redacted FRED and ALFRED certification."""

from __future__ import annotations

import os
import time
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from persistra.data import FredClient
from persistra.model import CacheStatus
from tests.live._redaction import redacted_call

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

RUN_LIVE = os.environ.get("PERSISTRA_RUN_LIVE") == "1"
REQUEST_INTERVAL_SECONDS = 0.55

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not RUN_LIVE, reason="set PERSISTRA_RUN_LIVE=1 for live certification"),
]


def test_fred_and_alfred_acquisition_replays_offline(tmp_path: Path) -> None:
    """Certify latest, revision-history, and vintage-date results without emitting values."""
    client = FredClient.from_env(cache_directory=tmp_path)
    next_request_at = 0.0

    def refreshed(label: str, acquire: Callable[[], Any]) -> Any:
        nonlocal next_request_at
        time.sleep(max(0.0, next_request_at - time.monotonic()))
        result = redacted_call(label, "refresh", acquire)
        next_request_at = time.monotonic() + REQUEST_INTERVAL_SECONDS
        return result

    definition = refreshed(
        "series_definition",
        lambda: client.series.definition("GDPC1", refresh=True),
    )
    assert definition.provider == "fred"

    latest = refreshed(
        "latest_observations",
        lambda: client.series.latest(
            "GDPC1",
            observation_start=date(2024, 1, 1),
            refresh=True,
        ),
    )
    offline_latest = redacted_call(
        "latest_observations",
        "offline replay",
        lambda: client.series.latest(
            "GDPC1",
            observation_start=date(2024, 1, 1),
            offline=True,
        ),
    )
    assert latest.frame.equals(offline_latest.frame)
    assert offline_latest.metadata.cache_status is CacheStatus.OFFLINE

    history = refreshed(
        "vintage_history",
        lambda: client.series.vintages(
            "GDPC1",
            realtime_start=date(2020, 1, 1),
            realtime_end=date(2020, 12, 31),
            observation_start=date(2019, 1, 1),
            refresh=True,
        ),
    )
    offline_history = redacted_call(
        "vintage_history",
        "offline replay",
        lambda: client.series.vintages(
            "GDPC1",
            realtime_start=date(2020, 1, 1),
            realtime_end=date(2020, 12, 31),
            observation_start=date(2019, 1, 1),
            offline=True,
        ),
    )
    assert history.frame.equals(offline_history.frame)
    assert offline_history.metadata.cache_status is CacheStatus.OFFLINE

    dates = refreshed(
        "vintage_dates",
        lambda: client.series.vintage_dates(
            "GDPC1",
            realtime_start=date(2020, 1, 1),
            realtime_end=date(2020, 12, 31),
            refresh=True,
        ),
    )
    assert dates.dates
