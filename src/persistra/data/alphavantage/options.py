"""Alpha Vantage historical U.S. options namespace."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.data.alphavantage._common import (
    AdapterContext,
    optional_float,
    optional_int,
    optional_text,
    parse_date,
    required_float,
    required_text,
    unknown_fields,
)
from persistra.errors import NoDataError, ResponseError
from persistra.model import InstrumentKind, OptionChain, SchemaDiagnostic, provider_instrument_id
from persistra.model._frames import (
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    typed_frame,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class OptionsNamespace:
    """Acquire historical option-chain observations."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def historical_chain(
        self,
        symbol: str,
        *,
        date: date | str | None = None,
        kind: InstrumentKind = InstrumentKind.EQUITY,
        refresh: bool = False,
        offline: bool = False,
    ) -> OptionChain:
        """Acquire one historical option chain without an underlying quote."""
        if not symbol:
            raise ValueError("symbol must not be empty")
        if kind not in {InstrumentKind.EQUITY, InstrumentKind.ETF}:
            raise ValueError("option underlying kind must be equity or ETF")
        requested_date = _coerce_date(date)
        parameters: dict[str, object] = {"symbol": symbol}
        if requested_date is not None:
            parameters["date"] = requested_date.isoformat()
        payload, raw = self._context.json(
            "HISTORICAL_OPTIONS", parameters, refresh=refresh, offline=offline
        )
        value = payload.get("data")
        if not isinstance(value, list):
            raise ResponseError("HISTORICAL_OPTIONS response has no data list")
        items = cast("list[Any]", value)
        if not all(isinstance(item, dict) for item in items):
            raise ResponseError("HISTORICAL_OPTIONS response has malformed rows")
        rows = cast("list[dict[str, Any]]", items)
        if not rows:
            raise NoDataError(f"no provider data for HISTORICAL_OPTIONS {symbol}")
        chain_date = requested_date or _response_date(payload, rows)
        underlying_id = provider_instrument_id("alpha_vantage", kind, symbol)
        contracts, observations, diagnostics = _parse_rows(
            rows,
            symbol=symbol,
            underlying_id=underlying_id,
            chain_date=chain_date,
            retrieved_at=raw.retrieved_at,
        )
        metadata = self._context.metadata(
            "HISTORICAL_OPTIONS", parameters, raw, diagnostics=diagnostics
        )
        return OptionChain(
            underlying_id,
            symbol,
            chain_date,
            contracts,
            observations,
            metadata,
        )

    def iter_historical_chains(
        self,
        symbol: str,
        *,
        start: date | str,
        end: date | str,
        kind: InstrumentKind = InstrumentKind.EQUITY,
        refresh: bool = False,
        offline: bool = False,
    ) -> Iterator[OptionChain]:
        """Yield successful chains for each calendar date in an inclusive range."""
        first = _coerce_date(start)
        last = _coerce_date(end)
        if first is None or last is None:
            raise ValueError("start and end are required")
        if first > last:
            raise ValueError("start must not follow end")
        current = first
        while current <= last:
            try:
                yield self.historical_chain(
                    symbol,
                    date=current,
                    kind=kind,
                    refresh=refresh,
                    offline=offline,
                )
            except NoDataError:
                pass
            current += timedelta(days=1)


def _parse_rows(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    underlying_id: str,
    chain_date: date,
    retrieved_at: date | Any,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[SchemaDiagnostic, ...]]:
    known = {
        "contractID",
        "contract_id",
        "symbol",
        "expiration",
        "strike",
        "type",
        "option_type",
        "last",
        "mark",
        "bid",
        "bid_size",
        "ask",
        "ask_size",
        "volume",
        "open_interest",
        "date",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
    }
    contracts: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    diagnostics: list[SchemaDiagnostic] = []
    for row in rows:
        diagnostics.extend(unknown_fields(row, known, context="option"))
        contract_id = required_text(row, "contractID", "contract_id")
        expiration = parse_date(required_text(row, "expiration"))
        if expiration is None:
            raise ResponseError("option expiration is missing")
        option_type = required_text(row, "type", "option_type").lower()
        contracts.append(
            {
                "contract_id": contract_id,
                "provider": "alpha_vantage",
                "underlying_instrument_id": underlying_id,
                "provider_symbol": optional_text(row, "symbol") or symbol,
                "expiration": expiration,
                "strike": required_float(row, "strike"),
                "option_type": option_type,
            }
        )
        row_date = parse_date(optional_text(row, "date")) or chain_date
        observations.append(
            {
                "contract_id": contract_id,
                "provider": "alpha_vantage",
                "chain_date": row_date,
                "last": optional_float(row, "last"),
                "mark": optional_float(row, "mark"),
                "bid": optional_float(row, "bid"),
                "bid_size": optional_int(row, "bid_size"),
                "ask": optional_float(row, "ask"),
                "ask_size": optional_int(row, "ask_size"),
                "volume": optional_int(row, "volume"),
                "open_interest": optional_int(row, "open_interest"),
                "implied_volatility": optional_float(row, "implied_volatility"),
                "delta": optional_float(row, "delta"),
                "gamma": optional_float(row, "gamma"),
                "theta": optional_float(row, "theta"),
                "vega": optional_float(row, "vega"),
                "rho": optional_float(row, "rho"),
                "provider_as_of": pd.NaT,
                "retrieved_at": retrieved_at,
            }
        )
    contract_values = {name: [row[name] for row in contracts] for name in OPTION_CONTRACT_DTYPES}
    observation_values = {
        name: [row[name] for row in observations] for name in OPTION_OBSERVATION_DTYPES
    }
    contract_frame = (
        typed_frame(contract_values, OPTION_CONTRACT_DTYPES)
        .sort_values(["expiration", "strike", "option_type", "contract_id"], kind="stable")
        .reset_index(drop=True)
    )
    observation_frame = (
        typed_frame(observation_values, OPTION_OBSERVATION_DTYPES)
        .sort_values(["provider", "contract_id"], kind="stable")
        .reset_index(drop=True)
    )
    return contract_frame, observation_frame, tuple(diagnostics)


def _response_date(payload: dict[str, Any], rows: list[dict[str, Any]]) -> date:
    candidates = {
        parsed
        for value in [payload.get("date"), *(row.get("date") for row in rows)]
        if (parsed := parse_date(None if value is None else str(value))) is not None
    }
    if len(candidates) != 1:
        raise ResponseError("historical option response has no single chain date")
    return candidates.pop()


def _coerce_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError("date must use YYYY-MM-DD")
    return parsed
