"""Contract tests for normalized result scope and provenance coherence."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from persistra.data import synthetic
from persistra.errors import DataValidationError
from persistra.model import (
    BarSet,
    IndexCatalogResult,
    InstrumentKind,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    SeriesSet,
    TopOfBookSet,
    VintageSeriesSet,
)
from persistra.model._frames import (
    BAR_DTYPES,
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    QUOTE_DTYPES,
    SERIES_DTYPES,
    TOP_OF_BOOK_DTYPES,
    VINTAGE_SERIES_DTYPES,
    empty_frame,
)
from persistra.model.reference import INDEX_CATALOG_DTYPES, MARKET_STATUS_DTYPES, SEARCH_DTYPES


def _set_string(frame: pd.DataFrame, column: str, value: str) -> None:
    frame[column] = pd.Series([value] * len(frame), dtype="string")


def test_empty_frames_retain_coherent_result_contracts() -> None:
    bars = synthetic.bars(periods=0)
    assert BarSet(bars.instrument, empty_frame(BAR_DTYPES), bars.metadata).frame.empty

    quotes = synthetic.quotes(())
    assert QuoteSet(empty_frame(QUOTE_DTYPES), quotes.metadata).frame.empty

    book = synthetic.top_of_book(())
    assert TopOfBookSet(empty_frame(TOP_OF_BOOK_DTYPES), book.metadata).frame.empty

    options = synthetic.option_chain()
    empty_options = OptionChain(
        options.underlying_instrument_id,
        options.provider_symbol,
        options.chain_date,
        empty_frame(OPTION_CONTRACT_DTYPES),
        empty_frame(OPTION_OBSERVATION_DTYPES),
        options.metadata,
    )
    assert empty_options.contracts.empty and empty_options.observations.empty

    series = synthetic.series(periods=0)
    assert SeriesSet(series.definition, empty_frame(SERIES_DTYPES), series.metadata).frame.empty

    vintage = synthetic.vintage_series(periods=0)
    assert VintageSeriesSet(
        vintage.definition,
        empty_frame(VINTAGE_SERIES_DTYPES),
        vintage.metadata,
    ).frame.empty
    with pytest.raises(DataValidationError, match="metadata provider differs"):
        SeriesSet(
            series.definition,
            empty_frame(SERIES_DTYPES),
            replace(series.metadata, provider="other"),
        )

    reference_metadata = synthetic.metadata("reference")
    assert InstrumentSearchResult(
        "query", empty_frame(SEARCH_DTYPES), reference_metadata
    ).frame.empty
    assert MarketStatusResult(empty_frame(MARKET_STATUS_DTYPES), reference_metadata).frame.empty
    assert IndexCatalogResult(empty_frame(INDEX_CATALOG_DTYPES), reference_metadata).frame.empty


def test_market_frames_must_match_result_metadata() -> None:
    bars = synthetic.bars()
    wrong_provider = bars.frame.copy()
    _set_string(wrong_provider, "provider", "other")
    with pytest.raises(DataValidationError, match="provider differs from result metadata"):
        BarSet(bars.instrument, wrong_provider, bars.metadata)

    wrong_retrieval = bars.frame.copy()
    wrong_retrieval["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs from result metadata"):
        BarSet(bars.instrument, wrong_retrieval, bars.metadata)

    quotes = synthetic.quotes(("AAA",))
    wrong_quote_provider = quotes.frame.copy()
    _set_string(wrong_quote_provider, "provider", "other")
    with pytest.raises(DataValidationError, match="provider differs from result metadata"):
        QuoteSet(wrong_quote_provider, quotes.metadata)
    wrong_quote_retrieval = quotes.frame.copy()
    wrong_quote_retrieval["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs from result metadata"):
        QuoteSet(wrong_quote_retrieval, quotes.metadata)
    wrong_entitlement = quotes.frame.copy()
    _set_string(wrong_entitlement, "entitlement", "realtime")
    with pytest.raises(DataValidationError, match="entitlement differs from result metadata"):
        QuoteSet(wrong_entitlement, quotes.metadata)

    book = synthetic.top_of_book(("AAA",))
    wrong_book_provider = book.frame.copy()
    _set_string(wrong_book_provider, "provider", "other")
    with pytest.raises(DataValidationError, match="provider differs from result metadata"):
        TopOfBookSet(wrong_book_provider, book.metadata)
    wrong_book_retrieval = book.frame.copy()
    wrong_book_retrieval["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs from result metadata"):
        TopOfBookSet(wrong_book_retrieval, book.metadata)


def test_pair_bar_currency_must_match_instrument_scope() -> None:
    bars = synthetic.bars("PAIR", kind=InstrumentKind.FIAT_PAIR)
    wrong = bars.frame.copy()
    _set_string(wrong, "currency", "OTHER")
    with pytest.raises(DataValidationError, match="currency differs from its result scope"):
        BarSet(bars.instrument, wrong, bars.metadata)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("series_id", "other"),
        ("provider", "other"),
        ("provider_series", "other"),
        ("series_kind", "commodity"),
        ("frequency", "daily"),
        ("unit", "percent"),
        ("geography", "other"),
        ("seasonal_adjustment", "adjusted"),
        ("maturity", "other"),
    ],
)
def test_series_rows_must_match_the_full_definition_scope(column: str, value: str) -> None:
    source = synthetic.series(periods=1, maturity="10year")
    wrong = source.frame.copy()
    _set_string(wrong, column, value)
    with pytest.raises(DataValidationError, match=rf"{column} differs from its result scope"):
        SeriesSet(source.definition, wrong, source.metadata)


def test_series_metadata_and_retrieval_must_match_scope() -> None:
    source = synthetic.series(periods=1)
    with pytest.raises(DataValidationError, match="metadata provider differs"):
        SeriesSet(source.definition, source.frame, replace(source.metadata, provider="other"))

    wrong = source.frame.copy()
    wrong["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs from result metadata"):
        SeriesSet(source.definition, wrong, source.metadata)


def test_option_chain_requires_full_contract_and_provenance_scope() -> None:
    source = synthetic.option_chain()

    wrong_underlying = source.contracts.copy()
    _set_string(wrong_underlying, "underlying_instrument_id", "other")
    with pytest.raises(DataValidationError, match="underlying_instrument_id differs"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            wrong_underlying,
            source.observations,
            source.metadata,
        )

    wrong_symbol = source.contracts.copy()
    _set_string(wrong_symbol, "provider_symbol", "OTHER")
    with pytest.raises(DataValidationError, match="provider_symbol differs"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            wrong_symbol,
            source.observations,
            source.metadata,
        )

    wrong_contract_provider = source.contracts.copy()
    _set_string(wrong_contract_provider, "provider", "other")
    with pytest.raises(DataValidationError, match="provider differs from result metadata"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            wrong_contract_provider,
            source.observations,
            source.metadata,
        )

    wrong_provider = source.observations.copy()
    _set_string(wrong_provider, "provider", "other")
    wrong_provider = wrong_provider.sort_values(["provider", "contract_id"]).reset_index(drop=True)
    with pytest.raises(DataValidationError, match="matching contract"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            source.contracts,
            wrong_provider,
            source.metadata,
        )

    wrong_retrieval = source.observations.copy()
    wrong_retrieval["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs"):
        OptionChain(
            source.underlying_instrument_id,
            source.provider_symbol,
            source.chain_date,
            source.contracts,
            wrong_retrieval,
            source.metadata,
        )


def test_scalar_quotes_must_match_identity_and_metadata() -> None:
    rate = synthetic.exchange_rate()
    with pytest.raises(DataValidationError, match="provider differs"):
        replace(rate, provider="other")
    with pytest.raises(DataValidationError, match="retrieved_at differs"):
        replace(rate, retrieved_at=rate.retrieved_at + pd.Timedelta(seconds=1))
    with pytest.raises(DataValidationError, match="must differ"):
        replace(rate, quote_currency=rate.base_currency.lower())

    spot = synthetic.commodity_spot()
    with pytest.raises(DataValidationError, match="provider differs"):
        replace(spot, provider="other")
    with pytest.raises(DataValidationError, match="retrieved_at differs"):
        replace(spot, retrieved_at=spot.retrieved_at + pd.Timedelta(seconds=1))


def test_market_status_retrieval_must_match_metadata() -> None:
    source = synthetic.market_status()
    wrong = source.frame.copy()
    wrong["retrieved_at"] += pd.Timedelta(seconds=1)
    with pytest.raises(DataValidationError, match="retrieved_at differs"):
        MarketStatusResult(wrong, source.metadata)


@pytest.mark.parametrize("score", [0.0, 0.25, 1.0])
def test_instrument_search_accepts_finite_normalized_scores(score: float) -> None:
    source = synthetic.search()
    frame = source.frame.copy()
    frame["match_score"] = score
    assert (
        InstrumentSearchResult(source.query, frame, source.metadata).frame.loc[0, "match_score"]
        == score
    )


@pytest.mark.parametrize("score", [np.nan, np.inf, -np.inf])
def test_instrument_search_rejects_nonfinite_scores(score: float) -> None:
    source = synthetic.search()
    frame = source.frame.copy()
    frame["match_score"] = score
    with pytest.raises(DataValidationError, match="finite and between zero and one"):
        InstrumentSearchResult(source.query, frame, source.metadata)
