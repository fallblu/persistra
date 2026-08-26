"""Tests for explicit local-file normalized imports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]
import pytest

from persistra.data import LocalDataAdapter, LocalFamily, LocalImportSpec, synthetic
from persistra.errors import DataValidationError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    OptionChain,
    SeriesSet,
    VintageDatesResult,
)

if TYPE_CHECKING:
    from pathlib import Path

pa: Any = _pyarrow
pq: Any = _parquet
IMPORTED_AT = datetime(2026, 8, 22, 12, tzinfo=UTC)


def _mapping(frame: pd.DataFrame) -> dict[str, str]:
    return {name: name for name in frame.columns if name != "retrieved_at"}


def _write_arrow(path: Path, frame: pd.DataFrame) -> None:
    table: Any = pa.Table.from_pandas(frame, preserve_index=False)
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, table.schema) as writer:
            writer.write_table(table)


def _adapter() -> LocalDataAdapter:
    return LocalDataAdapter(clock=lambda: IMPORTED_AT)


def test_csv_bars_require_explicit_mapping_and_record_file_identity(tmp_path: Path) -> None:
    source = synthetic.bars(periods=3)
    renamed = source.frame.drop(columns="retrieved_at").rename(
        columns={name: f"source_{name}" for name in source.frame if name != "retrieved_at"}
    )
    path = tmp_path / "bars.csv"
    renamed.to_csv(path, index=False)
    columns = {
        str(name): f"source_{name}" for name in source.frame if name != "retrieved_at"
    }
    first = source.frame.iloc[0]
    spec = LocalImportSpec(
        LocalFamily.BARS,
        columns,
        {
            "provider": "synthetic",
            "instrument_id": source.instrument.instrument_id,
            "instrument_kind": source.instrument.kind.value,
            "display_name": source.instrument.display_name,
            "base_currency": source.instrument.base_currency,
            "quote_currency": source.instrument.quote_currency,
            "price_adjustment": first["price_adjustment"],
            "timestamp_position": first["timestamp_position"],
            "source_timezone": first["source_timezone"],
            "currency": first["currency"],
        },
    )

    validation = _adapter().validate(path, spec)
    result = _adapter().import_file(path, spec)

    assert isinstance(result, BarSet)
    assert validation.is_valid
    assert validation.source is not None
    assert validation.source.path == path.resolve()
    assert result.frame["retrieved_at"].eq(IMPORTED_AT).all()
    provenance = result.metadata.request_parameters
    assert provenance["source"]["sha256"] == validation.source.sha256
    assert provenance["columns"]["close"] == "source_close"
    assert provenance["semantics"]["price_adjustment"] == first["price_adjustment"]


def test_arrow_series_round_trip_uses_declared_definition(tmp_path: Path) -> None:
    source = synthetic.series(periods=3)
    frame = source.frame.drop(columns="retrieved_at")
    path = tmp_path / "series.arrow"
    _write_arrow(path, frame)
    definition = source.definition
    spec = LocalImportSpec(
        LocalFamily.SERIES,
        _mapping(source.frame),
        {
            "provider": definition.provider,
            "series_id": definition.series_id,
            "series_kind": definition.kind.value,
            "display_name": definition.display_name,
            "provider_series": definition.provider_series,
            "frequency": definition.frequency,
            "unit": definition.unit,
            "geography": definition.geography,
            "seasonal_adjustment": definition.seasonal_adjustment,
            "maturity": definition.maturity,
        },
    )

    result = _adapter().import_file(path, spec)

    assert isinstance(result, SeriesSet)
    assert result.definition == definition
    assert result.frame.drop(columns="retrieved_at").equals(frame)


def test_parquet_options_split_contracts_and_observations(tmp_path: Path) -> None:
    source = synthetic.option_chain()
    frame = source.observations.drop(columns="retrieved_at").merge(
        source.contracts,
        on=["provider", "contract_id"],
        validate="one_to_one",
    )
    path = tmp_path / "options.parquet"
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)
    spec = LocalImportSpec(
        LocalFamily.OPTIONS,
        _mapping(pd.concat([source.contracts, source.observations], axis="columns")),
        {
            "provider": source.metadata.provider,
            "underlying_instrument_id": source.underlying_instrument_id,
            "provider_symbol": source.provider_symbol,
            "chain_date": source.chain_date.isoformat(),
        },
    )

    result = _adapter().import_file(path, spec)

    assert isinstance(result, OptionChain)
    assert result.contracts.equals(source.contracts)
    assert result.observations.drop(columns="retrieved_at").equals(
        source.observations.drop(columns="retrieved_at")
    )


@pytest.mark.parametrize(
    ("family", "factory", "semantics"),
    [
        (
            LocalFamily.QUOTES,
            synthetic.quotes,
            {"provider": "synthetic", "entitlement": "historical"},
        ),
        (LocalFamily.TOP_OF_BOOK, synthetic.top_of_book, {"provider": "synthetic"}),
        (
            LocalFamily.VINTAGE_SERIES,
            synthetic.vintage_series,
            {
                "provider": "synthetic",
                "series_id": "ps_2f2c9f62186407460b7b0215",
                "series_kind": "economic",
                "display_name": "Synth Gdp",
                "provider_series": "SYNTH_GDP",
                "frequency": "monthly",
                "unit": "index",
                "geography": "United States",
                "seasonal_adjustment": None,
                "maturity": None,
            },
        ),
        (LocalFamily.SEARCH, synthetic.search, {"provider": "synthetic", "query": "DEMO"}),
        (LocalFamily.MARKET_STATUS, synthetic.market_status, {"provider": "synthetic"}),
        (LocalFamily.INDEX_CATALOG, synthetic.index_catalog, {"provider": "synthetic"}),
    ],
)
def test_frame_families_construct_through_existing_contracts(
    tmp_path: Path,
    family: LocalFamily,
    factory: Any,
    semantics: dict[str, Any],
) -> None:
    source: Any = factory()
    frame: pd.DataFrame = source.frame.drop(columns="retrieved_at", errors="ignore")
    path = tmp_path / f"{family.value}.parquet"
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)
    spec = LocalImportSpec(family, _mapping(source.frame), semantics)

    result = _adapter().import_file(path, spec)

    assert type(result) is type(source)


@pytest.mark.parametrize(
    ("family", "factory"),
    [
        (LocalFamily.EXCHANGE_RATE, synthetic.exchange_rate),
        (LocalFamily.COMMODITY_SPOT, synthetic.commodity_spot),
    ],
)
def test_scalar_families_require_one_row(
    tmp_path: Path, family: LocalFamily, factory: Any
) -> None:
    source: Any = factory()
    values = {
        name: getattr(source, name)
        for name in source.__dataclass_fields__
        if name not in {"metadata", "retrieved_at"}
    }
    frame = pd.DataFrame([values])
    path = tmp_path / f"{family.value}.csv"
    frame.to_csv(path, index=False)
    spec = LocalImportSpec(family, {name: name for name in values}, {"provider": "synthetic"})

    result = _adapter().import_file(path, spec)

    assert isinstance(result, (ExchangeRateQuote, CommoditySpotQuote))
    assert type(result) is type(source)
    assert result.retrieved_at == IMPORTED_AT


def test_vintage_dates_and_malformed_inputs_return_structured_findings(tmp_path: Path) -> None:
    source = synthetic.vintage_dates()
    frame = pd.DataFrame(
        {"provider_series": source.provider_series, "vintage_date": source.dates}
    )
    path = tmp_path / "vintage_dates.csv"
    frame.to_csv(path, index=False)
    spec = LocalImportSpec(
        LocalFamily.VINTAGE_DATES,
        {"provider_series": "provider_series", "vintage_date": "vintage_date"},
        {"provider": "synthetic", "provider_series": source.provider_series},
    )

    result = _adapter().import_file(path, spec)
    assert isinstance(result, VintageDatesResult)
    assert result.dates == source.dates

    missing_mapping = LocalImportSpec(
        LocalFamily.VINTAGE_DATES,
        {"provider_series": "provider_series"},
        {"provider": "synthetic", "provider_series": source.provider_series},
    )
    validation = _adapter().validate(path, missing_mapping)
    assert not validation.is_valid
    assert validation.findings[0].code == "contract.invalid"
    assert "vintage_date" in validation.findings[0].message

    missing = _adapter().validate(tmp_path / "missing.csv", spec)
    assert missing.findings[0].code == "source.missing"
    with pytest.raises(DataValidationError, match="local import failed"):
        _adapter().import_file(tmp_path / "unsupported.txt", spec)
