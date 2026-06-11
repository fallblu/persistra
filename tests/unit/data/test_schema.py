import pyarrow as pa

from persistra.data.schema import (
    BAR_SCHEMA,
    CORPORATE_ACTION_SCHEMA,
    UNIVERSE_MEMBERSHIP_SCHEMA,
)


def test_bar_schema_fields_and_types():
    assert BAR_SCHEMA.field("bar_time").type == pa.timestamp("us")
    assert not BAR_SCHEMA.field("close").nullable
    assert BAR_SCHEMA.field("vwap").nullable
    assert BAR_SCHEMA.field("transactions").type == pa.int64()


def test_corporate_action_schema_date_type():
    assert CORPORATE_ACTION_SCHEMA.field("date").type == pa.date32()
    assert CORPORATE_ACTION_SCHEMA.field("ratio").nullable


def test_membership_schema_end_date_nullable():
    assert UNIVERSE_MEMBERSHIP_SCHEMA.field("end_date").nullable
    assert not UNIVERSE_MEMBERSHIP_SCHEMA.field("start_date").nullable
