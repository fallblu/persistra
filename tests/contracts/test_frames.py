"""Contract tests for normalized frames."""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from persistra.data import synthetic
from persistra.errors import DataValidationError
from persistra.model import BarSet, OptionChain, QuoteSet, SeriesSet, TopOfBookSet
from persistra.model._frames import (
    BAR_DTYPES,
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    QUOTE_DTYPES,
    SERIES_DTYPES,
    TOP_OF_BOOK_DTYPES,
    empty_frame,
    typed_frame,
)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("factory", "dtypes"),
    [
        (lambda: synthetic.bars().frame, BAR_DTYPES),
        (lambda: synthetic.quotes().frame, QUOTE_DTYPES),
        (lambda: synthetic.top_of_book().frame, TOP_OF_BOOK_DTYPES),
        (lambda: synthetic.option_chain().contracts, OPTION_CONTRACT_DTYPES),
        (lambda: synthetic.option_chain().observations, OPTION_OBSERVATION_DTYPES),
        (lambda: synthetic.series().frame, SERIES_DTYPES),
    ],
)
def test_exact_columns_and_dtypes(
    factory: Callable[[], pd.DataFrame], dtypes: dict[str, str]
) -> None:
    frame = factory()
    assert list(frame.columns) == list(dtypes)
    assert {name: str(dtype) for name, dtype in frame.dtypes.items()} == dtypes


def test_empty_frame_retains_contract() -> None:
    frame = empty_frame(BAR_DTYPES)
    result = synthetic.bars(periods=0)
    assert frame.equals(result.frame)
    assert list(result.frame.columns) == list(BAR_DTYPES)


def test_typed_frame_rejects_field_differences() -> None:
    with pytest.raises(DataValidationError, match="missing"):
        typed_frame({}, {"required": "string"})
    with pytest.raises(DataValidationError, match="extra"):
        typed_frame({"extra": []}, {})


def test_result_copies_input_frame() -> None:
    source = synthetic.quotes()
    result = QuoteSet(source.frame, source.metadata)
    source.frame.loc[0, "price"] = 999.0
    assert result.frame.loc[0, "price"] != 999.0


def test_frame_rejects_columns_dtypes_sorting_and_duplicates() -> None:
    source = synthetic.quotes()
    extra = source.frame.assign(extra="x")
    with pytest.raises(DataValidationError, match="expected columns"):
        QuoteSet(extra, source.metadata)
    wrong_dtype = source.frame.copy()
    wrong_dtype["price"] = wrong_dtype["price"].astype("Float64")
    with pytest.raises(DataValidationError, match="incorrect dtypes"):
        QuoteSet(wrong_dtype, source.metadata)
    reversed_frame = source.frame.iloc[::-1].reset_index(drop=True)
    with pytest.raises(DataValidationError, match="rows must sort"):
        QuoteSet(reversed_frame, source.metadata)
    duplicate = pd.concat([source.frame, source.frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataValidationError, match="duplicate"):
        QuoteSet(duplicate, source.metadata)


def test_bar_invariants() -> None:
    source = synthetic.bars(periods=3)
    both_times = source.frame.copy()
    both_times.loc[0, "timestamp"] = pd.Timestamp("2025-01-01", tz="UTC")
    with pytest.raises(DataValidationError, match="temporal"):
        BarSet(source.instrument, both_times, source.metadata)
    bad_low = source.frame.copy()
    bad_low.loc[0, "low"] = 10_000.0
    with pytest.raises(DataValidationError, match="low"):
        BarSet(source.instrument, bad_low, source.metadata)
    bad_high = source.frame.copy()
    bad_high.loc[0, "high"] = 0.01
    with pytest.raises(DataValidationError, match="high"):
        BarSet(source.instrument, bad_high, source.metadata)
    bad_identity = source.frame.copy()
    bad_identity["instrument_id"] = "wrong"
    bad_identity["instrument_id"] = bad_identity["instrument_id"].astype("string")
    with pytest.raises(DataValidationError, match="scope"):
        BarSet(source.instrument, bad_identity, source.metadata)


def test_numeric_invariants() -> None:
    quote = synthetic.quotes(("AAA",))
    negative = quote.frame.copy()
    negative.loc[0, "price"] = -1
    with pytest.raises(DataValidationError, match="positive"):
        QuoteSet(negative, quote.metadata)
    nonfinite = quote.frame.copy()
    nonfinite.loc[0, "change"] = np.inf
    with pytest.raises(DataValidationError, match="finite"):
        QuoteSet(nonfinite, quote.metadata)
    book = synthetic.top_of_book(("AAA",))
    negative_size = book.frame.copy()
    negative_size.loc[0, "bid_size"] = -1
    with pytest.raises(DataValidationError, match="nonnegative"):
        TopOfBookSet(negative_size, book.metadata)


def test_option_chain_invariants() -> None:
    source = synthetic.option_chain(chain_date=date(2025, 1, 17))
    bad_side = source.contracts.copy()
    bad_side.loc[0, "option_type"] = "other"
    with pytest.raises(DataValidationError, match="call or put"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            bad_side,
            source.observations,
            source.metadata,
        )
    bad_expiration = source.contracts.copy()
    bad_expiration.loc[0, "expiration"] = pd.Timestamp("2025-01-01")
    with pytest.raises(DataValidationError, match="precedes"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            bad_expiration,
            source.observations,
            source.metadata,
        )
    orphan = source.observations.copy()
    orphan.loc[0, "contract_id"] = "missing"
    orphan = orphan.sort_values(["provider", "contract_id"]).reset_index(drop=True)
    with pytest.raises(DataValidationError, match="matching contract"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            source.contracts,
            orphan,
            source.metadata,
        )


def test_series_scope_is_exact() -> None:
    source = synthetic.series(periods=2)
    wrong = source.frame.copy()
    wrong["series_id"] = "wrong"
    wrong["series_id"] = wrong["series_id"].astype("string")
    with pytest.raises(ValueError, match="scope"):
        SeriesSet(source.definition, wrong, source.metadata)
