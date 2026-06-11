from __future__ import annotations

from persistra.viz.formatting import METRIC_ROWS, format_metric


def test_metric_rows_is_nonempty_list_of_three_tuples():
    assert isinstance(METRIC_ROWS, list)
    assert len(METRIC_ROWS) > 0
    for item in METRIC_ROWS:
        assert isinstance(item, tuple)
        assert len(item) == 3
        key, label, fmt = item
        assert isinstance(key, str)
        assert isinstance(label, str)
        assert isinstance(fmt, str)


def test_format_metric_percentage():
    # 0.1234 formatted as "{:.2%}" -> "12.34%"
    result = format_metric(0.1234, "{:.2%}")
    assert result == "12.34%"


def test_format_metric_ratio():
    # 1.5 formatted as "{:.2f}" -> "1.50"
    result = format_metric(1.5, "{:.2f}")
    assert result == "1.50"


def test_format_metric_nan_returns_dash():
    result = format_metric(float("nan"), "{:.2f}")
    assert result == "—"


def test_metric_rows_contains_sharpe_and_return():
    keys = [row[0] for row in METRIC_ROWS]
    assert "sharpe" in keys
    assert "ann_return" in keys
