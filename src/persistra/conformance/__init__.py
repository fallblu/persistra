"""This package contains public extension conformance kits (spec 03 §18 and spec 18 §8).

A conformance suite contains a versioned set of cases for a capability adapter. The suite
produces a machine-readable :class:`ConformanceReport`."""

from persistra.conformance.providers import (
    AdapterCapability,
    ConformanceCase,
    ConformanceSuite,
    FixtureAdapter,
    ProviderCapabilityAdapter,
    standard_provider_suite,
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
    "standard_provider_suite",
]
