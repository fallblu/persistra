"""This module contains the typed failures for dependency-free domain primitives."""

from __future__ import annotations

from typing import ClassVar

from persistra._errors import PersistraError


class DomainValidationError(PersistraError, ValueError):
    """This class represents the base class for stable, machine-readable domain validation
    failures."""

    reason_code: ClassVar[str] = "domain.validation"


class InvalidEntityIdError(DomainValidationError):
    reason_code = "domain.identity.invalid"


class InvalidContentIdError(DomainValidationError):
    reason_code = "domain.content_id.invalid"


class InvalidQualifiedNameError(DomainValidationError):
    reason_code = "domain.name.invalid"


class UnsupportedSchemaVersionError(DomainValidationError):
    reason_code = "domain.schema_version.unsupported"


class NaiveDatetimeError(DomainValidationError):
    reason_code = "domain.time.naive"


class InvalidInstantError(DomainValidationError):
    reason_code = "domain.time.invalid"


class InvalidDurationError(DomainValidationError):
    reason_code = "domain.duration.invalid"


class DurationOverflowError(DomainValidationError):
    reason_code = "domain.duration.overflow"


class InvalidIntervalError(DomainValidationError):
    reason_code = "domain.interval.invalid"


class InvalidCurrencyError(DomainValidationError):
    reason_code = "domain.currency.invalid"


class CurrencyMismatchError(DomainValidationError):
    reason_code = "domain.currency.mismatch"


class InvalidDecimalError(DomainValidationError):
    reason_code = "domain.decimal.invalid"


class PrecisionLossError(DomainValidationError):
    reason_code = "domain.decimal.precision_loss"


class DecimalOverflowError(DomainValidationError):
    reason_code = "domain.decimal.overflow"


class InvalidPriceError(DomainValidationError):
    reason_code = "domain.price.invalid"


class InvalidQuantityError(DomainValidationError):
    reason_code = "domain.quantity.invalid"


class UnitMismatchError(DomainValidationError):
    reason_code = "domain.unit.mismatch"


class UnknownEventTypeError(DomainValidationError):
    reason_code = "domain.event.unknown_type"


class InvalidEventError(DomainValidationError):
    reason_code = "domain.event.invalid"


class DuplicateEventError(DomainValidationError):
    reason_code = "domain.event.duplicate"


class FrameContractError(DomainValidationError):
    reason_code = "domain.frame.contract"
