"""Capability-adapter protocol, versioned cases, and the suite runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from persistra.conformance.report import CaseOutcome, ConformanceReport, OutcomeStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@runtime_checkable
class ProviderCapabilityAdapter(Protocol):
    """Minimal capability surface a provider adapter exposes to the suite.

    A conforming adapter translates its fixture inputs into canonical staging
    records and reports its own material identity. It never receives a managed
    connection, table name, or write callback (spec 03 §18).
    """

    def adapter_identity(self) -> str:
        """Return a stable identity string (package/version/content digests)."""
        ...

    def capabilities(self) -> frozenset[str]:
        """Return the capability names this adapter declares support for."""
        ...

    def sample_records(self, capability: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        """Return canonical field rows demonstrating one declared capability."""
        ...


@dataclass(frozen=True, slots=True)
class AdapterCapability:
    """A named capability a case may require of an adapter."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class ConformanceCase:
    """One versioned conformance case bound to a required capability."""

    case_id: str
    capability: AdapterCapability
    check: Callable[[ProviderCapabilityAdapter], bool]

    def run(self, adapter: ProviderCapabilityAdapter) -> CaseOutcome:
        """Execute the case against an adapter, returning a structured outcome."""
        if self.capability.name not in adapter.capabilities():
            return CaseOutcome(
                self.case_id,
                OutcomeStatus.SKIPPED,
                f"adapter does not declare {self.capability.name!r}",
            )
        try:
            passed = self.check(adapter)
        except Exception as error:
            detail = f"{type(error).__name__}: {error}"
            return CaseOutcome(self.case_id, OutcomeStatus.FAILED, detail)
        status = OutcomeStatus.PASSED if passed else OutcomeStatus.FAILED
        return CaseOutcome(self.case_id, status)


@dataclass(frozen=True, slots=True)
class ConformanceSuite:
    """A versioned, ordered manifest of conformance cases."""

    name: str
    version: int
    cases: tuple[ConformanceCase, ...]

    def run(self, adapter: ProviderCapabilityAdapter) -> ConformanceReport:
        """Run every case and assemble a machine-readable report."""
        outcomes = tuple(case.run(adapter) for case in self.cases)
        return ConformanceReport(self.name, self.version, adapter.adapter_identity(), outcomes)


@dataclass(frozen=True, slots=True)
class FixtureAdapter:
    """Built-in adapter that replays declared fixture records for the suite."""

    identity: str
    declared: frozenset[str]
    rows: tuple[tuple[tuple[str, str], ...], ...]

    def adapter_identity(self) -> str:
        """Return the fixture adapter identity."""
        return self.identity

    def capabilities(self) -> frozenset[str]:
        """Return the declared capability names."""
        return self.declared

    def sample_records(self, capability: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        """Return the fixture rows for a declared capability."""
        if capability not in self.declared:
            raise KeyError(capability)
        return self.rows


def _field_rows(
    adapter: ProviderCapabilityAdapter, capability: str
) -> tuple[dict[str, str], ...]:
    rows = adapter.sample_records(capability)
    result: list[dict[str, str]] = []
    for row in rows:
        values = dict(row)
        if len(values) != len(row):
            return ()
        result.append(values)
    return tuple(result)


def _identity(adapter: ProviderCapabilityAdapter) -> bool:
    identity = adapter.adapter_identity()
    return bool(identity.strip()) and "@" in identity


def _schema(adapter: ProviderCapabilityAdapter) -> bool:
    return bool(_field_rows(adapter, "schema"))


def _availability(adapter: ProviderCapabilityAdapter) -> bool:
    allowed = {"observed", "policy_derived", "ingestion_bounded", "unknown"}
    for row in _field_rows(adapter, "availability"):
        try:
            instant = datetime.fromisoformat(row["available_at"])
        except (KeyError, ValueError):
            return False
        if instant.tzinfo is None or row.get("availability_quality") not in allowed:
            return False
    return bool(_field_rows(adapter, "availability"))


def _revisions(adapter: ProviderCapabilityAdapter) -> bool:
    rows = _field_rows(adapter, "revisions")
    identities = {
        (row.get("source_record_key"), row.get("source_revision_key")) for row in rows
    }
    return bool(rows) and all(None not in identity for identity in identities) and (
        len(identities) == len(rows)
    )


def _pagination(adapter: ProviderCapabilityAdapter) -> bool:
    rows = _field_rows(adapter, "pagination")
    try:
        pages = [int(row["page"]) for row in rows]
    except (KeyError, ValueError):
        return False
    return bool(pages) and pages == sorted(pages) and set(pages) == set(
        range(min(pages), max(pages) + 1)
    )


def _idempotency(adapter: ProviderCapabilityAdapter) -> bool:
    return adapter.sample_records("idempotency") == adapter.sample_records("idempotency")


def _quarantine(adapter: ProviderCapabilityAdapter) -> bool:
    rows = _field_rows(adapter, "quarantine")
    return bool(rows) and all(
        row.get("disposition") == "quarantined" and bool(row.get("reason_code"))
        for row in rows
    )


def _credentials(adapter: ProviderCapabilityAdapter) -> bool:
    forbidden = {"api_key", "authorization", "password", "secret", "token"}
    rows = _field_rows(adapter, "credentials")
    return bool(rows) and all(forbidden.isdisjoint(row) for row in rows)


def _retry(adapter: ProviderCapabilityAdapter) -> bool:
    first = _field_rows(adapter, "retry")
    second = _field_rows(adapter, "retry")
    return bool(first) and first == second and all(row.get("submission_key") for row in first)


def _licensing(adapter: ProviderCapabilityAdapter) -> bool:
    rows = _field_rows(adapter, "licensing")
    return bool(rows) and all(
        bool(row.get("licensing_class"))
        and row.get("redistributable") in {"true", "false"}
        for row in rows
    )


def standard_provider_suite() -> ConformanceSuite:
    """Return the complete versioned provider-adapter contract suite."""
    checks = (
        ("identity", "stable material adapter identity", _identity),
        ("schema", "canonical record shape", _schema),
        ("availability", "revision-specific availability evidence", _availability),
        ("revisions", "stable source revision identities", _revisions),
        ("pagination", "bounded deterministic pagination", _pagination),
        ("idempotency", "repeatable canonical translation", _idempotency),
        ("quarantine", "structured invalid-record disposition", _quarantine),
        ("credentials", "credential and secret redaction", _credentials),
        ("retry", "stable retry and submission identity", _retry),
        ("licensing", "explicit redistribution classification", _licensing),
    )
    return ConformanceSuite(
        "persistra.conformance.provider",
        1,
        tuple(
            ConformanceCase(name, AdapterCapability(name, description), check)
            for name, description, check in checks
        ),
    )


def run_suite(
    suite: ConformanceSuite, adapters: Sequence[ProviderCapabilityAdapter]
) -> tuple[ConformanceReport, ...]:
    """Run one suite against several adapters, returning one report each."""
    return tuple(suite.run(adapter) for adapter in adapters)
