from __future__ import annotations

import pyarrow as pa

from persistra.utils import data_hash, run_hash

# --------------------------------------------------------------------------- #
# run_hash
# --------------------------------------------------------------------------- #


def test_run_hash_is_deterministic():
    d = {"strategy": "EqualWeight", "start": "2022-01-03", "end": "2023-12-29"}
    assert run_hash(d) == run_hash(d)


def test_run_hash_key_order_does_not_matter():
    d1 = {"a": 1, "b": 2}
    d2 = {"b": 2, "a": 1}
    assert run_hash(d1) == run_hash(d2)


def test_run_hash_sensitive_to_different_inputs():
    d1 = {"x": 1}
    d2 = {"x": 2}
    assert run_hash(d1) != run_hash(d2)


def test_run_hash_returns_hex_string():
    h = run_hash({"k": "v"})
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 produces 64 hex chars
    int(h, 16)  # must be valid hex


# --------------------------------------------------------------------------- #
# data_hash
# --------------------------------------------------------------------------- #


def _small_table(values: list[float]) -> pa.Table:
    return pa.table({"close": pa.array(values, type=pa.float64())})


def test_data_hash_is_deterministic():
    t = _small_table([1.0, 2.0, 3.0])
    assert data_hash(t) == data_hash(t)


def test_data_hash_two_identical_calls_agree():
    t1 = _small_table([10.0, 20.0])
    t2 = _small_table([10.0, 20.0])
    assert data_hash(t1) == data_hash(t2)


def test_data_hash_sensitive_to_different_values():
    t1 = _small_table([1.0, 2.0])
    t2 = _small_table([1.0, 3.0])
    assert data_hash(t1) != data_hash(t2)


def test_data_hash_sensitive_to_row_order():
    t1 = _small_table([1.0, 2.0])
    t2 = _small_table([2.0, 1.0])
    assert data_hash(t1) != data_hash(t2)


def test_data_hash_multiple_tables_differ_from_single():
    t = _small_table([1.0, 2.0])
    assert data_hash(t, t) != data_hash(t)


def test_data_hash_returns_hex_string():
    h = data_hash(_small_table([1.0]))
    assert isinstance(h, str)
    assert len(h) == 64
    int(h, 16)
