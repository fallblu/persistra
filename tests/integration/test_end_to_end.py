def test_sample_backtest_anchors(sample_result):
    assert len(sample_result.equity_curve) == 501
    assert len(sample_result.trades) == 5010


def test_equity_curve_columns(sample_result):
    assert list(sample_result.equity_curve.columns) == [
        "equity",
        "cash",
        "gross_exposure",
        "net_exposure",
    ]


def test_trades_columns(sample_result):
    assert list(sample_result.trades.columns) == [
        "timestamp",
        "symbol",
        "quantity",
        "fill_price",
        "commission",
    ]


def test_meta_records_session_count(sample_result):
    assert sample_result.meta["n_sessions"] == 501
