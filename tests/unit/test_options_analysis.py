"""Tests for observed option-chain analysis."""

from typing import cast

import numpy as np
import pandas as pd
import pytest

from persistra.analysis import (
    chain_summary,
    days_to_expiration,
    filter_chain,
    greek_profile,
    implied_volatility_smile,
    implied_volatility_surface,
    intrinsic_value,
    log_moneyness,
    moneyness,
    option_absolute_spread,
    option_midprice,
    option_relative_spread,
    time_value,
)
from persistra.data import synthetic
from persistra.errors import AnalysisError
from persistra.model import OptionType


def test_filter_chain_uses_explicit_contract_terms_without_mutation() -> None:
    chain = synthetic.option_chain()
    expiration = chain.chain_date.replace(day=14) + pd.Timedelta(days=31)
    selected = filter_chain(
        chain,
        expiration=expiration,
        option_type=OptionType.CALL,
        minimum_strike=95,
        maximum_strike=105,
    )
    assert len(selected.contracts) == 1
    assert len(chain.contracts) == 12
    assert set(selected.contracts["option_type"]) == {"call"}
    contract_id = cast("str", selected.contracts.loc[0, "contract_id"])
    by_contract = filter_chain(chain, contract_ids=[contract_id])
    assert len(by_contract.contracts) == 1
    with pytest.raises(ValueError, match="must not exceed"):
        filter_chain(chain, minimum_strike=110, maximum_strike=100)


def test_expiration_and_moneyness_calculations() -> None:
    chain = synthetic.option_chain()
    days = days_to_expiration(chain)
    assert set(days["days_to_expiration"]) == {28, 56}
    ratios = moneyness(chain, underlying_price=100)
    assert ratios.loc[ratios["strike"] == 100, "moneyness"].eq(1).all()
    logs = log_moneyness(chain, underlying_price=100)
    assert logs.loc[logs["strike"] == 100, "log_moneyness"].eq(0).all()
    with pytest.raises(AnalysisError, match="positive"):
        moneyness(chain, underlying_price=0)
    with pytest.raises(AnalysisError, match="finite"):
        moneyness(chain, underlying_price=np.inf)


def test_spreads_intrinsic_and_time_value() -> None:
    chain = synthetic.option_chain()
    mid = option_midprice(chain)
    absolute = option_absolute_spread(chain)
    relative = option_relative_spread(chain)
    assert mid["midprice"].iloc[0] == chain.observations["mark"].iloc[0]
    assert absolute["absolute_spread"].round(6).eq(0.2).all()
    assert relative["relative_spread"].gt(0).all()
    intrinsic = intrinsic_value(chain, underlying_price=100)
    calls = intrinsic[intrinsic["option_type"] == "call"]
    puts = intrinsic[intrinsic["option_type"] == "put"]
    assert calls.loc[calls["strike"] == 90, "intrinsic_value"].eq(10).all()
    assert puts.loc[puts["strike"] == 110, "intrinsic_value"].eq(10).all()
    values = time_value(chain, underlying_price=100, option_value="mark")
    assert "time_value" in values
    with pytest.raises(ValueError, match="option_value"):
        time_value(chain, underlying_price=100, option_value="model")


def test_chain_summary_smile_surface_and_greeks() -> None:
    chain = synthetic.option_chain()
    summary = chain_summary(chain)
    assert summary["contract_count"].sum() == 12
    expiration = chain.chain_date + pd.Timedelta(days=28)
    smile = implied_volatility_smile(chain, expiration=expiration, option_type="call")
    assert len(smile) == 3
    surface = implied_volatility_surface(chain)
    assert len(surface) == 12
    profile = greek_profile(chain, "delta", expiration=expiration)
    assert "delta" in profile
    with pytest.raises(ValueError, match="greek"):
        greek_profile(chain, "charm")
