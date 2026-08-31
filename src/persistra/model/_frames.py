"""Exact normalized frame contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from persistra.errors import DataValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


@dataclass(frozen=True, slots=True)
class FrameContract:
    """Authoritative structure and shared validation rules for one public frame."""

    name: str
    target: str
    dtypes: Mapping[str, str]
    required: tuple[str, ...]
    identity_key: tuple[str, ...]
    sort_by: tuple[str, ...]
    invariants: tuple[str, ...]


BAR_DTYPES: dict[str, str] = {
    "instrument_id": "string",
    "provider": "string",
    "provider_symbol": "string",
    "interval": "string",
    "date": "datetime64[ns]",
    "timestamp": "datetime64[ns, UTC]",
    "provider_timestamp_label": "string",
    "timestamp_position": "string",
    "source_timezone": "string",
    "session": "string",
    "price_adjustment": "string",
    "currency": "string",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "adjusted_close": "Float64",
    "volume": "Float64",
    "dividend_amount": "Float64",
    "split_coefficient": "Float64",
    "provider_as_of": "datetime64[ns, UTC]",
    "retrieved_at": "datetime64[ns, UTC]",
}

QUOTE_DTYPES: dict[str, str] = {
    "instrument_id": "string",
    "provider": "string",
    "provider_symbol": "string",
    "price": "float64",
    "open": "Float64",
    "high": "Float64",
    "low": "Float64",
    "previous_close": "Float64",
    "change": "Float64",
    "change_percent": "Float64",
    "volume": "Float64",
    "latest_trading_day": "datetime64[ns]",
    "observed_at": "datetime64[ns, UTC]",
    "entitlement": "string",
    "provider_as_of": "datetime64[ns, UTC]",
    "retrieved_at": "datetime64[ns, UTC]",
}

TOP_OF_BOOK_DTYPES: dict[str, str] = {
    "instrument_id": "string",
    "provider": "string",
    "provider_symbol": "string",
    "bid_price": "Float64",
    "bid_size": "Int64",
    "ask_price": "Float64",
    "ask_size": "Int64",
    "observed_at": "datetime64[ns, UTC]",
    "provider_as_of": "datetime64[ns, UTC]",
    "retrieved_at": "datetime64[ns, UTC]",
}

OPTION_CONTRACT_DTYPES: dict[str, str] = {
    "contract_id": "string",
    "provider": "string",
    "underlying_instrument_id": "string",
    "provider_symbol": "string",
    "expiration": "datetime64[ns]",
    "strike": "float64",
    "option_type": "string",
}

OPTION_OBSERVATION_DTYPES: dict[str, str] = {
    "contract_id": "string",
    "provider": "string",
    "chain_date": "datetime64[ns]",
    "last": "Float64",
    "mark": "Float64",
    "bid": "Float64",
    "bid_size": "Int64",
    "ask": "Float64",
    "ask_size": "Int64",
    "volume": "Int64",
    "open_interest": "Int64",
    "implied_volatility": "Float64",
    "delta": "Float64",
    "gamma": "Float64",
    "theta": "Float64",
    "vega": "Float64",
    "rho": "Float64",
    "provider_as_of": "datetime64[ns, UTC]",
    "retrieved_at": "datetime64[ns, UTC]",
}

SERIES_DTYPES: dict[str, str] = {
    "series_id": "string",
    "provider": "string",
    "provider_series": "string",
    "series_kind": "string",
    "frequency": "string",
    "period_label": "string",
    "period_start": "datetime64[ns]",
    "period_end": "datetime64[ns]",
    "value": "float64",
    "unit": "string",
    "geography": "string",
    "seasonal_adjustment": "string",
    "maturity": "string",
    "provider_as_of": "datetime64[ns, UTC]",
    "retrieved_at": "datetime64[ns, UTC]",
}

VINTAGE_SERIES_DTYPES: dict[str, str] = {
    "series_id": "string",
    "provider": "string",
    "provider_series": "string",
    "series_kind": "string",
    "frequency": "string",
    "period_label": "string",
    "period_start": "datetime64[ns]",
    "period_end": "datetime64[ns]",
    "available_from": "datetime64[ns]",
    "available_through": "datetime64[ns]",
    "value": "Float64",
    "is_deleted": "bool",
    "unit": "string",
    "geography": "string",
    "seasonal_adjustment": "string",
    "maturity": "string",
    "retrieved_at": "datetime64[ns, UTC]",
}

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

BAR_CONTRACT = FrameContract(
    name="bars",
    target="BarSet.frame",
    dtypes=BAR_DTYPES,
    required=(
        "instrument_id",
        "provider",
        "provider_symbol",
        "interval",
        "timestamp_position",
        "source_timezone",
        "session",
        "price_adjustment",
        "open",
        "high",
        "low",
        "close",
        "retrieved_at",
    ),
    identity_key=(
        "instrument_id",
        "interval",
        "price_adjustment",
        "session",
        "date",
        "timestamp",
    ),
    sort_by=(
        "instrument_id",
        "interval",
        "price_adjustment",
        "session",
        "date",
        "timestamp",
    ),
    invariants=(
        "positive-ohlc",
        "nonnegative-activity",
        "exactly-one-temporal-identity",
        "known-timestamp-position",
        "provider-label-for-unspecified-position",
        "ohlc-bounds",
        "instrument-scope",
        "metadata-scope",
    ),
)

QUOTE_CONTRACT = FrameContract(
    name="latest-quotes",
    target="QuoteSet.frame",
    dtypes=QUOTE_DTYPES,
    required=(
        "instrument_id",
        "provider",
        "provider_symbol",
        "price",
        "entitlement",
        "retrieved_at",
    ),
    identity_key=("provider", "provider_symbol"),
    sort_by=(),
    invariants=("positive-price", "finite-quote-fields", "nonnegative-volume", "metadata-scope"),
)

TOP_OF_BOOK_CONTRACT = FrameContract(
    name="top-of-book",
    target="TopOfBookSet.frame",
    dtypes=TOP_OF_BOOK_DTYPES,
    required=("instrument_id", "provider", "provider_symbol", "retrieved_at"),
    identity_key=("provider", "provider_symbol"),
    sort_by=(),
    invariants=(
        "nonnegative-quotes",
        "size-requires-price",
        "quote-state-diagnostics",
        "metadata-scope",
    ),
)

OPTION_CONTRACT_CONTRACT = FrameContract(
    name="option-contracts",
    target="OptionChain.contracts",
    dtypes=OPTION_CONTRACT_DTYPES,
    required=tuple(OPTION_CONTRACT_DTYPES),
    identity_key=("provider", "contract_id"),
    sort_by=("expiration", "strike", "option_type", "contract_id"),
    invariants=(
        "positive-strike",
        "known-option-type",
        "expiration-on-or-after-chain-date",
        "chain-scope",
        "metadata-scope",
    ),
)

OPTION_OBSERVATION_CONTRACT = FrameContract(
    name="option-observations",
    target="OptionChain.observations",
    dtypes=OPTION_OBSERVATION_DTYPES,
    required=("contract_id", "provider", "chain_date", "retrieved_at"),
    identity_key=("provider", "contract_id", "chain_date"),
    sort_by=("provider", "contract_id"),
    invariants=(
        "nonnegative-market-fields",
        "finite-greeks",
        "size-requires-price",
        "chain-date-scope",
        "contract-membership",
        "metadata-scope",
        "quote-state-diagnostics",
    ),
)

SERIES_CONTRACT = FrameContract(
    name="scalar-series",
    target="SeriesSet.frame",
    dtypes=SERIES_DTYPES,
    required=(
        "series_id",
        "provider",
        "provider_series",
        "series_kind",
        "frequency",
        "period_label",
        "retrieved_at",
    ),
    identity_key=("series_id", "frequency", "maturity", "period_label"),
    sort_by=("series_id", "frequency", "maturity", "period_label"),
    invariants=("finite-values-when-observed", "definition-scope", "metadata-scope"),
)

VINTAGE_SERIES_CONTRACT = FrameContract(
    name="vintage-scalar-series",
    target="VintageSeriesSet.frame",
    dtypes=VINTAGE_SERIES_DTYPES,
    required=(
        "series_id",
        "provider",
        "provider_series",
        "series_kind",
        "frequency",
        "period_label",
        "available_from",
        "is_deleted",
        "retrieved_at",
    ),
    identity_key=(
        "series_id",
        "frequency",
        "maturity",
        "period_label",
        "available_from",
    ),
    sort_by=(
        "series_id",
        "frequency",
        "maturity",
        "period_label",
        "available_from",
    ),
    invariants=(
        "finite-values-when-observed",
        "calendar-date-availability",
        "nonoverlapping-availability",
        "deleted-value-missing",
        "definition-scope",
        "metadata-scope",
    ),
)

SEARCH_CONTRACT = FrameContract(
    name="symbol-search",
    target="InstrumentSearchResult.frame",
    dtypes=SEARCH_DTYPES,
    required=("provider_symbol", "name", "provider_type", "match_score"),
    identity_key=("provider_symbol", "region"),
    sort_by=("match_score", "provider_symbol"),
    invariants=("normalized-finite-match-score",),
)

MARKET_STATUS_CONTRACT = FrameContract(
    name="market-status",
    target="MarketStatusResult.frame",
    dtypes=MARKET_STATUS_DTYPES,
    required=("market_type", "region", "current_status", "retrieved_at"),
    identity_key=("market_type", "region"),
    sort_by=("market_type", "region"),
    invariants=("metadata-scope",),
)

INDEX_CATALOG_CONTRACT = FrameContract(
    name="index-catalog",
    target="IndexCatalogResult.frame",
    dtypes=INDEX_CATALOG_DTYPES,
    required=("provider_symbol", "name", "provider_type"),
    identity_key=("provider_symbol",),
    sort_by=("provider_symbol",),
    invariants=(),
)

FRAME_CONTRACTS = (
    BAR_CONTRACT,
    QUOTE_CONTRACT,
    TOP_OF_BOOK_CONTRACT,
    OPTION_CONTRACT_CONTRACT,
    OPTION_OBSERVATION_CONTRACT,
    SERIES_CONTRACT,
    VINTAGE_SERIES_CONTRACT,
    SEARCH_CONTRACT,
    MARKET_STATUS_CONTRACT,
    INDEX_CATALOG_CONTRACT,
)


def empty_frame(dtypes: Mapping[str, str]) -> pd.DataFrame:
    """Build an empty frame with exact contract dtypes."""
    return pd.DataFrame({name: pd.Series(dtype=dtype) for name, dtype in dtypes.items()})


def typed_frame(data: Mapping[str, Any], dtypes: Mapping[str, str]) -> pd.DataFrame:
    """Build a frame and apply exact contract dtypes."""
    missing = set(dtypes).difference(data)
    extra = set(data).difference(dtypes)
    if missing or extra:
        difference = f"missing={sorted(missing)}, extra={sorted(extra)}"
        raise DataValidationError(f"frame fields differ: {difference}")
    columns = {
        name: pd.Series(data[name], dtype=dtype).reset_index(drop=True)
        for name, dtype in dtypes.items()
    }
    return pd.DataFrame(columns)


def validate_frame(
    frame: pd.DataFrame,
    contract: FrameContract,
    *,
    validate_rows: Callable[[pd.DataFrame], None],
) -> pd.DataFrame:
    """Copy and validate an exact normalized frame."""
    result = frame.copy(deep=True)
    dtypes = contract.dtypes
    if list(result.columns) != list(dtypes):
        raise DataValidationError(f"expected columns {list(dtypes)}, got {list(result.columns)}")
    wrong = {
        name: (str(result.dtypes[name]), dtype)
        for name, dtype in dtypes.items()
        if str(result.dtypes[name]) != dtype
    }
    if wrong:
        raise DataValidationError(f"incorrect dtypes: {wrong}")
    validate_rows(result)
    missing_required = [name for name in contract.required if result[name].isna().any()]
    if missing_required:
        raise DataValidationError(f"required values are missing: {missing_required}")
    identity_key = list(contract.identity_key)
    if result.duplicated(identity_key).any():
        raise DataValidationError(f"duplicate rows for key {identity_key}")
    sort_by = list(contract.sort_by)
    expected = result.sort_values(sort_by, kind="stable", na_position="last").reset_index(drop=True)
    if not result.reset_index(drop=True).equals(expected):
        raise DataValidationError(f"rows must sort by {sort_by}")
    return result.reset_index(drop=True)


def require_finite(frame: pd.DataFrame, columns: list[str], *, positive: bool = False) -> None:
    """Validate finite numeric values while allowing missing values."""
    for column in columns:
        values = frame[column].dropna().astype(float)
        if not np.isfinite(values).all():
            raise DataValidationError(f"{column} must contain finite values")
        if positive and (values <= 0).any():
            raise DataValidationError(f"{column} must contain positive values")


def require_nonnegative(frame: pd.DataFrame, columns: list[str]) -> None:
    """Validate nonnegative numeric values while allowing missing values."""
    require_finite(frame, columns)
    for column in columns:
        if (frame[column].dropna() < 0).any():
            raise DataValidationError(f"{column} must contain nonnegative values")


def require_scope_values(frame: pd.DataFrame, expected: Mapping[str, Any | None]) -> None:
    """Require every row to agree with its enclosing result scope."""
    for column, value in expected.items():
        matches = frame[column].isna() if value is None else frame[column].eq(value)
        if not matches.fillna(False).all():
            raise DataValidationError(f"{column} differs from its result scope")


def require_metadata_values(
    frame: pd.DataFrame,
    *,
    provider: str | None = None,
    retrieved_at: Any | None = None,
    entitlement: str | None = None,
) -> None:
    """Require row-level provenance to agree with result metadata."""
    expected = {
        "provider": provider,
        "retrieved_at": retrieved_at,
        "entitlement": entitlement,
    }
    for column, value in expected.items():
        if value is None or column not in frame:
            continue
        if not frame[column].eq(value).fillna(False).all():
            raise DataValidationError(f"{column} differs from result metadata")
