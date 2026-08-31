"""Tests for portable resumable acquisition plans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from persistra.data import (
    AcquisitionCachePolicy,
    AcquisitionFamily,
    AcquisitionPlan,
    AcquisitionRequest,
    AcquisitionRunner,
    AcquisitionSuccess,
    DuckDBStore,
    acquisition_plan_from_json,
    acquisition_plan_to_json,
    synthetic,
)
from persistra.errors import DataValidationError

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 8, 22, 15, tzinfo=UTC)


def _request(
    request_id: str,
    operation: str,
    family: AcquisitionFamily,
    *,
    policy: AcquisitionCachePolicy = AcquisitionCachePolicy.DEFAULT,
) -> AcquisitionRequest:
    return AcquisitionRequest(
        request_id,
        "synthetic",
        operation,
        {"symbol": request_id},
        {"periods": 2},
        policy,
        family,
    )


def test_plan_round_trip_is_portable_and_applies_cache_policy() -> None:
    request = AcquisitionRequest(
        "gdp",
        "fred",
        "series.latest",
        {"provider_series": "GDPC1"},
        {"series_id": "GDPC1", "api_key": "secret"},
        AcquisitionCachePolicy.OFFLINE,
        AcquisitionFamily.SERIES,
    )
    plan = AcquisitionPlan("daily-macro", (request,))

    restored = acquisition_plan_from_json(acquisition_plan_to_json(plan))

    assert restored == plan
    assert "secret" not in acquisition_plan_to_json(plan)
    assert restored.requests[0].call_parameters == {
        "series_id": "GDPC1",
        "refresh": False,
        "offline": True,
    }


def test_partial_failure_retries_only_pending_requests_and_publishes_manifest(
    tmp_path: Path,
) -> None:
    series_request = _request(
        "series", "series.latest", AcquisitionFamily.SERIES, policy=AcquisitionCachePolicy.OFFLINE
    )
    quote_request = _request(
        "quotes", "quotes.latest", AcquisitionFamily.QUOTES, policy=AcquisitionCachePolicy.REFRESH
    )
    plan = AcquisitionPlan("morning", (series_request, quote_request))
    calls: list[str] = []
    quote_attempts = 0

    def series_handler(request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        calls.append(request.request_id)
        assert request.call_parameters["offline"] is True
        return synthetic.series(periods=2)

    def quote_handler(request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        nonlocal quote_attempts
        calls.append(request.request_id)
        quote_attempts += 1
        assert request.call_parameters["refresh"] is True
        if quote_attempts == 1:
            raise RuntimeError("temporary provider failure")
        return synthetic.quotes(symbols=("DEMO",))

    checkpoint = tmp_path / "state" / "checkpoint.json"
    manifest = tmp_path / "artifacts" / "acquisition.json"
    with DuckDBStore.create(tmp_path / "data.duckdb") as store:
        runner = AcquisitionRunner(
            {
                ("synthetic", "series.latest"): series_handler,
                ("synthetic", "quotes.latest"): quote_handler,
            },
            checkpoint,
            store=store,
            manifest_path=manifest,
            clock=lambda: NOW,
        )

        first = runner.run(plan)
        second = runner.run(plan)

        assert len(store.list_datasets()) == 2

    assert not first.is_complete
    assert first.failures[0].request_id == "quotes"
    assert first.failures[0].message == "temporary provider failure"
    assert second.is_complete
    assert second.resumed_request_ids == ("series",)
    assert calls == ["series", "quotes", "quotes"]
    published = json.loads(manifest.read_text())
    assert published["execution"]["is_complete"] is True
    assert published["execution"]["resumed_request_ids"] == ["series"]
    assert [item["request_id"] for item in published["execution"]["successes"]] == [
        "series",
        "quotes",
    ]


def test_interruption_preserves_prior_success_for_resume(tmp_path: Path) -> None:
    first_request = _request("first", "series.latest", AcquisitionFamily.SERIES)
    second_request = _request("second", "series.other", AcquisitionFamily.SERIES)
    plan = AcquisitionPlan("interruptible", (first_request, second_request))
    calls: list[str] = []

    def complete(request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        calls.append(request.request_id)
        return synthetic.series(periods=2)

    def interrupt(_request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    checkpoint = tmp_path / "checkpoint.json"
    interrupted = AcquisitionRunner(
        {
            ("synthetic", "series.latest"): complete,
            ("synthetic", "series.other"): interrupt,
        },
        checkpoint,
        clock=lambda: NOW,
    )
    with pytest.raises(KeyboardInterrupt):
        interrupted.run(plan)

    resumed = AcquisitionRunner(
        {
            ("synthetic", "series.latest"): complete,
            ("synthetic", "series.other"): complete,
        },
        checkpoint,
        clock=lambda: NOW,
    ).run(plan)

    assert resumed.is_complete
    assert resumed.resumed_request_ids == ("first",)
    assert calls == ["first", "second"]


def test_resume_retries_success_missing_from_target_store(tmp_path: Path) -> None:
    request = _request("one", "series.latest", AcquisitionFamily.SERIES)
    plan = AcquisitionPlan("store-bound", (request,))
    checkpoint = tmp_path / "checkpoint.json"
    calls = 0

    def acquire(_request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return synthetic.series(periods=2)

    with DuckDBStore.create(tmp_path / "first.duckdb") as store:
        first = AcquisitionRunner(
            {("synthetic", "series.latest"): acquire},
            checkpoint,
            store=store,
            clock=lambda: NOW,
        ).run(plan)
        assert first.is_complete

    with DuckDBStore.create(tmp_path / "second.duckdb") as store:
        second = AcquisitionRunner(
            {("synthetic", "series.latest"): acquire},
            checkpoint,
            store=store,
            clock=lambda: NOW,
        ).run(plan)
        assert second.is_complete
        assert second.resumed_request_ids == ()
        assert len(store.list_datasets()) == 1

    assert calls == 2


def test_store_does_not_resume_storeless_success(tmp_path: Path) -> None:
    request = _request("one", "series.latest", AcquisitionFamily.SERIES)
    plan = AcquisitionPlan("storeless", (request,))
    checkpoint = tmp_path / "checkpoint.json"
    calls = 0

    def acquire(_request: AcquisitionRequest):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return synthetic.series(periods=2)

    assert AcquisitionRunner(
        {("synthetic", "series.latest"): acquire}, checkpoint, clock=lambda: NOW
    ).run(plan).is_complete

    with DuckDBStore.create(tmp_path / "data.duckdb") as store:
        resumed = AcquisitionRunner(
            {("synthetic", "series.latest"): acquire},
            checkpoint,
            store=store,
            clock=lambda: NOW,
        ).run(plan)
        assert resumed.is_complete
        assert resumed.resumed_request_ids == ()
        assert len(store.list_datasets()) == 1

    assert calls == 2


def test_completion_cannot_precede_provider_retrieval(tmp_path: Path) -> None:
    request = _request("one", "series.latest", AcquisitionFamily.SERIES)
    clock_time = datetime(2024, 8, 31, 1, 9, 4, tzinfo=UTC)

    report = AcquisitionRunner(
        {("synthetic", "series.latest"): lambda _request: synthetic.series(periods=2)},
        tmp_path / "checkpoint.json",
        clock=lambda: clock_time,
    ).run(AcquisitionPlan("causal", (request,)))

    success = report.successes[0]
    assert success.retrieved_at == synthetic.SYNTHETIC_NOW
    assert success.completed_at == synthetic.SYNTHETIC_NOW
    assert report.finished_at == synthetic.SYNTHETIC_NOW
    with pytest.raises(ValueError, match="completed_at must not precede retrieved_at"):
        AcquisitionSuccess(
            "invalid",
            AcquisitionFamily.SERIES,
            clock_time,
            synthetic.SYNTHETIC_NOW,
            None,
        )


def test_resume_rejects_changed_plan_and_output_mismatch(tmp_path: Path) -> None:
    request = _request("one", "series.latest", AcquisitionFamily.SERIES)
    plan = AcquisitionPlan("stable", (request,))
    checkpoint = tmp_path / "checkpoint.json"
    runner = AcquisitionRunner(
        {("synthetic", "series.latest"): lambda _request: synthetic.series(periods=2)},
        checkpoint,
        clock=lambda: NOW,
    )
    assert runner.run(plan).is_complete

    changed = AcquisitionPlan(
        "stable",
        (
            _request(
                "one",
                "series.latest",
                AcquisitionFamily.SERIES,
                policy=AcquisitionCachePolicy.OFFLINE,
            ),
        ),
    )
    with pytest.raises(DataValidationError, match="different plan"):
        runner.run(changed)

    mismatch = AcquisitionRunner(
        {("synthetic", "quotes.latest"): lambda _request: synthetic.series(periods=2)},
        tmp_path / "other.json",
        clock=lambda: NOW,
    ).run(
        AcquisitionPlan("mismatch", (_request("quote", "quotes.latest", AcquisitionFamily.QUOTES),))
    )
    assert not mismatch.is_complete
    assert "expected quotes, received series" in mismatch.failures[0].message
