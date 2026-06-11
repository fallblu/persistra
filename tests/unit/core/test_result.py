import pandas as pd

from persistra.core.result import Result


def test_result_holds_frames_and_meta():
    ec = pd.DataFrame({"equity": [1.0]})
    r = Result(equity_curve=ec, trades=pd.DataFrame(), positions=pd.DataFrame(), meta={"k": 1})
    assert r.meta["k"] == 1
    assert r.equity_curve is ec


def _empty_result():
    import pandas as pd

    from persistra.core.result import Result

    return Result(
        equity_curve=pd.DataFrame(),
        trades=pd.DataFrame(),
        positions=pd.DataFrame(),
    )


def test_result_diagnostics_defaults_to_empty_frame_with_columns():
    r = _empty_result()
    assert list(r.diagnostics.columns) == ["bar_time", "timeframe", "name", "symbol", "value"]
    assert r.diagnostics.empty


def test_diagnostic_pivots_per_symbol_to_wide_frame():
    import pandas as pd

    from persistra.core.result import Result

    diag = pd.DataFrame(
        [
            {
                "bar_time": pd.Timestamp("2022-01-03"),
                "timeframe": "1d",
                "name": "z",
                "symbol": "AAA",
                "value": 1.0,
            },
            {
                "bar_time": pd.Timestamp("2022-01-03"),
                "timeframe": "1d",
                "name": "z",
                "symbol": "BBB",
                "value": 2.0,
            },
        ]
    )
    r = Result(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), diagnostics=diag)
    wide = r.diagnostic("z")
    assert list(wide.columns) == ["AAA", "BBB"]
    assert wide.loc[pd.Timestamp("2022-01-03"), "AAA"] == 1.0


def test_diagnostic_scalar_yields_single_named_column():
    import pandas as pd

    from persistra.core.result import Result

    diag = pd.DataFrame(
        [
            {
                "bar_time": pd.Timestamp("2022-01-03"),
                "timeframe": "1d",
                "name": "regime",
                "symbol": None,
                "value": 1.0,
            }
        ]
    )
    r = Result(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), diagnostics=diag)
    wide = r.diagnostic("regime")
    assert list(wide.columns) == ["regime"]


def test_diagnostic_missing_name_raises_keyerror_listing_available():
    import pytest

    r = _empty_result()
    with pytest.raises(KeyError):
        r.diagnostic("nope")
