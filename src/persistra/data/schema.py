# src/persistra/data/schema.py
"""Arrow schemas for stored market data."""

import pyarrow as pa

BAR_SCHEMA = pa.schema(
    [
        pa.field("bar_time", pa.timestamp("us"), nullable=False),
        pa.field("symbol", pa.utf8(), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("volume", pa.float64(), nullable=False),
        pa.field("vwap", pa.float64(), nullable=True),
        pa.field("transactions", pa.int64(), nullable=True),
    ]
)

CORPORATE_ACTION_SCHEMA = pa.schema(
    [
        pa.field("date", pa.date32(), nullable=False),
        pa.field("symbol", pa.utf8(), nullable=False),
        pa.field("action_type", pa.utf8(), nullable=False),
        pa.field("amount", pa.float64(), nullable=True),
        pa.field("ratio", pa.float64(), nullable=True),
    ]
)

UNIVERSE_MEMBERSHIP_SCHEMA = pa.schema(
    [
        pa.field("universe_name", pa.utf8(), nullable=False),
        pa.field("symbol", pa.utf8(), nullable=False),
        pa.field("start_date", pa.date32(), nullable=False),
        pa.field("end_date", pa.date32(), nullable=True),
    ]
)
