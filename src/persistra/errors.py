"""Public Persistra exceptions."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "AnalysisError",
    "AuthenticationError",
    "CacheError",
    "DataValidationError",
    "EntitlementError",
    "NoDataError",
    "PersistraError",
    "ProjectError",
    "ProviderError",
    "RateLimitError",
    "ResponseError",
    "StoreError",
    "TransportError",
]


class PersistraError(Exception):
    """Base class for Persistra failures."""


class DataValidationError(PersistraError, ValueError):
    """Raised when normalized data violates its contract."""


class ProviderError(PersistraError):
    """Base class for provider failures."""


class AuthenticationError(ProviderError):
    """Raised when provider credentials are invalid or absent."""


class EntitlementError(ProviderError):
    """Raised when an account cannot access requested data."""


class RateLimitError(ProviderError):
    """Raised when provider rate limiting exhausts all retries."""


class ResponseError(ProviderError):
    """Raised when a provider response is invalid."""

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, str | int] | None = None,
    ) -> None:
        super().__init__(message)
        self.context = MappingProxyType(dict(context or {}))


class TransportError(ProviderError):
    """Raised when transport retries are exhausted."""


class NoDataError(ProviderError):
    """Raised for an unambiguous provider no-data response."""


class CacheError(PersistraError):
    """Raised when a raw cache operation fails."""


class StoreError(PersistraError):
    """Raised when a normalized store operation fails."""


class ProjectError(PersistraError, ValueError):
    """Raised when a project manifest or layout operation fails."""


class AnalysisError(PersistraError, ValueError):
    """Raised when data violates a mathematical assumption."""
