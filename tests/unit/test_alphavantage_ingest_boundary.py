from __future__ import annotations

from typing import Any, cast

from persistra.sources.alphavantage.ingest import (
    AlphaVantageIngestor,
    IngestReport,
    ParsedFamilyBatch,
)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        def method(argument: Any) -> tuple[()]:
            self.calls.append((name, argument))
            return ()

        return method


class _FakeMarket:
    def __init__(self) -> None:
        self.bars = _Recorder()
        self.actions = _Recorder()
        self.status = _Recorder()
        self.macro = _Recorder()
        self.rates = _Recorder()
        self.benchmarks = _Recorder()


class _FakeServices:
    def __init__(self) -> None:
        self.market = _FakeMarket()


class _FakeProject:
    def __init__(self) -> None:
        self.services = _FakeServices()


def test_empty_batch_touches_no_service() -> None:
    project = _FakeProject()
    report = AlphaVantageIngestor(cast("Any", project)).ingest(ParsedFamilyBatch())
    assert report == IngestReport()
    market = project.services.market
    assert market.bars.calls == []
    assert market.actions.calls == []
    assert market.status.calls == []
    assert market.macro.calls == []
    assert market.rates.calls == []
    assert market.benchmarks.calls == []


def test_each_family_routes_to_its_typed_service() -> None:
    project = _FakeProject()
    bar = object()
    action = object()
    status = object()
    release_one = object()
    release_two = object()
    point = object()
    benchmark = object()
    batch = ParsedFamilyBatch(
        bars=cast("Any", (bar,)),
        corporate_actions=cast("Any", (action,)),
        trading_status=cast("Any", (status,)),
        macro_releases=cast("Any", (release_one, release_two)),
        risk_free_points=cast("Any", (point,)),
        benchmark_observations=cast("Any", (benchmark,)),
    )
    report = AlphaVantageIngestor(cast("Any", project)).ingest(batch)
    assert report == IngestReport(
        bars=1,
        corporate_actions=1,
        trading_status=1,
        macro_releases=2,
        risk_free_points=1,
        benchmark_observations=1,
    )
    market = project.services.market
    assert market.bars.calls == [("ingest", (bar,))]
    assert market.actions.calls == [("ingest", (action,))]
    assert market.status.calls == [("ingest", (status,))]
    assert market.macro.calls == [("ingest", release_one), ("ingest", release_two)]
    assert market.rates.calls == [("ingest", (point,))]
    assert market.benchmarks.calls == [("ingest_series", (benchmark,))]
