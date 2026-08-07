"""Analysis of observed historical option chains."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError
from persistra.model import OptionChain, OptionType

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date


def filter_chain(
    chain: OptionChain,
    *,
    expiration: date | None = None,
    option_type: OptionType | str | None = None,
    minimum_strike: float | None = None,
    maximum_strike: float | None = None,
    contract_ids: Iterable[str] | None = None,
) -> OptionChain:
    """Return a chain restricted by explicit contract terms."""
    if minimum_strike is not None and maximum_strike is not None:
        if minimum_strike > maximum_strike:
            raise ValueError("minimum_strike must not exceed maximum_strike")
    contracts = chain.contracts.copy(deep=True)
    selected = pd.Series(True, index=contracts.index)
    if expiration is not None:
        selected &= contracts["expiration"].dt.date == expiration
    if option_type is not None:
        selected &= contracts["option_type"] == OptionType(option_type).value
    if minimum_strike is not None:
        selected &= contracts["strike"] >= minimum_strike
    if maximum_strike is not None:
        selected &= contracts["strike"] <= maximum_strike
    if contract_ids is not None:
        selected &= contracts["contract_id"].isin(set(contract_ids))
    contracts = contracts.loc[selected].reset_index(drop=True)
    observations = chain.observations[
        chain.observations["contract_id"].isin(contracts["contract_id"])
    ].copy(deep=True)
    return OptionChain(
        chain.underlying_instrument_id,
        chain.provider_symbol,
        chain.chain_date,
        contracts,
        observations.reset_index(drop=True),
        chain.metadata,
    )


def days_to_expiration(chain: OptionChain) -> pd.DataFrame:
    """Calculate whole calendar days from chain date to expiration."""
    result = chain.contracts[["contract_id", "expiration"]].copy()
    result["days_to_expiration"] = (
        result["expiration"] - pd.Timestamp(chain.chain_date)
    ).dt.days.astype("Int64")
    return result


def moneyness(chain: OptionChain, *, underlying_price: float) -> pd.DataFrame:
    """Calculate spot divided by strike for each observed contract."""
    price = _positive_price(underlying_price)
    result = chain.contracts[["contract_id", "strike", "option_type"]].copy()
    result["moneyness"] = price / result["strike"]
    return result


def log_moneyness(chain: OptionChain, *, underlying_price: float) -> pd.DataFrame:
    """Calculate the natural log of spot divided by strike."""
    result = moneyness(chain, underlying_price=underlying_price)
    result["log_moneyness"] = np.log(result.pop("moneyness"))
    return result


def option_midprice(chain: OptionChain) -> pd.DataFrame:
    """Calculate observed bid-ask midprices without filling missing quotes."""
    result = chain.observations[["contract_id", "bid", "ask"]].copy()
    result["midprice"] = (result["bid"] + result["ask"]) / 2
    return result


def option_absolute_spread(chain: OptionChain) -> pd.DataFrame:
    """Calculate observed ask minus bid."""
    result = chain.observations[["contract_id", "bid", "ask"]].copy()
    result["absolute_spread"] = result["ask"] - result["bid"]
    return result


def option_relative_spread(chain: OptionChain) -> pd.DataFrame:
    """Calculate absolute spread divided by midprice."""
    result = option_absolute_spread(chain)
    midpoint = (result["bid"] + result["ask"]) / 2
    result["relative_spread"] = (result["absolute_spread"] / midpoint).where(midpoint > 0)
    return result


def intrinsic_value(chain: OptionChain, *, underlying_price: float) -> pd.DataFrame:
    """Calculate intrinsic value from one explicit underlying price."""
    price = _positive_price(underlying_price)
    result = chain.contracts[["contract_id", "strike", "option_type"]].copy()
    call = result["option_type"] == OptionType.CALL.value
    result["intrinsic_value"] = np.where(
        call,
        np.maximum(price - result["strike"], 0),
        np.maximum(result["strike"] - price, 0),
    )
    return result


def time_value(
    chain: OptionChain,
    *,
    underlying_price: float,
    option_value: str = "mark",
) -> pd.DataFrame:
    """Subtract intrinsic value from one explicit observed option-value field."""
    if option_value not in {"last", "mark", "bid", "ask"}:
        raise ValueError("option_value must be last, mark, bid, or ask")
    intrinsic = intrinsic_value(chain, underlying_price=underlying_price)
    values = chain.observations[["contract_id", option_value]].copy()
    result = intrinsic.merge(values, on="contract_id", validate="one_to_one")
    result["time_value"] = result[option_value] - result["intrinsic_value"]
    return result


def chain_summary(chain: OptionChain) -> pd.DataFrame:
    """Summarize observed contracts by expiration and option type."""
    joined = _joined(chain)
    grouped = joined.groupby(["expiration", "option_type"], dropna=False, sort=True)
    return grouped.agg(
        contract_count=("contract_id", "count"),
        volume=("volume", "sum"),
        open_interest=("open_interest", "sum"),
        median_implied_volatility=("implied_volatility", "median"),
    ).reset_index()


def implied_volatility_smile(
    chain: OptionChain,
    *,
    expiration: date,
    option_type: OptionType | str | None = None,
) -> pd.DataFrame:
    """Prepare observed implied volatility across strikes for one expiration."""
    selected = filter_chain(chain, expiration=expiration, option_type=option_type)
    result = _joined(selected)[
        ["contract_id", "expiration", "strike", "option_type", "implied_volatility"]
    ]
    return result.sort_values(["strike", "option_type"], kind="stable").reset_index(drop=True)


def implied_volatility_surface(chain: OptionChain) -> pd.DataFrame:
    """Prepare observed implied volatility without fitting or interpolation."""
    result = _joined(chain)[
        ["contract_id", "expiration", "strike", "option_type", "implied_volatility"]
    ]
    return result.sort_values(["expiration", "strike", "option_type"], kind="stable").reset_index(
        drop=True
    )


def greek_profile(
    chain: OptionChain,
    greek: str,
    *,
    expiration: date | None = None,
    option_type: OptionType | str | None = None,
) -> pd.DataFrame:
    """Prepare one provider-supplied Greek across observed strikes."""
    if greek not in {"delta", "gamma", "theta", "vega", "rho"}:
        raise ValueError("greek must be delta, gamma, theta, vega, or rho")
    selected = filter_chain(chain, expiration=expiration, option_type=option_type)
    result = _joined(selected)[["contract_id", "expiration", "strike", "option_type", greek]]
    return result.sort_values(["expiration", "strike", "option_type"], kind="stable").reset_index(
        drop=True
    )


def _joined(chain: OptionChain) -> pd.DataFrame:
    return chain.contracts.merge(
        chain.observations,
        on=["contract_id", "provider"],
        validate="one_to_one",
    )


def _positive_price(value: float) -> float:
    if not np.isfinite(value) or value <= 0:
        raise AnalysisError("underlying_price must be positive and finite")
    return value
