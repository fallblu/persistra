from __future__ import annotations

from persistra.utils import captured_versions


def test_captured_versions_returns_dict():
    result = captured_versions()
    assert isinstance(result, dict)


def test_captured_versions_is_nonempty():
    result = captured_versions()
    assert len(result) > 0


def test_captured_versions_contains_numpy():
    result = captured_versions()
    # Package names from importlib.metadata may be normalised; try both forms
    assert "numpy" in result or "numpy" in {k.lower() for k in result}


def test_captured_versions_contains_pandas():
    result = captured_versions()
    assert "pandas" in result or "pandas" in {k.lower() for k in result}


def test_captured_versions_values_are_strings():
    result = captured_versions()
    for name, version in result.items():
        assert isinstance(name, str)
        assert isinstance(version, str)
