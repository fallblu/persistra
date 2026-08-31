"""Reusable bounded strategies for untrusted serialized inputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

if TYPE_CHECKING:
    from hypothesis.strategies import SearchStrategy

FUZZ_SETTINGS = settings(max_examples=25, deadline=None)
FILE_FUZZ_SETTINGS = settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)

identifier_strings: SearchStrategy[str] = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
    min_size=1,
    max_size=64,
)
malformed_identifiers: SearchStrategy[str] = st.sampled_from(
    ["", " ", "\t", "\n", "/", "../escape", "nul\x00identifier"]
)

json_scalars: SearchStrategy[object] = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.text(max_size=64),
)
portable_json: SearchStrategy[object] = st.recursive(
    json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=6),
        st.dictionaries(st.text(max_size=24), children, max_size=6),
    ),
    max_leaves=18,
)
portable_mappings: SearchStrategy[dict[str, object]] = st.dictionaries(
    st.text(max_size=24), portable_json, max_size=8
)

malformed_scalars: SearchStrategy[object] = st.one_of(
    st.none(),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=32),
    st.lists(json_scalars, max_size=4),
    st.dictionaries(st.text(max_size=12), json_scalars, max_size=4),
)
extreme_sizes: SearchStrategy[int] = st.sampled_from(
    [-(2**63), -1, 0, 1, 2**31 - 1, 2**63 - 1, 10**100]
)
timestamp_strings: SearchStrategy[str] = st.one_of(
    st.datetimes(
        min_value=datetime(1970, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=st.just(UTC),
    ).map(datetime.isoformat),
    st.sampled_from(["", "not-a-time", "2025-01-01", "2025-13-40T99:00:00Z", "999999999999-01-01"]),
)
decimal_strings: SearchStrategy[str] = st.one_of(
    st.decimals(
        min_value=Decimal("-1000000000000"),
        max_value=Decimal("1000000000000"),
        allow_nan=False,
        allow_infinity=False,
        places=6,
    ).map(lambda value: format(value, "f")),
    st.sampled_from(["", "NaN", "Infinity", "1e1000000", "+1", "01", "1.0.0"]),
)


def _duplicate_document(values: tuple[str, object, object]) -> str:
    key, first, second = values
    encoded_key = json.dumps(key)
    return f"{{{encoded_key}:{json.dumps(first)},{encoded_key}:{json.dumps(second)}}}"


duplicate_field_documents: SearchStrategy[str] = st.tuples(
    identifier_strings,
    json_scalars,
    json_scalars,
).map(_duplicate_document)
