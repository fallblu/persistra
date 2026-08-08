"""Opt-in, redacted FRED and ALFRED certification."""

from __future__ import annotations

import os
from datetime import date
from typing import TYPE_CHECKING

import pytest

from persistra.data import FredClient
from persistra.model import CacheStatus

if TYPE_CHECKING:
    from pathlib import Path

RUN_LIVE = os.environ.get("PERSISTRA_RUN_LIVE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not RUN_LIVE, reason="set PERSISTRA_RUN_LIVE=1 for live certification"),
]


def test_fred_and_alfred_acquisition_replays_offline(tmp_path: Path) -> None:
    """Certify latest, revision-history, and vintage-date results without emitting values."""
    client = FredClient.from_env(cache_directory=tmp_path)
    definition = client.series.definition("GDPC1", refresh=True)
    assert definition.provider == "fred"

    latest = client.series.latest(
        "GDPC1",
        observation_start=date(2024, 1, 1),
        refresh=True,
    )
    offline_latest = client.series.latest(
        "GDPC1",
        observation_start=date(2024, 1, 1),
        offline=True,
    )
    assert latest.frame.equals(offline_latest.frame)
    assert offline_latest.metadata.cache_status is CacheStatus.OFFLINE

    history = client.series.vintages(
        "GDPC1",
        realtime_start=date(2020, 1, 1),
        realtime_end=date(2020, 12, 31),
        observation_start=date(2019, 1, 1),
        refresh=True,
    )
    offline_history = client.series.vintages(
        "GDPC1",
        realtime_start=date(2020, 1, 1),
        realtime_end=date(2020, 12, 31),
        observation_start=date(2019, 1, 1),
        offline=True,
    )
    assert history.frame.equals(offline_history.frame)
    assert offline_history.metadata.cache_status is CacheStatus.OFFLINE

    dates = client.series.vintage_dates(
        "GDPC1",
        realtime_start=date(2020, 1, 1),
        realtime_end=date(2020, 12, 31),
        refresh=True,
    )
    assert dates.dates
