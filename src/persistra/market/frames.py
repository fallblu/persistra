"""This module contains the versioned public dataframe contracts for canonical market families."""

from __future__ import annotations

from persistra.domain import QualifiedName, SchemaVersion
from persistra.domain.frames import (
    FRAME_REGISTRY,
    ColumnDtype,
    ColumnSpec,
    FrameContract,
)


def _contract(
    name: str,
    columns: tuple[tuple[str, ColumnDtype], ...],
    ordering: tuple[str, ...],
) -> FrameContract:
    return FRAME_REGISTRY.register(
        FrameContract(
            QualifiedName(name),
            SchemaVersion(1),
            tuple(ColumnSpec(column, dtype) for column, dtype in columns),
            ordering,
        )
    )


BARS_FRAME = _contract(
    "persistra.dataframe.bars",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("bar_spec_id", ColumnDtype.STRING),
        ("bar_spec_version", ColumnDtype.INT),
        ("source_id", ColumnDtype.STRING),
        ("observation_scope", ColumnDtype.STRING),
        ("venue_id", ColumnDtype.STRING),
        ("aggregation_name", ColumnDtype.STRING),
        ("aggregation_version", ColumnDtype.INT),
        ("aggregation_content_id", ColumnDtype.STRING),
        ("interval_start", ColumnDtype.INSTANT),
        ("interval_end", ColumnDtype.INSTANT),
        ("observed_through_at", ColumnDtype.INSTANT),
        ("session_date", ColumnDtype.DATE),
        ("bar_phase", ColumnDtype.STRING),
        ("calendar_schedule_content_id", ColumnDtype.STRING),
        ("bar_state", ColumnDtype.STRING),
        ("currency", ColumnDtype.STRING),
        ("open", ColumnDtype.FLOAT),
        ("high", ColumnDtype.FLOAT),
        ("low", ColumnDtype.FLOAT),
        ("close", ColumnDtype.FLOAT),
        ("volume", ColumnDtype.FLOAT),
        ("vwap", ColumnDtype.FLOAT),
        ("notional_amount", ColumnDtype.FLOAT),
        ("trade_count", ColumnDtype.INT),
        ("available_at", ColumnDtype.INSTANT),
        ("availability_quality", ColumnDtype.STRING),
        ("warning_codes", ColumnDtype.JSON),
    ),
    ("interval_start", "instrument_id", "canonical_revision_id"),
)

TRADES_FRAME = _contract(
    "persistra.dataframe.trades",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("venue_id", ColumnDtype.STRING),
        ("source_id", ColumnDtype.STRING),
        ("source_trade_key", ColumnDtype.STRING),
        ("source_sequence", ColumnDtype.INT),
        ("event_at", ColumnDtype.INSTANT),
        ("available_at", ColumnDtype.INSTANT),
        ("availability_quality", ColumnDtype.STRING),
        ("currency", ColumnDtype.STRING),
        ("price", ColumnDtype.FLOAT),
        ("quantity", ColumnDtype.FLOAT),
        ("trade_condition_codes", ColumnDtype.JSON),
        ("raw_condition_codes", ColumnDtype.JSON),
        ("price_forming", ColumnDtype.BOOL),
        ("volume_forming", ColumnDtype.BOOL),
        ("extended_hours", ColumnDtype.BOOL),
        ("correction_reference_key", ColumnDtype.STRING),
    ),
    ("event_at", "source_sequence", "source_trade_key", "canonical_revision_id"),
)

QUOTES_FRAME = _contract(
    "persistra.dataframe.quotes",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("source_id", ColumnDtype.STRING),
        ("venue_id", ColumnDtype.STRING),
        ("bid_venue_id", ColumnDtype.STRING),
        ("ask_venue_id", ColumnDtype.STRING),
        ("source_quote_key", ColumnDtype.STRING),
        ("source_sequence", ColumnDtype.INT),
        ("event_at", ColumnDtype.INSTANT),
        ("available_at", ColumnDtype.INSTANT),
        ("availability_quality", ColumnDtype.STRING),
        ("quote_state", ColumnDtype.STRING),
        ("quote_scope", ColumnDtype.STRING),
        ("currency", ColumnDtype.STRING),
        ("bid_price", ColumnDtype.FLOAT),
        ("bid_size", ColumnDtype.FLOAT),
        ("ask_price", ColumnDtype.FLOAT),
        ("ask_size", ColumnDtype.FLOAT),
        ("spread", ColumnDtype.FLOAT),
        ("midpoint", ColumnDtype.FLOAT),
        ("locked", ColumnDtype.BOOL),
        ("crossed", ColumnDtype.BOOL),
        ("indicative", ColumnDtype.BOOL),
        ("quote_condition_codes", ColumnDtype.JSON),
        ("raw_condition_codes", ColumnDtype.JSON),
    ),
    ("event_at", "source_sequence", "source_quote_key", "canonical_revision_id"),
)

TRADING_STATUS_FRAME = _contract(
    "persistra.dataframe.trading_status",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("venue_id", ColumnDtype.STRING),
        ("source_id", ColumnDtype.STRING),
        ("source_status_key", ColumnDtype.STRING),
        ("source_sequence", ColumnDtype.INT),
        ("event_at", ColumnDtype.INSTANT),
        ("available_at", ColumnDtype.INSTANT),
        ("availability_quality", ColumnDtype.STRING),
        ("trading_status", ColumnDtype.STRING),
        ("status_reason_code", ColumnDtype.STRING),
        ("expected_resume_at", ColumnDtype.INSTANT),
        ("effective_to", ColumnDtype.INSTANT),
        ("source_condition_codes", ColumnDtype.JSON),
    ),
    ("event_at", "source_sequence", "canonical_revision_id"),
)

CORPORATE_ACTIONS_FRAME = _contract(
    "persistra.dataframe.corporate_actions",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("corporate_action_id", ColumnDtype.STRING),
        ("subject_security_id", ColumnDtype.STRING),
        ("subject_instrument_id", ColumnDtype.STRING),
        ("source_id", ColumnDtype.STRING),
        ("source_action_key", ColumnDtype.STRING),
        ("action_kind", ColumnDtype.STRING),
        ("action_status", ColumnDtype.STRING),
        ("announced_date", ColumnDtype.DATE),
        ("announced_at", ColumnDtype.INSTANT),
        ("declaration_date", ColumnDtype.DATE),
        ("ex_date", ColumnDtype.DATE),
        ("ex_at", ColumnDtype.INSTANT),
        ("record_date", ColumnDtype.DATE),
        ("payable_date", ColumnDtype.DATE),
        ("payment_at", ColumnDtype.INSTANT),
        ("effective_date", ColumnDtype.DATE),
        ("effective_at", ColumnDtype.INSTANT),
        ("expiration_date", ColumnDtype.DATE),
        ("share_ratio", ColumnDtype.FLOAT),
        ("terms_basis", ColumnDtype.STRING),
        ("available_at", ColumnDtype.INSTANT),
        ("availability_quality", ColumnDtype.STRING),
        ("action_fingerprint_content_id", ColumnDtype.STRING),
        ("resolution_method", ColumnDtype.STRING),
        ("safety_status", ColumnDtype.STRING),
    ),
    (
        "effective_at",
        "ex_at",
        "corporate_action_id",
        "canonical_revision_id",
    ),
)

ACTION_LEGS_FRAME = _contract(
    "persistra.dataframe.corporate_action_legs",
    (
        ("canonical_revision_id", ColumnDtype.STRING),
        ("corporate_action_id", ColumnDtype.STRING),
        ("leg_ordinal", ColumnDtype.INT),
        ("leg_kind", ColumnDtype.STRING),
        ("target_security_id", ColumnDtype.STRING),
        ("target_instrument_id", ColumnDtype.STRING),
        ("cash_per_subject_unit", ColumnDtype.FLOAT),
        ("quantity_per_subject_unit", ColumnDtype.FLOAT),
        ("currency", ColumnDtype.STRING),
        ("entitlement_code", ColumnDtype.STRING),
        ("terms_basis", ColumnDtype.STRING),
        ("leg_details", ColumnDtype.JSON),
    ),
    ("canonical_revision_id", "leg_ordinal"),
)

ADJUSTMENT_FACTORS_FRAME = _contract(
    "persistra.dataframe.adjustment_factors",
    (
        ("adjustment_materialization_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("corporate_action_ids", ColumnDtype.JSON),
        ("effective_at", ColumnDtype.INSTANT),
        ("factor_ordinal", ColumnDtype.INT),
        ("split_price_multiplier", ColumnDtype.FLOAT),
        ("cash_price_multiplier", ColumnDtype.FLOAT),
        ("volume_multiplier", ColumnDtype.FLOAT),
        ("cumulative_price_multiplier", ColumnDtype.FLOAT),
        ("cumulative_volume_multiplier", ColumnDtype.FLOAT),
        ("reference_price", ColumnDtype.FLOAT),
        ("input_revision_ids", ColumnDtype.JSON),
        ("evidence_content_id", ColumnDtype.STRING),
    ),
    ("instrument_id", "effective_at", "factor_ordinal"),
)

ADJUSTED_BARS_FRAME = _contract(
    "persistra.dataframe.adjusted_bars",
    (
        ("adjustment_materialization_id", ColumnDtype.STRING),
        ("raw_canonical_revision_id", ColumnDtype.STRING),
        ("instrument_id", ColumnDtype.STRING),
        ("interval_start", ColumnDtype.INSTANT),
        ("interval_end", ColumnDtype.INSTANT),
        ("session_date", ColumnDtype.DATE),
        ("adjusted_open", ColumnDtype.FLOAT),
        ("adjusted_high", ColumnDtype.FLOAT),
        ("adjusted_low", ColumnDtype.FLOAT),
        ("adjusted_close", ColumnDtype.FLOAT),
        ("adjusted_volume", ColumnDtype.FLOAT),
        ("adjusted_vwap", ColumnDtype.FLOAT),
        ("price_multiplier", ColumnDtype.FLOAT),
        ("volume_multiplier", ColumnDtype.FLOAT),
        ("adjustment_status", ColumnDtype.STRING),
        ("reason_codes", ColumnDtype.JSON),
        ("lineage_content_id", ColumnDtype.STRING),
    ),
    ("interval_start", "instrument_id", "raw_canonical_revision_id"),
)
