from __future__ import annotations

import hashlib
import json

import pyarrow as pa


def run_hash(d: dict) -> str:
    """SHA-256 of the canonical JSON form of a run-definition dict.

    Deterministic across processes; key order does not matter.
    """
    blob = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def data_hash(*tables: pa.Table) -> str:
    """SHA-256 folded over each table's Arrow IPC stream bytes, in argument order.

    Arrow IPC serialization is deterministic given identical schema (field
    order + types) and row order, so two runs over identical, identically-sorted
    data hash equal. Empty tables contribute their schema-only IPC bytes.
    """
    h = hashlib.sha256()
    for table in tables:
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        h.update(sink.getvalue().to_pybytes())
    return h.hexdigest()
