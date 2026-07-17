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


class CatalogDefinitionError(PersistraError, ValueError):
    reason_code = "catalog.definition.invalid"


class CatalogReferenceError(PersistraError):
    reason_code = "catalog.reference.not_found"


class BatchStateError(PersistraError):
    reason_code = "ingestion.batch.invalid_state"


class BatchConflictError(PersistraError):
    reason_code = "ingestion.batch.submission_conflict"


class ValidationTokenError(PersistraError):
    reason_code = "ingestion.validation.token_invalid"


class ReferenceDefinitionError(PersistraError, ValueError):
    reason_code = "reference.definition.invalid"


class ReferenceResolutionError(PersistraError):
    reason_code = "reference.resolution.failed"


class CalendarReferenceError(PersistraError):
    reason_code = "calendar.reference.not_found"


class CalendarCoverageError(PersistraError):
    reason_code = "calendar.coverage.insufficient"


class UniverseDefinitionError(PersistraError, ValueError):
    reason_code = "universe.definition.invalid"


class UniverseEvaluationError(PersistraError):
    reason_code = "universe.evaluation.failed"


class BarSpecError(PersistraError, ValueError):
    reason_code = "bar.spec.invalid"


class MarketDataQueryError(PersistraError, ValueError):
    reason_code = "market.query.invalid"


class MarketDataLimitError(PersistraError):
    reason_code = "market.query.row_limit"


class MarketDataCoverageError(PersistraError):
    reason_code = "market.coverage.insufficient"


class TradingStatusError(PersistraError, ValueError):
    reason_code = "status.query.invalid"


class CorporateActionTermsError(PersistraError, ValueError):
    reason_code = "action.terms.invalid"


class AdjustmentUnavailableError(PersistraError):
    reason_code = "adjustment.unavailable"


class ResearchDatasetDefinitionError(PersistraError, ValueError):
    reason_code = "research.dataset.definition.invalid"


class ResearchDatasetBuildError(PersistraError):
    reason_code = "research.dataset.build.failed"


class ResearchResultLimitError(PersistraError):
    reason_code = "research.result.row_limit"


__all__ = [
    "AdjustmentUnavailableError",
    "BarSpecError",
    "BatchConflictError",
    "BatchStateError",
    "CalendarCoverageError",
    "CalendarReferenceError",
    "CapabilityUnavailableError",
    "CatalogDefinitionError",
    "CatalogReferenceError",
    "CopyVerificationError",
    "CorporateActionTermsError",
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
    "MarketDataCoverageError",
    "MarketDataLimitError",
    "MarketDataQueryError",
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
    "ReferenceDefinitionError",
    "ReferenceResolutionError",
    "ResearchDatasetBuildError",
    "ResearchDatasetDefinitionError",
    "ResearchResultLimitError",
    "TradingStatusError",
    "UnitMismatchError",
    "UniverseDefinitionError",
    "UniverseEvaluationError",
    "UnknownEventTypeError",
    "UnmanagedDatabaseError",
    "UnsupportedFilesystemError",
    "UnsupportedSchemaVersionError",
    "ValidationTokenError",
]
