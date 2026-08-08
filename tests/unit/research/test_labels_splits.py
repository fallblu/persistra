"""Tests for separate forward labels and leakage-safe temporal splits."""

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.research import (
    ForwardReturnLabels,
    TemporalSplit,
    expanding_window_splits,
    forward_returns,
    rolling_window_splits,
    validate_temporal_split,
)


def price_levels(periods: int = 12) -> pd.DataFrame:
    """Return deterministic positive daily levels."""
    index = pd.date_range("2025-01-01", periods=periods)
    return pd.DataFrame({"asset": np.arange(100.0, 100.0 + periods)}, index=index)


def test_forward_returns_keep_explicit_horizon_end_dates() -> None:
    levels = price_levels(5)

    result = forward_returns(levels, horizon=2)

    assert result.horizon == 2
    assert result.frame.iloc[0, 0] == pytest.approx(0.02)
    assert result.label_ends.iloc[0] == levels.index[2]
    assert result.frame.iloc[-2:].isna().all(axis=None)
    assert result.label_ends.iloc[-2:].isna().all()
    pd.testing.assert_frame_equal(levels, price_levels(5))


def test_forward_returns_validate_levels_and_index() -> None:
    with pytest.raises(ValueError, match="positive"):
        forward_returns(price_levels(), horizon=0)
    with pytest.raises(AnalysisError, match="positive"):
        forward_returns(
            pd.DataFrame({"x": [1.0, 0.0]}, index=pd.date_range("2025", periods=2)),
            horizon=1,
        )
    with pytest.raises(TypeError, match="DatetimeIndex"):
        forward_returns(pd.DataFrame({"x": [1.0, 2.0]}), horizon=1)
    valid = forward_returns(price_levels(), horizon=2)
    invalid_ends = valid.label_ends.shift(1)
    with pytest.raises(ValueError, match="explicit horizon"):
        ForwardReturnLabels(valid.frame, invalid_ends, horizon=2)


def test_expanding_splits_purge_boundary_labels_without_shuffling() -> None:
    labels = forward_returns(price_levels(14), horizon=2)

    splits = expanding_window_splits(
        labels,
        initial_train_size=5,
        evaluation_size=2,
    )

    assert len(splits) == 3
    assert splits[0].train_index.equals(labels.frame.index[:3])
    assert splits[0].purged_index.equals(labels.frame.index[3:5])
    assert splits[0].evaluation_index.equals(labels.frame.index[5:7])
    assert splits[1].train_index.equals(labels.frame.index[:5])
    for split in splits:
        validate_temporal_split(split, labels)


def test_rolling_splits_keep_a_fixed_candidate_window() -> None:
    labels = forward_returns(price_levels(), horizon=2)

    splits = rolling_window_splits(labels, train_size=5, evaluation_size=2)

    assert splits[1].train_index.equals(labels.frame.index[2:5])
    assert splits[1].purged_index.equals(labels.frame.index[5:7])
    assert splits[1].evaluation_index.equals(labels.frame.index[7:9])


def test_split_validation_rejects_temporal_leakage_and_bad_windows() -> None:
    labels = forward_returns(price_levels(), horizon=2)
    index = pd.DatetimeIndex(labels.frame.index)
    leaking = TemporalSplit(
        index[:5],
        index[5:7],
        index[:0],
    )
    with pytest.raises(AnalysisError, match="horizons overlap"):
        validate_temporal_split(leaking, labels)
    purged_overlap = TemporalSplit(index[:3], index[5:7], index[2:4])
    with pytest.raises(AnalysisError, match="purged observations"):
        validate_temporal_split(purged_overlap, labels)
    with pytest.raises(ValueError, match="overlap"):
        expanding_window_splits(
            labels,
            initial_train_size=5,
            evaluation_size=2,
            step=1,
        )
    with pytest.raises(ValueError, match="positive"):
        rolling_window_splits(labels, train_size=0, evaluation_size=2)
    short = forward_returns(price_levels(4), horizon=2)
    assert expanding_window_splits(short, initial_train_size=5, evaluation_size=1) == ()
