"""Versioned public dataframe contracts: fixed column order, dtypes, and coercion.

A :class:`FrameContract` names an ordered set of typed columns under a
``name@version`` schema identity. :func:`build_frame` materializes canonical rows
into a pandas frame with exactly those columns, coerced to the contract dtypes and
sorted deterministically by the contract ordering keys; empty inputs keep the full
typed schema. :func:`validate_frame` asserts an existing frame matches its contract
and is used by the contract-test kit.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.domain.errors import FrameContractError
from persistra.domain.identity import QualifiedName, SchemaVersion

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class ColumnDtype(StrEnum):
    """Supported public dataframe column kinds and their pandas realizations."""

    STRING = "string"
    INSTANT = "instant"
    DATE = "date"
    INT = "int"
    BOOL = "bool"
    FLOAT = "float"
    JSON = "json"


_INSTANT_DTYPE = "datetime64[us, UTC]"
_PANDAS_DTYPE: dict[ColumnDtype, str] = {
    ColumnDtype.STRING: "string",
    ColumnDtype.INSTANT: _INSTANT_DTYPE,
    ColumnDtype.DATE: "object",
    ColumnDtype.INT: "Int64",
    ColumnDtype.BOOL: "boolean",
    ColumnDtype.FLOAT: "float64",
    ColumnDtype.JSON: "string",
}
_UNSORTABLE = frozenset({ColumnDtype.JSON})


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One named column bound to a contract dtype."""

    name: str
    dtype: ColumnDtype

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.name), str) or not self.name:
            raise FrameContractError("column name must be non-empty text")
        if not isinstance(cast("object", self.dtype), ColumnDtype):
            raise FrameContractError("column dtype must be a ColumnDtype")


@dataclass(frozen=True, slots=True)
class FrameContract:
    """Immutable schema identity plus ordered typed columns and ordering keys."""

    name: QualifiedName
    version: SchemaVersion
    columns: tuple[ColumnSpec, ...]
    ordering: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.name), QualifiedName):
            raise FrameContractError("frame contract name must be a QualifiedName")
        if not isinstance(cast("object", self.version), SchemaVersion):
            raise FrameContractError("frame contract version must be a SchemaVersion")
        if not self.columns:
            raise FrameContractError("frame contract requires at least one column")
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise FrameContractError("frame contract column names must be unique")
        known = {column.name: column.dtype for column in self.columns}
        for key in self.ordering:
            if key not in known:
                raise FrameContractError(f"ordering key {key!r} is not a declared column")
            if known[key] in _UNSORTABLE:
                raise FrameContractError(f"ordering key {key!r} has an unsortable dtype")

    @property
    def schema_id(self) -> str:
        """Return the ``name@version`` schema identity string."""
        return f"{self.name}@{self.version}"

    @property
    def column_names(self) -> tuple[str, ...]:
        """Return the fixed column order."""
        return tuple(column.name for column in self.columns)


class FrameContractRegistry:
    """Mutable registry mapping schema identity to its frame contract."""

    def __init__(self) -> None:
        self._by_id: dict[str, FrameContract] = {}

    def register(self, contract: FrameContract) -> FrameContract:
        """Register a contract, rejecting a conflicting re-registration."""
        existing = self._by_id.get(contract.schema_id)
        if existing is not None and existing != contract:
            raise FrameContractError(f"frame contract {contract.schema_id} already registered")
        self._by_id[contract.schema_id] = contract
        return contract

    def get(self, schema_id: str) -> FrameContract:
        """Return a registered contract by ``name@version`` identity."""
        try:
            return self._by_id[schema_id]
        except KeyError as error:
            raise FrameContractError(f"frame contract {schema_id} is not registered") from error

    def identities(self) -> frozenset[str]:
        """Return every registered schema identity."""
        return frozenset(self._by_id)


FRAME_REGISTRY = FrameContractRegistry()


def _coerce_string(values: list[Any]) -> Any:
    return pd.Series(values, dtype="object").astype("string")


def _coerce_instant(values: list[Any]) -> Any:
    for value in values:
        if value is not None and not isinstance(value, dt.datetime):
            raise FrameContractError("instant column requires datetime or None values")
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            raise FrameContractError("instant column requires tz-aware datetimes")
    series = pd.to_datetime(pd.Series(values, dtype="object"), utc=True)
    return series.astype(_INSTANT_DTYPE)


def _coerce_date(values: list[Any]) -> Any:
    for value in values:
        if value is None:
            continue
        if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
            raise FrameContractError("date column requires datetime.date or None values")
    return pd.Series(values, dtype="object")


def _coerce_int(values: list[Any]) -> Any:
    for value in values:
        if isinstance(value, bool) or (value is not None and not isinstance(value, int)):
            raise FrameContractError("int column requires int or None values")
    return pd.array(values, dtype="Int64")


def _coerce_bool(values: list[Any]) -> Any:
    for value in values:
        if value is not None and not isinstance(value, bool):
            raise FrameContractError("bool column requires bool or None values")
    return pd.array(values, dtype="boolean")


def _coerce_float(values: list[Any]) -> Any:
    coerced: list[float | None] = []
    for value in values:
        if value is None:
            coerced.append(None)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FrameContractError("float column requires numeric or None values")
        number = float(value)
        if not math.isfinite(number):
            raise FrameContractError("float column requires finite values")
        coerced.append(number)
    return pd.Series(coerced, dtype="float64")


def _coerce_json(values: list[Any]) -> Any:
    encoded: list[str | None] = []
    for value in values:
        if value is None:
            encoded.append(None)
        elif isinstance(value, str):
            try:
                json.loads(value)
            except json.JSONDecodeError as error:
                raise FrameContractError("json column string is not valid JSON") from error
            encoded.append(value)
        elif isinstance(value, (list, dict)):
            encoded.append(json.dumps(value, sort_keys=True, separators=(",", ":")))
        else:
            raise FrameContractError("json column requires str, list, dict, or None values")
    return pd.Series(encoded, dtype="object").astype("string")


_COERCERS = {
    ColumnDtype.STRING: _coerce_string,
    ColumnDtype.INSTANT: _coerce_instant,
    ColumnDtype.DATE: _coerce_date,
    ColumnDtype.INT: _coerce_int,
    ColumnDtype.BOOL: _coerce_bool,
    ColumnDtype.FLOAT: _coerce_float,
    ColumnDtype.JSON: _coerce_json,
}


def build_frame(
    contract: FrameContract, rows: Sequence[Mapping[str, Any]]
) -> pd.DataFrame:
    """Materialize canonical row mappings into a contract-conforming frame."""
    known = contract.column_names
    known_set = set(known)
    columns: dict[str, Any] = {}
    for column in contract.columns:
        values: list[Any] = []
        for row in rows:
            if column.name not in row:
                raise FrameContractError(f"row is missing column {column.name!r}")
            values.append(row[column.name])
        columns[column.name] = _COERCERS[column.dtype](values)
    for row in rows:
        extra = set(row) - known_set
        if extra:
            raise FrameContractError(f"row has columns outside the contract: {sorted(extra)}")
    frame = pd.DataFrame(columns)
    frame = frame.reindex(columns=list(known))
    if contract.ordering:
        frame = frame.sort_values(
            list(contract.ordering), kind="mergesort", na_position="last"
        ).reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)
    return frame


def validate_frame(contract: FrameContract, frame: pd.DataFrame) -> None:
    """Assert a frame matches its contract's column order and dtypes.

    Raises :class:`FrameContractError` on the first divergence.
    """
    actual = list(frame.columns)
    if actual != list(contract.column_names):
        raise FrameContractError(
            f"frame columns {actual} do not match contract {list(contract.column_names)}"
        )
    for column in contract.columns:
        series = frame[column.name]
        dtype_text = str(series.dtype)
        if column.dtype is ColumnDtype.DATE:
            if dtype_text != "object":
                raise FrameContractError(f"column {column.name!r} must be object-typed dates")
            for value in series:
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    continue
                if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
                    raise FrameContractError(f"column {column.name!r} holds a non-date value")
        elif column.dtype is ColumnDtype.JSON:
            if dtype_text != "string":
                raise FrameContractError(f"column {column.name!r} must hold canonical JSON strings")
            for value in series:
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    continue
                if pd.isna(value):
                    continue
                try:
                    json.loads(cast("str", value))
                except (json.JSONDecodeError, TypeError) as error:
                    raise FrameContractError(
                        f"column {column.name!r} holds invalid JSON"
                    ) from error
        else:
            expected = _PANDAS_DTYPE[column.dtype]
            if dtype_text != expected:
                raise FrameContractError(
                    f"column {column.name!r} dtype {dtype_text} != expected {expected}"
                )
