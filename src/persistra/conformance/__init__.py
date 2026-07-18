"""Public extension conformance kits (spec 03 §18, spec 18 §8).

A conformance suite is a versioned set of cases run against a capability adapter,
producing a machine-readable :class:`ConformanceReport`. The provider suite is
completed in a later slice; this module provides the shared case/adapter/report
machinery and a built-in fixture adapter used by the contract-test kit.
"""

from persistra.conformance.providers import (
    AdapterCapability,
    ConformanceCase,
    ConformanceSuite,
    FixtureAdapter,
    ProviderCapabilityAdapter,
)
from persistra.conformance.report import (
    CaseOutcome,
    ConformanceReport,
    OutcomeStatus,
)

__all__ = [
    "AdapterCapability",
    "CaseOutcome",
    "ConformanceCase",
    "ConformanceReport",
    "ConformanceSuite",
    "FixtureAdapter",
    "OutcomeStatus",
    "ProviderCapabilityAdapter",
]
