"""This module contains the unified managed feature and label graph contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import total_ordering
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Protocol

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.domain.serialization import scoped_content_id
from persistra.errors import FeatureDefinitionError, LabelDefinitionError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import pandas as pd

    from persistra.research.models import ResearchDatasetBuildId
    from persistra.research.sql_models import (
        InformationClass,
        LineageCompleteness,
        SafetyStatus,
        TemporalContractKind,
    )


class LabelDefinitionId(EntityId):
    KIND: ClassVar[str] = "label_definition"


class LabelMaterializationId(EntityId):
    KIND: ClassVar[str] = "label_materialization"


class TemporalConformanceResultId(EntityId):
    KIND: ClassVar[str] = "temporal_conformance_result"


class ResearchComponentKind(StrEnum):
    FEATURE = "feature"
    LABEL = "label"


class ComponentInputKind(StrEnum):
    DATASET_FIELD = "dataset_field"
    FEATURE_OUTPUT = "feature_output"
    LABEL_OUTPUT = "label_output"


class ComponentImplementationKind(StrEnum):
    MANAGED_OPERATOR = "managed_operator"
    BOUNDED_PYTHON = "bounded_python"
    BOUNDED_SQL = "bounded_sql"
    UNRESTRICTED_PYTHON = "unrestricted_python"
    UNRESTRICTED_SQL = "unrestricted_sql"


class ExecutionTrust(StrEnum):
    MANAGED = "managed"
    TEMPORALLY_CONFORMING = "temporally_conforming"
    OPAQUE = "opaque"


class PartitionShape(StrEnum):
    ROW_LOCAL = "row_local"
    ENTITY_TIME = "entity_time"
    CROSS_SECTION = "cross_section"
    PANEL_BLOCK = "panel_block"


class ComponentDependencyScope(StrEnum):
    ENTITY = "entity"
    GROUP = "group"
    PANEL = "panel"
    OPAQUE = "opaque"


class ComponentValueState(StrEnum):
    COMPUTED = "computed"
    NOT_SCHEDULED = "not_scheduled"
    INPUT_MISSING = "input_missing"
    INSUFFICIENT_HISTORY = "insufficient_history"
    NOT_AVAILABLE = "not_available"
    CENSORED = "censored"
    AMBIGUOUS_PATH = "ambiguous_path"
    INVALID_NUMERIC = "invalid_numeric"


class ManagedOperator(StrEnum):
    PRICE = "price"
    SIMPLE_RETURN = "simple_return"
    LOG_RETURN = "log_return"
    MOMENTUM = "momentum"
    REVERSAL = "reversal"
    REALIZED_VOLATILITY = "realized_volatility"
    DOWNSIDE_DEVIATION = "downside_deviation"
    MAX_DRAWDOWN = "max_drawdown"
    RETURN_SKEWNESS = "return_skewness"
    EXPECTED_SHORTFALL = "expected_shortfall"
    TURNOVER = "turnover"
    AMIHUD_ILLIQUIDITY = "amihud_illiquidity"
    QUOTED_SPREAD_BPS = "quoted_spread_bps"
    VOLUME_ACTIVITY = "volume_activity"
    TRADE_ACTIVITY = "trade_activity"
    FUNDAMENTAL_RATIO = "fundamental_ratio"
    FUNDAMENTAL_GROWTH = "fundamental_growth"
    ESTIMATE_REVISION = "estimate_revision"
    ESTIMATE_DISPERSION = "estimate_dispersion"
    MACRO_LEVEL = "macro_level"
    MACRO_CHANGE = "macro_change"
    REGIME_THRESHOLD = "regime_threshold"
    CROSS_SECTIONAL_RANK = "cross_sectional_rank"
    CROSS_SECTIONAL_WINSORIZE = "cross_sectional_winsorize"
    CROSS_SECTIONAL_ZSCORE = "cross_sectional_zscore"
    ROLLING_COVARIANCE = "rolling_covariance"
    ROLLING_CORRELATION = "rolling_correlation"
    ROLLING_BETA = "rolling_beta"
    FORWARD_RETURN = "forward_return"
    FUTURE_VOLATILITY = "future_volatility"
    FUTURE_DRAWDOWN = "future_drawdown"
    MAXIMUM_FAVORABLE_EXCURSION = "maximum_favorable_excursion"
    MAXIMUM_ADVERSE_EXCURSION = "maximum_adverse_excursion"
    TRIPLE_BARRIER = "triple_barrier"
    EVENT_RETURN = "event_return"


@dataclass(frozen=True, slots=True)
class ParameterValues:
    """This class represents the immutable expanded scalar parameters supplied to a bounded
    component."""

    _values: Mapping[str, str]

    def __init__(self, values: Mapping[str, str]) -> None:
        object.__setattr__(self, "_values", MappingProxyType(dict(values)))

    def __getitem__(self, name: str) -> str:
        return self._values[name]

    def get(self, name: str, default: str | None = None) -> str | None:
        return self._values.get(name, default)

    def items(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._values.items()))


@dataclass(frozen=True, slots=True)
class ComponentOutput:
    """This class represents one bounded callback result aligned exactly to its core rows."""

    values: tuple[float | None, ...]
    states: tuple[ComponentValueState, ...]
    reason_codes: tuple[str, ...]
    used_input_rows: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        lengths = {
            len(self.values),
            len(self.states),
            len(self.reason_codes),
            len(self.used_input_rows),
        }
        if len(lengths) != 1:
            raise FeatureDefinitionError("component output columns have unequal lengths")
        if any(not reason.strip() or len(reason) > 128 for reason in self.reason_codes):
            raise FeatureDefinitionError("component output reason code is invalid")


@dataclass(frozen=True, slots=True)
class FeaturePartition:
    """This class represents the defensive bounded feature inputs with backward overlap only."""

    _core: pd.DataFrame
    _history: pd.DataFrame

    def core_rows(self) -> pd.DataFrame:
        return self._core.copy(deep=True)

    def history_rows(self) -> pd.DataFrame:
        return self._history.copy(deep=True)


@dataclass(frozen=True, slots=True)
class LabelPartition:
    """This class represents the defensive bounded label inputs with its declared forward horizon
    only."""

    _core: pd.DataFrame
    _window: pd.DataFrame
    horizon: int

    def core_rows(self) -> pd.DataFrame:
        return self._core.copy(deep=True)

    def window_rows(self) -> pd.DataFrame:
        return self._window.copy(deep=True)


class BoundedFeatureComponent(Protocol):
    def compute(
        self, partition: FeaturePartition, parameters: ParameterValues
    ) -> ComponentOutput: ...


class BoundedLabelComponent(Protocol):
    def compute(
        self, partition: LabelPartition, parameters: ParameterValues
    ) -> ComponentOutput: ...


@dataclass(frozen=True, slots=True)
class BoundedPythonImplementation:
    """This class represents the captured bounded callback identity and callable."""

    version: str
    content_id: ContentId
    callback: Callable[
        [FeaturePartition | LabelPartition, ParameterValues], ComponentOutput
    ] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.version.strip() or len(self.version) > 128:
            raise FeatureDefinitionError("bounded implementation version is invalid")


@dataclass(frozen=True, slots=True)
class BoundedSqlImplementation:
    """This class represents one captured parsed SELECT for the executor-owned partition."""

    version: str
    query: str
    content_id: ContentId

    @classmethod
    def create(cls, version: str, query: str) -> BoundedSqlImplementation:
        return cls(
            version,
            query,
            scoped_content_id(
                {
                    "schema": "persistra.research.bounded_sql",
                    "version": version,
                    "query": query.replace("\r\n", "\n"),
                }
            ),
        )

    def __post_init__(self) -> None:
        if not self.version.strip() or len(self.version) > 128:
            raise FeatureDefinitionError("bounded SQL version is invalid")
        if not self.query.strip() or len(self.query.encode()) > 262_144:
            raise FeatureDefinitionError("bounded SQL is empty or too large")
        expected = scoped_content_id(
            {
                "schema": "persistra.research.bounded_sql",
                "version": self.version,
                "query": self.query.replace("\r\n", "\n"),
            }
        )
        if self.content_id != expected:
            raise FeatureDefinitionError("bounded SQL content identity does not reproduce")


@total_ordering
@dataclass(frozen=True, slots=True)
class ResearchComponentVersion:
    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        if any(not 0 <= value <= 2_147_483_647 for value in self.parts):
            raise FeatureDefinitionError("component version part is out of range")

    @property
    def parts(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    @classmethod
    def parse(cls, value: str) -> ResearchComponentVersion:
        if re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value) is None:
            raise FeatureDefinitionError("component version must be MAJOR.MINOR.PATCH")
        return cls(*(int(part) for part in value.split(".")))

    def __str__(self) -> str:
        return ".".join(str(part) for part in self.parts)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ResearchComponentVersion):
            return NotImplemented
        return self.parts < other.parts


@dataclass(frozen=True, slots=True)
class FeatureDefinitionRef:
    name: QualifiedName
    version: ResearchComponentVersion


@dataclass(frozen=True, slots=True)
class LabelDefinitionRef:
    name: QualifiedName
    version: ResearchComponentVersion


ComponentDefinitionRef = FeatureDefinitionRef | LabelDefinitionRef


@dataclass(frozen=True, slots=True)
class ComponentInputSpec:
    name: str
    ordinal: int
    kind: ComponentInputKind
    field_name: str | None = None
    dependency: ComponentDefinitionRef | None = None
    dependency_output: str | None = None

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.name) is None
            or self.ordinal < 1
        ):
            raise FeatureDefinitionError("component input name or ordinal is invalid")
        dataset = self.kind is ComponentInputKind.DATASET_FIELD
        if dataset and (
            self.field_name is None
            or self.dependency is not None
            or self.dependency_output is not None
        ):
            raise FeatureDefinitionError("component input reference variant is invalid")
        if not dataset and (
            self.field_name is not None
            or self.dependency is None
            or self.dependency_output is None
        ):
            raise FeatureDefinitionError("component dependency output is incomplete")


@dataclass(frozen=True, slots=True)
class ManagedComponentDefinition:
    name: QualifiedName
    version: ResearchComponentVersion
    kind: ResearchComponentKind
    operator: ManagedOperator
    inputs: tuple[ComponentInputSpec, ...]
    output_name: str
    assumptions_and_limitations: str
    parameters: tuple[tuple[str, str], ...] = ()
    lookback: int = 0
    horizon: int = 0
    partition_shape: PartitionShape = PartitionShape.ENTITY_TIME
    dependency_scope: ComponentDependencyScope = ComponentDependencyScope.ENTITY
    implementation_kind: ComponentImplementationKind = (
        ComponentImplementationKind.MANAGED_OPERATOR
    )
    implementation_content_id: ContentId = field(
        default_factory=lambda: ContentId.from_bytes(b"persistra-managed-operator@1")
    )

    def __post_init__(self) -> None:
        error = (
            LabelDefinitionError
            if self.kind is ResearchComponentKind.LABEL
            else FeatureDefinitionError
        )
        if not self.inputs or tuple(item.ordinal for item in self.inputs) != tuple(
            range(1, len(self.inputs) + 1)
        ):
            raise error("component inputs must have contiguous ordinals")
        if len({item.name for item in self.inputs}) != len(self.inputs):
            raise error("component input names must be unique")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.output_name) is None:
            raise error("component output name is invalid")
        if self.output_name.startswith(("research_", "feature_", "label_")):
            raise error("component output name uses a reserved prefix")
        if not self.assumptions_and_limitations.strip():
            raise error("assumptions and limitations are required")
        if self.lookback < 0 or self.horizon < 0:
            raise error("component lookback and horizon must be nonnegative")
        if self.kind is ResearchComponentKind.FEATURE:
            if self.horizon != 0:
                raise error("features cannot declare a forward horizon")
            if any(
                item.kind is ComponentInputKind.LABEL_OUTPUT for item in self.inputs
            ):
                raise error("feature definitions cannot depend on labels")
        elif self.horizon < 1:
            raise error("labels require a positive horizon")
        if self.implementation_kind not in {
            ComponentImplementationKind.MANAGED_OPERATOR,
            ComponentImplementationKind.BOUNDED_PYTHON,
            ComponentImplementationKind.BOUNDED_SQL,
        }:
            raise error("implementation kind is not supported by this executor")


@dataclass(frozen=True, slots=True)
class ResolvedComponentDefinition:
    component_definition_id: EntityId
    kind: ResearchComponentKind
    version: ResearchComponentVersion
    registration_sequence: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ComponentMaterializationLimits:
    max_base_rows: int = 25_000_000
    max_output_rows: int = 25_000_000
    max_output_columns: int = 1_024
    core_partition_rows: int = 100_000
    max_partition_rows_with_overlap: int = 500_000
    direct_pandas_rows: int = 2_000_000

    def __post_init__(self) -> None:
        if any(
            value < 1
            for value in (
                self.max_base_rows,
                self.max_output_rows,
                self.max_output_columns,
                self.core_partition_rows,
                self.max_partition_rows_with_overlap,
                self.direct_pandas_rows,
            )
        ):
            raise FeatureDefinitionError("component materialization limits must be positive")


@dataclass(frozen=True, slots=True)
class ComponentMaterializationRef:
    component_materialization_id: EntityId
    component_definition_id: EntityId
    component_version: ResearchComponentVersion
    kind: ResearchComponentKind
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    information_class: InformationClass
    temporal_contract_kind: TemporalContractKind
    lineage_completeness: LineageCompleteness
    safety_status: SafetyStatus
    structurally_decision_eligible: bool
    row_count: int
    computed_count: int


@dataclass(frozen=True, slots=True)
class TemporalConformanceResult:
    temporal_conformance_result_id: TemporalConformanceResultId
    component_definition_id: EntityId
    component_version: ResearchComponentVersion
    passed: bool
    evidence_content_id: ContentId
