"""Pure reconciliation helpers for imported Trading Engine journals."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def imported_values_equal(left: object, right: object) -> bool:
    """Compare imported scalars while preserving missing-value semantics."""
    if left is pd.NA or right is pd.NA:
        return left is pd.NA and right is pd.NA
    if left is None or right is None:
        return left is None and right is None
    return bool(left == right)


def compare_attribution_rows(
    final_rows: Sequence[Mapping[str, object]],
    completion_rows: Sequence[Mapping[str, object]],
    *,
    key: str,
    fields: set[str],
    name: str,
) -> None:
    """Require terminal attribution rows to equal the final valuation."""
    final = {cast("str", row[key]): row for row in final_rows}
    completed = {cast("str", row[key]): row for row in completion_rows}
    if set(final) != set(completed):
        raise ValueError(f"run_completed {name} differ from the final valuation")
    for identifier_value, row in final.items():
        if any(
            not imported_values_equal(row[field], completed[identifier_value][field])
            for field in fields
        ):
            raise ValueError(f"run_completed {name} differ from the final valuation")


def terminal_order_counts(
    orders: Sequence[Mapping[str, object]],
    *,
    adjustments: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    """Derive terminal order counts from validated lifecycle rows."""
    rejected = {
        cast("str", order["order_id"])
        for order in orders
        if order["event_type"] == "order_rejected"
    }
    cancelled = {cast("str", item["order_id"]) for item in cancellations}
    filled: set[str] = set()
    for order in orders:
        order_id = cast("str", order["order_id"])
        if order_id in rejected or order_id in cancelled:
            continue
        snapshots = [item for item in adjustments if item["order_id"] == order_id]
        latest = (
            order
            if not snapshots
            else max(snapshots, key=lambda item: cast("int", item["engine_sequence"]))
        )
        quantity = cast("int", latest["quantity_micros"])
        filled_quantity = cast("int", latest["filled_quantity_micros"])
        filled_quantity += sum(
            cast("int", fill["quantity_micros"])
            for fill in fills
            if fill["order_id"] == order_id
            and cast("int", fill["engine_sequence"])
            > cast("int", latest["engine_sequence"])
        )
        if filled_quantity > quantity:
            raise ValueError("terminal fills exceed their latest adjusted order quantity")
        if filled_quantity == quantity:
            filled.add(order_id)
    total = len(orders)
    return {
        "total": total,
        "active": total - len(rejected) - len(cancelled) - len(filled),
        "filled": len(filled),
        "rejected": len(rejected),
        "cancelled": len(cancelled),
    }
