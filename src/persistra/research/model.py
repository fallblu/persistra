"""Typed outputs and policies for point-in-time research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

from persistra._portable import freeze_portable_mapping
from persistra._validation import require_integer
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
RegressionCovariance = Literal["classical", "hc3", "newey_west"]

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
        if (
            not provenance["decision_date"].isin(frame.index).all()
            or not provenance["feature"].isin(frame.columns).all()
        ):
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
        horizon = require_integer(self.horizon, name="horizon", minimum=1)
        frame = self.frame.copy(deep=True)
        datetime_index(frame.index, name="label index")
        ends = self.label_ends.copy(deep=True)
        if not ends.index.equals(frame.index):
            raise ValueError("label ends must use the label index")
        expected = pd.Series(index=frame.index, dtype=frame.index.dtype)
        if horizon < len(frame.index):
            expected.iloc[:-horizon] = frame.index[horizon:]
        if not ends.equals(expected):
            raise ValueError("label ends must match the explicit horizon")
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "label_ends", ends)
        object.__setattr__(self, "horizon", horizon)


@dataclass(frozen=True, slots=True)
class FactorRegressionResult:
    """Aligned estimates and diagnostics from static time-series regressions."""

    coefficients: pd.DataFrame
    standard_errors: pd.DataFrame
    t_statistics: pd.DataFrame
    p_values: pd.DataFrame
    fitted_values: pd.DataFrame
    residuals: pd.DataFrame
    diagnostics: pd.DataFrame
    factor_names: tuple[str, ...]
    intercept: bool
    covariance: RegressionCovariance
    hac_lags: int | None

    def __post_init__(self) -> None:
        _copy_regression_frames(self)
        if self.hac_lags is not None:
            object.__setattr__(
                self,
                "hac_lags",
                require_integer(self.hac_lags, name="hac_lags", minimum=0),
            )


@dataclass(frozen=True, slots=True)
class RollingFactorRegressionResult:
    """Point-in-time coefficient histories from rolling or expanding regressions."""

    coefficients: pd.DataFrame
    standard_errors: pd.DataFrame
    t_statistics: pd.DataFrame
    p_values: pd.DataFrame
    diagnostics: pd.DataFrame
    factor_names: tuple[str, ...]
    intercept: bool
    covariance: RegressionCovariance
    hac_lags: int | None
    window: int | None
    minimum_observations: int

    def __post_init__(self) -> None:
        _copy_regression_frames(self)
        if self.hac_lags is not None:
            object.__setattr__(
                self,
                "hac_lags",
                require_integer(self.hac_lags, name="hac_lags", minimum=0),
            )
        if self.window is not None:
            object.__setattr__(
                self,
                "window",
                require_integer(self.window, name="window", minimum=1),
            )
        object.__setattr__(
            self,
            "minimum_observations",
            require_integer(
                self.minimum_observations,
                name="minimum_observations",
                minimum=1,
            ),
        )


@dataclass(frozen=True, slots=True)
class CrossSectionalFactorModelResult:
    """Period factor-return estimates from time-varying supplied exposures."""

    factor_returns: pd.DataFrame
    standard_errors: pd.DataFrame
    t_statistics: pd.DataFrame
    p_values: pd.DataFrame
    fitted_values: pd.DataFrame
    residuals: pd.DataFrame
    diagnostics: pd.DataFrame
    factor_names: tuple[str, ...]
    intercept: bool
    covariance: Literal["classical", "hc3"]
    label_horizon: int | None

    def __post_init__(self) -> None:
        _copy_regression_frames(self)
        if self.label_horizon is not None:
            object.__setattr__(
                self,
                "label_horizon",
                require_integer(self.label_horizon, name="label_horizon", minimum=1),
            )


@dataclass(frozen=True, slots=True)
class FactorPremiaResult:
    """Average factor premia with time-series inference."""

    statistics: pd.DataFrame
    factor_returns: pd.DataFrame
    covariance: RegressionCovariance
    hac_lags: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "statistics", self.statistics.copy(deep=True))
        object.__setattr__(self, "factor_returns", self.factor_returns.copy(deep=True))
        if self.hac_lags is not None:
            object.__setattr__(
                self,
                "hac_lags",
                require_integer(self.hac_lags, name="hac_lags", minimum=0),
            )


@dataclass(frozen=True, slots=True)
class FamaMacBethResult:
    """Cross-sectional factor returns and their time-series premia summary."""

    cross_sectional: CrossSectionalFactorModelResult
    premia: FactorPremiaResult


@dataclass(frozen=True, slots=True)
class FactorRiskModel:
    """Factor and idiosyncratic components of one asset covariance estimate."""

    exposures: pd.DataFrame
    factor_covariance: pd.DataFrame
    idiosyncratic_variance: pd.Series
    asset_covariance: pd.DataFrame
    shrinkage: float
    as_of: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        for name in ("exposures", "factor_covariance", "asset_covariance"):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        object.__setattr__(
            self,
            "idiosyncratic_variance",
            self.idiosyncratic_variance.copy(deep=True),
        )
        if not 0.0 <= self.shrinkage <= 1.0:
            raise ValueError("shrinkage must be between zero and one")


@dataclass(frozen=True, slots=True)
class FactorPortfolioForecast:
    """Point-in-time expected returns and covariance from caller-defined factors."""

    expected_returns: pd.Series
    expected_return_contributions: pd.DataFrame
    exposures: pd.DataFrame
    factor_premia: pd.Series
    alpha: pd.Series
    factor_covariance: pd.DataFrame
    idiosyncratic_variance: pd.Series
    asset_covariance: pd.DataFrame
    as_of: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        for name in (
            "expected_returns",
            "factor_premia",
            "alpha",
            "idiosyncratic_variance",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        for name in (
            "expected_return_contributions",
            "exposures",
            "factor_covariance",
            "asset_covariance",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))


@dataclass(frozen=True, slots=True)
class FactorPortfolioAttribution:
    """Expected-return and variance attribution for supplied portfolio weights."""

    weights: pd.Series
    factor_exposures: pd.Series
    expected_return_contributions: pd.Series
    variance_contributions: pd.Series
    expected_return: float
    variance: float
    volatility: float
    as_of: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        for name in (
            "weights",
            "factor_exposures",
            "expected_return_contributions",
            "variance_contributions",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))


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
class NestedTemporalSplit:
    """One outer evaluation split with ordered inner model-selection splits."""

    outer: TemporalSplit
    inner: tuple[TemporalSplit, ...]
    outer_policy: Literal["expanding", "rolling"]
    inner_policy: Literal["expanding", "rolling"]

    def __post_init__(self) -> None:
        inner = tuple(self.inner)
        if not inner:
            raise ValueError("nested temporal split must contain inner splits")
        if self.outer_policy not in {"expanding", "rolling"}:
            raise ValueError("unsupported outer split policy")
        if self.inner_policy not in {"expanding", "rolling"}:
            raise ValueError("unsupported inner split policy")
        object.__setattr__(self, "inner", inner)


def _copy_regression_frames(result: object) -> None:
    for name in (
        "coefficients",
        "standard_errors",
        "t_statistics",
        "p_values",
        "factor_returns",
        "fitted_values",
        "residuals",
        "diagnostics",
    ):
        if hasattr(result, name):
            object.__setattr__(result, name, getattr(result, name).copy(deep=True))


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
        horizon = require_integer(self.horizon, name="horizon", minimum=1)
        object.__setattr__(self, "statistics", statistics)
        object.__setattr__(self, "horizon", horizon)


@dataclass(frozen=True, slots=True)
class QuantilePortfolioResult:
    """Quantile returns, formation weights, linear costs, and diagnostics."""

    assignments: pd.DataFrame
    weights: pd.DataFrame
    weight_diagnostics: pd.DataFrame
    returns: pd.DataFrame
    costs: pd.DataFrame
    net_returns: pd.DataFrame
    counts: pd.DataFrame
    turnover: pd.DataFrame
    capacity: pd.DataFrame
    spread: pd.Series
    spread_costs: pd.Series
    net_spread: pd.Series
    summary: pd.DataFrame
    horizon: int
    quantiles: int
    weighting: Literal["equal", "caller"]

    def __post_init__(self) -> None:
        horizon = require_integer(self.horizon, name="horizon", minimum=1)
        quantiles = require_integer(self.quantiles, name="quantiles", minimum=2)
        expected_columns = pd.Index(range(1, quantiles + 1), name="quantile")
        panels = {
            "returns": self.returns,
            "costs": self.costs,
            "net_returns": self.net_returns,
            "counts": self.counts,
            "turnover": self.turnover,
        }
        for name, panel in panels.items():
            if not panel.index.equals(self.assignments.index):
                raise ValueError(f"quantile {name} must use the assignment index")
            if not panel.columns.equals(expected_columns):
                raise ValueError(f"quantile {name} columns differ from the contract")
            object.__setattr__(self, name, panel.copy(deep=True))
        if not self.weights.index.equals(self.assignments.index) or not self.weights.columns.equals(
            self.assignments.columns
        ):
            raise ValueError("quantile weights must use the assignment axes")
        for name, series in {
            "spread": self.spread,
            "spread costs": self.spread_costs,
            "net spread": self.net_spread,
        }.items():
            if not series.index.equals(self.assignments.index):
                raise ValueError(f"quantile {name} must use the assignment index")
        if self.weighting not in {"equal", "caller"}:
            raise ValueError("unsupported quantile weighting policy")
        object.__setattr__(self, "assignments", self.assignments.copy(deep=True))
        object.__setattr__(self, "weights", self.weights.copy(deep=True))
        object.__setattr__(self, "weight_diagnostics", self.weight_diagnostics.copy(deep=True))
        object.__setattr__(self, "capacity", self.capacity.copy(deep=True))
        object.__setattr__(self, "spread", self.spread.copy(deep=True))
        object.__setattr__(self, "spread_costs", self.spread_costs.copy(deep=True))
        object.__setattr__(self, "net_spread", self.net_spread.copy(deep=True))
        object.__setattr__(self, "summary", self.summary.copy(deep=True))
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "quantiles", quantiles)


@dataclass(frozen=True, slots=True)
class GroupSignalResult:
    """Signal and forward-return statistics for time-varying classifications."""

    statistics: pd.DataFrame
    horizon: int

    def __post_init__(self) -> None:
        horizon = require_integer(self.horizon, name="horizon", minimum=1)
        object.__setattr__(self, "statistics", self.statistics.copy(deep=True))
        object.__setattr__(self, "horizon", horizon)


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
    """One dataset scope with deeply immutable portable JSON values and identity."""

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
    """Immutable record of research data, parameters, environment, and outputs."""

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
        if type(self.manifest_version) is not int or self.manifest_version != 1:
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
            if name == "environment" and any(not key or not item for key, item in value.items()):
                raise ValueError("environment names and versions must be nonempty strings")
            if name == "random_seeds" and any(
                not key or isinstance(item, bool) or not isinstance(item, int)
                for key, item in value.items()
            ):
                raise ValueError("random seed names must be nonempty and values must be integers")
            object.__setattr__(self, name, _portable_mapping(value, name=name))


def _portable_mapping(value: Mapping[str, Any], *, name: str) -> Mapping[str, Any]:
    return freeze_portable_mapping(value, name=name)
