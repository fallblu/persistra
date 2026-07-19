from __future__ import annotations

from persistra.sources.alphavantage.registration import (
    ALPHAVANTAGE_SOURCE,
    alphavantage_dataset_definitions,
    alphavantage_source_definition,
)


def test_source_definition_records_non_redistributable_licensing() -> None:
    source = alphavantage_source_definition()
    assert source.name == ALPHAVANTAGE_SOURCE.name
    assert source.provider_display_name == "Alpha Vantage"
    assert source.redistributable is False
    assert source.enabled is True
    assert source.timezone_guarantee == "utc"
    assert source.timestamp_precision == "second"


def test_dataset_definitions_cover_every_family_once() -> None:
    datasets = alphavantage_dataset_definitions()
    names = [str(dataset.name) for dataset in datasets]
    assert names == [
        "alphavantage.equity_bars",
        "alphavantage.equity_actions",
        "alphavantage.trading_status",
        "alphavantage.macro_series",
        "alphavantage.rate_curves",
        "alphavantage.benchmark_series",
        "alphavantage.crypto_bars",
        "alphavantage.fx_bars",
    ]
    for dataset in datasets:
        assert dataset.supported_sources == (ALPHAVANTAGE_SOURCE,)
        assert dataset.retractions_allowed is False
        assert dataset.retraction_schema_content_id is None
        assert str(dataset.availability_policy) == "alphavantage.ingestion_bounded"
