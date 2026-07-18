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
    standard_provider_suite,
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


@contract_id("V3-P03-18-PROVIDER-STANDARD")
def test_standard_provider_suite_covers_temporal_operational_and_licensing_contracts() -> (
    None
):
    class CompleteFixtureAdapter:
        def adapter_identity(self) -> str:
            return "example.adapter@1.0"

        def capabilities(self) -> frozenset[str]:
            return frozenset(
                {
                    "availability",
                    "credentials",
                    "idempotency",
                    "identity",
                    "licensing",
                    "pagination",
                    "quarantine",
                    "retry",
                    "revisions",
                    "schema",
                }
            )

        def sample_records(
            self, capability: str
        ) -> tuple[tuple[tuple[str, str], ...], ...]:
            rows = {
                "availability": (
                    ("available_at", "2026-01-10T12:00:00+00:00"),
                    ("availability_quality", "observed"),
                ),
                "credentials": (("status", "redacted"),),
                "idempotency": (("source_record_key", "row-1"),),
                "licensing": (
                    ("licensing_class", "redistributable"),
                    ("redistributable", "true"),
                ),
                "pagination": (("page", "0"),),
                "quarantine": (
                    ("disposition", "quarantined"),
                    ("reason_code", "provider.record.invalid"),
                ),
                "retry": (
                    ("submission_key", "fixture-page-0"),
                    ("status", "complete"),
                ),
                "revisions": (
                    ("source_record_key", "row-1"),
                    ("source_revision_key", "revision-1"),
                ),
                "schema": (("concept", "revenue"), ("value", "100")),
            }
            if capability in {"identity"}:
                return ((("identity", self.adapter_identity()),),)
            return (rows[capability],)

    report = standard_provider_suite().run(CompleteFixtureAdapter())

    assert report.passed
    assert len(report.outcomes) == 10
    assert {outcome.status for outcome in report.outcomes} == {OutcomeStatus.PASSED}
