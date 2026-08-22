"""Normalized reference results and explicit catalog mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import numpy as np

from persistra.errors import DataValidationError
from persistra.model._frames import (
    INDEX_CATALOG_CONTRACT,
    MARKET_STATUS_CONTRACT,
    SEARCH_CONTRACT,
    require_metadata_values,
    validate_frame,
)

if TYPE_CHECKING:
    import pandas as pd

    from persistra.model.identity import Instrument, ProviderSymbol
    from persistra.model.market import ResultMetadata

INDEX_CATALOG_DTYPES = cast("dict[str, str]", INDEX_CATALOG_CONTRACT.dtypes)
MARKET_STATUS_DTYPES = cast("dict[str, str]", MARKET_STATUS_CONTRACT.dtypes)
SEARCH_DTYPES = cast("dict[str, str]", SEARCH_CONTRACT.dtypes)

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
            SEARCH_CONTRACT,
            validate_rows=_validate_scores,
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
            MARKET_STATUS_CONTRACT,
            validate_rows=lambda _frame: None,
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
            INDEX_CATALOG_CONTRACT,
            validate_rows=lambda _frame: None,
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
