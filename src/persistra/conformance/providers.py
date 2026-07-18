"""Capability-adapter protocol, versioned cases, and the suite runner."""

from __future__ import annotations

from dataclasses import dataclass
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


def run_suite(
    suite: ConformanceSuite, adapters: Sequence[ProviderCapabilityAdapter]
) -> tuple[ConformanceReport, ...]:
    """Run one suite against several adapters, returning one report each."""
    return tuple(suite.run(adapter) for adapter in adapters)
