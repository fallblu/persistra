"""Normalized historical option-chain results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from persistra.errors import DataValidationError
from persistra.model._frames import (
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    require_finite,
    require_metadata_values,
    require_nonnegative,
    require_scope_values,
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
        _require_text(self.underlying_instrument_id, "underlying_instrument_id")
        _require_text(self.provider_symbol, "provider_symbol")

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
        require_scope_values(
            contracts,
            {
                "underlying_instrument_id": self.underlying_instrument_id,
                "provider_symbol": self.provider_symbol,
            },
        )
        require_metadata_values(contracts, provider=self.metadata.provider)

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
        contract_keys = set(
            contracts[["provider", "contract_id"]].itertuples(index=False, name=None)
        )
        observation_keys = set(
            observations[["provider", "contract_id"]].itertuples(index=False, name=None)
        )
        if observation_keys.difference(contract_keys):
            raise DataValidationError("an observation has no matching contract")
        require_metadata_values(
            observations,
            provider=self.metadata.provider,
            retrieved_at=self.metadata.retrieved_at,
        )
        object.__setattr__(self, "contracts", contracts)
        object.__setattr__(self, "observations", observations)


def _require_text(value: str, name: str) -> None:
    if not isinstance(cast("object", value), str) or not value.strip():
        raise DataValidationError(f"{name} must not be empty")
