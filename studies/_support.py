"""Shared live-data, statistical, and plotting support for the study notebooks."""

from __future__ import annotations

import atexit
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import NormalDist
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import PercentFormatter

from persistra.data import AlphaVantageClient, DuckDBStore, FredClient
from persistra.model import InstrumentKind, VintageSeriesSet
from persistra.research import (
    FeatureSpec,
    ForwardReturnLabels,
    build_feature_panel,
    forward_returns,
    select_vintage,
    summarize_regimes,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from persistra.model import SeriesSet
    from persistra.research import FeaturePanel

CORE_SYMBOLS = ("SPY", "IEF", "GLD", "DBC", "UUP")
PRICE_HISTORY_START = pd.Timestamp("2007-03-01")
STUDY_START = pd.Timestamp("2008-03-01")
HISTORY_START = "2005-01-01"
REALTIME_START = "2006-01-01"
HORIZONS = (1, 3, 12)
PRIMARY_HORIZON = 1
DEFAULT_PUBLICATION_LAG = pd.Timedelta(days=1)
MINIMUM_CONTRAST_OUTCOMES = 12
MINIMUM_CONTRAST_EPISODES = 2
MINIMUM_FACTORIAL_CELL_OUTCOMES = 6

ASSET_LABELS = {
    "SPY": "US equities",
    "IEF": "Intermediate Treasuries",
    "GLD": "Gold",
    "DBC": "Broad commodities",
    "UUP": "US dollar",
    "TLT": "Long Treasuries",
    "TIP": "Inflation-linked Treasuries",
    "SHY": "Short Treasuries",
}

ASSET_COLORS = {
    "SPY": "#2667ff",
    "IEF": "#5c7cfa",
    "GLD": "#e6a700",
    "DBC": "#d95f02",
    "UUP": "#6a4c93",
    "TLT": "#264653",
    "TIP": "#2a9d8f",
    "SHY": "#8ab17d",
}

REGIME_COLORS = (
    "#2667ff",
    "#e76f51",
    "#2a9d8f",
    "#e9c46a",
    "#6a4c93",
    "#8d99ae",
)


def regime_style(label: str) -> tuple[str, str]:
    """Return one stable color and marker from a regime label."""
    position = sum((index + 1) * ord(character) for index, character in enumerate(label))
    markers = ("o", "s", "^", "D", "P", "X")
    return (
        REGIME_COLORS[position % len(REGIME_COLORS)],
        markers[position % len(markers)],
    )


@dataclass(slots=True)
class LiveStudySession:
    """Provider clients backed by a temporary response directory."""

    alpha_vantage: AlphaVantageClient
    fred: FredClient
    store: DuckDBStore
    _temporary: TemporaryDirectory[str]
    _closed: bool = False

    def close(self) -> None:
        """Remove every raw response created by this study kernel."""
        if self._closed:
            return
        try:
            self.store.close()
        finally:
            try:
                self._temporary.cleanup()
            finally:
                self._closed = True


def open_live_session() -> LiveStudySession:
    """Open live provider clients whose raw responses disappear on close."""
    parent = os.environ.get("PERSISTRA_STUDY_TEMP_ROOT")
    temporary = TemporaryDirectory(prefix="persistra-live-study-", dir=parent)
    session = LiveStudySession(
        alpha_vantage=AlphaVantageClient.from_env(
            cache_directory=temporary.name,
            requests_per_minute=150,
            timeout=60,
        ),
        fred=FredClient.from_env(
            cache_directory=temporary.name,
            timeout=60,
        ),
        store=DuckDBStore.create(Path(temporary.name) / "study.duckdb"),
        _temporary=temporary,
    )
    atexit.register(session.close)
    return session


def configure_plots() -> None:
    """Apply one compact, colorblind-conscious Matplotlib style."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "figure.figsize": (11, 5.5),
            "figure.dpi": 110,
            "legend.frameon": False,
        }
    )


def acquire_monthly_prices(
    session: LiveStudySession,
    symbols: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Acquire adjusted daily bars and select the last close of complete months."""
    columns: list[pd.Series] = []
    provenance: list[dict[str, Any]] = []
    for symbol in symbols:
        acquired = session.alpha_vantage.securities.bars(
            symbol,
            kind=InstrumentKind.ETF,
            interval="daily",
            adjusted=True,
            outputsize="full",
            refresh=True,
        )
        session.store.save(acquired)
        result = session.store.load_bars(acquired.instrument.instrument_id)
        if result is None:
            raise RuntimeError(f"temporary store did not reload {symbol} bars")
        frame = result.frame
        values = frame.set_index("date")["adjusted_close"].rename(symbol)
        if values.empty or values.isna().any():
            raise ValueError(f"{symbol} has incomplete adjusted daily closes")
        columns.append(values)
        provenance.append(
            {
                "symbol": symbol,
                "provider": result.metadata.provider,
                "operation": result.metadata.operation,
                "retrieved_at": result.metadata.retrieved_at,
                "first_observation": values.index.min(),
                "last_observation": values.index.max(),
                "daily_observations": len(values),
                "diagnostics": len(result.metadata.diagnostics),
            }
        )
    daily = pd.concat(columns, axis=1).sort_index().dropna()
    current_month_start = pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M").start_time
    last_complete_month = current_month_start - pd.Timedelta(days=1)
    complete = daily.loc[:last_complete_month]
    monthly = complete.groupby(complete.index.to_period("M"), sort=True).tail(1)
    monthly = monthly.loc[monthly.index >= PRICE_HISTORY_START]
    if monthly.empty or monthly[list(symbols)].isna().any(axis=None):
        raise ValueError("the selected ETF universe has incomplete joint monthly coverage")
    periods = monthly.index.to_period("M")
    expected = pd.period_range(periods.min(), periods.max(), freq="M")
    if not periods.equals(expected):
        raise ValueError("the selected ETF universe does not cover consecutive months")
    distance_from_month_end = periods.to_timestamp("M") - monthly.index
    if (distance_from_month_end < pd.Timedelta(0)).any() or (
        distance_from_month_end > pd.Timedelta(days=7)
    ).any():
        raise ValueError("a selected common close is not near its calendar month end")
    return monthly.astype(float), pd.DataFrame(provenance).set_index("symbol")


def acquire_vintage_histories(
    session: LiveStudySession,
    series_ids: Sequence[str],
    decision_dates: pd.DatetimeIndex,
    *,
    selected_view_series: frozenset[str] = frozenset(),
    selected_view_lags: Sequence[int] = (0, 1, 2),
) -> dict[str, VintageSeriesSet]:
    """Acquire ALFRED histories, using explicit views for selected daily series."""
    histories: dict[str, VintageSeriesSet] = {}
    for series_id in series_ids:
        if series_id in selected_view_series:
            cutoff_sets = {
                lag: tuple(
                    (date - pd.Timedelta(days=lag)).strftime("%Y-%m-%d")
                    for date in decision_dates
                )
                for lag in selected_view_lags
            }
            views = [
                session.fred.series.vintages(
                    series_id,
                    vintage_dates=cutoff_sets[lag],
                    observation_start=HISTORY_START,
                    refresh=True,
                )
                for lag in selected_view_lags
            ]
            history = _combine_selected_views(
                views,
                series_id,
                selected_view_lags=selected_view_lags,
                cutoff_sets=cutoff_sets,
            )
        else:
            history = session.fred.series.vintages(
                series_id,
                realtime_start=REALTIME_START,
                observation_start=HISTORY_START,
                refresh=True,
            )
        session.store.save(history)
        reloaded = session.store.load_vintage_series(history.definition.series_id)
        if reloaded is None:
            raise RuntimeError(f"temporary store did not reload {series_id} vintages")
        histories[series_id] = reloaded
    return histories


def _combine_selected_views(
    views: Sequence[VintageSeriesSet],
    series_id: str,
    *,
    selected_view_lags: Sequence[int],
    cutoff_sets: Mapping[int, Sequence[str]],
) -> VintageSeriesSet:
    """Combine bounded views and reconstruct intervals across selected revision starts."""
    if not views:
        raise ValueError("at least one selected view is required")
    retrieved_at = max(view.metadata.retrieved_at for view in views)
    frame = pd.concat([view.frame for view in views], ignore_index=True)
    frame["retrieved_at"] = retrieved_at
    frame["retrieved_at"] = frame["retrieved_at"].astype("datetime64[ns, UTC]")
    identity = ["period_label", "available_from"]
    query_dependent = {"available_through", "retrieved_at"}
    semantic = [column for column in frame.columns if column not in query_dependent]
    for _, duplicates in frame.groupby(identity, dropna=False, sort=False):
        normalized = duplicates[semantic].astype("string").fillna("<missing>")
        if len(normalized.drop_duplicates()) > 1:
            differing = [
                column
                for column in semantic
                if normalized[column].nunique(dropna=False) > 1
            ]
            raise ValueError(
                f"selected views conflict for {series_id}: fields {differing}"
            )
    frame = frame.drop_duplicates(identity, keep="last")
    frame["available_through"] = pd.NaT
    observation_key = ["series_id", "frequency", "maturity", "period_label"]
    for _, versions in frame.groupby(observation_key, dropna=False, sort=False):
        ordered = versions.sort_values("available_from", kind="stable")
        next_starts = ordered["available_from"].shift(-1)
        frame.loc[ordered.index, "available_through"] = (
            next_starts - pd.Timedelta(days=1)
        ).to_numpy()
    frame = frame.sort_values(
        ["series_id", "frequency", "maturity", "period_label", "available_from"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    diagnostics = tuple(
        diagnostic for view in views for diagnostic in view.metadata.diagnostics
    )
    metadata = replace(
        views[-1].metadata,
        request_parameters={
            "series_id": series_id,
            "selected_view_lags": tuple(selected_view_lags),
            "selected_view_cutoffs": {
                str(lag): tuple(cutoff_sets[lag]) for lag in selected_view_lags
            },
            "observation_start": HISTORY_START,
            "query_retrieved_at": tuple(
                view.metadata.retrieved_at.isoformat() for view in views
            ),
        },
        retrieved_at=retrieved_at,
        diagnostics=diagnostics,
    )
    combined = VintageSeriesSet(views[-1].definition, frame, metadata)
    _assert_selected_view_equivalence(
        views,
        combined,
        selected_view_lags=selected_view_lags,
        cutoff_sets=cutoff_sets,
    )
    return combined


def _assert_selected_view_equivalence(
    views: Sequence[VintageSeriesSet],
    combined: VintageSeriesSet,
    *,
    selected_view_lags: Sequence[int],
    cutoff_sets: Mapping[int, Sequence[str]],
) -> None:
    """Require combined selections to reproduce every original bounded view."""
    identity = ["period_label", "available_from", "value", "is_deleted"]
    for lag, view in zip(selected_view_lags, views, strict=True):
        for cutoff in cutoff_sets[lag]:
            original = select_vintage(view, known_on=cutoff).frame[identity]
            reconstructed = select_vintage(combined, known_on=cutoff).frame[identity]
            left = original.astype("string").fillna("<missing>").reset_index(drop=True)
            right = reconstructed.astype("string").fillna("<missing>").reset_index(drop=True)
            if not left.equals(right):
                raise AssertionError("combined selected view changes a requested snapshot")


def acquire_latest_series(
    session: LiveStudySession,
    series_ids: Sequence[str],
) -> dict[str, SeriesSet]:
    """Acquire today's latest-revised histories for the explicit bias comparison."""
    results: dict[str, SeriesSet] = {}
    for series_id in series_ids:
        acquired = session.fred.series.latest(
            series_id,
            observation_start=HISTORY_START,
            refresh=True,
        )
        session.store.save(acquired)
        reloaded = session.store.load_series(acquired.definition.series_id)
        if reloaded is None:
            raise RuntimeError(f"temporary store did not reload {series_id} series")
        results[series_id] = reloaded
    return results


def build_point_in_time_levels(
    histories: Mapping[str, VintageSeriesSet],
    decision_dates: pd.DatetimeIndex,
    maximum_staleness: Mapping[str, pd.Timedelta],
    *,
    publication_lag: pd.Timedelta = DEFAULT_PUBLICATION_LAG,
    observation_date_columns: Mapping[str, str] | None = None,
    latest_nonmissing_series: frozenset[str] = frozenset(),
) -> FeaturePanel:
    """Select the most recent admissible macro level for every decision date."""
    date_columns = observation_date_columns or {}
    specs: list[FeatureSpec] = []
    for series_id, history in histories.items():
        source = (
            _without_explicit_missing(history)
            if series_id in latest_nonmissing_series
            else history
        )
        observation_date_column = date_columns.get(series_id, "period_start")
        if observation_date_column == "period_end":
            source = _with_observation_period_end(source)
        specs.append(
            FeatureSpec(
                name=series_id,
                source=source,
                maximum_staleness=maximum_staleness[series_id],
                publication_lag=publication_lag,
                observation_date_column=observation_date_column,
            )
        )
    return build_feature_panel(specs, decision_dates=decision_dates)


def _without_explicit_missing(source: VintageSeriesSet) -> VintageSeriesSet:
    """Apply the declared daily-market policy of selecting the latest valid observation."""
    usable = source.frame.loc[source.frame["value"].notna() & ~source.frame["is_deleted"]]
    return VintageSeriesSet(source.definition, usable, source.metadata)


def _with_observation_period_end(source: VintageSeriesSet) -> VintageSeriesSet:
    """Derive a quarterly observation end when the normalized provider field is absent."""
    frame = source.frame.copy()
    missing = frame["period_end"].isna()
    if not missing.any():
        return source
    if str(source.definition.frequency).lower() != "quarterly":
        raise ValueError("period-end derivation is declared only for quarterly series")
    frame.loc[missing, "period_end"] = (
        frame.loc[missing, "period_start"] + pd.offsets.QuarterEnd(0)
    )
    return VintageSeriesSet(source.definition, frame, source.metadata)


def latest_revised_counterpart(
    point_in_time: FeaturePanel,
    latest: Mapping[str, SeriesSet],
) -> pd.DataFrame:
    """Substitute current revisions while preserving each selected observation period."""
    revised: dict[str, pd.Series] = {}
    for feature in point_in_time.frame.columns:
        provenance = point_in_time.provenance.loc[
            point_in_time.provenance["feature"].eq(feature),
            ["decision_date", "period_label"],
        ].set_index("decision_date")
        lookup = (
            latest[str(feature)]
            .frame.drop_duplicates("period_label", keep="last")
            .set_index("period_label")["value"]
        )
        values = provenance["period_label"].map(lookup)
        revised[str(feature)] = pd.Series(
            values.to_numpy(),
            index=point_in_time.frame.index,
            dtype="Float64",
        )
    return pd.DataFrame(revised, index=point_in_time.frame.index)


def feature_provenance_summary(point_in_time: FeaturePanel) -> pd.DataFrame:
    """Summarize matched versions and staleness without discarding row-level provenance."""
    frame = point_in_time.provenance.copy()
    frame["matched"] = frame["selected_value"].notna()
    summary = frame.groupby("feature", sort=False).agg(
        decisions=("decision_date", "size"),
        matched=("matched", "sum"),
        first_available=("available_from", "min"),
        last_available=("available_from", "max"),
        maximum_matched_age=("matched_age", "max"),
        source_retrieved_at=("source_retrieved_at", "first"),
    )
    summary["coverage"] = summary["matched"] / summary["decisions"]
    return summary


def study_run_manifest(
    prices: pd.DataFrame,
    *,
    series_ids: Sequence[str],
    thresholds: str,
    staleness: Mapping[str, pd.Timedelta],
) -> pd.DataFrame:
    """Build a temporary procedural manifest without retaining provider observations."""
    entries = {
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "persistra_version": version("persistra"),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "matplotlib_version": plt.matplotlib.__version__,
        "analysis_first_close": prices.index.min().isoformat(),
        "analysis_last_close": prices.index.max().isoformat(),
        "assets": ", ".join(str(column) for column in prices.columns),
        "economic_series": ", ".join(series_ids),
        "information_lag": str(DEFAULT_PUBLICATION_LAG),
        "staleness": ", ".join(
            f"{name}={window}" for name, window in staleness.items()
        ),
        "forward_horizons_months": ", ".join(str(value) for value in HORIZONS),
        "thresholds": thresholds,
        "exact_result_reconstruction": "not possible without retained provider snapshots",
    }
    return pd.DataFrame(
        {"field": tuple(entries), "value": tuple(entries.values())}
    ).set_index("field")


@dataclass(frozen=True, slots=True)
class TransformResult:
    """A within-vintage transformed feature and all of its source components."""

    frame: pd.DataFrame
    provenance: pd.DataFrame

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame", self.frame.copy(deep=True))
        object.__setattr__(self, "provenance", self.provenance.copy(deep=True))


def point_in_time_year_over_year(
    histories: Mapping[str, VintageSeriesSet],
    point_in_time: FeaturePanel,
) -> TransformResult:
    """Compute each year-over-year rate inside one decision-date vintage snapshot."""
    values: dict[str, pd.Series] = {}
    provenance: list[dict[str, Any]] = []
    policies = {policy.name: policy for policy in point_in_time.policies}
    for feature in point_in_time.frame.columns:
        results: list[float] = []
        periods = _selected_periods(point_in_time, str(feature))
        for decision_date, current_period in periods.items():
            if pd.isna(current_period):
                results.append(float("nan"))
                continue
            policy = policies[str(feature)]
            selected = select_vintage(
                histories[str(feature)],
                known_on=decision_date,
                publication_lag=policy.publication_lag,
            ).frame
            current = pd.Timestamp(current_period)
            previous = current - pd.DateOffset(years=1)
            numerator = _component_row(selected, current)
            denominator = _component_row(selected, previous)
            provenance.extend(
                _component_provenance(
                    feature=str(feature),
                    decision_date=pd.Timestamp(decision_date),
                    publication_lag=policy.publication_lag,
                    components=(
                        ("current", current, numerator),
                        ("year_ago", previous, denominator),
                    ),
                    view="point-in-time",
                )
            )
            results.append(_percent_change(numerator, denominator))
        values[str(feature)] = pd.Series(results, index=point_in_time.frame.index, dtype=float)
    return TransformResult(pd.DataFrame(values), pd.DataFrame(provenance))


def latest_revised_year_over_year(
    point_in_time: FeaturePanel,
    latest: Mapping[str, SeriesSet],
) -> TransformResult:
    """Compute revised rates from the exact source periods used by the real-time feature."""
    values: dict[str, pd.Series] = {}
    provenance: list[dict[str, Any]] = []
    for feature in point_in_time.frame.columns:
        source = latest[str(feature)].frame.set_index("period_label", drop=False)
        results: list[float] = []
        periods = _selected_periods(point_in_time, str(feature))
        for decision_date, current_period in periods.items():
            if pd.isna(current_period):
                results.append(float("nan"))
                continue
            current = pd.Timestamp(current_period)
            previous = current - pd.DateOffset(years=1)
            numerator = _component_row(source, current)
            denominator = _component_row(source, previous)
            provenance.extend(
                _component_provenance(
                    feature=str(feature),
                    decision_date=pd.Timestamp(decision_date),
                    publication_lag=pd.Timedelta(0),
                    components=(
                        ("current", current, numerator),
                        ("year_ago", previous, denominator),
                    ),
                    view="latest-revised",
                )
            )
            results.append(_percent_change(numerator, denominator))
        values[str(feature)] = pd.Series(results, index=point_in_time.frame.index, dtype=float)
    return TransformResult(pd.DataFrame(values), pd.DataFrame(provenance))


def point_in_time_inflation_momentum(
    histories: Mapping[str, VintageSeriesSet],
    point_in_time: FeaturePanel,
    *,
    comparison_months: int = 6,
) -> TransformResult:
    """Compare two year-over-year inflation rates inside each available vintage."""
    return _inflation_momentum(
        histories=histories,
        point_in_time=point_in_time,
        latest=None,
        comparison_months=comparison_months,
    )


def latest_revised_inflation_momentum(
    point_in_time: FeaturePanel,
    latest: Mapping[str, SeriesSet],
    *,
    comparison_months: int = 6,
) -> TransformResult:
    """Repeat inflation momentum with current values for identical component periods."""
    return _inflation_momentum(
        histories=None,
        point_in_time=point_in_time,
        latest=latest,
        comparison_months=comparison_months,
    )


def _inflation_momentum(
    *,
    histories: Mapping[str, VintageSeriesSet] | None,
    point_in_time: FeaturePanel,
    latest: Mapping[str, SeriesSet] | None,
    comparison_months: int,
) -> TransformResult:
    values: dict[str, pd.Series] = {}
    provenance: list[dict[str, Any]] = []
    policies = {policy.name: policy for policy in point_in_time.policies}
    for feature in point_in_time.frame.columns:
        results: list[float] = []
        periods = _selected_periods(point_in_time, str(feature))
        latest_source = None
        if latest is not None:
            latest_source = latest[str(feature)].frame.set_index("period_label", drop=False)
        for decision_date, current_period in periods.items():
            if pd.isna(current_period):
                results.append(float("nan"))
                continue
            current = pd.Timestamp(current_period)
            earlier = current - pd.DateOffset(months=comparison_months)
            component_periods = (
                ("current", current),
                ("current_year_ago", current - pd.DateOffset(years=1)),
                ("comparison", earlier),
                ("comparison_year_ago", earlier - pd.DateOffset(years=1)),
            )
            if histories is not None:
                policy = policies[str(feature)]
                source = select_vintage(
                    histories[str(feature)],
                    known_on=decision_date,
                    publication_lag=policy.publication_lag,
                ).frame
                publication_lag = policy.publication_lag
                view = "point-in-time"
            else:
                if latest_source is None:
                    raise RuntimeError("latest source is required")
                source = latest_source
                publication_lag = pd.Timedelta(0)
                view = "latest-revised"
            rows = tuple(
                (name, period, _component_row(source, period))
                for name, period in component_periods
            )
            provenance.extend(
                _component_provenance(
                    feature=str(feature),
                    decision_date=pd.Timestamp(decision_date),
                    publication_lag=publication_lag,
                    components=rows,
                    view=view,
                )
            )
            current_rate = _percent_change(rows[0][2], rows[1][2])
            comparison_rate = _percent_change(rows[2][2], rows[3][2])
            results.append(current_rate - comparison_rate)
        values[str(feature)] = pd.Series(results, index=point_in_time.frame.index, dtype=float)
    return TransformResult(pd.DataFrame(values), pd.DataFrame(provenance))


def point_in_time_labor_deterioration(
    history: VintageSeriesSet,
    point_in_time: FeaturePanel,
) -> TransformResult:
    """Compute the labor alert from consecutive months in one decision-date vintage."""
    return _labor_deterioration(history=history, point_in_time=point_in_time, latest=None)


def latest_revised_labor_deterioration(
    point_in_time: FeaturePanel,
    latest: SeriesSet,
) -> TransformResult:
    """Repeat the labor calculation with current values for identical source periods."""
    return _labor_deterioration(history=None, point_in_time=point_in_time, latest=latest)


def _labor_deterioration(
    *,
    history: VintageSeriesSet | None,
    point_in_time: FeaturePanel,
    latest: SeriesSet | None,
) -> TransformResult:
    feature = str(point_in_time.frame.columns[0])
    policy = point_in_time.policies[0]
    periods = _selected_periods(point_in_time, feature)
    results: list[float] = []
    provenance: list[dict[str, Any]] = []
    latest_source = None if latest is None else latest.frame.set_index("period_label", drop=False)
    for decision_date, current_period in periods.items():
        if pd.isna(current_period):
            results.append(float("nan"))
            continue
        current = pd.Timestamp(current_period)
        expected = pd.date_range(end=current, periods=15, freq="MS")
        if history is not None:
            source = select_vintage(
                history,
                known_on=decision_date,
                publication_lag=policy.publication_lag,
            ).frame
            publication_lag = policy.publication_lag
            view = "point-in-time"
        else:
            if latest_source is None:
                raise RuntimeError("latest source is required")
            source = latest_source
            publication_lag = pd.Timedelta(0)
            view = "latest-revised"
        rows = tuple(
            (f"month_{position - 14}", period, _component_row(source, period))
            for position, period in enumerate(expected)
        )
        provenance.extend(
            _component_provenance(
                feature=feature,
                decision_date=pd.Timestamp(decision_date),
                publication_lag=publication_lag,
                components=rows,
                view=view,
            )
        )
        sequence = pd.Series(
            [_row_value(row) for _name, _period, row in rows],
            index=expected,
            dtype=float,
        )
        smoothed = sequence.rolling(3, min_periods=3).mean()
        prior_twelve = smoothed.iloc[-13:-1]
        if pd.isna(smoothed.iloc[-1]) or prior_twelve.isna().any():
            results.append(float("nan"))
        else:
            results.append(float(smoothed.iloc[-1] - prior_twelve.min()))
    frame = pd.DataFrame({feature: results}, index=point_in_time.frame.index, dtype=float)
    return TransformResult(frame, pd.DataFrame(provenance))


def _selected_periods(point_in_time: FeaturePanel, feature: str) -> pd.Series:
    return (
        point_in_time.provenance.loc[
            point_in_time.provenance["feature"].eq(feature),
            ["decision_date", "period_label"],
        ]
        .set_index("decision_date")["period_label"]
        .reindex(point_in_time.frame.index)
    )


def _component_row(source: pd.DataFrame, period: pd.Timestamp) -> pd.Series | None:
    indexed = (
        source
        if source.index.name == "period_label"
        else source.set_index("period_label", drop=False)
    )
    matches = indexed.loc[indexed.index == period.strftime("%Y-%m-%d")]
    if matches.empty:
        return None
    if len(matches) > 1:
        raise ValueError(f"multiple active source values for period {period.date()}")
    return matches.iloc[0]


def _row_value(row: pd.Series | None) -> float:
    if row is None or bool(row.get("is_deleted", False)) or pd.isna(row["value"]):
        return float("nan")
    return float(row["value"])


def _percent_change(numerator: pd.Series | None, denominator: pd.Series | None) -> float:
    top = _row_value(numerator)
    bottom = _row_value(denominator)
    if not np.isfinite(top) or not np.isfinite(bottom) or bottom == 0:
        return float("nan")
    return (top / bottom - 1) * 100


def _component_provenance(
    *,
    feature: str,
    decision_date: pd.Timestamp,
    publication_lag: pd.Timedelta,
    components: Sequence[tuple[str, pd.Timestamp, pd.Series | None]],
    view: str,
) -> list[dict[str, Any]]:
    return [
        {
            "decision_date": decision_date,
            "information_cutoff": decision_date - publication_lag,
            "feature": feature,
            "view": view,
            "component": name,
            "expected_period": period,
            "period_label": pd.NaT if row is None else pd.Timestamp(row["period_label"]),
            "available_from": pd.NaT if row is None else row.get("available_from", pd.NaT),
            "available_through": pd.NaT if row is None else row.get("available_through", pd.NaT),
            "is_deleted": pd.NA if row is None else row.get("is_deleted", False),
            "value": pd.NA if row is None else row["value"],
            "series_id": pd.NA if row is None else row.get("series_id", pd.NA),
            "provider": pd.NA if row is None else row.get("provider", pd.NA),
            "provider_series": pd.NA
            if row is None
            else row.get("provider_series", pd.NA),
            "series_kind": pd.NA if row is None else row.get("series_kind", pd.NA),
            "frequency": pd.NA if row is None else row.get("frequency", pd.NA),
            "unit": pd.NA if row is None else row.get("unit", pd.NA),
            "geography": pd.NA if row is None else row.get("geography", pd.NA),
            "seasonal_adjustment": pd.NA
            if row is None
            else row.get("seasonal_adjustment", pd.NA),
            "maturity": pd.NA if row is None else row.get("maturity", pd.NA),
            "retrieved_at": pd.NaT if row is None else row.get("retrieved_at", pd.NaT),
        }
        for name, period, row in components
    ]


def forward_labels(
    prices: pd.DataFrame,
    horizons: Sequence[int] = HORIZONS,
) -> dict[int, ForwardReturnLabels]:
    """Construct separate forward-return label objects for explicit horizons."""
    return {horizon: forward_returns(prices, horizon=horizon) for horizon in horizons}


def regime_statistics(
    labels: Mapping[int, ForwardReturnLabels],
    regimes: pd.Series,
) -> pd.DataFrame:
    """Report coverage, episodes, and serial-dependence-robust mean intervals."""
    rows: list[dict[str, Any]] = []
    for horizon, label in labels.items():
        aligned_regimes = regimes.reindex(label.frame.index)
        public_summary = None
        if horizon == PRIMARY_HORIZON:
            public_summary = summarize_regimes(
                label.frame,
                aligned_regimes,
                periods_per_year=12,
            ).regime_statistics
        for regime in pd.unique(aligned_regimes.dropna()):
            mask = aligned_regimes.eq(regime).fillna(False)
            regime_decisions = int(mask.sum())
            for asset in label.frame.columns:
                sample = label.frame[asset].where(mask)
                observed = sample.dropna().astype(float)
                standard_error, bandwidth = hac_mean_standard_error(
                    sample,
                    minimum_lag=horizon - 1,
                )
                if public_summary is not None:
                    public_row = public_summary.loc[(regime, asset)]
                    mean_return = float(public_row["mean_return"])
                    annualized_volatility = float(public_row["volatility"])
                    max_drawdown = float(public_row["max_drawdown"])
                else:
                    mean_return = float(observed.mean())
                    annualized_volatility = float("nan")
                    max_drawdown = float("nan")
                outcome_episodes = regime_episode_summary(
                    aligned_regimes.where(label.frame[asset].notna())
                ).set_index("regime")
                episode_count = (
                    int(outcome_episodes.loc[str(regime), "episode_count"])
                    if str(regime) in outcome_episodes.index
                    else 0
                )
                rows.append(
                    {
                        "horizon_months": horizon,
                        "regime": str(regime),
                        "asset": str(asset),
                        "count": len(observed),
                        "episode_count": episode_count,
                        "coverage": len(observed) / regime_decisions if regime_decisions else 0.0,
                        "mean_return": mean_return,
                        "horizon_return_std": float(observed.std(ddof=1)),
                        "one_month_annualized_volatility": annualized_volatility,
                        "positive_share": float(observed.gt(0).mean()),
                        "hac_bandwidth": bandwidth,
                        "hac_standard_error": standard_error,
                        "ci_lower": mean_return - 1.96 * standard_error,
                        "ci_upper": mean_return + 1.96 * standard_error,
                        "max_drawdown": max_drawdown,
                    }
                )
    return pd.DataFrame(rows)


def hac_mean_standard_error(values: pd.Series, *, minimum_lag: int) -> tuple[float, int]:
    """Estimate a Bartlett HAC mean error with overlap and automatic bandwidth floors."""
    numeric = values.astype(float)
    observed = numeric.dropna()
    count = len(observed)
    if count < 2:
        return float("nan"), 0
    maximum_lag = _hac_bandwidth(count, minimum_lag)
    centered = numeric - observed.mean()
    long_run_variance = float((centered.dropna() ** 2).sum() / count)
    for lag in range(1, min(maximum_lag, len(numeric) - 1) + 1):
        left = centered.iloc[lag:]
        right = centered.shift(lag).iloc[lag:]
        paired = left.notna() & right.notna()
        covariance = float((left[paired] * right[paired]).sum() / count)
        weight = 1 - lag / (maximum_lag + 1)
        long_run_variance += 2 * weight * covariance
    return float(np.sqrt(max(long_run_variance, 0.0) / count)), maximum_lag


def _hac_bandwidth(count: int, minimum_lag: int) -> int:
    automatic = int(np.floor(4 * (count / 100) ** (2 / 9)))
    return max(minimum_lag, automatic)


def regime_episode_summary(regimes: pd.Series) -> pd.DataFrame:
    """Summarize contiguous nonmissing regime episodes separately from decision counts."""
    records: list[dict[str, Any]] = []
    current: str | None = None
    start: pd.Timestamp | None = None
    previous: pd.Timestamp | None = None
    length = 0
    for decision_date, raw_regime in regimes.items():
        regime = None if pd.isna(raw_regime) else str(raw_regime)
        if regime == current and regime is not None:
            length += 1
            previous = pd.Timestamp(decision_date)
            continue
        if current is not None and start is not None:
            records.append(
                {
                    "regime": current,
                    "start": start,
                    "end": previous,
                    "decision_count": length,
                }
            )
        current = regime
        start = pd.Timestamp(decision_date) if regime is not None else None
        length = 1 if regime is not None else 0
        previous = pd.Timestamp(decision_date)
    if current is not None and start is not None:
        records.append(
            {
                "regime": current,
                "start": start,
                "end": previous,
                "decision_count": length,
            }
        )
    if not records:
        return pd.DataFrame(
            columns=[
                "regime",
                "episode_count",
                "decision_count",
                "median_episode_length",
                "minimum_episode_length",
                "maximum_episode_length",
            ]
        )
    episodes = pd.DataFrame(records)
    return (
        episodes.groupby("regime", sort=False)
        .agg(
            episode_count=("decision_count", "size"),
            decision_count=("decision_count", "sum"),
            median_episode_length=("decision_count", "median"),
            minimum_episode_length=("decision_count", "min"),
            maximum_episode_length=("decision_count", "max"),
        )
        .reset_index()
    )


def regime_contrast_statistics(
    labels: Mapping[int, ForwardReturnLabels],
    regimes: pd.Series,
    *,
    treated: str,
    reference: str,
    assets: Sequence[str] | None = None,
    horizons: Sequence[int] | None = None,
) -> pd.DataFrame:
    """Estimate a predeclared treated-minus-reference contrast with HAC uncertainty."""
    rows: list[dict[str, Any]] = []
    for horizon, label in labels.items():
        if horizons is not None and horizon not in horizons:
            continue
        states = regimes.reindex(label.frame.index)
        for asset in label.frame.columns:
            if assets is not None and asset not in assets:
                continue
            effect, standard_error, bandwidth, treated_count, reference_count = (
                _hac_regime_difference(
                    label.frame[asset],
                    states,
                    treated=treated,
                    reference=reference,
                    minimum_lag=horizon - 1,
                )
            )
            outcome_episodes = regime_episode_summary(
                states.where(label.frame[asset].notna())
            ).set_index("regime")
            treated_episodes = _episode_count(outcome_episodes, treated)
            reference_episodes = _episode_count(outcome_episodes, reference)
            rows.append(
                {
                    "horizon_months": horizon,
                    "asset": str(asset),
                    "treated": treated,
                    "reference": reference,
                    "treated_count": treated_count,
                    "reference_count": reference_count,
                    "treated_episodes": treated_episodes,
                    "reference_episodes": reference_episodes,
                    "mean_difference": effect,
                    "hac_bandwidth": bandwidth,
                    "hac_standard_error": standard_error,
                    "ci_lower": effect - 1.96 * standard_error,
                    "ci_upper": effect + 1.96 * standard_error,
                    "meets_display_threshold": treated_count
                    >= MINIMUM_CONTRAST_OUTCOMES
                    and reference_count >= MINIMUM_CONTRAST_OUTCOMES
                    and treated_episodes >= MINIMUM_CONTRAST_EPISODES
                    and reference_episodes >= MINIMUM_CONTRAST_EPISODES,
                }
            )
    return familywise_primary_intervals(pd.DataFrame(rows))


def familywise_primary_intervals(contrasts: pd.DataFrame) -> pd.DataFrame:
    """Add Bonferroni intervals for the declared one-month contrast family only."""
    result = contrasts.copy()
    primary = result["horizon_months"].eq(PRIMARY_HORIZON)
    family_size = int(primary.sum())
    critical = (
        NormalDist().inv_cdf(1 - 0.05 / (2 * family_size))
        if family_size
        else float("nan")
    )
    result["familywise_ci_lower"] = np.nan
    result["familywise_ci_upper"] = np.nan
    result["primary_family_size"] = family_size
    result.loc[primary, "familywise_ci_lower"] = (
        result.loc[primary, "mean_difference"]
        - critical * result.loc[primary, "hac_standard_error"]
    )
    result.loc[primary, "familywise_ci_upper"] = (
        result.loc[primary, "mean_difference"]
        + critical * result.loc[primary, "hac_standard_error"]
    )
    return result


def simultaneous_interval_family(
    contrasts: pd.DataFrame,
    *,
    family_id: str,
) -> pd.DataFrame:
    """Apply one Bonferroni interval across an explicitly combined exploratory family."""
    result = contrasts.copy()
    family_size = len(result)
    critical = (
        NormalDist().inv_cdf(1 - 0.05 / (2 * family_size))
        if family_size
        else float("nan")
    )
    result["family_id"] = family_id
    result["family_size"] = family_size
    result["familywise_ci_lower"] = (
        result["mean_difference"] - critical * result["hac_standard_error"]
    )
    result["familywise_ci_upper"] = (
        result["mean_difference"] + critical * result["hac_standard_error"]
    )
    return result


def factorial_contrast_statistics(
    labels: Mapping[int, ForwardReturnLabels],
    focal_states: pd.Series,
    adjustment_states: pd.Series,
    *,
    treated: str,
    reference: str,
    adjustment_levels: tuple[str, str],
    assets: Sequence[str],
) -> pd.DataFrame:
    """Estimate an effect-coded two-factor contrast averaged across the other factor."""
    rows: list[dict[str, Any]] = []
    for horizon, label in labels.items():
        focal = focal_states.reindex(label.frame.index)
        adjustment = adjustment_states.reindex(label.frame.index)
        for asset in assets:
            values = label.frame[asset].astype(float)
            (
                effect,
                standard_error,
                bandwidth,
                treated_count,
                reference_count,
                minimum_cell_count,
            ) = _hac_factorial_effect(
                values,
                focal,
                adjustment,
                treated=treated,
                reference=reference,
                adjustment_levels=adjustment_levels,
                minimum_lag=horizon - 1,
            )
            joint_focal = focal.where(adjustment.isin(adjustment_levels) & values.notna())
            episodes = regime_episode_summary(joint_focal).set_index("regime")
            treated_episodes = _episode_count(episodes, treated)
            reference_episodes = _episode_count(episodes, reference)
            rows.append(
                {
                    "horizon_months": horizon,
                    "asset": str(asset),
                    "treated": treated,
                    "reference": reference,
                    "adjustment_factor": " / ".join(adjustment_levels),
                    "treated_count": treated_count,
                    "reference_count": reference_count,
                    "minimum_factorial_cell_count": minimum_cell_count,
                    "treated_episodes": treated_episodes,
                    "reference_episodes": reference_episodes,
                    "mean_difference": effect,
                    "hac_bandwidth": bandwidth,
                    "hac_standard_error": standard_error,
                    "ci_lower": effect - 1.96 * standard_error,
                    "ci_upper": effect + 1.96 * standard_error,
                    "meets_display_threshold": treated_count
                    >= MINIMUM_CONTRAST_OUTCOMES
                    and reference_count >= MINIMUM_CONTRAST_OUTCOMES
                    and minimum_cell_count >= MINIMUM_FACTORIAL_CELL_OUTCOMES
                    and treated_episodes >= MINIMUM_CONTRAST_EPISODES
                    and reference_episodes >= MINIMUM_CONTRAST_EPISODES,
                }
            )
    return familywise_primary_intervals(pd.DataFrame(rows))


def _hac_factorial_effect(
    values: pd.Series,
    focal: pd.Series,
    adjustment: pd.Series,
    *,
    treated: str,
    reference: str,
    adjustment_levels: tuple[str, str],
    minimum_lag: int,
) -> tuple[float, float, int, int, int, int]:
    valid = (
        values.notna()
        & focal.isin((treated, reference))
        & adjustment.isin(adjustment_levels)
    )
    focal_valid = focal.loc[valid]
    adjustment_valid = adjustment.loc[valid]
    treated_count = int(focal_valid.eq(treated).sum())
    reference_count = int(focal_valid.eq(reference).sum())
    cell_counts = pd.crosstab(focal_valid, adjustment_valid).reindex(
        index=[reference, treated],
        columns=list(adjustment_levels),
        fill_value=0,
    )
    minimum_cell_count = int(cell_counts.to_numpy().min())
    count = int(valid.sum())
    if minimum_cell_count < 2:
        return (
            float("nan"),
            float("nan"),
            0,
            treated_count,
            reference_count,
            minimum_cell_count,
        )
    focal_code = focal_valid.eq(treated).to_numpy(dtype=float) - 0.5
    adjustment_code = (
        adjustment_valid.eq(adjustment_levels[0]).to_numpy(dtype=float) - 0.5
    )
    design = np.column_stack(
        [
            np.ones(count, dtype=float),
            focal_code,
            adjustment_code,
            focal_code * adjustment_code,
        ]
    )
    outcome = values.loc[valid].to_numpy(dtype=float)
    inverse = np.linalg.inv(design.T @ design)
    coefficients = inverse @ design.T @ outcome
    direct_effects = []
    for adjustment_level in adjustment_levels:
        treated_cell = valid & focal.eq(treated) & adjustment.eq(adjustment_level)
        reference_cell = valid & focal.eq(reference) & adjustment.eq(adjustment_level)
        direct_effects.append(
            float(values.loc[treated_cell].mean())
            - float(values.loc[reference_cell].mean())
        )
    direct = float(np.mean(direct_effects))
    if not np.isclose(coefficients[1], direct, rtol=1e-12, atol=1e-12):
        raise AssertionError("factorial coefficient differs from equal-weight cell effects")
    residuals = outcome - design @ coefficients
    scores = np.zeros((len(values), 4), dtype=float)
    scores[valid.to_numpy()] = design * residuals[:, None]
    bandwidth = _hac_bandwidth(count, minimum_lag)
    meat = scores.T @ scores
    for lag in range(1, min(bandwidth, len(scores) - 1) + 1):
        weight = 1 - lag / (bandwidth + 1)
        cross = scores[lag:].T @ scores[:-lag]
        meat += weight * (cross + cross.T)
    covariance = inverse @ meat @ inverse
    standard_error = float(np.sqrt(max(float(covariance[1, 1]), 0.0)))
    return (
        float(coefficients[1]),
        standard_error,
        bandwidth,
        treated_count,
        reference_count,
        minimum_cell_count,
    )


def _hac_regime_difference(
    values: pd.Series,
    regimes: pd.Series,
    *,
    treated: str,
    reference: str,
    minimum_lag: int,
) -> tuple[float, float, int, int, int]:
    numeric = values.astype(float)
    valid = numeric.notna() & regimes.isin((treated, reference))
    treated_count = int((valid & regimes.eq(treated)).sum())
    reference_count = int((valid & regimes.eq(reference)).sum())
    count = int(valid.sum())
    if treated_count < 2 or reference_count < 2:
        return float("nan"), float("nan"), 0, treated_count, reference_count
    design = np.column_stack(
        [np.ones(count, dtype=float), regimes.loc[valid].eq(treated).to_numpy(dtype=float)]
    )
    outcome = numeric.loc[valid].to_numpy(dtype=float)
    inverse = np.linalg.inv(design.T @ design)
    coefficients = inverse @ design.T @ outcome
    residuals = outcome - design @ coefficients
    scores = np.zeros((len(numeric), 2), dtype=float)
    scores[valid.to_numpy()] = design * residuals[:, None]
    bandwidth = _hac_bandwidth(count, minimum_lag)
    meat = scores.T @ scores
    for lag in range(1, min(bandwidth, len(scores) - 1) + 1):
        weight = 1 - lag / (bandwidth + 1)
        cross = scores[lag:].T @ scores[:-lag]
        meat += weight * (cross + cross.T)
    covariance = inverse @ meat @ inverse
    standard_error = float(np.sqrt(max(float(covariance[1, 1]), 0.0)))
    direct = float(numeric.loc[valid & regimes.eq(treated)].mean()) - float(
        numeric.loc[valid & regimes.eq(reference)].mean()
    )
    if not np.isclose(coefficients[1], direct, rtol=1e-12, atol=1e-12):
        raise AssertionError("regression contrast differs from direct group means")
    return float(coefficients[1]), standard_error, bandwidth, treated_count, reference_count


def return_spread_labels(
    labels: Mapping[int, ForwardReturnLabels],
    spreads: Mapping[str, tuple[str, str]],
) -> dict[int, ForwardReturnLabels]:
    """Create paired cross-asset outcome differences on identical dates and horizons."""
    results: dict[int, ForwardReturnLabels] = {}
    for horizon, label in labels.items():
        frame = pd.DataFrame(
            {
                name: label.frame[left] - label.frame[right]
                for name, (left, right) in spreads.items()
            },
            index=label.frame.index,
        )
        results[horizon] = ForwardReturnLabels(frame, label.label_ends, horizon)
    return results


def combined_outcome_labels(
    labels: Mapping[int, ForwardReturnLabels],
    *,
    assets: Sequence[str],
    spreads: Mapping[str, tuple[str, str]] | None = None,
) -> dict[int, ForwardReturnLabels]:
    """Combine selected raw assets and paired return spreads in one label family."""
    spread_labels = return_spread_labels(labels, spreads or {})
    results: dict[int, ForwardReturnLabels] = {}
    for horizon, label in labels.items():
        frame = pd.concat(
            [label.frame[list(assets)], spread_labels[horizon].frame],
            axis=1,
        )
        results[horizon] = ForwardReturnLabels(frame, label.label_ends, horizon)
    return results


def unconditional_statistics(
    labels: Mapping[int, ForwardReturnLabels],
    *,
    eligible: pd.Series | None = None,
) -> pd.DataFrame:
    """Calculate the unconditional baseline on the primary regime-eligible sample."""
    index = next(iter(labels.values())).frame.index
    regimes = pd.Series(pd.NA, index=index, dtype="string")
    mask = (
        pd.Series(True, index=index)
        if eligible is None
        else eligible.reindex(index).fillna(False)
    )
    regimes.loc[mask] = "unconditional"
    return regime_statistics(labels, regimes)


def momentum_baseline(
    price_history: pd.DataFrame,
    labels: Mapping[int, ForwardReturnLabels],
    *,
    eligible: pd.Series | None = None,
) -> pd.DataFrame:
    """Evaluate momentum only where the primary macro regime is also observable."""
    label_index = next(iter(labels.values())).frame.index
    trailing = price_history.pct_change(12, fill_method=None).reindex(label_index)
    macro_eligible = (
        pd.Series(True, index=label_index)
        if eligible is None
        else eligible.reindex(label_index).fillna(False)
    )
    collected: list[pd.DataFrame] = []
    for asset in trailing.columns:
        state = pd.Series(pd.NA, index=label_index, dtype="string")
        state.loc[macro_eligible & trailing[asset].notna() & trailing[asset].gt(0)] = (
            "positive momentum"
        )
        state.loc[macro_eligible & trailing[asset].notna() & trailing[asset].le(0)] = (
            "nonpositive momentum"
        )
        asset_labels = {
            horizon: ForwardReturnLabels(
                label.frame[[asset]],
                label.label_ends,
                horizon,
            )
            for horizon, label in labels.items()
        }
        statistics = regime_statistics(asset_labels, state)
        statistics["baseline"] = "trailing 12-month momentum"
        collected.append(statistics)
    return pd.concat(collected, ignore_index=True)


def compare_statistics(
    point_in_time: pd.DataFrame,
    latest_revised: pd.DataFrame,
) -> pd.DataFrame:
    """Compare matched regime summaries without hiding sign reversals or missing groups."""
    keys = ["horizon_months", "regime", "asset"]
    left = point_in_time[[*keys, "count", "mean_return"]].rename(
        columns={"count": "point_in_time_count", "mean_return": "point_in_time_mean"}
    )
    right = latest_revised[[*keys, "count", "mean_return"]].rename(
        columns={"count": "latest_count", "mean_return": "latest_mean"}
    )
    comparison = left.merge(right, on=keys, how="outer", validate="one_to_one")
    comparison["mean_difference"] = (
        comparison["latest_mean"] - comparison["point_in_time_mean"]
    )
    comparison["group_count_difference"] = (
        comparison["latest_count"] - comparison["point_in_time_count"]
    )
    return comparison


def revision_contrast_change(
    labels: Mapping[int, ForwardReturnLabels],
    point_in_time: pd.Series,
    latest_revised: pd.Series,
    *,
    treated: str,
    reference: str,
    common_classified_only: bool = False,
) -> pd.DataFrame:
    """Estimate how revision-based reclassification changes one predeclared contrast."""
    rows: list[dict[str, Any]] = []
    for horizon, label in labels.items():
        point_states = point_in_time.reindex(label.frame.index)
        latest_states = latest_revised.reindex(label.frame.index)
        if common_classified_only:
            common = point_states.notna() & latest_states.notna()
            point_states = point_states.where(common)
            latest_states = latest_states.where(common)
        for asset in label.frame.columns:
            values = label.frame[asset].astype(float)
            point_effect, point_influence, point_treated, point_reference = (
                _difference_in_means_influence(
                    values,
                    point_states,
                    treated=treated,
                    reference=reference,
                )
            )
            latest_effect, latest_influence, latest_treated, latest_reference = (
                _difference_in_means_influence(
                    values,
                    latest_states,
                    treated=treated,
                    reference=reference,
                )
            )
            influence_change = latest_influence - point_influence
            effective = int(
                (
                    values.notna()
                    & (
                        point_states.isin((treated, reference))
                        | latest_states.isin((treated, reference))
                    )
                ).sum()
            )
            standard_error, bandwidth = _hac_sum_standard_error(
                influence_change,
                effective_count=effective,
                minimum_lag=horizon - 1,
            )
            outcome_mask = values.notna()
            point_episodes = regime_episode_summary(
                point_states.where(outcome_mask)
            ).set_index("regime")
            latest_episodes = regime_episode_summary(
                latest_states.where(outcome_mask)
            ).set_index("regime")
            point_treated_episodes = _episode_count(point_episodes, treated)
            point_reference_episodes = _episode_count(point_episodes, reference)
            latest_treated_episodes = _episode_count(latest_episodes, treated)
            latest_reference_episodes = _episode_count(latest_episodes, reference)
            effect_change = latest_effect - point_effect
            rows.append(
                {
                    "horizon_months": horizon,
                    "asset": str(asset),
                    "treated": treated,
                    "reference": reference,
                    "comparison_sample": "common classified"
                    if common_classified_only
                    else "total revision and availability",
                    "point_in_time_difference": point_effect,
                    "latest_revised_difference": latest_effect,
                    "revision_change": effect_change,
                    "point_treated_count": point_treated,
                    "point_reference_count": point_reference,
                    "latest_treated_count": latest_treated,
                    "latest_reference_count": latest_reference,
                    "hac_bandwidth": bandwidth,
                    "hac_standard_error": standard_error,
                    "ci_lower": effect_change - 1.96 * standard_error,
                    "ci_upper": effect_change + 1.96 * standard_error,
                    "meets_display_threshold": min(
                        point_treated,
                        point_reference,
                        latest_treated,
                        latest_reference,
                    )
                    >= MINIMUM_CONTRAST_OUTCOMES
                    and min(
                        point_treated_episodes,
                        point_reference_episodes,
                        latest_treated_episodes,
                        latest_reference_episodes,
                    )
                    >= MINIMUM_CONTRAST_EPISODES,
                }
            )
    result = pd.DataFrame(rows)
    primary = result["horizon_months"].eq(PRIMARY_HORIZON)
    family_size = int(primary.sum())
    critical = (
        NormalDist().inv_cdf(1 - 0.05 / (2 * family_size))
        if family_size
        else float("nan")
    )
    result["familywise_ci_lower"] = np.nan
    result["familywise_ci_upper"] = np.nan
    result["primary_family_size"] = family_size
    result.loc[primary, "familywise_ci_lower"] = (
        result.loc[primary, "revision_change"]
        - critical * result.loc[primary, "hac_standard_error"]
    )
    result.loc[primary, "familywise_ci_upper"] = (
        result.loc[primary, "revision_change"]
        + critical * result.loc[primary, "hac_standard_error"]
    )
    return result


def _difference_in_means_influence(
    values: pd.Series,
    regimes: pd.Series,
    *,
    treated: str,
    reference: str,
) -> tuple[float, pd.Series, int, int]:
    valid = values.notna()
    treated_mask = valid & regimes.eq(treated).fillna(False)
    reference_mask = valid & regimes.eq(reference).fillna(False)
    treated_count = int(treated_mask.sum())
    reference_count = int(reference_mask.sum())
    influence = pd.Series(0.0, index=values.index, dtype=float)
    if treated_count < 2 or reference_count < 2:
        return float("nan"), influence, treated_count, reference_count
    treated_mean = float(values.loc[treated_mask].mean())
    reference_mean = float(values.loc[reference_mask].mean())
    influence.loc[treated_mask] = (
        values.loc[treated_mask] - treated_mean
    ) / treated_count
    influence.loc[reference_mask] = -(
        values.loc[reference_mask] - reference_mean
    ) / reference_count
    if not np.isclose(influence.sum(), 0.0, rtol=1e-12, atol=1e-12):
        raise AssertionError("contrast influence contributions do not sum to zero")
    return treated_mean - reference_mean, influence, treated_count, reference_count


def _hac_sum_standard_error(
    influence: pd.Series,
    *,
    effective_count: int,
    minimum_lag: int,
) -> tuple[float, int]:
    if effective_count < 2:
        return float("nan"), 0
    values = influence.to_numpy(dtype=float)
    bandwidth = _hac_bandwidth(effective_count, minimum_lag)
    variance = float(values @ values)
    for lag in range(1, min(bandwidth, len(values) - 1) + 1):
        weight = 1 - lag / (bandwidth + 1)
        variance += 2 * weight * float(values[lag:] @ values[:-lag])
    return float(np.sqrt(max(variance, 0.0))), bandwidth


def _episode_count(episodes: pd.DataFrame, regime: str) -> int:
    return int(episodes.loc[regime, "episode_count"]) if regime in episodes.index else 0


def classification_transition_table(
    point_in_time: pd.Series,
    latest_revised: pd.Series,
) -> pd.DataFrame:
    """Count explicit classification and availability transitions on matched decisions."""
    point = point_in_time.astype("string").fillna("unclassified")
    latest = latest_revised.astype("string").fillna("unclassified")
    return pd.crosstab(
        point.rename("point-in-time"),
        latest.rename("latest-revised"),
        dropna=False,
    )


def classification_change_summary(
    point_in_time: pd.Series,
    latest_revised: pd.Series,
) -> pd.DataFrame:
    """Separate common-sample reclassification from availability transitions."""
    point_present = point_in_time.notna()
    latest_present = latest_revised.notna()
    common = point_present & latest_present
    changed = common & point_in_time.ne(latest_revised).fillna(False)
    denominator = int(common.sum())
    return pd.DataFrame(
        {
            "common_classified": [denominator],
            "reclassified": [int(changed.sum())],
            "reclassification_share": [
                float(changed.sum() / denominator) if denominator else float("nan")
            ],
            "point_only": [int((point_present & ~latest_present).sum())],
            "latest_only": [int((~point_present & latest_present).sum())],
            "neither_classified": [int((~point_present & ~latest_present).sum())],
        }
    )


def temporal_contrast_stability(
    labels: Mapping[int, ForwardReturnLabels],
    regimes: pd.Series,
    *,
    treated: str,
    reference: str,
) -> pd.DataFrame:
    """Report first/second-half and leave-one-episode-out primary contrast estimates."""
    primary = labels[PRIMARY_HORIZON]
    eligible = regimes.isin((treated, reference)) & primary.frame.notna().any(axis=1)
    masks = _temporal_stability_masks(regimes, eligible)
    rows: list[pd.DataFrame] = []
    for name, raw_mask in masks.items():
        mask = pd.Series(raw_mask, index=regimes.index)
        selected = regimes.where(mask)
        table = regime_contrast_statistics(
            {PRIMARY_HORIZON: primary},
            selected,
            treated=treated,
            reference=reference,
        )
        table.insert(0, "stability_sample", name)
        rows.append(table)
    return pd.concat(rows, ignore_index=True)


def temporal_factorial_stability(
    labels: Mapping[int, ForwardReturnLabels],
    focal_states: pd.Series,
    adjustment_states: pd.Series,
    *,
    treated: str,
    reference: str,
    adjustment_levels: tuple[str, str],
    assets: Sequence[str],
) -> pd.DataFrame:
    """Stress an exact primary factorial effect across time and focal-state episodes."""
    primary = labels[PRIMARY_HORIZON]
    joint_focal = focal_states.where(adjustment_states.isin(adjustment_levels))
    eligible = (
        joint_focal.isin((treated, reference))
        & primary.frame[list(assets)].notna().any(axis=1)
    )
    rows: list[pd.DataFrame] = []
    for name, raw_mask in _temporal_stability_masks(joint_focal, eligible).items():
        mask = pd.Series(raw_mask, index=focal_states.index)
        table = factorial_contrast_statistics(
            {PRIMARY_HORIZON: primary},
            focal_states.where(mask),
            adjustment_states.where(mask),
            treated=treated,
            reference=reference,
            adjustment_levels=adjustment_levels,
            assets=assets,
        )
        table.insert(0, "stability_sample", name)
        rows.append(table)
    return pd.concat(rows, ignore_index=True)


def temporal_revision_change_stability(
    labels: Mapping[int, ForwardReturnLabels],
    point_in_time: pd.Series,
    latest_revised: pd.Series,
    *,
    treated: str,
    reference: str,
    assets: Sequence[str],
) -> pd.DataFrame:
    """Stress the common-classified signed revision change across time and episodes."""
    selected_labels = combined_outcome_labels(labels, assets=assets)
    primary = selected_labels[PRIMARY_HORIZON]
    common = point_in_time.notna() & latest_revised.notna()
    episode_states = point_in_time.where(common)
    eligible = common & primary.frame.notna().any(axis=1)
    rows: list[pd.DataFrame] = []
    for name, raw_mask in _temporal_stability_masks(episode_states, eligible).items():
        mask = pd.Series(raw_mask, index=point_in_time.index)
        table = revision_contrast_change(
            {PRIMARY_HORIZON: primary},
            point_in_time.where(mask),
            latest_revised.where(mask),
            treated=treated,
            reference=reference,
            common_classified_only=True,
        )
        table.insert(0, "stability_sample", name)
        rows.append(table)
    return pd.concat(rows, ignore_index=True)


def _temporal_stability_masks(
    episode_states: pd.Series,
    eligible: pd.Series,
) -> dict[str, pd.Series | np.ndarray[Any, Any]]:
    dates = episode_states.index[eligible]
    midpoint = len(dates) // 2
    masks: dict[str, pd.Series | np.ndarray[Any, Any]] = {
        "first half": episode_states.index.isin(dates[:midpoint]),
        "second half": episode_states.index.isin(dates[midpoint:]),
    }
    episode_ids = _episode_ids(episode_states)
    for episode_id in sorted(episode_ids.dropna().unique()):
        masks[f"leave episode {int(episode_id)} out"] = episode_ids.ne(
            episode_id
        ).fillna(True)
    return masks


def _episode_ids(regimes: pd.Series) -> pd.Series:
    changed = regimes.ne(regimes.shift()) | regimes.isna() | regimes.shift().isna()
    identifiers = changed.cumsum().astype("Float64")
    return identifiers.where(regimes.notna())


def validate_study_outputs(
    prices: pd.DataFrame,
    point_in_time: FeaturePanel,
    labels: Mapping[int, ForwardReturnLabels],
    regimes: pd.Series,
    statistics: pd.DataFrame,
    *,
    expected_regimes: frozenset[str] | None = None,
    transformed: TransformResult | None = None,
) -> pd.DataFrame:
    """Fail live execution on empty, misaligned, or nonfinite study products."""
    observed_means = statistics["mean_return"].dropna()
    label_end_order = all(
        label.label_ends.dropna().gt(label.label_ends.dropna().index).all()
        for label in labels.values()
    )
    price_periods = prices.index.to_period("M")
    consecutive_periods = price_periods.equals(
        pd.period_range(price_periods.min(), price_periods.max(), freq="M")
    )
    exact_label_horizons = True
    for horizon, label in labels.items():
        ends = label.label_ends.dropna()
        starts = ends.index.to_period("M")
        exact_label_horizons = exact_label_horizons and bool(
            np.array_equal(
                ends.dt.to_period("M").to_numpy(),
                (starts + horizon).to_numpy(),
            )
        )
    terminal_horizons = all(
        label.frame.tail(horizon).isna().all(axis=None)
        for horizon, label in labels.items()
    )
    provenance_timing = _feature_panel_timing_is_valid(point_in_time)
    transform_timing = True if transformed is None else _transform_timing_is_valid(transformed)
    checks = {
        "positive prices": bool(prices.gt(0).all(axis=None)),
        "unique price index": bool(prices.index.is_unique),
        "ordered price index": bool(prices.index.is_monotonic_increasing),
        "consecutive price months": consecutive_periods,
        "complete provenance": len(point_in_time.provenance)
        == len(point_in_time.frame) * len(point_in_time.frame.columns),
        "causal source intervals": provenance_timing,
        "within-vintage transform timing": transform_timing,
        "separate label objects": len({id(label) for label in labels.values()}) == len(labels),
        "explicit horizons": set(labels) == set(HORIZONS)
        and all(label.horizon == horizon for horizon, label in labels.items()),
        "aligned label indexes": all(
            label.frame.index.equals(prices.index) for label in labels.values()
        ),
        "future label ends": label_end_order,
        "exact calendar label horizons": exact_label_horizons,
        "terminal labels remain missing": terminal_horizons,
        "at least two regimes": regimes.dropna().nunique() >= 2,
        "expected regime inventory": expected_regimes is None
        or set(regimes.dropna().unique()) == set(expected_regimes),
        "nonempty statistics": not statistics.empty,
        "finite observed means": not observed_means.empty
        and bool(np.isfinite(observed_means.to_numpy(dtype=float)).all()),
        "ordered confidence intervals": bool(
            statistics.dropna(subset=["ci_lower", "ci_upper"])["ci_lower"].le(
                statistics.dropna(subset=["ci_lower", "ci_upper"])["ci_upper"]
            ).all()
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise AssertionError(f"live study validation failed: {failed}")
    return pd.DataFrame.from_dict(checks, orient="index", columns=["passed"])


def assert_feature_panel_timing(point_in_time: FeaturePanel) -> None:
    """Require every matched feature row to satisfy its declared timing policy."""
    expected = len(point_in_time.frame) * len(point_in_time.frame.columns)
    has_coverage = all(
        point_in_time.frame[column].notna().any()
        for column in point_in_time.frame.columns
    )
    if (
        len(point_in_time.provenance) != expected
        or not has_coverage
        or not _feature_panel_timing_is_valid(point_in_time)
    ):
        raise AssertionError("feature panel violates its publication or staleness policy")


def _feature_panel_timing_is_valid(point_in_time: FeaturePanel) -> bool:
    matched = point_in_time.provenance["available_from"].notna()
    provenance = point_in_time.provenance.loc[matched]
    policies = {policy.name: policy for policy in point_in_time.policies}
    return all(
        row.available_from <= row.decision_date - policies[str(row.feature)].publication_lag
        and (
            pd.isna(row.available_through)
            or row.available_through
            >= row.decision_date - policies[str(row.feature)].publication_lag
        )
        and row.observation_date <= row.decision_date
        and row.matched_age <= policies[str(row.feature)].maximum_staleness
        for row in provenance.itertuples()
    )


def _transform_timing_is_valid(transformed: TransformResult) -> bool:
    point = transformed.provenance.loc[transformed.provenance["view"].eq("point-in-time")]
    present = point["available_from"].notna()
    rows = point.loc[present]
    return bool(
        rows["expected_period"].eq(rows["period_label"]).all()
        and rows["available_from"].le(rows["information_cutoff"]).all()
        and (
            rows["available_through"].isna()
            | rows["available_through"].ge(rows["information_cutoff"])
        ).all()
    )


def assert_component_periods_match(
    point_in_time: TransformResult,
    latest_revised: TransformResult,
) -> None:
    """Require revised diagnostics to use the real-time feature's exact source periods."""
    keys = ["decision_date", "feature", "component", "expected_period"]
    point_keys = point_in_time.provenance[keys].sort_values(keys).reset_index(drop=True)
    latest_keys = latest_revised.provenance[keys].sort_values(keys).reset_index(drop=True)
    if not point_keys.equals(latest_keys):
        raise AssertionError("latest-revised transform uses different source periods")
    merged = point_in_time.provenance[[*keys, "period_label"]].merge(
        latest_revised.provenance[[*keys, "period_label"]],
        on=keys,
        how="inner",
        suffixes=("_point", "_latest"),
        validate="one_to_one",
    )
    common = merged["period_label_point"].notna() & merged["period_label_latest"].notna()
    if not merged.loc[common, "period_label_point"].eq(
        merged.loc[common, "period_label_latest"]
    ).all():
        raise AssertionError("common transform components use different actual periods")


def component_availability_summary(
    point_in_time: TransformResult,
    latest_revised: TransformResult,
) -> pd.DataFrame:
    """Count component availability transitions separately from revision values."""
    keys = ["decision_date", "feature", "component", "expected_period"]
    merged = point_in_time.provenance[[*keys, "period_label"]].merge(
        latest_revised.provenance[[*keys, "period_label"]],
        on=keys,
        how="outer",
        suffixes=("_point", "_latest"),
        validate="one_to_one",
    )
    point_present = merged["period_label_point"].notna()
    latest_present = merged["period_label_latest"].notna()
    return pd.DataFrame(
        {
            "both_available": [int((point_present & latest_present).sum())],
            "point_only": [int((point_present & ~latest_present).sum())],
            "latest_only": [int((~point_present & latest_present).sum())],
            "neither_available": [int((~point_present & ~latest_present).sum())],
        }
    )


def assert_revision_change_identities(
    labels: Mapping[int, ForwardReturnLabels],
    regimes: pd.Series,
    *,
    treated: str,
    reference: str,
) -> None:
    """Check the revision estimator's zero-change identity on live outcomes."""
    unchanged = revision_contrast_change(
        labels,
        regimes,
        regimes,
        treated=treated,
        reference=reference,
    )
    finite = unchanged["revision_change"].dropna().to_numpy(dtype=float)
    errors = unchanged["hac_standard_error"].dropna().to_numpy(dtype=float)
    if not np.allclose(finite, 0.0, rtol=1e-12, atol=1e-12):
        raise AssertionError("identical classifications changed a revision contrast")
    if not np.allclose(errors, 0.0, rtol=1e-12, atol=1e-12):
        raise AssertionError("identical classifications have nonzero revision uncertainty")


def plot_coverage(
    market_provenance: pd.DataFrame,
    feature_provenance: pd.DataFrame,
) -> tuple[Figure, np.ndarray[Any, Any]]:
    """Plot market history and point-in-time macro matching coverage."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    market_provenance["daily_observations"].plot.bar(
        ax=axes[0],
        color=[ASSET_COLORS.get(symbol, "#8d99ae") for symbol in market_provenance.index],
    )
    axes[0].set(title="Acquired market-history depth", ylabel="Daily observations", xlabel="")
    feature_provenance["coverage"].plot.bar(ax=axes[1], color="#2a9d8f")
    axes[1].set(title="Point-in-time feature coverage", ylabel="Matched share", xlabel="")
    axes[1].set_ylim(0, 1.05)
    figure.tight_layout()
    return figure, axes


def plot_normalized_prices(prices: pd.DataFrame) -> tuple[Figure, Axes]:
    """Plot growth of one unit for every asset without implying a strategy."""
    normalized = prices.divide(prices.iloc[0])
    figure, axis = plt.subplots(figsize=(12, 5.5))
    line_styles = ("-", "--", "-.", ":")
    for position, asset in enumerate(normalized.columns):
        axis.plot(
            normalized.index,
            normalized[asset],
            label=f"{asset} — {ASSET_LABELS.get(str(asset), str(asset))}",
            color=ASSET_COLORS.get(str(asset), "#8d99ae"),
            linestyle=line_styles[position % len(line_styles)],
            linewidth=1.6,
        )
    axis.set(title="Asset context: normalized adjusted closes", ylabel="Growth of one unit")
    axis.legend(ncol=4)
    figure.tight_layout()
    return figure, axis


def plot_feature_comparison(
    point_in_time: pd.DataFrame,
    latest_revised: pd.DataFrame,
    columns: Sequence[str],
) -> tuple[Figure, np.ndarray[Any, Any]]:
    """Plot information-time and latest-revised feature paths side by side."""
    figure, axes = plt.subplots(len(columns), 1, figsize=(12, 3.6 * len(columns)), squeeze=False)
    for axis, column in zip(axes[:, 0], columns, strict=True):
        axis.plot(point_in_time.index, point_in_time[column], label="Point-in-time", linewidth=1.8)
        axis.plot(
            latest_revised.index,
            latest_revised[column],
            label="Latest-revised substitution",
            linewidth=1.2,
            linestyle="--",
            alpha=0.8,
        )
        axis.set(title=column, ylabel="Feature value")
        axis.legend()
    figure.tight_layout()
    return figure, axes


def plot_regime_timeline(
    feature: pd.Series,
    regimes: pd.Series,
    *,
    title: str,
    ylabel: str,
    boundaries: Sequence[float] = (),
) -> tuple[Figure, Axes]:
    """Plot a feature path with regime-colored decision markers."""
    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(feature.index, feature, color="#4a4a4a", linewidth=1.3, alpha=0.8)
    for regime in pd.unique(regimes.dropna()):
        color, marker = regime_style(str(regime))
        selected = regimes.eq(regime).fillna(False) & feature.notna()
        axis.scatter(
            feature.index[selected],
            feature[selected],
            s=22,
            label=str(regime),
            color=color,
            marker=marker,
        )
    for boundary in boundaries:
        axis.axhline(boundary, color="#333333", linewidth=0.9, linestyle="--")
    axis.set(title=title, ylabel=ylabel)
    axis.legend(ncol=3)
    figure.tight_layout()
    return figure, axis


def plot_regime_means(
    statistics: pd.DataFrame,
    *,
    horizon: int = PRIMARY_HORIZON,
    title: str = "Regime-conditioned forward returns",
) -> tuple[Figure, Axes]:
    """Plot conditional means and HAC confidence intervals for every asset."""
    selected = statistics.loc[statistics["horizon_months"].eq(horizon)].copy()
    regimes = tuple(selected["regime"].drop_duplicates())
    assets = tuple(selected["asset"].drop_duplicates())
    figure, axis = plt.subplots(figsize=(12, 5.5))
    width = 0.8 / max(len(regimes), 1)
    centers = np.arange(len(assets), dtype=float)
    for position, regime in enumerate(regimes):
        rows = selected.set_index(["regime", "asset"]).reindex(
            pd.MultiIndex.from_product([[regime], assets], names=["regime", "asset"])
        )
        means = rows["mean_return"].to_numpy(dtype=float)
        lower = means - rows["ci_lower"].to_numpy(dtype=float)
        upper = rows["ci_upper"].to_numpy(dtype=float) - means
        x_values = centers - 0.4 + width / 2 + position * width
        color, marker = regime_style(str(regime))
        axis.errorbar(
            x_values,
            means,
            yerr=np.vstack([lower, upper]),
            fmt=marker,
            capsize=3,
            label=regime,
            color=color,
        )
    axis.axhline(0, color="#333333", linewidth=0.9)
    axis.set(
        title=title,
        ylabel=f"{horizon}-month simple return",
        xticks=centers,
        xticklabels=[f"{asset}\n{ASSET_LABELS.get(asset, asset)}" for asset in assets],
    )
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.legend(ncol=3)
    figure.tight_layout()
    return figure, axis


def plot_regime_distributions(
    labels: ForwardReturnLabels,
    regimes: pd.Series,
    *,
    assets: Sequence[str],
    title: str,
) -> tuple[Figure, Axes]:
    """Plot conditional quartiles while retaining every tail point as a flier."""
    observed_regimes = tuple(pd.unique(regimes.dropna()))
    data: list[np.ndarray[Any, Any]] = []
    labels_text: list[str] = []
    colors: list[str] = []
    for asset in assets:
        for regime in observed_regimes:
            values = labels.frame[asset].where(regimes.eq(regime)).dropna().to_numpy(dtype=float)
            if len(values):
                data.append(values)
                labels_text.append(f"{asset}\n{regime}")
                colors.append(regime_style(str(regime))[0])
    figure, axis = plt.subplots(figsize=(max(12, len(data) * 0.75), 5.5))
    artists = axis.boxplot(data, tick_labels=labels_text, patch_artist=True, showfliers=True)
    for box, color in zip(artists["boxes"], colors, strict=True):
        box.set_facecolor(color)
        box.set_alpha(0.7)
    axis.axhline(0, color="#333333", linewidth=0.9)
    axis.set(title=title, ylabel="Forward simple return")
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.tick_params(axis="x", rotation=45)
    figure.tight_layout()
    return figure, axis


def plot_sample_sizes(
    statistics: pd.DataFrame,
    *,
    horizon: int = PRIMARY_HORIZON,
) -> tuple[Figure, np.ndarray[Any, Any]]:
    """Separate monthly outcome counts from contiguous macro episode counts."""
    selected = statistics.loc[statistics["horizon_months"].eq(horizon)]
    decisions = selected.groupby("regime", sort=False)["count"].min()
    episodes = selected.groupby("regime", sort=False)["episode_count"].min()
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    decision_colors = [regime_style(str(regime))[0] for regime in decisions.index]
    decisions.plot.bar(ax=axes[0], color=decision_colors)
    axes[0].set(title="Observed monthly outcomes", ylabel="Decision count", xlabel="")
    episodes.plot.bar(
        ax=axes[1],
        color=[regime_style(str(regime))[0] for regime in episodes.index],
    )
    axes[1].set(title="Contiguous macro episodes", ylabel="Episode count", xlabel="")
    figure.tight_layout()
    return figure, axes


def plot_sensitivity_heatmap(
    values: pd.DataFrame,
    *,
    title: str,
    color_label: str,
) -> tuple[Figure, Axes]:
    """Plot a complete parameter grid without selecting a preferred cell afterward."""
    figure, axis = plt.subplots(figsize=(8.5, 5.5))
    array = values.to_numpy(dtype=float)
    finite = np.abs(array[np.isfinite(array)])
    limit = float(finite.max()) if len(finite) else 1.0
    limit = max(limit, np.finfo(float).eps)
    image = axis.imshow(
        array,
        aspect="auto",
        cmap="coolwarm",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
    )
    axis.set(
        title=title,
        xticks=np.arange(len(values.columns)),
        xticklabels=[str(value) for value in values.columns],
        yticks=np.arange(len(values.index)),
        yticklabels=[str(value) for value in values.index],
    )
    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label(color_label)
    for row in range(array.shape[0]):
        for column in range(array.shape[1]):
            value = array[row, column]
            label = "below threshold" if not np.isfinite(value) else f"{value:.2%}"
            axis.text(column, row, label, ha="center", va="center", fontsize=8)
    figure.tight_layout()
    return figure, axis


def plot_regime_contrasts(
    contrasts: pd.DataFrame,
    *,
    title: str,
    horizon: int = PRIMARY_HORIZON,
) -> tuple[Figure, Axes]:
    """Plot primary treated-minus-reference contrasts with simultaneous intervals."""
    selected = contrasts.loc[contrasts["horizon_months"].eq(horizon)].copy()
    figure, axis = plt.subplots(figsize=(11, 5.2))
    positions = np.arange(len(selected))
    effect = selected["mean_difference"].to_numpy(dtype=float)
    lower = effect - selected["familywise_ci_lower"].to_numpy(dtype=float)
    upper = selected["familywise_ci_upper"].to_numpy(dtype=float) - effect
    colors = [
        "#2667ff" if sufficient else "#8d99ae"
        for sufficient in selected["meets_display_threshold"]
    ]
    for position, value, low, high, color in zip(
        positions, effect, lower, upper, colors, strict=True
    ):
        axis.errorbar(position, value, yerr=[[low], [high]], fmt="o", capsize=4, color=color)
    labels = []
    for asset in selected["asset"]:
        description = ASSET_LABELS.get(str(asset))
        labels.append(str(asset) if description is None else f"{asset}\n{description}")
    axis.axhline(0, color="#333333", linewidth=0.9)
    axis.set(title=title, ylabel="Treated minus reference mean return", xticks=positions)
    axis.set_xticklabels(labels)
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.text(
        1.0,
        -0.2,
        "Gray: below the predeclared display threshold",
        transform=axis.transAxes,
        ha="right",
        color="#666666",
        fontsize=9,
    )
    figure.tight_layout()
    return figure, axis


def plot_revision_gap(
    point_in_time: pd.Series,
    latest_revised: pd.Series,
    *,
    title: str,
) -> tuple[Figure, Axes]:
    """Plot the revision substitution gap while keeping it outside the feature set."""
    difference = latest_revised - point_in_time
    figure, axis = plt.subplots(figsize=(12, 4.8))
    axis.fill_between(difference.index, 0, difference.to_numpy(dtype=float), alpha=0.55)
    axis.axhline(0, color="#333333", linewidth=0.9)
    axis.set(title=title, ylabel="Latest minus point-in-time")
    figure.tight_layout()
    return figure, axis


def plot_revision_contrast_change(
    changes: pd.DataFrame,
    *,
    title: str,
) -> tuple[Figure, Axes]:
    """Plot the signed latest-minus-real-time change in one-month regime contrasts."""
    selected = changes.loc[changes["horizon_months"].eq(PRIMARY_HORIZON)].copy()
    positions = np.arange(len(selected))
    effect = selected["revision_change"].to_numpy(dtype=float)
    lower = effect - selected["familywise_ci_lower"].to_numpy(dtype=float)
    upper = selected["familywise_ci_upper"].to_numpy(dtype=float) - effect
    figure, axis = plt.subplots(figsize=(11, 5.2))
    colors = [
        "#6a4c93" if sufficient else "#8d99ae"
        for sufficient in selected["meets_display_threshold"]
    ]
    for position, value, low, high, color in zip(
        positions, effect, lower, upper, colors, strict=True
    ):
        axis.errorbar(
            position,
            value,
            yerr=[[low], [high]],
            fmt="D",
            capsize=4,
            color=color,
        )
    axis.axhline(0, color="#333333", linewidth=0.9)
    axis.set(
        title=title,
        ylabel="Latest-revised minus point-in-time contrast",
        xticks=positions,
        xticklabels=[str(asset) for asset in selected["asset"]],
    )
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.text(
        1.0,
        -0.2,
        "Gray: below the predeclared display threshold",
        transform=axis.transAxes,
        ha="right",
        color="#666666",
        fontsize=9,
    )
    figure.tight_layout()
    return figure, axis
