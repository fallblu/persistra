from persistra.data.schema import BAR_SCHEMA
from persistra.providers.massive.aggregates import fetch_aggregates, parse_timeframe


def test_parse_timeframe_maps_to_massive_timespan():
    assert parse_timeframe("1d") == (1, "day")
    assert parse_timeframe("5m") == (5, "minute")
    assert parse_timeframe("1h") == (1, "hour")


def test_fetch_aggregates_builds_bar_schema_table(fake_rest_client):
    table = fetch_aggregates(fake_rest_client, "AAA", "1d", "2023-01-01", "2023-01-31")
    assert table.schema.equals(BAR_SCHEMA)
    assert table.num_rows == 3
    df = table.to_pandas()
    assert df["symbol"].tolist() == ["AAA", "AAA", "AAA"]
    assert df["close"].tolist() == [100.5, 101.5, 102.5]
    # daily bars are normalised to ET session midnight, tz-naive
    assert df["bar_time"].dt.tz is None
    assert (df["bar_time"].dt.normalize() == df["bar_time"]).all()


def test_fetch_aggregates_empty_returns_empty_schema_table():
    from types import SimpleNamespace

    empty_client = SimpleNamespace(list_aggs=lambda **kw: iter(()))
    table = fetch_aggregates(empty_client, "AAA", "1d", "2023-01-01", "2023-01-02")
    assert table.num_rows == 0
    assert table.schema.equals(BAR_SCHEMA)


def test_fetch_aggregates_requests_unadjusted_bars():
    from types import SimpleNamespace

    captured: dict = {}

    def list_aggs(**kw):
        captured.update(kw)
        return iter(())

    client = SimpleNamespace(list_aggs=list_aggs)
    fetch_aggregates(client, "AAA", "1d", "2023-01-01", "2023-01-02")
    assert captured["adjusted"] is False
