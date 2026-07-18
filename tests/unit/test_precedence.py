"""Source-precedence grammar validation and winner resolution (spec 03 §12.4)."""

from __future__ import annotations

import pytest

from persistra.catalog import DatasetRef, SourcePrecedencePolicy, SourcePriority, SourceRef
from persistra.catalog.precedence import (
    CONFLICT,
    Candidate,
    resolve_winner,
    validate_policy,
)
from persistra.domain import QualifiedName
from persistra.errors import SourcePrecedencePolicyError

_DATASET = DatasetRef(QualifiedName("example.daily_values"), 1)
_PRIMARY = SourceRef(QualifiedName("example.primary"), 1)
_SECONDARY = SourceRef(QualifiedName("example.secondary"), 1)


def _policy(**overrides: object) -> SourcePrecedencePolicy:
    base: dict[str, object] = {
        "name": QualifiedName("example.precedence"),
        "version": 1,
        "dataset": _DATASET,
        "priorities": (
            SourcePriority(_PRIMARY, 0),
            SourcePriority(_SECONDARY, 1),
        ),
    }
    base.update(overrides)
    return SourcePrecedencePolicy(**base)  # type: ignore[arg-type]


def _candidate(source: str, ordinal: int, revision: str, *, retraction: bool = False) -> Candidate:
    return Candidate(
        source_id=source,
        revision_ordinal=ordinal,
        available_at_key="2026-01-10T00:00:00+00:00",
        source_sequence=0 if source == "primary" else 1,
        natural_key_content_id="nk",
        canonical_revision_id=revision,
        is_retraction=retraction,
    )


def test_valid_policy_passes() -> None:
    validate_policy(_policy())


def test_empty_priorities_rejected() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(_policy(priorities=()))


def test_duplicate_priority_rejected() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(
            _policy(priorities=(SourcePriority(_PRIMARY, 0), SourcePriority(_SECONDARY, 0)))
        )


def test_duplicate_source_rejected() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(
            _policy(priorities=(SourcePriority(_PRIMARY, 0), SourcePriority(_PRIMARY, 1)))
        )


def test_tie_breakers_must_be_total() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(_policy(same_source_tie_breakers=("revision_ordinal_desc",)))


def test_unknown_tie_breaker_rejected() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(
            _policy(same_source_tie_breakers=("made_up_desc", "canonical_revision_id_asc"))
        )


def test_bad_retraction_action_rejected() -> None:
    with pytest.raises(SourcePrecedencePolicyError):
        validate_policy(_policy(retraction_action="coalesce"))


_TIE_BREAKERS = ("revision_ordinal_desc", "available_at_desc", "canonical_revision_id_asc")


def test_lowest_priority_source_wins() -> None:
    decision = resolve_winner(
        [_candidate("primary", 3, "rev-p"), _candidate("secondary", 9, "rev-s")],
        priorities={"primary": 0, "secondary": 1},
        tie_breakers=_TIE_BREAKERS,
    )
    assert decision is not None
    assert decision.canonical_revision_id == "rev-p"
    assert decision.state == "available"


def test_winning_retraction_masks_lower_sources() -> None:
    decision = resolve_winner(
        [
            _candidate("primary", 3, "rev-p", retraction=True),
            _candidate("secondary", 9, "rev-s"),
        ],
        priorities={"primary": 0, "secondary": 1},
        tie_breakers=_TIE_BREAKERS,
    )
    assert decision is not None
    assert decision.canonical_revision_id == "rev-p"
    assert decision.state == "retracted"


def test_inapplicable_sources_yield_no_winner() -> None:
    decision = resolve_winner(
        [_candidate("unknown", 1, "rev-u")],
        priorities={"primary": 0},
        tie_breakers=_TIE_BREAKERS,
    )
    assert decision is None


def test_equal_priority_resolved_by_tie_breaker() -> None:
    decision = resolve_winner(
        [_candidate("a", 1, "rev-low"), _candidate("b", 5, "rev-high")],
        priorities={"a": 0, "b": 0},
        tie_breakers=_TIE_BREAKERS,
    )
    assert decision is not None
    # revision_ordinal_desc prefers the higher ordinal.
    assert decision.canonical_revision_id == "rev-high"


def test_indistinguishable_candidates_conflict() -> None:
    left = Candidate("a", 1, "t", 0, "nk", "rev", False)
    right = Candidate("b", 1, "t", 0, "nk", "rev", False)
    decision = resolve_winner(
        [left, right], priorities={"a": 0, "b": 0}, tie_breakers=("canonical_revision_id_asc",)
    )
    assert decision is not None
    assert decision.state == CONFLICT
