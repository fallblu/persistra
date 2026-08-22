"""Tests for point-in-time investable universes."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from persistra.research import (
    DelistingPolicy,
    MissingMembershipPolicy,
    UniverseMembership,
    align_universe,
    apply_universe,
    create_research_manifest,
    forward_returns,
    information_coefficients,
)


def _universe() -> UniverseMembership:
    retrieved = datetime(2026, 8, 22, tzinfo=UTC)
    return UniverseMembership(
        "us-demo-history",
        pd.DataFrame(
            [
                ("A", "2024-01-01", "2024-01-02", "included", "committee", "2023-12-31", retrieved),
                ("A", "2024-01-03", None, "excluded", "committee", "2024-01-02", retrieved),
                ("B", "2024-01-02", None, "included", "committee", "2024-01-01", retrieved),
                ("C", "2024-01-01", "2024-01-01", "included", "listing", "2023-12-31", retrieved),
                ("C", "2024-01-02", None, "delisted", "listing", "2024-01-02", retrieved),
            ],
            columns=[
                "asset_id",
                "valid_from",
                "valid_through",
                "state",
                "source",
                "source_as_of",
                "retrieved_at",
            ],
        ),
    )


def test_alignment_uses_exact_intervals_without_survivorship_fill() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    mask = align_universe(
        _universe(),
        dates,
        ["A", "B", "C"],
        missing=MissingMembershipPolicy.EXCLUDE,
    )

    expected = pd.DataFrame(
        [[True, False, True], [True, True, False], [False, True, False]],
        index=dates,
        columns=["A", "B", "C"],
    )
    assert mask.equals(expected)


def test_missing_history_and_delisting_policies_are_explicit() -> None:
    with pytest.raises(ValueError, match="membership is missing for B"):
        align_universe(_universe(), pd.DatetimeIndex(["2024-01-01"]), ["B"])
    with pytest.raises(ValueError, match="C is delisted"):
        align_universe(
            _universe(),
            pd.DatetimeIndex(["2024-01-02"]),
            ["C"],
            delistings=DelistingPolicy.ERROR,
        )


def test_masked_panels_feed_labels_evaluation_and_portfolio_inputs() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    levels = pd.DataFrame(
        {"A": [100.0, 101.0, 102.0], "B": [50.0, 51.0, 52.0], "C": [20.0, 21.0, 22.0]},
        index=dates,
    )
    masked = apply_universe(levels, _universe(), missing=MissingMembershipPolicy.EXCLUDE)
    labels = forward_returns(masked, horizon=1)
    signals = masked.pct_change(fill_method=None).replace(0.0, np.nan)
    result = information_coefficients(signals, labels, minimum_count=2)

    assert pd.isna(masked.loc[dates[0], "B"])
    assert pd.isna(masked.loc[dates[1], "C"])
    assert labels.frame.loc[dates[0], "B"] != labels.frame.loc[dates[0], "B"]
    assert result.statistics["count"].max() <= 2


def test_universe_identity_is_stable_and_manifest_ready() -> None:
    universe = _universe()
    copied = UniverseMembership(universe.universe_id, universe.frame)
    scope = universe.dataset_scope()
    manifest = create_research_manifest(
        [scope],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        environment={"persistra": "4"},
        include_runtime=False,
    )

    assert copied.content_identity == universe.content_identity
    assert manifest.datasets[0].scope["universe_id"] == universe.universe_id
    assert manifest.datasets[0].content_identity == universe.content_identity


def test_membership_rejects_overlapping_intervals() -> None:
    frame = _universe().frame.iloc[[0, 1]].copy()
    frame.loc[1, "valid_from"] = pd.Timestamp("2024-01-02")
    with pytest.raises(ValueError, match="must not overlap"):
        UniverseMembership("overlap", frame)
