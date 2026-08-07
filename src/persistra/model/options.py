"""Normalized historical option-chain results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from persistra.errors import DataValidationError
from persistra.model._frames import (
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    require_finite,
    require_nonnegative,
    validate_frame,
)

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd

    from persistra.model.market import ResultMetadata


@dataclass(frozen=True, slots=True)
class OptionChain:
    """Contracts and observations for one historical chain."""

    underlying_instrument_id: str
    provider_symbol: str
    chain_date: date
    contracts: pd.DataFrame
    observations: pd.DataFrame
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        def contract_rows(frame: pd.DataFrame) -> None:
            require_finite(frame, ["strike"], positive=True)
            if not frame["option_type"].isin(["call", "put"]).all():
                raise DataValidationError("option_type must be call or put")
            if (frame["expiration"].dt.date < self.chain_date).any():
                raise DataValidationError("option expiration precedes chain date")

        contracts = validate_frame(
            self.contracts,
            OPTION_CONTRACT_DTYPES,
            validate_rows=contract_rows,
            sort_by=["expiration", "strike", "option_type", "contract_id"],
            unique_by=["provider", "contract_id"],
        )

        def observation_rows(frame: pd.DataFrame) -> None:
            require_nonnegative(
                frame,
                [
                    "last",
                    "mark",
                    "bid",
                    "bid_size",
                    "ask",
                    "ask_size",
                    "volume",
                    "open_interest",
                    "implied_volatility",
                ],
            )
            require_finite(frame, ["delta", "gamma", "theta", "vega", "rho"])
            if not frame.empty and not (frame["chain_date"].dt.date == self.chain_date).all():
                raise DataValidationError("observation date differs from chain scope")

        observations = validate_frame(
            self.observations,
            OPTION_OBSERVATION_DTYPES,
            validate_rows=observation_rows,
            sort_by=["provider", "contract_id"],
            unique_by=["provider", "contract_id", "chain_date"],
        )
        if set(observations["contract_id"]).difference(contracts["contract_id"]):
            raise DataValidationError("an observation has no matching contract")
        object.__setattr__(self, "contracts", contracts)
        object.__setattr__(self, "observations", observations)
