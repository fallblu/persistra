from scripts.sample_universe import SAMPLE_SYMBOLS


def test_sample_symbols_are_ten_unique_uppercase():
    assert len(SAMPLE_SYMBOLS) == 10
    assert len(set(SAMPLE_SYMBOLS)) == 10
    assert all(s == s.upper() and s.isalpha() for s in SAMPLE_SYMBOLS)
