"""This module contains the machine-readable conformance report shapes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OutcomeStatus(StrEnum):
    """This class represents the terminal status of a single conformance case."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """This class represents the structured result from one conformance case."""

    case_id: str
    status: OutcomeStatus
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible mapping for the report envelope."""
        return {"case_id": self.case_id, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """This class represents the versioned envelope of case outcomes for one adapter run."""

    suite_name: str
    suite_version: int
    adapter_identity: str
    outcomes: tuple[CaseOutcome, ...]

    @property
    def passed(self) -> bool:
        """Return true if each case that ran passed."""
        return all(outcome.status is not OutcomeStatus.FAILED for outcome in self.outcomes)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible mapping that describes all parts of the run."""
        return {
            "suite_name": self.suite_name,
            "suite_version": self.suite_version,
            "adapter_identity": self.adapter_identity,
            "passed": self.passed,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }
