"""Ordered expanding and rolling temporal research splits."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.research.model import ForwardReturnLabels, NestedTemporalSplit, TemporalSplit

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


def nested_expanding_window_splits(
    labels: ForwardReturnLabels,
    *,
    outer_initial_train_size: int,
    outer_evaluation_size: int,
    inner_initial_train_size: int,
    inner_evaluation_size: int,
    outer_step: int | None = None,
    inner_step: int | None = None,
    outer_embargo: int = 0,
    inner_embargo: int = 0,
) -> tuple[NestedTemporalSplit, ...]:
    """Generate expanding outer and inner splits for unbiased model selection."""
    return _nested_splits(
        labels,
        outer_train_size=outer_initial_train_size,
        outer_evaluation_size=outer_evaluation_size,
        inner_train_size=inner_initial_train_size,
        inner_evaluation_size=inner_evaluation_size,
        outer_step=outer_step,
        inner_step=inner_step,
        outer_embargo=outer_embargo,
        inner_embargo=inner_embargo,
        outer_expanding=True,
        inner_expanding=True,
    )


def nested_rolling_window_splits(
    labels: ForwardReturnLabels,
    *,
    outer_train_size: int,
    outer_evaluation_size: int,
    inner_train_size: int,
    inner_evaluation_size: int,
    outer_step: int | None = None,
    inner_step: int | None = None,
    outer_embargo: int = 0,
    inner_embargo: int = 0,
) -> tuple[NestedTemporalSplit, ...]:
    """Generate rolling outer and inner splits for unbiased model selection."""
    return _nested_splits(
        labels,
        outer_train_size=outer_train_size,
        outer_evaluation_size=outer_evaluation_size,
        inner_train_size=inner_train_size,
        inner_evaluation_size=inner_evaluation_size,
        outer_step=outer_step,
        inner_step=inner_step,
        outer_embargo=outer_embargo,
        inner_embargo=inner_embargo,
        outer_expanding=False,
        inner_expanding=False,
    )


def validate_nested_temporal_split(split: NestedTemporalSplit, labels: ForwardReturnLabels) -> None:
    """Reject inner leakage outside the outer training observations."""
    validate_temporal_split(split.outer, labels)
    allowed = split.outer.train_index
    for inner in split.inner:
        validate_temporal_split(inner, labels)
        retained = inner.train_index.union(inner.evaluation_index)
        retained = retained.union(inner.purged_index).union(inner.embargoed_index)
        if not retained.isin(allowed).all():
            raise AnalysisError("inner split observations must belong to outer training")
        if inner.evaluation_index.intersection(split.outer.evaluation_index).size:
            raise AnalysisError("inner evaluation must not reuse outer evaluation")


def _nested_splits(
    labels: ForwardReturnLabels,
    *,
    outer_train_size: int,
    outer_evaluation_size: int,
    inner_train_size: int,
    inner_evaluation_size: int,
    outer_step: int | None,
    inner_step: int | None,
    outer_embargo: int,
    inner_embargo: int,
    outer_expanding: bool,
    inner_expanding: bool,
) -> tuple[NestedTemporalSplit, ...]:
    outer_splits = tuple(
        _generate_splits(
            labels,
            train_size=outer_train_size,
            evaluation_size=outer_evaluation_size,
            step=outer_step,
            embargo=outer_embargo,
            expanding=outer_expanding,
        )
    )
    results: list[NestedTemporalSplit] = []
    for outer in outer_splits:
        inner = tuple(
            _generate_splits(
                labels,
                train_size=inner_train_size,
                evaluation_size=inner_evaluation_size,
                step=inner_step,
                embargo=inner_embargo,
                expanding=inner_expanding,
                index=outer.train_index,
            )
        )
        if not inner:
            raise AnalysisError("outer training window cannot produce an inner split")
        nested = NestedTemporalSplit(
            outer,
            inner,
            "expanding" if outer_expanding else "rolling",
            "expanding" if inner_expanding else "rolling",
        )
        validate_nested_temporal_split(nested, labels)
        results.append(nested)
    return tuple(results)


def validate_temporal_split(split: TemporalSplit, labels: ForwardReturnLabels) -> None:
    """Reject observation or label-horizon leakage into an evaluation period."""
    if split.train_index.empty or split.evaluation_index.empty:
        raise AnalysisError("training and evaluation indexes must not be empty")
    if (
        not split.train_index.isin(labels.frame.index).all()
        or not split.evaluation_index.isin(labels.frame.index).all()
    ):
        raise AnalysisError("split indexes must belong to the labels")
    if split.train_index[-1] >= split.evaluation_index[0]:
        raise AnalysisError("training observations must precede evaluation observations")
    if split.train_index.intersection(split.evaluation_index).size:
        raise AnalysisError("training and evaluation observations must not overlap")
    if (
        split.purged_index.intersection(split.train_index).size
        or split.purged_index.intersection(split.evaluation_index).size
    ):
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
    index: pd.DatetimeIndex | None = None,
) -> Iterator[TemporalSplit]:
    train_size, evaluation_size, step, embargo = _validate_sizes(
        train_size, evaluation_size, step, embargo
    )
    increment = evaluation_size if step is None else step
    selected_index = cast("pd.DatetimeIndex", labels.frame.index) if index is None else index
    origin = train_size
    while origin + evaluation_size <= len(selected_index):
        evaluation = selected_index[origin : origin + evaluation_size]
        evaluation_ends = labels.label_ends.reindex(evaluation)
        if evaluation_ends.isna().any():
            break
        start = 0 if expanding else origin - train_size
        candidates = selected_index[start:origin]
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
) -> tuple[int, int, int | None, int]:
    checked_train = require_integer(train_size, name="train_size", minimum=1)
    checked_evaluation = require_integer(evaluation_size, name="evaluation_size", minimum=1)
    checked_step = None if step is None else require_integer(step, name="step", minimum=1)
    checked_embargo = require_integer(embargo, name="embargo", minimum=0)
    if checked_step is not None and checked_step < checked_evaluation:
        raise ValueError("step must not make evaluation periods overlap")
    if checked_embargo >= checked_train:
        raise ValueError("embargo must be nonnegative and smaller than the training window")
    return checked_train, checked_evaluation, checked_step, checked_embargo
