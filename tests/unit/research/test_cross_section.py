"""Tests for cross-sectional signal transforms."""

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.research import (
    clip_cross_section,
    neutralize_cross_section,
    rank_cross_section,
    standardize_cross_section,
)


def signal_panel() -> pd.DataFrame:
    """Return a small fixed-universe signal panel."""
    return pd.DataFrame(
        [[1.0, 2.0, 3.0, 100.0], [4.0, 4.0, np.nan, 4.0]],
        index=pd.date_range("2025-01-01", periods=2),
        columns=["a", "b", "c", "d"],
    )


def test_rank_clip_and_standardize_each_date_without_mutation() -> None:
    signals = signal_panel()

    ranked = rank_cross_section(signals)
    clipped = clip_cross_section(signals, lower_quantile=0.25, upper_quantile=0.75)
    standardized = standardize_cross_section(signals)

    assert ranked.iloc[0].tolist() == [0.25, 0.5, 0.75, 1.0]
    assert ranked.iloc[1].dropna().eq(2 / 3).all()
    assert clipped.iloc[0].tolist() == pytest.approx([1.75, 2.0, 3.0, 27.25])
    assert standardized.iloc[0].mean() == pytest.approx(0)
    assert standardized.iloc[0].std(ddof=0) == pytest.approx(1)
    assert standardized.iloc[1].isna().all()
    pd.testing.assert_frame_equal(signals, signal_panel())


def test_neutralization_removes_time_varying_groups_and_numeric_exposures() -> None:
    index = pd.date_range("2025-01-01", periods=2)
    columns = list("abcdef")
    exposures = pd.DataFrame(
        [[0.0, 1.0, 2.0, 0.0, 1.0, 2.0], [2.0, 1.0, 0.0, 2.0, 1.0, 0.0]],
        index=index,
        columns=columns,
    )
    groups = pd.DataFrame(
        [["x", "x", "x", "y", "y", "y"], ["x", "y", "x", "y", "x", "y"]],
        index=index,
        columns=columns,
    )
    group_effect = pd.DataFrame(
        [[0.0, 0.0, 0.0, 3.0, 3.0, 3.0], [0.0, 3.0, 0.0, 3.0, 0.0, 3.0]],
        index=index,
        columns=columns,
    )
    noise = pd.DataFrame(
        [[0.2, -0.4, 0.2, -0.1, 0.2, -0.1], [0.3, -0.2, -0.3, 0.2, 0.0, 0.0]],
        index=index,
        columns=columns,
    )
    signals = exposures.mul(2).add(group_effect).add(noise)

    result = neutralize_cross_section(signals, groups=groups, exposures={"size": exposures})

    for position in range(len(index)):
        residual = result.iloc[position]
        assert residual.mean() == pytest.approx(0, abs=1e-12)
        assert residual.corr(exposures.iloc[position]) == pytest.approx(0, abs=1e-12)
        for group in ("x", "y"):
            assert residual[groups.iloc[position].eq(group)].mean() == pytest.approx(0, abs=1e-12)


def test_cross_sectional_transforms_reject_ambiguous_or_misaligned_inputs() -> None:
    signals = signal_panel()
    with pytest.raises(ValueError, match="quantile bounds"):
        clip_cross_section(signals, lower_quantile=0.8, upper_quantile=0.2)
    with pytest.raises(ValueError, match="ddof"):
        standardize_cross_section(signals, ddof=-1)
    with pytest.raises(AnalysisError, match="infinite"):
        rank_cross_section(signals.replace(100, np.inf))
    with pytest.raises(ValueError, match="same index and columns"):
        neutralize_cross_section(signals, groups=signals.rename(columns={"a": "other"}))
    with pytest.raises(ValueError, match="columns must be unique"):
        rank_cross_section(signals.set_axis(["a", "a", "c", "d"], axis="columns"))
