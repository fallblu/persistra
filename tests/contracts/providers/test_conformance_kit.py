"""Prove the provider conformance kit runs against a built-in fixture adapter."""

from __future__ import annotations

import pytest
from support.ids import contract_id

from persistra.conformance import (
    AdapterCapability,
    ConformanceCase,
    ConformanceSuite,
    FixtureAdapter,
    OutcomeStatus,
    ProviderCapabilityAdapter,
)

pytestmark = pytest.mark.contract

_IDENTITY = AdapterCapability("identity", "stable adapter identity")
_SCHEMA = AdapterCapability("schema", "canonical record shape")
_MISSING = AdapterCapability("credentials", "credential redaction")


def _identity_check(adapter: ProviderCapabilityAdapter) -> bool:
    return bool(adapter.adapter_identity())


def _schema_check(adapter: ProviderCapabilityAdapter) -> bool:
    rows = adapter.sample_records("schema")
    return bool(rows) and all(all(len(pair) == 2 for pair in row) for row in rows)


def _suite() -> ConformanceSuite:
    return ConformanceSuite(
        name="persistra.conformance.provider",
        version=1,
        cases=(
            ConformanceCase("identity", _IDENTITY, _identity_check),
            ConformanceCase("schema", _SCHEMA, _schema_check),
            ConformanceCase("credentials", _MISSING, lambda _adapter: True),
        ),
    )


def _adapter() -> FixtureAdapter:
    return FixtureAdapter(
        identity="example.adapter@1.0",
        declared=frozenset({"identity", "schema"}),
        rows=((("concept", "revenue"), ("value", "100")),),
    )


@contract_id("V3-P18-8-PROVIDER-KIT")
def test_conformance_report_is_machine_readable() -> None:
    report = _suite().run(_adapter())
    assert report.passed
    by_id = {outcome.case_id: outcome.status for outcome in report.outcomes}
    assert by_id["identity"] is OutcomeStatus.PASSED
    assert by_id["schema"] is OutcomeStatus.PASSED
    assert by_id["credentials"] is OutcomeStatus.SKIPPED
    payload = report.to_dict()
    assert payload["suite_name"] == "persistra.conformance.provider"
    assert payload["passed"] is True


@contract_id("V3-P18-8-PROVIDER-FAILURE")
def test_conformance_failure_is_reported_not_raised() -> None:
    def _boom(_adapter: ProviderCapabilityAdapter) -> bool:
        raise RuntimeError("adapter exploded")

    suite = ConformanceSuite(
        name="persistra.conformance.provider",
        version=1,
        cases=(ConformanceCase("identity", _IDENTITY, _boom),),
    )
    report = suite.run(_adapter())
    assert not report.passed
    assert report.outcomes[0].status is OutcomeStatus.FAILED
    assert "adapter exploded" in report.outcomes[0].detail
