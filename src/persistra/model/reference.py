"""Normalized reference results and explicit catalog mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import numpy as np

from persistra.errors import DataValidationError
from persistra.model._frames import require_metadata_values, validate_frame

if TYPE_CHECKING:
    import pandas as pd

    from persistra.model.identity import Instrument, ProviderSymbol
    from persistra.model.market import ResultMetadata

SEARCH_DTYPES: dict[str, str] = {
    "provider_symbol": "string",
    "name": "string",
    "provider_type": "string",
    "region": "string",
    "market_open": "string",
    "market_close": "string",
    "timezone": "string",
    "currency": "string",
    "match_score": "float64",
}

MARKET_STATUS_DTYPES: dict[str, str] = {
    "market_type": "string",
    "region": "string",
    "primary_exchanges": "string",
    "local_open": "string",
    "local_close": "string",
    "current_status": "string",
    "notes": "string",
    "retrieved_at": "datetime64[ns, UTC]",
}

INDEX_CATALOG_DTYPES: dict[str, str] = {
    "provider_symbol": "string",
    "name": "string",
    "market": "string",
    "currency": "string",
    "provider_type": "string",
}


@dataclass(frozen=True, slots=True)
class InstrumentSearchResult:
    """Provider search matches without inferred canonical identity."""

    query: str
    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.query), str) or not self.query.strip():
            raise DataValidationError("query must not be empty")
        result = validate_frame(
            self.frame,
            SEARCH_DTYPES,
            validate_rows=_validate_scores,
            sort_by=["match_score", "provider_symbol"],
            unique_by=["provider_symbol", "region"],
        )
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class MarketStatusResult:
    """Provider market-status observations."""

    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        result = validate_frame(
            self.frame,
            MARKET_STATUS_DTYPES,
            validate_rows=lambda _frame: None,
            sort_by=["market_type", "region"],
            unique_by=["market_type", "region"],
        )
        require_metadata_values(result, retrieved_at=self.metadata.retrieved_at)
        object.__setattr__(self, "frame", result)


@dataclass(frozen=True, slots=True)
class IndexCatalogResult:
    """A normalized provider index catalog."""

    frame: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        result = validate_frame(
            self.frame,
            INDEX_CATALOG_DTYPES,
            validate_rows=lambda _frame: None,
            sort_by=["provider_symbol"],
            unique_by=["provider_symbol"],
        )
        object.__setattr__(self, "frame", result)


@dataclass(slots=True)
class Catalog:
    """An explicit in-memory instrument and provider-symbol catalog."""

    _instruments: dict[str, Instrument] = field(
        default_factory=lambda: cast("dict[str, Instrument]", {})
    )
    _provider_symbols: dict[tuple[str, str, str], ProviderSymbol] = field(
        default_factory=lambda: cast("dict[tuple[str, str, str], ProviderSymbol]", {})
    )

    def add_instrument(self, instrument: Instrument) -> None:
        """Add an instrument without replacing a populated identity."""
        existing = self._instruments.get(instrument.instrument_id)
        if existing is not None and existing != instrument:
            raise ValueError("instrument_id already identifies a different instrument")
        self._instruments[instrument.instrument_id] = instrument

    def map_provider_symbol(self, mapping: ProviderSymbol) -> None:
        """Register one explicit provider-symbol mapping."""
        if mapping.instrument_id not in self._instruments:
            raise ValueError("instrument must be added before a provider symbol")
        key = (mapping.provider, mapping.kind.value, mapping.symbol)
        existing = self._provider_symbols.get(key)
        if existing is not None and existing.instrument_id != mapping.instrument_id:
            raise ValueError("provider symbol already maps to another instrument")
        self._provider_symbols[key] = mapping

    def resolve(self, provider: str, kind: str, symbol: str) -> Instrument | None:
        """Resolve an explicit provider mapping when one exists."""
        mapping = self._provider_symbols.get((provider, kind, symbol))
        return None if mapping is None else self._instruments[mapping.instrument_id]


def _validate_scores(frame: pd.DataFrame) -> None:
    scores = frame["match_score"]
    if not np.isfinite(scores.to_numpy()).all() or ((scores < 0) | (scores > 1)).any():
        raise DataValidationError("match_score must be finite and between zero and one")
