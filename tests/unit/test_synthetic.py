"""Tests for deterministic offline research data."""

from datetime import date

import pandas as pd
import pytest

from persistra.data import synthetic
from persistra.model import BarSet, InstrumentKind, OptionChain, QuoteSet, SeriesSet, TopOfBookSet


def test_synthetic_bars_are_deterministic_and_have_regimes() -> None:
    first = synthetic.bars(periods=20, seed=2)
    second = synthetic.bars(periods=20, seed=2)
    assert isinstance(first, BarSet)
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert first.frame.iloc[10:]["volume"].mean() > first.frame.iloc[:10]["volume"].mean()


def test_synthetic_intraday_uses_utc_instants() -> None:
    result = synthetic.bars(interval="5min", periods=2)
    assert result.frame["date"].isna().all()
    assert result.frame["timestamp"].notna().all()
    assert set(result.frame["timestamp_position"]) == {"provider_label"}


def test_synthetic_families_are_typed() -> None:
    assert isinstance(synthetic.quotes(), QuoteSet)
    assert isinstance(synthetic.top_of_book(), TopOfBookSet)
    assert isinstance(synthetic.option_chain(), OptionChain)
    assert isinstance(synthetic.series(), SeriesSet)
    assert len(synthetic.option_chain().contracts) == 12


def test_synthetic_supports_empty_inputs() -> None:
    assert synthetic.quotes(()).frame.empty
    assert synthetic.top_of_book(()).frame.empty
    assert synthetic.series(periods=0).frame.empty
    with pytest.raises(ValueError, match="nonnegative"):
        synthetic.bars(periods=-1)


def test_synthetic_preserves_requested_identity() -> None:
    bars = synthetic.bars("PAIR", kind=InstrumentKind.CRYPTO_PAIR)
    assert bars.instrument.kind is InstrumentKind.CRYPTO_PAIR
    assert synthetic.option_chain(chain_date=date(2024, 3, 1)).chain_date == date(2024, 3, 1)
