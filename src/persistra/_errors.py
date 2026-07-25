"""This module contains the shared exception base. It does not depend on subsystem
implementations."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping


class PersistraError(Exception):
    """This class represents the base for stable, machine-readable Persistra failures."""

    reason_code: ClassVar[str] = "persistra.error"

    def __init__(
        self,
        message: str,
        *,
        field_path: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field_path = field_path
        self.context = MappingProxyType(dict(context or {}))
