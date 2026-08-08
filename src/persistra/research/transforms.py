"""Cross-sectional transforms for explicit fixed-universe signal panels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from persistra.research._validation import aligned_panel, cross_sectional_frame, numeric_frame

if TYPE_CHECKING:
    from collections.abc import Mapping

RankMethod = Literal["average", "min", "max", "first", "dense"]


def rank_cross_section(
    signals: pd.DataFrame,
    *,
    method: RankMethod = "average",
    percentile: bool = True,
    ascending: bool = True,
) -> pd.DataFrame:
    """Rank each date across the panel's explicit asset columns."""
    data = cross_sectional_frame(signals, name="signal")
    if method not in {"average", "min", "max", "first", "dense"}:
        raise ValueError("unsupported rank method")
    return data.rank(axis="columns", method=method, pct=percentile, ascending=ascending)


def clip_cross_section(
    signals: pd.DataFrame,
    *,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> pd.DataFrame:
    """Clip each date to explicit cross-sectional quantile bounds."""
    data = cross_sectional_frame(signals, name="signal")
    if not 0 <= lower_quantile <= upper_quantile <= 1:
        raise ValueError("quantile bounds must satisfy 0 <= lower <= upper <= 1")
    lower = data.quantile(lower_quantile, axis="columns")
    upper = data.quantile(upper_quantile, axis="columns")
    return data.clip(lower=lower, upper=upper, axis="index")


def standardize_cross_section(signals: pd.DataFrame, *, ddof: int = 0) -> pd.DataFrame:
    """Center and scale each date across available assets."""
    data = cross_sectional_frame(signals, name="signal")
    if isinstance(ddof, bool) or ddof < 0:
        raise ValueError("ddof must be a nonnegative integer")
    means = data.mean(axis="columns")
    deviations = data.std(axis="columns", ddof=ddof).replace(0, np.nan)
    return data.sub(means, axis="index").div(deviations, axis="index")


def neutralize_cross_section(
    signals: pd.DataFrame,
    *,
    groups: pd.DataFrame | None = None,
    exposures: Mapping[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Return per-date residuals after group and numeric exposure controls.

    The regression includes an intercept. A time-varying group panel contributes fixed effects,
    and each named exposure contributes one numeric regressor. Rows without enough complete
    observations to estimate the requested controls remain missing.
    """
    data = cross_sectional_frame(signals, name="signal")
    classifications = None if groups is None else aligned_panel(groups, data, name="groups")
    controls: dict[str, pd.DataFrame] = {}
    requested_controls: Mapping[str, pd.DataFrame] = {} if exposures is None else exposures
    for name, frame in requested_controls.items():
        if not name:
            raise ValueError("exposure names must not be empty")
        aligned = aligned_panel(frame, data, name=f"exposure {name}")
        controls[name] = numeric_frame(aligned)

    result = pd.DataFrame(np.nan, index=data.index, columns=data.columns, dtype=float)
    for position in range(len(data.index)):
        values = data.iloc[position]
        group_row = (
            None if classifications is None else classifications.iloc[position]
        )
        exposure_rows = {
            name: frame.iloc[position] for name, frame in controls.items()
        }
        result.iloc[position] = _neutralize_row(values, group_row, exposure_rows)
    return result


def _neutralize_row(
    values: pd.Series,
    groups: pd.Series | None,
    exposures: Mapping[str, pd.Series],
) -> pd.Series:
    valid = values.notna()
    if groups is not None:
        valid &= groups.notna()
    for exposure in exposures.values():
        valid &= exposure.notna()
    output = pd.Series(np.nan, index=values.index, dtype=float)
    if not valid.any():
        return output

    design_parts = [np.ones((int(valid.sum()), 1), dtype=float)]
    if groups is not None:
        labels = groups.loc[valid]
        indicators = pd.get_dummies(labels, dtype=float)
        if indicators.shape[1] > 1:
            design_parts.append(indicators.iloc[:, 1:].to_numpy(dtype=float))
    for exposure in exposures.values():
        design_parts.append(exposure.loc[valid].to_numpy(dtype=float).reshape(-1, 1))
    design = np.concatenate(design_parts, axis=1)
    if design.shape[0] <= design.shape[1] or np.linalg.matrix_rank(design) < design.shape[1]:
        return output
    observations = values.loc[valid].to_numpy(dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(design, observations, rcond=None)
    output.loc[valid] = observations - design @ coefficients
    return output
