"""Public typed exception namespace."""

from persistra._errors import PersistraError
from persistra.domain.errors import (
    CurrencyMismatchError,
    DecimalOverflowError,
    DomainValidationError,
    DuplicateEventError,
    DurationOverflowError,
    FrameContractError,
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


class SourcePrecedencePolicyError(PersistraError, ValueError):
    reason_code = "catalog.source_precedence.invalid"


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


class TradeConditionError(PersistraError, ValueError):
    reason_code = "trade.condition.invalid"


class QuoteConditionError(PersistraError, ValueError):
    reason_code = "quote.condition.invalid"


class TradingStatusError(PersistraError, ValueError):
    reason_code = "status.query.invalid"


class CorporateActionResolutionError(PersistraError):
    reason_code = "action.resolution.failed"


class CorporateActionTermsError(PersistraError, ValueError):
    reason_code = "action.terms.invalid"


class AdjustmentPolicyError(PersistraError, ValueError):
    reason_code = "adjustment.policy.invalid"


class AdjustmentUnavailableError(PersistraError):
    reason_code = "adjustment.unavailable"


class AdjustmentMaterializationError(PersistraError):
    reason_code = "adjustment.materialization.failed"


class FilingResolutionError(PersistraError, ValueError):
    reason_code = "filing.resolution.failed"


class FundamentalQueryError(PersistraError, ValueError):
    reason_code = "fundamental.query.invalid"


class FundamentalMappingError(PersistraError, ValueError):
    reason_code = "fundamental.mapping.invalid"


class EstimateQueryError(PersistraError, ValueError):
    reason_code = "estimate.query.invalid"


class MacroQueryError(PersistraError, ValueError):
    reason_code = "macro.query.invalid"


class BenchmarkResolutionError(PersistraError, ValueError):
    reason_code = "benchmark.resolution.failed"


class RateConventionError(PersistraError, ValueError):
    reason_code = "rate.convention.invalid"


class RateUnavailableError(PersistraError):
    reason_code = "rate.unavailable"


class ResearchDatasetDefinitionError(PersistraError, ValueError):
    reason_code = "research.dataset.definition.invalid"


class ResearchDatasetBuildError(PersistraError):
    reason_code = "research.dataset.build.failed"


class ResearchResultLimitError(PersistraError):
    reason_code = "research.result.row_limit"


class ResearchLabelLeakageError(PersistraError):
    reason_code = "research.label.leakage"


class SqlQueryError(PersistraError, ValueError):
    reason_code = "research.sql.query.invalid"


class SqlSecurityError(PersistraError):
    reason_code = "research.sql.security.rejected"


class WorkspaceConflictError(PersistraError):
    reason_code = "research.workspace.conflict"


class WorkspaceMaterializationError(PersistraError):
    reason_code = "research.workspace.materialization.failed"


class FeatureDefinitionError(PersistraError, ValueError):
    reason_code = "research.feature.definition.invalid"


class FeatureMaterializationError(PersistraError):
    reason_code = "research.feature.materialization.failed"


class LabelDefinitionError(PersistraError, ValueError):
    reason_code = "research.label.definition.invalid"


class LabelMaterializationError(PersistraError):
    reason_code = "research.label.materialization.failed"


class TemporalConformanceError(PersistraError):
    reason_code = "research.temporal_conformance.failed"


class AlphaAnalysisDefinitionError(PersistraError, ValueError):
    reason_code = "alpha.definition.invalid"


class AlphaExecutionError(PersistraError):
    reason_code = "alpha.execution.failed"


class ValidationSchemeError(PersistraError, ValueError):
    reason_code = "validation.scheme.invalid"


class ValidationPlanError(PersistraError):
    reason_code = "validation.plan.failed"


class FinalHoldoutAccessError(PersistraError):
    reason_code = "validation.holdout.access_denied"


class SignalDefinitionError(PersistraError, ValueError):
    reason_code = "portfolio.signal.definition.invalid"


class ForecastDefinitionError(PersistraError, ValueError):
    reason_code = "portfolio.forecast.definition.invalid"


class ForecastMaterializationError(PersistraError):
    reason_code = "portfolio.forecast.materialization.failed"


class RiskModelError(PersistraError):
    reason_code = "portfolio.risk.failed"


class OptimizationError(PersistraError):
    reason_code = "portfolio.optimization.failed"


class PortfolioConstructionError(PersistraError):
    reason_code = "portfolio.construction.failed"


class AccountingInvariantError(PersistraError):
    reason_code = "accounting.invariant.failed"


class AccountingRequestError(PersistraError, ValueError):
    reason_code = "accounting.request.invalid"


class VectorizedSimulationRequestError(PersistraError, ValueError):
    reason_code = "simulation.vectorized.request.invalid"


class VectorizedSimulationError(PersistraError):
    reason_code = "simulation.vectorized.failed"


class EventSimulationRequestError(PersistraError, ValueError):
    reason_code = "simulation.event.request.invalid"


class EventSimulationError(PersistraError):
    reason_code = "simulation.event.failed"


class ExperimentRequestError(PersistraError, ValueError):
    reason_code = "experiments.request.invalid"


class ExperimentStateError(PersistraError):
    reason_code = "experiments.state.invalid"


class ResultQueryLimitError(PersistraError):
    reason_code = "results.query.row_limit"


class AnalysisUnavailableError(PersistraError):
    reason_code = "analysis.unavailable"


class VisualizationExtraRequiredError(PersistraError):
    reason_code = "viz.extra.required"


class FigureInputError(PersistraError, ValueError):
    reason_code = "viz.figure.input.invalid"


class ReportPlanningError(PersistraError, ValueError):
    reason_code = "report.plan.invalid"


class ReportRenderError(PersistraError):
    reason_code = "report.render.failed"


__all__ = [
    "AccountingInvariantError",
    "AccountingRequestError",
    "AdjustmentMaterializationError",
    "AdjustmentPolicyError",
    "AdjustmentUnavailableError",
    "AlphaAnalysisDefinitionError",
    "AlphaExecutionError",
    "AnalysisUnavailableError",
    "BarSpecError",
    "BatchConflictError",
    "BatchStateError",
    "BenchmarkResolutionError",
    "CalendarCoverageError",
    "CalendarReferenceError",
    "CapabilityUnavailableError",
    "CatalogDefinitionError",
    "CatalogReferenceError",
    "CopyVerificationError",
    "CorporateActionResolutionError",
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
    "EstimateQueryError",
    "EventSimulationError",
    "EventSimulationRequestError",
    "ExperimentRequestError",
    "ExperimentStateError",
    "FeatureDefinitionError",
    "FeatureMaterializationError",
    "FigureInputError",
    "FilingResolutionError",
    "FinalHoldoutAccessError",
    "ForecastDefinitionError",
    "ForecastMaterializationError",
    "FrameContractError",
    "FundamentalMappingError",
    "FundamentalQueryError",
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
    "LabelDefinitionError",
    "LabelMaterializationError",
    "LeaseUpgradeError",
    "MacroQueryError",
    "MarketDataCoverageError",
    "MarketDataLimitError",
    "MarketDataQueryError",
    "MigrationChecksumError",
    "MigrationFailedError",
    "MigrationRequiredError",
    "NaiveDatetimeError",
    "OptimizationError",
    "PersistraError",
    "PortfolioConstructionError",
    "PrecisionLossError",
    "ProjectAlreadyExistsError",
    "ProjectCloseError",
    "ProjectClosedError",
    "ProjectConfigError",
    "ProjectConfigNotFoundError",
    "ProjectProcessError",
    "ProjectThreadError",
    "QuoteConditionError",
    "RateConventionError",
    "RateUnavailableError",
    "ReferenceDefinitionError",
    "ReferenceResolutionError",
    "ReportPlanningError",
    "ReportRenderError",
    "ResearchDatasetBuildError",
    "ResearchDatasetDefinitionError",
    "ResearchLabelLeakageError",
    "ResearchResultLimitError",
    "ResultQueryLimitError",
    "RiskModelError",
    "SignalDefinitionError",
    "SourcePrecedencePolicyError",
    "SqlQueryError",
    "SqlSecurityError",
    "TemporalConformanceError",
    "TradeConditionError",
    "TradingStatusError",
    "UnitMismatchError",
    "UniverseDefinitionError",
    "UniverseEvaluationError",
    "UnknownEventTypeError",
    "UnmanagedDatabaseError",
    "UnsupportedFilesystemError",
    "UnsupportedSchemaVersionError",
    "ValidationPlanError",
    "ValidationSchemeError",
    "ValidationTokenError",
    "VectorizedSimulationError",
    "VectorizedSimulationRequestError",
    "VisualizationExtraRequiredError",
    "WorkspaceConflictError",
    "WorkspaceMaterializationError",
]
