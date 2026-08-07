"""Snapshot tests for supported public imports."""

import persistra.data
import persistra.model


def test_model_public_api_snapshot() -> None:
    assert persistra.model.__all__ == [
        "BarSet",
        "CacheStatus",
        "Catalog",
        "CommoditySpotQuote",
        "EntitlementMode",
        "ExchangeRateQuote",
        "IndexCatalogResult",
        "Instrument",
        "InstrumentKind",
        "InstrumentSearchResult",
        "Listing",
        "MarketStatusResult",
        "OptionChain",
        "OptionContract",
        "OptionType",
        "ProviderSymbol",
        "QuoteSet",
        "ResultMetadata",
        "SchemaDiagnostic",
        "SeriesDefinition",
        "SeriesKind",
        "SeriesSet",
        "TopOfBookSet",
        "provider_instrument_id",
        "provider_series_id",
    ]


def test_data_public_api_snapshot() -> None:
    assert persistra.data.__all__ == [
        "BarSource",
        "OptionChainSource",
        "QuoteSource",
        "ReferenceSource",
        "ScalarSeriesSource",
        "synthetic",
    ]
