"""Shared normalized bid-ask quote rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pandas as pd

    from persistra.model.market import ResultMetadata


@dataclass(frozen=True, slots=True)
class QuoteState:
    """One bid-ask pair used to derive nonfatal state diagnostics."""

    identity: str
    bid: Any
    ask: Any
    context: str


def require_sizes_have_prices(
    frame: pd.DataFrame,
    *,
    bid_price: str,
    bid_size: str,
    ask_price: str,
    ask_size: str,
) -> None:
    """Reject a quoted size when the corresponding price is missing."""
    from persistra.errors import DataValidationError

    for price, size in ((bid_price, bid_size), (ask_price, ask_size)):
        if (frame[size].notna() & frame[price].isna()).any():
            raise DataValidationError(f"{size} requires {price}")


def with_quote_diagnostics(
    metadata: ResultMetadata,
    states: Iterable[QuoteState],
) -> ResultMetadata:
    """Add deterministic locked and crossed quote diagnostics."""
    import pandas as pd

    from persistra.model.market import SchemaDiagnostic

    existing = {(item.field, item.message) for item in metadata.diagnostics}
    additions: list[SchemaDiagnostic] = []
    for quote in states:
        if pd.isna(quote.bid) or pd.isna(quote.ask) or quote.bid < quote.ask:
            continue
        state = "crossed" if quote.bid > quote.ask else "locked"
        diagnostic = SchemaDiagnostic(
            "bid_ask",
            f"{quote.identity}: {state} {quote.context}",
        )
        key = (diagnostic.field, diagnostic.message)
        if key not in existing:
            additions.append(diagnostic)
            existing.add(key)
    if not additions:
        return metadata
    return replace(metadata, diagnostics=(*metadata.diagnostics, *additions))
