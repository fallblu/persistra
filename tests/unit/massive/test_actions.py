from persistra.data.store import ActionQuery
from persistra.providers.massive.actions import fetch_dividends, fetch_splits


def test_fetch_splits_computes_ratio(fake_rest_client):
    rows = fetch_splits(fake_rest_client, "AAA")
    assert len(rows) == 1
    row = rows[0]
    assert row["action_type"] == "split"
    assert row["ratio"] == 2.0  # split_to/split_from = 2/1
    assert str(row["date"]) == "2023-06-15"
    assert row["amount"] is None


def test_fetch_dividends_carries_cash_amount(fake_rest_client):
    rows = fetch_dividends(fake_rest_client, "BBB")
    assert len(rows) == 1
    row = rows[0]
    assert row["action_type"] == "dividend"
    assert row["amount"] == 0.25
    assert row["ratio"] is None
    assert str(row["date"]) == "2023-09-20"


def test_ingest_actions_writes_to_store(fake_rest_client, tmp_path):
    import pandas as pd

    from persistra.data.store import ParquetMarketData
    from persistra.providers.massive.actions import ingest_actions

    store = ParquetMarketData(tmp_path / "s")
    ingest_actions(["AAA"], store, fake_rest_client)
    table = store.corporate_actions(
        ActionQuery(("AAA",), pd.Timestamp("2023-01-01"), pd.Timestamp("2023-12-31"))
    )
    assert table.num_rows == 2  # one split + one dividend
