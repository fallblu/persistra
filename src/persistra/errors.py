"""Public typed exception namespace."""

from persistra._errors import PersistraError
from persistra.domain.errors import (
    CurrencyMismatchError,
    DecimalOverflowError,
    DomainValidationError,
    DuplicateEventError,
    DurationOverflowError,
    InvalidContentIdError,
    InvalidCurrencyError,
    InvalidDecimalError,
    InvalidDurationError,
    InvalidEntityIdError,
    InvalidEventError,
    InvalidInstantError,
    InvalidIntervalError,
    InvalidPriceError,
    InvalidQualifiedNameError,
    InvalidQuantityError,
    NaiveDatetimeError,
    PrecisionLossError,
    UnitMismatchError,
    UnknownEventTypeError,
    UnsupportedSchemaVersionError,
)


class ProjectConfigNotFoundError(PersistraError):
    reason_code = "project.config.not_found"


class ProjectConfigError(PersistraError, ValueError):
    reason_code = "project.config.invalid"


class ProjectAlreadyExistsError(PersistraError):
    reason_code = "project.init.exists"


class ProjectClosedError(PersistraError):
    reason_code = "project.closed"


class ProjectThreadError(PersistraError):
    reason_code = "project.wrong_thread"


class ProjectProcessError(PersistraError):
    reason_code = "project.wrong_process"


class CapabilityUnavailableError(PersistraError):
    reason_code = "project.capability.unavailable"


class DatabaseNotFoundError(PersistraError):
    reason_code = "db.not_found"


class DatabaseAlreadyExistsError(PersistraError):
    reason_code = "db.already_exists"


class UnmanagedDatabaseError(PersistraError):
    reason_code = "db.unmanaged"


class DatabaseRoleError(PersistraError):
    reason_code = "db.role_mismatch"


class DatabaseLeaseConflictError(PersistraError):
    reason_code = "db.lease.conflict"


class LeaseUpgradeError(PersistraError):
    reason_code = "db.lease.upgrade_forbidden"


class UnsupportedFilesystemError(PersistraError):
    reason_code = "db.filesystem.unsupported"


class DatabaseCompatibilityError(PersistraError):
    reason_code = "db.compatibility.unsupported"


class MigrationRequiredError(PersistraError):
    reason_code = "db.migration.required"


class MigrationChecksumError(PersistraError):
    reason_code = "db.migration.checksum_mismatch"


class MigrationFailedError(PersistraError):
    reason_code = "db.migration.failed"


class DatabaseRecoveryRequiredError(PersistraError):
    reason_code = "db.recovery.required"


class CopyVerificationError(PersistraError):
    reason_code = "db.copy.verification_failed"


class ProjectCloseError(PersistraError):
    reason_code = "project.close.failed"


__all__ = [
    "CapabilityUnavailableError",
    "CopyVerificationError",
    "CurrencyMismatchError",
    "DatabaseAlreadyExistsError",
    "DatabaseCompatibilityError",
    "DatabaseLeaseConflictError",
    "DatabaseNotFoundError",
    "DatabaseRecoveryRequiredError",
    "DatabaseRoleError",
    "DecimalOverflowError",
    "DomainValidationError",
    "DuplicateEventError",
    "DurationOverflowError",
    "InvalidContentIdError",
    "InvalidCurrencyError",
    "InvalidDecimalError",
    "InvalidDurationError",
    "InvalidEntityIdError",
    "InvalidEventError",
    "InvalidInstantError",
    "InvalidIntervalError",
    "InvalidPriceError",
    "InvalidQualifiedNameError",
    "InvalidQuantityError",
    "LeaseUpgradeError",
    "MigrationChecksumError",
    "MigrationFailedError",
    "MigrationRequiredError",
    "NaiveDatetimeError",
    "PersistraError",
    "PrecisionLossError",
    "ProjectAlreadyExistsError",
    "ProjectCloseError",
    "ProjectClosedError",
    "ProjectConfigError",
    "ProjectConfigNotFoundError",
    "ProjectProcessError",
    "ProjectThreadError",
    "UnitMismatchError",
    "UnknownEventTypeError",
    "UnmanagedDatabaseError",
    "UnsupportedFilesystemError",
    "UnsupportedSchemaVersionError",
]
