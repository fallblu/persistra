"""Ordered expanding and rolling temporal research splits."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from persistra.errors import AnalysisError
from persistra.research.model import ForwardReturnLabels, TemporalSplit

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pandas as pd


def expanding_window_splits(
    labels: ForwardReturnLabels,
    *,
    initial_train_size: int,
    evaluation_size: int,
    step: int | None = None,
    embargo: int = 0,
) -> tuple[TemporalSplit, ...]:
    """Generate expanding splits with label purging and an observation-count embargo."""
    return tuple(
        _generate_splits(
            labels,
            train_size=initial_train_size,
            evaluation_size=evaluation_size,
            step=step,
            embargo=embargo,
            expanding=True,
        )
    )


def rolling_window_splits(
    labels: ForwardReturnLabels,
    *,
    train_size: int,
    evaluation_size: int,
    step: int | None = None,
    embargo: int = 0,
) -> tuple[TemporalSplit, ...]:
    """Generate rolling splits with label purging and an observation-count embargo."""
    return tuple(
        _generate_splits(
            labels,
            train_size=train_size,
            evaluation_size=evaluation_size,
            step=step,
            embargo=embargo,
            expanding=False,
        )
    )


def validate_temporal_split(split: TemporalSplit, labels: ForwardReturnLabels) -> None:
    """Reject observation or label-horizon leakage into an evaluation period."""
    if split.train_index.empty or split.evaluation_index.empty:
        raise AnalysisError("training and evaluation indexes must not be empty")
    if not split.train_index.isin(labels.frame.index).all() or not split.evaluation_index.isin(
        labels.frame.index
    ).all():
        raise AnalysisError("split indexes must belong to the labels")
    if split.train_index[-1] >= split.evaluation_index[0]:
        raise AnalysisError("training observations must precede evaluation observations")
    if split.train_index.intersection(split.evaluation_index).size:
        raise AnalysisError("training and evaluation observations must not overlap")
    if split.purged_index.intersection(split.train_index).size or split.purged_index.intersection(
        split.evaluation_index
    ).size:
        raise AnalysisError("purged observations must not belong to training or evaluation")
    if (
        split.embargoed_index.intersection(split.train_index).size
        or split.embargoed_index.intersection(split.evaluation_index).size
        or split.embargoed_index.intersection(split.purged_index).size
    ):
        raise AnalysisError("embargoed observations must be separate from the split")
    if not split.purged_index.isin(labels.frame.index).all():
        raise AnalysisError("purged indexes must belong to the labels")
    if not split.embargoed_index.isin(labels.frame.index).all():
        raise AnalysisError("embargoed indexes must belong to the labels")
    if not split.embargoed_index.empty and split.embargoed_index[-1] >= split.evaluation_index[0]:
        raise AnalysisError("embargoed observations must precede evaluation observations")
    train_ends = labels.label_ends.reindex(split.train_index)
    if train_ends.isna().any():
        raise AnalysisError("training label horizons must be complete")
    if train_ends.ge(split.evaluation_index[0]).any():
        raise AnalysisError("training label horizons overlap the evaluation period")
    evaluation_ends = labels.label_ends.reindex(split.evaluation_index)
    if evaluation_ends.isna().any():
        raise AnalysisError("evaluation label horizons must be complete")


def _generate_splits(
    labels: ForwardReturnLabels,
    *,
    train_size: int,
    evaluation_size: int,
    step: int | None,
    embargo: int,
    expanding: bool,
) -> Iterator[TemporalSplit]:
    _validate_sizes(train_size, evaluation_size, step, embargo)
    increment = evaluation_size if step is None else step
    index = cast("pd.DatetimeIndex", labels.frame.index)
    origin = train_size
    while origin + evaluation_size <= len(index):
        evaluation = index[origin : origin + evaluation_size]
        evaluation_ends = labels.label_ends.reindex(evaluation)
        if evaluation_ends.isna().any():
            break
        start = 0 if expanding else origin - train_size
        candidates = index[start:origin]
        candidate_ends = labels.label_ends.reindex(candidates)
        safe = candidate_ends.notna() & candidate_ends.lt(evaluation[0])
        eligible = candidates[safe.to_numpy()]
        purged = candidates[~safe.to_numpy()]
        embargoed = eligible[-embargo:] if embargo else eligible[:0]
        train = eligible[:-embargo] if embargo else eligible
        split = TemporalSplit(train, evaluation, purged, embargoed)
        validate_temporal_split(split, labels)
        yield split
        origin += increment


def _validate_sizes(
    train_size: int,
    evaluation_size: int,
    step: int | None,
    embargo: int,
) -> None:
    sizes = (train_size, evaluation_size, embargo)
    if any(isinstance(value, bool) for value in sizes) or (
        step is not None and isinstance(step, bool)
    ):
        raise ValueError("split sizes and embargo must be integers")
    if train_size <= 0 or evaluation_size <= 0:
        raise ValueError("train and evaluation sizes must be positive")
    if step is not None and step < evaluation_size:
        raise ValueError("step must not make evaluation periods overlap")
    if embargo < 0 or embargo >= train_size:
        raise ValueError("embargo must be nonnegative and smaller than the training window")
