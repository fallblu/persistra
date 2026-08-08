"""Typed outputs and policies for point-in-time research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from persistra.research._validation import (
    ZERO_DAYS,
    calendar_date,
    calendar_index,
    datetime_index,
    require_whole_days,
)

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.model import VintageSeriesSet

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
    """One ordered train/evaluation split with purged boundary observations."""

    train_index: pd.DatetimeIndex
    evaluation_index: pd.DatetimeIndex
    purged_index: pd.DatetimeIndex

    def __post_init__(self) -> None:
        train = datetime_index(self.train_index, name="training index")
        evaluation = datetime_index(self.evaluation_index, name="evaluation index")
        purged = datetime_index(self.purged_index, name="purged index")
        object.__setattr__(self, "train_index", train)
        object.__setattr__(self, "evaluation_index", evaluation)
        object.__setattr__(self, "purged_index", purged)


@dataclass(frozen=True, slots=True)
class ResearchSummary:
    """Coverage and regime-conditioned return statistics."""

    coverage: pd.DataFrame
    regime_statistics: pd.DataFrame
    periods_per_year: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", self.coverage.copy(deep=True))
        object.__setattr__(self, "regime_statistics", self.regime_statistics.copy(deep=True))
