"""Stable diagnostics shared by read-only validators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["ValidationFinding", "ValidationSeverity"]

_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)+$")


class ValidationSeverity(StrEnum):
    """Severity of one validation finding."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One stable, deterministic validation diagnostic."""

    code: str
    severity: ValidationSeverity
    message: str
    location: str | None = None

    def __post_init__(self) -> None:
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("validation finding code is invalid")
        if not self.message:
            raise ValueError("validation finding message must not be empty")

    def to_dict(self) -> dict[str, object]:
        """Return the version-neutral JSON representation of this finding."""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
        }
