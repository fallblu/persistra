"""Typed outputs and policies for point-in-time research."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

from persistra.research._validation import (
    ZERO_DAYS,
    calendar_date,
    calendar_index,
    datetime_index,
    require_whole_days,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from persistra.model import VintageSeriesSet

VintagePolicy = Literal["final_vintage", "first_release", "real_time"]

FEATURE_PROVENANCE_COLUMNS = (
    "decision_date",
    "feature",
    "series_id",
    "provider",
    "provider_series",
    "period_label",
    "observation_date",
    "available_from",
    "available_through",
    "source_retrieved_at",
    "matched_age",
    "publication_lag",
    "maximum_staleness",
    "is_deleted",
    "selected_value",
)


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """One named vintage source and its explicit availability policy."""

    name: str
    source: VintageSeriesSet
    maximum_staleness: pd.Timedelta
    publication_lag: pd.Timedelta = ZERO_DAYS
    observation_date_column: str = "period_start"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("feature name must not be empty")
        require_whole_days(self.maximum_staleness, name="maximum_staleness")
        require_whole_days(self.publication_lag, name="publication_lag")
        if self.observation_date_column not in {"period_start", "period_end"}:
            raise ValueError("observation_date_column must be period_start or period_end")


@dataclass(frozen=True, slots=True)
class FeaturePolicy:
    """Recorded source identity and policy for one constructed feature."""

    name: str
    series_id: str
    provider: str
    provider_series: str
    maximum_staleness: pd.Timedelta
    publication_lag: pd.Timedelta
    observation_date_column: str
    source_retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class VintageSelection:
    """Source versions applicable on one explicit knowledge date."""

    frame: pd.DataFrame
    known_on: pd.Timestamp
    publication_lag: pd.Timedelta
    series_id: str
    provider: str
    provider_series: str
    source_retrieved_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "known_on", calendar_date(self.known_on, name="known_on"))
        object.__setattr__(self, "frame", self.frame.copy(deep=True).reset_index(drop=True))


@dataclass(frozen=True, slots=True)
class FeaturePanel:
    """Point-in-time feature values with row-level source-version provenance."""

    frame: pd.DataFrame
    provenance: pd.DataFrame
    policies: tuple[FeaturePolicy, ...]

    def __post_init__(self) -> None:
        frame = self.frame.copy(deep=True)
        calendar_index(frame.index, name="feature panel index")
        if list(frame.columns) != [policy.name for policy in self.policies]:
            raise ValueError("feature panel columns must match policies")
        provenance = self.provenance.copy(deep=True).reset_index(drop=True)
        if list(provenance.columns) != list(FEATURE_PROVENANCE_COLUMNS):
            raise ValueError("feature provenance columns differ from the contract")
        expected_rows = len(frame) * len(self.policies)
        if len(provenance) != expected_rows:
            raise ValueError("feature provenance must cover every panel cell")
        key = ["decision_date", "feature"]
        if provenance.duplicated(key).any():
            raise ValueError("feature provenance decision keys must be unique")
        if not provenance["decision_date"].isin(frame.index).all() or not provenance[
            "feature"
        ].isin(frame.columns).all():
            raise ValueError("feature provenance keys must belong to the panel")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "provenance", provenance)


@dataclass(frozen=True, slots=True)
class ForwardReturnLabels:
    """Forward simple-return labels and the end date of every label horizon."""

    frame: pd.DataFrame
    label_ends: pd.Series
    horizon: int

    def __post_init__(self) -> None:
        frame = self.frame.copy(deep=True)
        datetime_index(frame.index, name="label index")
        ends = self.label_ends.copy(deep=True)
        if not ends.index.equals(frame.index):
            raise ValueError("label ends must use the label index")
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        expected = pd.Series(index=frame.index, dtype=frame.index.dtype)
        if self.horizon < len(frame.index):
            expected.iloc[: -self.horizon] = frame.index[self.horizon :]
        if not ends.equals(expected):
            raise ValueError("label ends must match the explicit horizon")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "label_ends", ends)


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    """One ordered split with separately recorded purged and embargoed observations."""

    train_index: pd.DatetimeIndex
    evaluation_index: pd.DatetimeIndex
    purged_index: pd.DatetimeIndex
    embargoed_index: pd.DatetimeIndex

    def __post_init__(self) -> None:
        train = datetime_index(self.train_index, name="training index")
        evaluation = datetime_index(self.evaluation_index, name="evaluation index")
        purged = datetime_index(self.purged_index, name="purged index")
        embargoed = datetime_index(self.embargoed_index, name="embargoed index")
        object.__setattr__(self, "train_index", train)
        object.__setattr__(self, "evaluation_index", evaluation)
        object.__setattr__(self, "purged_index", purged)
        object.__setattr__(self, "embargoed_index", embargoed)


@dataclass(frozen=True, slots=True)
class ResearchSummary:
    """Coverage and regime-conditioned return statistics."""

    coverage: pd.DataFrame
    regime_statistics: pd.DataFrame
    periods_per_year: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", self.coverage.copy(deep=True))
        object.__setattr__(self, "regime_statistics", self.regime_statistics.copy(deep=True))


@dataclass(frozen=True, slots=True)
class InformationCoefficientResult:
    """Pearson and rank information coefficients with pairwise sample counts."""

    statistics: pd.DataFrame
    horizon: int
    grouped: bool

    def __post_init__(self) -> None:
        statistics = self.statistics.copy(deep=True)
        if list(statistics.columns) != ["count", "pearson", "rank"]:
            raise ValueError("information coefficient columns differ from the contract")
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        object.__setattr__(self, "statistics", statistics)


@dataclass(frozen=True, slots=True)
class QuantilePortfolioResult:
    """Equal-weight quantile results with membership and capacity diagnostics."""

    assignments: pd.DataFrame
    returns: pd.DataFrame
    counts: pd.DataFrame
    turnover: pd.DataFrame
    capacity: pd.DataFrame
    spread: pd.Series
    summary: pd.DataFrame
    horizon: int
    quantiles: int

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.quantiles < 2:
            raise ValueError("quantiles must be at least 2")
        expected_columns = pd.Index(range(1, self.quantiles + 1), name="quantile")
        panels = {
            "returns": self.returns,
            "counts": self.counts,
            "turnover": self.turnover,
        }
        for name, panel in panels.items():
            if not panel.index.equals(self.assignments.index):
                raise ValueError(f"quantile {name} must use the assignment index")
            if not panel.columns.equals(expected_columns):
                raise ValueError(f"quantile {name} columns differ from the contract")
            object.__setattr__(self, name, panel.copy(deep=True))
        if not self.spread.index.equals(self.assignments.index):
            raise ValueError("quantile spread must use the assignment index")
        object.__setattr__(self, "assignments", self.assignments.copy(deep=True))
        object.__setattr__(self, "capacity", self.capacity.copy(deep=True))
        object.__setattr__(self, "spread", self.spread.copy(deep=True))
        object.__setattr__(self, "summary", self.summary.copy(deep=True))


@dataclass(frozen=True, slots=True)
class GroupSignalResult:
    """Signal and forward-return statistics for time-varying classifications."""

    statistics: pd.DataFrame
    horizon: int

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        object.__setattr__(self, "statistics", self.statistics.copy(deep=True))


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    """Candidate results compared with one aligned benchmark series."""

    differences: pd.DataFrame
    summary: pd.DataFrame
    benchmark_name: str

    def __post_init__(self) -> None:
        if not self.benchmark_name:
            raise ValueError("benchmark_name must not be empty")
        object.__setattr__(self, "differences", self.differences.copy(deep=True))
        object.__setattr__(self, "summary", self.summary.copy(deep=True))


@dataclass(frozen=True, slots=True)
class MultipleTestingResult:
    """Raw and adjusted p-values for one explicit repeated-search correction."""

    statistics: pd.DataFrame
    method: Literal["bonferroni", "benjamini-hochberg"]
    alpha: float

    def __post_init__(self) -> None:
        if list(self.statistics.columns) != ["raw_pvalue", "adjusted_pvalue", "rejected"]:
            raise ValueError("multiple-testing columns differ from the contract")
        if self.method not in {"bonferroni", "benjamini-hochberg"}:
            raise ValueError("unsupported multiple-testing method")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        object.__setattr__(self, "statistics", self.statistics.copy(deep=True))


@dataclass(frozen=True, slots=True)
class DatasetScope:
    """One dataset scope, schema, and portable content or snapshot identity."""

    name: str
    scope: Mapping[str, Any]
    schema_version: str
    content_identity: str | None = None
    snapshot_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.schema_version:
            raise ValueError("dataset name and schema_version must not be empty")
        if not self.content_identity and not self.snapshot_identity:
            raise ValueError("dataset must have a content or snapshot identity")
        object.__setattr__(self, "scope", _portable_mapping(self.scope, name="dataset scope"))


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Portable identity for one external research output artifact."""

    name: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("artifact name must not be empty")
        invalid_digest = len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        )
        if invalid_digest:
            raise ValueError("artifact sha256 must be a lowercase hexadecimal digest")
        if self.size_bytes < 0:
            raise ValueError("artifact size_bytes must not be negative")


@dataclass(frozen=True, slots=True)
class ResearchManifest:
    """Transparent record of research data, parameters, environment, and outputs."""

    manifest_version: int
    datasets: tuple[DatasetScope, ...]
    feature_parameters: Mapping[str, Any]
    label_parameters: Mapping[str, Any]
    split_parameters: Mapping[str, Any]
    benchmark_parameters: Mapping[str, Any]
    environment: Mapping[str, str]
    random_seeds: Mapping[str, int]
    execution_status: Literal["not-run", "succeeded", "failed"]
    artifacts: tuple[ArtifactIdentity, ...] = ()

    def __post_init__(self) -> None:
        if self.manifest_version != 1:
            raise ValueError("unsupported research manifest version")
        if self.execution_status not in {"not-run", "succeeded", "failed"}:
            raise ValueError("unsupported execution_status")
        if self.execution_status == "not-run" and self.artifacts:
            raise ValueError("not-run research must not record output artifacts")
        names = [dataset.name for dataset in self.datasets]
        if len(names) != len(set(names)):
            raise ValueError("dataset names must be unique")
        artifact_names = [artifact.name for artifact in self.artifacts]
        if len(artifact_names) != len(set(artifact_names)):
            raise ValueError("artifact names must be unique")
        for name in (
            "feature_parameters",
            "label_parameters",
            "split_parameters",
            "benchmark_parameters",
            "environment",
            "random_seeds",
        ):
            value = getattr(self, name)
            if name == "environment" and any(
                not key or not item for key, item in value.items()
            ):
                raise ValueError("environment names and versions must be nonempty strings")
            if name == "random_seeds" and any(
                not key or isinstance(item, bool) or not isinstance(item, int)
                for key, item in value.items()
            ):
                raise ValueError("random seed names must be nonempty and values must be integers")
            object.__setattr__(self, name, _portable_mapping(value, name=name))


def _portable_mapping(value: Mapping[str, Any], *, name: str) -> Mapping[str, Any]:
    copied = deepcopy(dict(value))
    try:
        json.dumps(copied, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain portable JSON values") from error
    return MappingProxyType(copied)
