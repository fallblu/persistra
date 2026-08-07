"""Alpha Vantage symbol-search and market-status namespace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_text,
    required_float,
    required_text,
    unknown_fields,
)
from persistra.errors import ResponseError
from persistra.model import InstrumentSearchResult, MarketStatusResult, SchemaDiagnostic
from persistra.model._frames import typed_frame
from persistra.model.reference import MARKET_STATUS_DTYPES, SEARCH_DTYPES

if TYPE_CHECKING:
    import pandas as pd


class ReferenceNamespace:
    """Acquire provider search matches and market status."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def search(
        self,
        keywords: str,
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> InstrumentSearchResult:
        """Search provider symbols without inferring canonical identity."""
        if not keywords.strip():
            raise ValueError("keywords must not be empty")
        parameters = {"keywords": keywords}
        payload, raw = self._context.json(
            "SYMBOL_SEARCH", parameters, refresh=refresh, offline=offline
        )
        value = payload.get("bestMatches")
        if not isinstance(value, list):
            raise ResponseError("SYMBOL_SEARCH response has no bestMatches list")
        items = cast("list[Any]", value)
        if not all(isinstance(row, dict) for row in items):
            raise ResponseError("SYMBOL_SEARCH response has malformed matches")
        rows = cast("list[dict[str, Any]]", items)
        diagnostics: list[SchemaDiagnostic] = []
        output: list[dict[str, Any]] = []
        known = {
            "1. symbol",
            "2. name",
            "3. type",
            "4. region",
            "5. marketOpen",
            "6. marketClose",
            "7. timezone",
            "8. currency",
            "9. matchScore",
        }
        for row in rows:
            diagnostics.extend(unknown_fields(row, known, context="search"))
            output.append(
                {
                    "provider_symbol": required_text(row, "1. symbol"),
                    "name": required_text(row, "2. name"),
                    "provider_type": required_text(row, "3. type"),
                    "region": optional_text(row, "4. region"),
                    "market_open": optional_text(row, "5. marketOpen"),
                    "market_close": optional_text(row, "6. marketClose"),
                    "timezone": optional_text(row, "7. timezone"),
                    "currency": optional_text(row, "8. currency"),
                    "match_score": required_float(row, "9. matchScore"),
                }
            )
        frame = _frame(output, SEARCH_DTYPES, ["match_score", "provider_symbol"])
        metadata = self._context.metadata(
            "SYMBOL_SEARCH", parameters, raw, diagnostics=tuple(diagnostics)
        )
        return InstrumentSearchResult(keywords, frame, metadata)

    def market_status(self, *, refresh: bool = False, offline: bool = False) -> MarketStatusResult:
        """Acquire market status without inferring exchange calendars."""
        payload, raw = self._context.json(
            "MARKET_STATUS", {}, cache_age=None, refresh=refresh, offline=offline
        )
        value = payload.get("markets")
        if not isinstance(value, list):
            raise ResponseError("MARKET_STATUS response has no markets list")
        items = cast("list[Any]", value)
        if not all(isinstance(row, dict) for row in items):
            raise ResponseError("MARKET_STATUS response has malformed markets")
        rows = cast("list[dict[str, Any]]", items)
        diagnostics: list[SchemaDiagnostic] = []
        output: list[dict[str, Any]] = []
        known = {
            "market_type",
            "region",
            "primary_exchanges",
            "local_open",
            "local_close",
            "current_status",
            "notes",
        }
        for row in rows:
            diagnostics.extend(unknown_fields(row, known, context="market-status"))
            output.append(
                {
                    "market_type": required_text(row, "market_type"),
                    "region": required_text(row, "region"),
                    "primary_exchanges": optional_text(row, "primary_exchanges"),
                    "local_open": optional_text(row, "local_open"),
                    "local_close": optional_text(row, "local_close"),
                    "current_status": required_text(row, "current_status"),
                    "notes": optional_text(row, "notes"),
                    "retrieved_at": raw.retrieved_at,
                }
            )
        frame = _frame(output, MARKET_STATUS_DTYPES, ["market_type", "region"])
        metadata = self._context.metadata("MARKET_STATUS", {}, raw, diagnostics=tuple(diagnostics))
        return MarketStatusResult(frame, metadata)


def _frame(rows: list[dict[str, Any]], dtypes: dict[str, str], sort_by: list[str]) -> pd.DataFrame:
    values = {name: [row[name] for row in rows] for name in dtypes}
    return typed_frame(values, dtypes).sort_values(sort_by, kind="stable").reset_index(drop=True)
