"""This module contains Alpha Vantage index-series parsers for the benchmark family.

Native Alpha Vantage index coverage is small. Alpha Vantage does not supply a dedicated
historical index endpoint. Thus, Persistra ingests levels from the available daily series.
Index-tracking symbols are one example.

Persistra models these levels as ``SOURCE_SERIES`` benchmarks, not as tradeable instruments."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any

from persistra.domain import (
    AvailabilityQuality,
    ContentId,
    Currency,
    NumericKind,
    QualifiedName,
    SourceNumeric,
    SourceNumericKind,
    Unit,
    UnitSpec,
)
from persistra.domain.time import validate_instant
from persistra.errors import SourceResponseError
from persistra.market import (
    BenchmarkDefinition,
    BenchmarkKind,
    BenchmarkSeriesKind,
    BenchmarkSeriesObservation,
)
from persistra.sources.alphavantage._parsing import (
    decimal_value,
    json_object,
    series_payload,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from persistra.market import ResolvedBenchmarkVersionRef
    from persistra.reference import CalendarRef

_UNIT_RATIO = UnitSpec(Unit("ratio"), NumericKind.DECIMAL)
_SLUG = re.compile(r"[a-z][a-z0-9_]*")


def index_benchmark_definition(
    slug: str,
    *,
    calendar: CalendarRef,
    currency: str = "USD",
    series_kind: BenchmarkSeriesKind = BenchmarkSeriesKind.PRICE_INDEX,
    version: int = 1,
) -> BenchmarkDefinition:
    """Return a source-series benchmark definition for one Alpha Vantage index."""
    if _SLUG.fullmatch(slug) is None:
        raise SourceResponseError(f"alpha vantage index slug {slug!r} is invalid")
    if series_kind is BenchmarkSeriesKind.PERIOD_RETURN:
        raise SourceResponseError(
            "alpha vantage index benchmarks carry levels, not period returns"
        )
    return BenchmarkDefinition(
        QualifiedName(f"alphavantage.index.{slug}"),
        version,
        BenchmarkKind.SOURCE_SERIES,
        None,
        Currency(currency),
        calendar,
        ContentId.from_bytes(f"alphavantage.index.{slug}.methodology@1".encode()),
        "licensed_no_redistribution",
    )


def parse_index_series(
    payload: dict[str, Any],
    *,
    benchmark: ResolvedBenchmarkVersionRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    calendar_schedule_content_id: ContentId,
    available_at: datetime,
    series_kind: BenchmarkSeriesKind = BenchmarkSeriesKind.PRICE_INDEX,
    currency: str = "USD",
) -> tuple[BenchmarkSeriesObservation, ...]:
    """Parse a daily series payload into benchmark index-level observations.

    The close of each covered session becomes one level observation at the session
    close. Skip sessions that are not final at ``available_at``.
    """
    validate_instant(available_at)
    if series_kind is BenchmarkSeriesKind.PERIOD_RETURN:
        raise SourceResponseError(
            "alpha vantage index benchmarks carry levels, not period returns"
        )
    series = series_payload(payload, "Time Series (Daily)")
    observations: list[BenchmarkSeriesObservation] = []
    for raw_date in sorted(series):
        try:
            session_date = date.fromisoformat(raw_date)
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage index series key is not a date"
            ) from cause
        session = sessions.get(session_date)
        if session is None:
            continue
        close_at = session[1]
        if close_at > available_at:
            continue
        row = json_object(series[raw_date], f"index row {raw_date}")
        close = decimal_value(row.get("4. close"), "index close")
        if close <= 0:
            raise SourceResponseError("alpha vantage index level must be positive")
        observations.append(
            BenchmarkSeriesObservation(
                benchmark,
                series_kind,
                close_at,
                SourceNumeric(close, SourceNumericKind.PURE, _UNIT_RATIO),
                Currency(currency),
                calendar_schedule_content_id,
                ContentId.from_bytes(b"alphavantage.index.source_methodology@1"),
                available_at,
                session_date=session_date,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(observations)
