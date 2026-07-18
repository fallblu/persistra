"""Source-precedence policy grammar and winner resolution (spec 03 §12.4).

The installed policy kind is ``persistra.source_precedence.explicit_order@1``: an
explicit, complete, unique source priority list plus a closed tie-breaker grammar
that must be total for the dataset candidate key. Selection chooses the lowest
source priority and then applies the declared tie breakers; a residual unequal tie
is :data:`CONFLICT`, never insertion order. The winning source's head participates
even when it is a retraction, masking lower-priority providers for that key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from persistra.errors import SourcePrecedencePolicyError

if TYPE_CHECKING:
    from collections.abc import Callable

    from persistra.catalog.models import SourcePrecedencePolicy

POLICY_KIND = "persistra.source_precedence.explicit_order"
POLICY_KIND_VERSION = 1
CLOSED_TIE_BREAKERS = (
    "revision_ordinal_desc",
    "available_at_desc",
    "source_sequence_desc",
    "natural_key_content_id_asc",
    "canonical_revision_id_asc",
)
_TOTAL_TIE_BREAKER = "canonical_revision_id_asc"
CONFLICT = "conflict"


def validate_policy(policy: SourcePrecedencePolicy) -> None:
    """Validate an explicit-order policy's completeness, uniqueness, and totality."""
    if not policy.priorities:
        raise SourcePrecedencePolicyError("precedence policy requires at least one source")
    priorities = [entry.priority for entry in policy.priorities]
    if len(set(priorities)) != len(priorities):
        raise SourcePrecedencePolicyError("precedence priorities must be unique")
    sources = [entry.source for entry in policy.priorities]
    if len(set(sources)) != len(sources):
        raise SourcePrecedencePolicyError("precedence sources must be unique")
    if policy.retraction_action != "mask_lower_sources":
        raise SourcePrecedencePolicyError("only mask_lower_sources retraction action is installed")
    tie_breakers = policy.same_source_tie_breakers
    if not tie_breakers:
        raise SourcePrecedencePolicyError("precedence policy requires tie breakers")
    unknown = [name for name in tie_breakers if name not in CLOSED_TIE_BREAKERS]
    if unknown:
        raise SourcePrecedencePolicyError(f"unknown tie breakers: {unknown}")
    if len(set(tie_breakers)) != len(tie_breakers):
        raise SourcePrecedencePolicyError("tie breakers must not repeat")
    if _TOTAL_TIE_BREAKER not in tie_breakers:
        raise SourcePrecedencePolicyError(
            "tie-break sequence is not total for the dataset candidate key"
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """One per-source head row competing for a natural key."""

    source_id: str
    revision_ordinal: int
    available_at_key: str
    source_sequence: int
    natural_key_content_id: str
    canonical_revision_id: str
    is_retraction: bool


@dataclass(frozen=True, slots=True)
class WinnerDecision:
    """Result of resolving competing candidates for one natural key."""

    canonical_revision_id: str
    state: str  # "available", "retracted", or CONFLICT


def _descending_text(value: str) -> tuple[int, ...]:
    return tuple(-byte for byte in value.encode())


_TIE_BREAKER_KEY: dict[str, Callable[[Candidate], tuple[Any, ...]]] = {
    "revision_ordinal_desc": lambda c: (-c.revision_ordinal,),
    "available_at_desc": lambda c: (_descending_text(c.available_at_key),),
    "source_sequence_desc": lambda c: (-c.source_sequence,),
    "natural_key_content_id_asc": lambda c: (c.natural_key_content_id,),
    "canonical_revision_id_asc": lambda c: (c.canonical_revision_id,),
}


def resolve_winner(
    candidates: list[Candidate],
    *,
    priorities: dict[str, int],
    tie_breakers: tuple[str, ...],
) -> WinnerDecision | None:
    """Select the winning candidate for a natural key under the precedence policy.

    Returns ``None`` when no candidate's source is applicable. A residual tie under
    every declared tie breaker yields a :data:`CONFLICT` state.
    """
    eligible = [candidate for candidate in candidates if candidate.source_id in priorities]
    if not eligible:
        return None
    best_priority = min(priorities[candidate.source_id] for candidate in eligible)
    contenders = [
        candidate for candidate in eligible if priorities[candidate.source_id] == best_priority
    ]
    if len(contenders) == 1:
        winner = contenders[0]
        return WinnerDecision(
            winner.canonical_revision_id,
            "retracted" if winner.is_retraction else "available",
        )
    def _key(candidate: Candidate) -> tuple[Any, ...]:
        return tuple(_TIE_BREAKER_KEY[name](candidate) for name in tie_breakers)

    ordered = sorted(contenders, key=_key)
    first, second = ordered[0], ordered[1]
    first_key = _key(first)
    second_key = _key(second)
    if first_key == second_key:
        return WinnerDecision(first.canonical_revision_id, CONFLICT)
    return WinnerDecision(
        first.canonical_revision_id,
        "retracted" if first.is_retraction else "available",
    )
