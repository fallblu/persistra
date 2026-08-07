"""Snapshot tests for supported public imports."""

import persistra.analysis
import persistra.data
import persistra.errors
import persistra.model
import persistra.viz


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
        "AlphaVantageClient",
        "BarSource",
        "DuckDBStore",
        "OptionChainSource",
        "QuoteSource",
        "RawCacheEntry",
        "RawResponseCache",
        "ReferenceSource",
        "ScalarSeriesSource",
        "align",
        "asof_align",
        "pivot_bars",
        "pivot_series",
        "resample_bars",
        "synthetic",
    ]


def test_synthetic_public_api_snapshot() -> None:
    assert persistra.data.synthetic.__all__ == [
        "SYNTHETIC_NOW",
        "bars",
        "commodity_spot",
        "exchange_rate",
        "index_catalog",
        "market_status",
        "metadata",
        "option_chain",
        "quotes",
        "search",
        "series",
        "top_of_book",
        "treasury_curve",
    ]


def test_analysis_public_api_snapshot() -> None:
    assert persistra.analysis.__all__ == [
        "absolute_change",
        "absolute_spread",
        "bar_range",
        "basis_point_change",
        "chain_summary",
        "correlation_matrix",
        "covariance_matrix",
        "coverage_summary",
        "cumulative_returns",
        "days_to_expiration",
        "drawdowns",
        "filter_chain",
        "greek_profile",
        "growth_rate",
        "implied_volatility_smile",
        "implied_volatility_surface",
        "intrinsic_value",
        "log_change",
        "log_moneyness",
        "log_returns",
        "midprice",
        "moneyness",
        "option_absolute_spread",
        "option_midprice",
        "option_relative_spread",
        "percentage_change",
        "realized_volatility",
        "rebase",
        "relative_spread",
        "rolling_mean",
        "rolling_standard_deviation",
        "rolling_volatility",
        "rolling_zscore",
        "session_coverage",
        "simple_returns",
        "summary_statistics",
        "time_value",
        "true_range",
        "volume_summary",
        "yield_curve",
        "yield_curve_history",
    ]


def test_visualization_public_api_snapshot() -> None:
    assert persistra.viz.__all__ == [
        "PriceVolumeAxes",
        "plot_bid_ask_history",
        "plot_candlesticks",
        "plot_correlation",
        "plot_coverage",
        "plot_cumulative_returns",
        "plot_distribution",
        "plot_drawdowns",
        "plot_greek_profile",
        "plot_implied_volatility_smile",
        "plot_implied_volatility_surface",
        "plot_option_chain_prices",
        "plot_option_volume_open_interest",
        "plot_rebased",
        "plot_returns",
        "plot_rolling_statistic",
        "plot_rolling_volatility",
        "plot_scalar_series",
        "plot_series",
        "plot_series_change",
        "plot_spread_history",
        "plot_yield_curve",
        "plot_yield_curve_history",
    ]


def test_error_public_api_snapshot() -> None:
    assert persistra.errors.__all__ == [
        "AnalysisError",
        "AuthenticationError",
        "CacheError",
        "DataValidationError",
        "EntitlementError",
        "NoDataError",
        "PersistraError",
        "ProviderError",
        "RateLimitError",
        "ResponseError",
        "StoreError",
        "TransportError",
    ]
