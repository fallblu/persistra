"""Project-owned daily market data and point-in-time adjustment services."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog import CompositeSnapshotRef
from persistra.catalog.services import advance_catalog, insert_event
from persistra.db import DatabaseRole, ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.domain.frames import build_frame
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    AdjustmentMaterializationError,
    AdjustmentPolicyError,
    BarSpecError,
    CapabilityUnavailableError,
    CorporateActionTermsError,
    MarketDataLimitError,
    MarketDataQueryError,
)
from persistra.market.frames import (
    ACTION_LEGS_FRAME,
    ADJUSTED_BARS_FRAME,
    ADJUSTMENT_FACTORS_FRAME,
    BARS_FRAME,
    CORPORATE_ACTIONS_FRAME,
    QUOTES_FRAME,
    TRADES_FRAME,
    TRADING_STATUS_FRAME,
)
from persistra.market.models import (
    AdjustmentKnowledgeMode,
    AdjustmentMaterializationId,
    AdjustmentPolicyDefinition,
    AdjustmentPolicyId,
    AdjustmentPolicyRef,
    AdjustmentPriceMode,
    AdjustmentRowStatus,
    AdjustmentViewRequest,
    BarAlignment,
    BarIntervalKind,
    BarQuery,
    BarSpecDefinition,
    BarSpecId,
    BarSpecRef,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionLeg,
    CorporateActionObservation,
    CorporateActionQuery,
    CorporateActionStatus,
    DailyBar,
    QuoteObservation,
    QuoteQuery,
    ResolvedAdjustmentPolicyRef,
    ResolvedBarSpecRef,
    TradeObservation,
    TradeQuery,
    TradingStatus,
    TradingStatusObservation,
    TradingStatusQuery,
)
from persistra.reference.models import AsOfContext, InstrumentId
from persistra.reference.services import cutoff_sql, market_for_context

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


def _occurrence_id(content_id: ContentId) -> UUID:
    return UUID(bytes=content_id.digest[:16])


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _insert_market_metadata(
    connection: Any,
    *,
    revision_id: UUID,
    source_id: UUID | None,
    event_at: datetime | None,
    available_at: datetime,
    availability_quality: str,
    ingested_at: datetime,
    catalog_sequence: int,
    content_id: ContentId,
) -> None:
    connection.execute(
        "INSERT INTO canonical.market_revision_metadata "
        "(canonical_revision_id, source_id, event_at, available_at, "
        "availability_quality, ingested_at, catalog_sequence, content_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            revision_id,
            source_id,
            event_at,
            available_at,
            availability_quality,
            ingested_at,
            catalog_sequence,
            str(content_id),
        ],
    )


class MarketService:
    """Canonical market-data and point-in-time adjustment capability group."""

    __slots__ = (
        "actions",
        "adjustment_policies",
        "adjustments",
        "bar_specs",
        "bars",
        "benchmarks",
        "estimates",
        "fundamentals",
        "macro",
        "quotes",
        "rates",
        "risk_free_curves",
        "status",
        "trades",
    )

    def __init__(self, project: Project) -> None:
        from persistra.market.economic_services import (
            BenchmarkService,
            EstimateService,
            FundamentalService,
            MacroService,
            RateService,
            RiskFreeCurveService,
        )

        self.bar_specs = BarSpecService(project)
        self.bars = BarService(project, self.bar_specs)
        self.trades = TradeService(project)
        self.quotes = QuoteService(project)
        self.status = TradingStatusService(project)
        self.actions = CorporateActionService(project)
        self.adjustment_policies = AdjustmentPolicyService(project)
        self.adjustments = AdjustmentService(
            project, self.bars, self.adjustment_policies
        )
        self.fundamentals = FundamentalService(project)
        self.estimates = EstimateService(project)
        self.macro = MacroService(project)
        self.benchmarks = BenchmarkService(project)
        self.risk_free_curves = RiskFreeCurveService(project)
        self.rates = RateService(project, self.risk_free_curves)


class BarSpecService:
    """Versioned session and fixed-grid bar specification registry."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: BarSpecDefinition) -> ResolvedBarSpecRef:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("bar spec registration requires market_write mode")
        content_id = scoped_content_id(
            {"schema": "persistra.market.bar_spec", "definition": definition}
        )

        def operation(context: TransactionContext) -> ResolvedBarSpecRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT bar_spec_id, definition_content_id, definition_json "
                "FROM canonical.bar_specs WHERE qualified_name = ? "
                "AND bar_spec_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            encoded = canonical_bytes(definition).decode()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded:
                    raise BarSpecError("bar spec version conflicts")
                return ResolvedBarSpecRef(
                    BarSpecId.parse(existing[0]), definition.version, content_id
                )
            prior = connection.execute(
                "SELECT bar_spec_id, bar_spec_version, interval_kind, nominal_interval_us "
                "FROM canonical.bar_specs WHERE qualified_name = ? "
                "ORDER BY bar_spec_version DESC LIMIT 1",
                [str(definition.name)],
            ).fetchone()
            if prior is not None and int(prior[1]) + 1 != definition.version:
                raise BarSpecError("bar spec versions must be contiguous")
            if prior is not None and (
                prior[2] != definition.interval_kind.value
                or prior[3]
                != (
                    None
                    if definition.nominal_interval is None
                    else definition.nominal_interval.microseconds
                )
            ):
                raise BarSpecError(
                    "bar interval-kind or duration changes require a new name"
                )
            spec_id = BarSpecId.new() if prior is None else BarSpecId.parse(prior[0])
            sequence = advance_catalog(
                connection,
                change_kind="market.bar_spec_registered",
                entity_id=spec_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.bar_specs "
                "(bar_spec_id, bar_spec_version, qualified_name, definition_content_id, "
                "definition_json, created_catalog_sequence, interval_kind, "
                "nominal_interval_us, alignment, phase, "
                "phase_boundary_policy_content_id, allow_short_final_interval) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    spec_id.value,
                    definition.version,
                    str(definition.name),
                    str(content_id),
                    encoded,
                    sequence,
                    definition.interval_kind.value,
                    (
                        None
                        if definition.nominal_interval is None
                        else definition.nominal_interval.microseconds
                    ),
                    definition.alignment.value,
                    definition.phase.value,
                    str(definition.phase_boundary_policy_content_id),
                    definition.allow_short_final_interval,
                ],
            )
            insert_event(
                connection,
                event_name="persistra.market_data.bar_spec_registered",
                aggregate_kind="persistra.aggregate.bar_spec",
                aggregate_id=spec_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,
                payload={"bar_spec_id": spec_id, "definition_content_id": content_id},
            )
            return ResolvedBarSpecRef(spec_id, definition.version, content_id)

        return self._project.services.transactions.run("bar_spec_register", operation)

    def resolve(self, reference: BarSpecRef, *, context: AsOfContext) -> ResolvedBarSpecRef:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT bar_spec_id, bar_spec_version, definition_content_id "
            "FROM canonical.bar_specs WHERE qualified_name = ? "
            "AND bar_spec_version = ? AND created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise BarSpecError("bar spec is not present in the snapshot")
        return ResolvedBarSpecRef(
            BarSpecId.parse(row[0]), int(row[1]), ContentId.parse(row[2])
        )


class BarService:
    """Raw daily bar ingestion and bounded point-in-time queries."""

    __slots__ = ("_project", "_specs")

    def __init__(self, project: Project, specs: BarSpecService) -> None:
        self._project = project
        self._specs = specs

    def ingest(self, bars: tuple[DailyBar, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("bar ingestion requires market_write mode")
        if not bars:
            raise MarketDataQueryError("bar ingestion requires at least one row")
        if len(
            {
                (
                    bar.instrument_id,
                    bar.spec.bar_spec_id,
                    bar.spec.version,
                    bar.interval_start,
                    bar.interval_end,
                    bar.scope,
                    bar.venue_id,
                )
                for bar in bars
            }
        ) != len(bars):
            raise MarketDataQueryError("bar batch contains duplicate natural keys")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identifiers: list[UUID] = []
            for bar in bars:
                spec = connection.execute(
                    "SELECT definition_content_id, interval_kind, nominal_interval_us, "
                    "alignment, phase, allow_short_final_interval "
                    "FROM canonical.bar_specs "
                    "WHERE bar_spec_id = ? AND bar_spec_version = ?",
                    [bar.spec.bar_spec_id.value, bar.spec.version],
                ).fetchone()
                if spec is None or spec[0] != str(bar.spec.definition_content_id):
                    raise BarSpecError("bar references an unknown specification")
                calendar = connection.execute(
                    "SELECT open_at, close_at, schedule_root_content_id "
                    "FROM canonical.calendar_dates d JOIN canonical.calendar_definitions c "
                    "USING (calendar_id, calendar_version) "
                    "WHERE calendar_id = ? AND calendar_version = ? "
                    "AND calendar_date = ? AND is_session",
                    [
                        bar.calendar.calendar_id.value,
                        bar.calendar.version,
                        bar.session_date,
                    ],
                ).fetchone()
                if calendar is None:
                    raise MarketDataQueryError("bar calendar session is unavailable")
                if str(bar.calendar_schedule_content_id) != calendar[2]:
                    raise MarketDataQueryError("bar calendar schedule identity conflicts")
                if spec[4] != bar.phase.value:
                    raise MarketDataQueryError("bar phase does not match its specification")
                if spec[1] == BarIntervalKind.SESSION.value:
                    if (calendar[0], calendar[1]) != (
                        bar.interval_start,
                        bar.interval_end,
                    ):
                        raise MarketDataQueryError(
                            "session bar is not aligned to its calendar"
                        )
                else:
                    self._validate_fixed_interval(
                        bar,
                        open_at=calendar[0],
                        close_at=calendar[1],
                        interval_us=int(spec[2]),
                        alignment=BarAlignment(spec[3]),
                        allow_short_final=bool(spec[5]),
                    )
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.market.bar",
                        "instrument_id": bar.instrument_id,
                        "spec": bar.spec,
                        "calendar": bar.calendar,
                        "interval_start": bar.interval_start,
                        "interval_end": bar.interval_end,
                        "session_date": bar.session_date,
                        "state": bar.state,
                        "currency": bar.currency,
                        "open": _decimal_text(bar.open),
                        "high": _decimal_text(bar.high),
                        "low": _decimal_text(bar.low),
                        "close": _decimal_text(bar.close),
                        "volume": _decimal_text(bar.volume),
                        "trade_count": bar.trade_count,
                        "available_at": bar.available_at,
                        "observed_through_at": bar.observed_through_at,
                        "scope": bar.scope,
                        "venue_id": bar.venue_id,
                        "aggregation_name": bar.aggregation_name,
                        "aggregation_version": bar.aggregation_version,
                        "aggregation_content_id": bar.aggregation_content_id,
                        "phase": bar.phase,
                        "calendar_schedule_content_id": (
                            bar.calendar_schedule_content_id
                        ),
                        "vwap": _decimal_text(bar.vwap),
                        "notional_amount": _decimal_text(bar.notional_amount),
                        "source_condition_codes": bar.source_condition_codes,
                        "source_id": bar.source_id,
                        "availability_quality": bar.availability_quality,
                    }
                )
                existing = connection.execute(
                    "SELECT canonical_revision_id FROM "
                    "canonical.market_revision_metadata WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    identifiers.append(existing[0])
                    continue
                revision_id = (
                    _occurrence_id(content_id)
                    if bar.canonical_revision_id is None
                    else bar.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind="market.bar_ingested",
                    entity_id=bar.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.bars "
                    "(bar_id, instrument_id, bar_spec_id, bar_spec_version, "
                    "interval_start, interval_end, session_date, bar_state, currency, "
                    "open_price, high_price, low_price, close_price, volume, trade_count, "
                    "available_at, ingested_at, catalog_sequence, content_id, "
                    "canonical_revision_id, observation_scope, venue_id, aggregation_name, "
                    "aggregation_version, aggregation_content_id, observed_through_at, "
                    "bar_phase, calendar_schedule_content_id, vwap, notional_amount, "
                    "source_condition_codes_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        revision_id,
                        bar.instrument_id.value,
                        bar.spec.bar_spec_id.value,
                        bar.spec.version,
                        bar.interval_start,
                        bar.interval_end,
                        bar.session_date,
                        bar.state.value,
                        bar.currency,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        bar.trade_count,
                        bar.available_at,
                        context.recorded_at,
                        sequence,
                        str(content_id),
                        revision_id,
                        bar.scope.value,
                        None if bar.venue_id is None else bar.venue_id.value,
                        (
                            None
                            if bar.aggregation_name is None
                            else str(bar.aggregation_name)
                        ),
                        bar.aggregation_version,
                        (
                            None
                            if bar.aggregation_content_id is None
                            else str(bar.aggregation_content_id)
                        ),
                        bar.observed_through_at,
                        bar.phase.value,
                        str(bar.calendar_schedule_content_id),
                        bar.vwap,
                        bar.notional_amount,
                        _canonical_json(list(bar.source_condition_codes)),
                    ],
                )
                _insert_market_metadata(
                    connection,
                    revision_id=revision_id,
                    source_id=(
                        None if bar.source_id is None else bar.source_id.value
                    ),
                    event_at=bar.observed_through_at,
                    available_at=bar.available_at,
                    availability_quality=bar.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=content_id,
                )
                identifiers.append(revision_id)
            return tuple(identifiers)

        return self._project.services.transactions.run("daily_bars_ingest", operation)

    @staticmethod
    def _validate_fixed_interval(
        bar: DailyBar,
        *,
        open_at: datetime,
        close_at: datetime,
        interval_us: int,
        alignment: BarAlignment,
        allow_short_final: bool,
    ) -> None:
        if bar.interval_start < open_at or bar.interval_end > close_at:
            raise MarketDataQueryError("fixed bar crosses its calendar phase")
        duration_us = int(
            (bar.interval_end - bar.interval_start).total_seconds() * 1_000_000
        )
        is_short_final = (
            allow_short_final
            and bar.interval_end == close_at
            and 0 < duration_us < interval_us
        )
        if duration_us != interval_us and not is_short_final:
            raise MarketDataQueryError("fixed bar duration is off grid")
        origin = open_at if alignment is BarAlignment.SESSION_OPEN else datetime.fromtimestamp(
            0, tz=bar.interval_start.tzinfo
        )
        offset_us = int((bar.interval_start - origin).total_seconds() * 1_000_000)
        if offset_us % interval_us:
            raise MarketDataQueryError("fixed bar start is off grid")

    def query(self, query: BarQuery) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, query.context)
        spec = self._specs.resolve(query.spec, context=query.context)
        cutoff_clause, cutoff_parameters = cutoff_sql(query.context)
        states = [BarState.COMPLETE.value]
        if query.include_partial:
            states.append(BarState.PARTIAL.value)
        if query.include_no_trade:
            states.append(BarState.NO_TRADE.value)
        parameters: list[Any] = [
            spec.bar_spec_id.value,
            spec.version,
            [item.value for item in query.instruments],
            query.start,
            query.end,
            query.scope.value,
            *cutoff_parameters,
            sequence,
            states,
            query.max_rows + 1,
        ]
        rows = opened.connection.execute(
            "SELECT b.canonical_revision_id, b.instrument_id, b.bar_spec_id, "
            "b.bar_spec_version, m.source_id, b.observation_scope, b.venue_id, "
            "b.aggregation_name, b.aggregation_version, b.aggregation_content_id, "
            "b.interval_start, b.interval_end, b.observed_through_at, b.session_date, "
            "b.bar_phase, b.calendar_schedule_content_id, b.bar_state, b.currency, "
            "b.open_price, b.high_price, b.low_price, b.close_price, b.volume, b.vwap, "
            "b.notional_amount, b.trade_count, m.available_at, m.availability_quality "
            "FROM canonical.bars b JOIN canonical.market_revision_metadata m "
            "USING (canonical_revision_id) "
            "WHERE b.bar_spec_id = ? AND b.bar_spec_version = ? "
            "AND b.instrument_id IN (SELECT unnest(?)) AND b.interval_start >= ? "
            "AND b.interval_end <= ? AND b.observation_scope = ? "
            f"AND m.{cutoff_clause.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? "
            "AND bar_state IN (SELECT unnest(?)) "
            "QUALIFY row_number() OVER (PARTITION BY b.instrument_id, b.interval_start, "
            "b.interval_end, b.observation_scope, b.venue_id, b.aggregation_name "
            "ORDER BY m.catalog_sequence DESC, b.canonical_revision_id) = 1 "
            "ORDER BY b.interval_start, b.instrument_id, b.canonical_revision_id LIMIT ?",
            parameters,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("bar query exceeds its row ceiling")
        records: list[dict[str, Any]] = [
            {
                "canonical_revision_id": str(row[0]),
                "instrument_id": str(row[1]),
                "bar_spec_id": str(row[2]),
                "bar_spec_version": int(row[3]),
                "source_id": None if row[4] is None else str(row[4]),
                "observation_scope": row[5],
                "venue_id": None if row[6] is None else str(row[6]),
                "aggregation_name": row[7],
                "aggregation_version": row[8],
                "aggregation_content_id": row[9],
                "interval_start": row[10],
                "interval_end": row[11],
                "observed_through_at": row[12],
                "session_date": row[13],
                "bar_phase": row[14],
                "calendar_schedule_content_id": row[15],
                "bar_state": row[16],
                "currency": row[17],
                "open": None if row[18] is None else float(row[18]),
                "high": None if row[19] is None else float(row[19]),
                "low": None if row[20] is None else float(row[20]),
                "close": None if row[21] is None else float(row[21]),
                "volume": float(row[22]),
                "vwap": None if row[23] is None else float(row[23]),
                "notional_amount": None if row[24] is None else float(row[24]),
                "trade_count": None if row[25] is None else int(row[25]),
                "available_at": row[26],
                "availability_quality": row[27],
                "warning_codes": [],
            }
            for row in rows
        ]
        return build_frame(BARS_FRAME, records)

    def classify_at(
        self,
        instrument: InstrumentId,
        decision_at: datetime,
        *,
        spec: BarSpecRef,
        context: AsOfContext,
    ) -> dict[str, Any]:
        query = BarQuery(
            (instrument,),
            spec,
            datetime.min.replace(tzinfo=decision_at.tzinfo),
            decision_at,
            context,
            include_no_trade=True,
            max_rows=1_000_000,
        )
        frame = self.query(query)
        if frame.empty:
            return {"state": "missing", "reason_code": "market.price.missing"}
        row = frame.iloc[-1]
        if row["bar_state"] == BarState.NO_TRADE.value:
            return {"state": "no_trade", "reason_code": "market.price.no_trade"}
        return {
            "state": "selected",
            "reason_code": "market.price.selected",
            "canonical_revision_id": row["canonical_revision_id"],
            "close": row["close"],
        }


class TradeService:
    """Executed-trade ingestion and bounded point-in-time queries."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, observations: tuple[TradeObservation, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("trade ingestion requires market_write mode")
        if not observations:
            raise MarketDataQueryError("trade ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identifiers: list[UUID] = []
            for observation in observations:
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.market.trade",
                        "source_trade_key": observation.source_trade_key,
                        "instrument_id": observation.instrument_id,
                        "venue_id": observation.venue_id,
                        "event_at": observation.event_at,
                        "available_at": observation.available_at,
                        "source_sequence": observation.source_sequence,
                        "price": _decimal_text(observation.price),
                        "quantity": _decimal_text(observation.quantity),
                        "currency": observation.currency,
                        "trade_condition_codes": observation.trade_condition_codes,
                        "raw_condition_codes": observation.raw_condition_codes,
                        "price_forming": observation.price_forming,
                        "volume_forming": observation.volume_forming,
                        "extended_hours": observation.extended_hours,
                        "correction_reference_key": (
                            observation.correction_reference_key
                        ),
                        "source_id": observation.source_id,
                    }
                )
                existing = connection.execute(
                    "SELECT canonical_revision_id FROM "
                    "canonical.market_revision_metadata WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    identifiers.append(existing[0])
                    continue
                source_id = (
                    None
                    if observation.source_id is None
                    else observation.source_id.value
                )
                conflict = connection.execute(
                    "SELECT t.source_trade_key FROM canonical.trades t "
                    "JOIN canonical.market_revision_metadata m "
                    "USING (canonical_revision_id) "
                    "WHERE m.source_id IS NOT DISTINCT FROM ? "
                    "AND t.source_sequence = ? AND t.source_trade_key <> ? LIMIT 1",
                    [
                        source_id,
                        observation.source_sequence,
                        observation.source_trade_key,
                    ],
                ).fetchone()
                if conflict is not None:
                    raise MarketDataQueryError("trade source sequence conflicts")
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind="market.trade_ingested",
                    entity_id=observation.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.trades VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        revision_id,
                        observation.source_trade_key,
                        observation.instrument_id.value,
                        observation.venue_id.value,
                        observation.currency,
                        observation.source_sequence,
                        observation.price,
                        observation.quantity,
                        _canonical_json(list(observation.trade_condition_codes)),
                        _canonical_json(list(observation.raw_condition_codes)),
                        observation.price_forming,
                        observation.volume_forming,
                        observation.extended_hours,
                        observation.correction_reference_key,
                    ],
                )
                _insert_market_metadata(
                    connection,
                    revision_id=revision_id,
                    source_id=source_id,
                    event_at=observation.event_at,
                    available_at=observation.available_at,
                    availability_quality=observation.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=content_id,
                )
                identifiers.append(revision_id)
            return tuple(identifiers)

        return self._project.services.transactions.run("trades_ingest", operation)

    def query(
        self,
        query: TradeQuery | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        if query is None:
            query = TradeQuery(**kwargs)
        opened, sequence = market_for_context(self._project, query.context)
        cutoff_clause, cutoff_parameters = cutoff_sql(query.context)
        predicates = [
            "t.instrument_id IN (SELECT unnest(?))",
            "m.event_at >= ?",
            "m.event_at < ?",
            f"m.{cutoff_clause.replace(' AND ', ' AND m.')}",
            "m.catalog_sequence <= ?",
        ]
        parameters: list[Any] = [
            [item.value for item in query.instruments],
            query.start,
            query.end,
            *cutoff_parameters,
            sequence,
        ]
        if query.venue_ids:
            predicates.append("t.venue_id IN (SELECT unnest(?))")
            parameters.append([item.value for item in query.venue_ids])
        for column, value in (
            ("price_forming", query.price_forming),
            ("volume_forming", query.volume_forming),
            ("extended_hours", query.extended_hours),
        ):
            if value is not None:
                predicates.append(f"t.{column} = ?")
                parameters.append(value)
        parameters.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT t.canonical_revision_id, t.instrument_id, t.venue_id, m.source_id, "
            "t.source_trade_key, t.source_sequence, m.event_at, m.available_at, "
            "m.availability_quality, t.currency, t.price, t.quantity, "
            "t.trade_condition_codes_json, t.raw_condition_codes_json, "
            "t.price_forming, t.volume_forming, t.extended_hours, "
            "t.correction_reference_key FROM canonical.trades t "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY m.event_at, t.source_sequence, t.source_trade_key, "
            "t.canonical_revision_id LIMIT ?",
            parameters,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("trade query exceeds its row ceiling")
        records = [
            {
                "canonical_revision_id": str(row[0]),
                "instrument_id": str(row[1]),
                "venue_id": str(row[2]),
                "source_id": None if row[3] is None else str(row[3]),
                "source_trade_key": row[4],
                "source_sequence": int(row[5]),
                "event_at": row[6],
                "available_at": row[7],
                "availability_quality": row[8],
                "currency": row[9],
                "price": float(row[10]),
                "quantity": float(row[11]),
                "trade_condition_codes": row[12],
                "raw_condition_codes": row[13],
                "price_forming": bool(row[14]),
                "volume_forming": bool(row[15]),
                "extended_hours": bool(row[16]),
                "correction_reference_key": row[17],
            }
            for row in rows
        ]
        return build_frame(TRADES_FRAME, records)

    def iter_chunks(self, query: TradeQuery) -> Any:
        frame = self.query(query)
        for offset in range(0, len(frame), query.chunk_rows):
            yield frame.iloc[offset : offset + query.chunk_rows].reset_index(drop=True)


class QuoteService:
    """Top-of-book quote ingestion and bounded point-in-time queries."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, observations: tuple[QuoteObservation, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("quote ingestion requires market_write mode")
        if not observations:
            raise MarketDataQueryError("quote ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identifiers: list[UUID] = []
            for observation in observations:
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.market.quote",
                        "source_quote_key": observation.source_quote_key,
                        "instrument_id": observation.instrument_id,
                        "event_at": observation.event_at,
                        "available_at": observation.available_at,
                        "source_sequence": observation.source_sequence,
                        "state": observation.state,
                        "scope": observation.scope,
                        "venue_id": observation.venue_id,
                        "bid_venue_id": observation.bid_venue_id,
                        "ask_venue_id": observation.ask_venue_id,
                        "currency": observation.currency,
                        "bid_price": _decimal_text(observation.bid_price),
                        "bid_size": _decimal_text(observation.bid_size),
                        "ask_price": _decimal_text(observation.ask_price),
                        "ask_size": _decimal_text(observation.ask_size),
                        "quote_condition_codes": observation.quote_condition_codes,
                        "raw_condition_codes": observation.raw_condition_codes,
                        "indicative": observation.indicative,
                        "source_id": observation.source_id,
                    }
                )
                existing = connection.execute(
                    "SELECT canonical_revision_id FROM "
                    "canonical.market_revision_metadata WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    identifiers.append(existing[0])
                    continue
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind="market.quote_ingested",
                    entity_id=observation.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.quotes VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        revision_id,
                        observation.source_quote_key,
                        observation.instrument_id.value,
                        observation.state.value,
                        observation.scope.value,
                        (
                            None
                            if observation.venue_id is None
                            else observation.venue_id.value
                        ),
                        (
                            None
                            if observation.bid_venue_id is None
                            else observation.bid_venue_id.value
                        ),
                        (
                            None
                            if observation.ask_venue_id is None
                            else observation.ask_venue_id.value
                        ),
                        observation.currency,
                        observation.source_sequence,
                        observation.bid_price,
                        observation.bid_size,
                        observation.ask_price,
                        observation.ask_size,
                        _canonical_json(list(observation.quote_condition_codes)),
                        _canonical_json(list(observation.raw_condition_codes)),
                        observation.indicative,
                    ],
                )
                _insert_market_metadata(
                    connection,
                    revision_id=revision_id,
                    source_id=(
                        None
                        if observation.source_id is None
                        else observation.source_id.value
                    ),
                    event_at=observation.event_at,
                    available_at=observation.available_at,
                    availability_quality=observation.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=content_id,
                )
                identifiers.append(revision_id)
            return tuple(identifiers)

        return self._project.services.transactions.run("quotes_ingest", operation)

    def query(
        self,
        query: QuoteQuery | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        if query is None:
            query = QuoteQuery(**kwargs)
        opened, sequence = market_for_context(self._project, query.context)
        cutoff_clause, cutoff_parameters = cutoff_sql(query.context)
        parameters: list[Any] = [
            [item.value for item in query.instruments],
            query.scope.value,
            query.start,
            query.end,
            *cutoff_parameters,
            sequence,
        ]
        indicative = "" if query.include_indicative else "AND NOT q.indicative "
        parameters.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT q.canonical_revision_id, q.instrument_id, m.source_id, q.venue_id, "
            "q.bid_venue_id, q.ask_venue_id, q.source_quote_key, q.source_sequence, "
            "m.event_at, m.available_at, m.availability_quality, q.quote_state, "
            "q.quote_scope, q.currency, q.bid_price, q.bid_size, q.ask_price, q.ask_size, "
            "q.indicative, q.quote_condition_codes_json, q.raw_condition_codes_json "
            "FROM canonical.quotes q JOIN canonical.market_revision_metadata m "
            "USING (canonical_revision_id) "
            "WHERE q.instrument_id IN (SELECT unnest(?)) AND q.quote_scope = ? "
            f"AND m.event_at >= ? AND m.event_at < ? AND "
            f"m.{cutoff_clause.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? {indicative}"
            "ORDER BY m.event_at, q.source_sequence, q.source_quote_key, "
            "q.canonical_revision_id LIMIT ?",
            parameters,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("quote query exceeds its row ceiling")
        records: list[dict[str, Any]] = []
        for row in rows:
            bid = None if row[14] is None else float(row[14])
            ask = None if row[16] is None else float(row[16])
            spread = None if bid is None or ask is None else ask - bid
            midpoint = None if bid is None or ask is None else (ask + bid) / 2.0
            records.append(
                {
                    "canonical_revision_id": str(row[0]),
                    "instrument_id": str(row[1]),
                    "source_id": None if row[2] is None else str(row[2]),
                    "venue_id": None if row[3] is None else str(row[3]),
                    "bid_venue_id": None if row[4] is None else str(row[4]),
                    "ask_venue_id": None if row[5] is None else str(row[5]),
                    "source_quote_key": row[6],
                    "source_sequence": int(row[7]),
                    "event_at": row[8],
                    "available_at": row[9],
                    "availability_quality": row[10],
                    "quote_state": row[11],
                    "quote_scope": row[12],
                    "currency": row[13],
                    "bid_price": bid,
                    "bid_size": None if row[15] is None else float(row[15]),
                    "ask_price": ask,
                    "ask_size": None if row[17] is None else float(row[17]),
                    "spread": spread,
                    "midpoint": midpoint,
                    "locked": None if spread is None else spread == 0,
                    "crossed": None if spread is None else spread < 0,
                    "indicative": bool(row[18]),
                    "quote_condition_codes": row[19],
                    "raw_condition_codes": row[20],
                }
            )
        return build_frame(QUOTES_FRAME, records)

    def iter_chunks(self, query: QuoteQuery) -> Any:
        frame = self.query(query)
        for offset in range(0, len(frame), query.chunk_rows):
            yield frame.iloc[offset : offset + query.chunk_rows].reset_index(drop=True)


class TradingStatusService:
    """Orthogonal trading-status observation service."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(self, observations: tuple[TradingStatusObservation, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("status ingestion requires market_write mode")
        if not observations:
            raise MarketDataQueryError("status ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            for observation in observations:
                content_id = scoped_content_id(
                    {"schema": "persistra.market.trading_status", "value": observation}
                )
                existing = connection.execute(
                    "SELECT canonical_revision_id FROM "
                    "canonical.market_revision_metadata WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    result.append(existing[0])
                    continue
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind="market.trading_status_ingested",
                    entity_id=observation.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.trading_status_observations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        revision_id,
                        observation.source_status_key or str(revision_id),
                        observation.instrument_id.value,
                        (
                            None
                            if observation.venue_id is None
                            else observation.venue_id.value
                        ),
                        observation.source_sequence,
                        observation.status.value,
                        observation.status_reason_code,
                        observation.expected_resume_at,
                        _canonical_json(list(observation.source_condition_codes)),
                        observation.effective_to,
                    ],
                )
                _insert_market_metadata(
                    connection,
                    revision_id=revision_id,
                    source_id=(
                        None
                        if observation.source_id is None
                        else observation.source_id.value
                    ),
                    event_at=observation.effective_at,
                    available_at=observation.available_at,
                    availability_quality=observation.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=content_id,
                )
                result.append(revision_id)
            return tuple(result)

        return self._project.services.transactions.run("trading_status_ingest", operation)

    def at(
        self,
        instrument: InstrumentId,
        instant: datetime,
        *,
        context: AsOfContext,
    ) -> TradingStatus | None:
        opened, sequence = market_for_context(self._project, context)
        cutoff_clause, parameters = cutoff_sql(context)
        row = opened.connection.execute(
            "SELECT s.trading_status FROM canonical.trading_status_observations s "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE s.instrument_id = ? AND m.event_at <= ? "
            "AND (s.effective_to IS NULL OR ? < s.effective_to) "
            f"AND m.{cutoff_clause.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? "
            "ORDER BY m.event_at DESC, s.source_sequence DESC, "
            "s.canonical_revision_id LIMIT 1",
            [instrument.value, instant, instant, *parameters, sequence],
        ).fetchone()
        return None if row is None else TradingStatus(row[0])

    def query(self, query: TradingStatusQuery) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, query.context)
        cutoff_clause, parameters = cutoff_sql(query.context)
        predicates = [
            "s.instrument_id IN (SELECT unnest(?))",
            "m.event_at >= ?",
            "m.event_at < ?",
            f"m.{cutoff_clause.replace(' AND ', ' AND m.')}",
            "m.catalog_sequence <= ?",
        ]
        values: list[Any] = [
            [item.value for item in query.instruments],
            query.start,
            query.end,
            *parameters,
            sequence,
        ]
        if query.venue_ids:
            predicates.append("s.venue_id IN (SELECT unnest(?))")
            values.append([item.value for item in query.venue_ids])
        values.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT s.canonical_revision_id, s.instrument_id, s.venue_id, m.source_id, "
            "s.source_status_key, s.source_sequence, m.event_at, m.available_at, "
            "m.availability_quality, s.trading_status, s.status_reason_code, "
            "s.expected_resume_at, s.effective_to, s.source_condition_codes_json "
            "FROM canonical.trading_status_observations s "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY m.event_at, s.source_sequence, s.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("status query exceeds its row ceiling")
        return build_frame(
            TRADING_STATUS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "instrument_id": str(row[1]),
                    "venue_id": None if row[2] is None else str(row[2]),
                    "source_id": None if row[3] is None else str(row[3]),
                    "source_status_key": row[4],
                    "source_sequence": int(row[5]),
                    "event_at": row[6],
                    "available_at": row[7],
                    "availability_quality": row[8],
                    "trading_status": row[9],
                    "status_reason_code": row[10],
                    "expected_resume_at": row[11],
                    "effective_to": row[12],
                    "source_condition_codes": row[13],
                }
                for row in rows
            ],
        )


class CorporateActionService:
    """Resolved corporate-action observations and ordered economic legs."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest(
        self, observations: tuple[CorporateActionObservation, ...]
    ) -> tuple[CorporateActionId, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("action ingestion requires market_write mode")
        if not observations:
            raise CorporateActionTermsError("action ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[CorporateActionId, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[CorporateActionId] = []
            for observation in observations:
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.market.corporate_action",
                        "action_id": observation.action_id,
                        "kind": observation.kind,
                        "subject_security_id": observation.subject_security_id,
                        "subject_instrument_id": observation.subject_instrument_id,
                        "status": observation.status,
                        "available_at": observation.available_at,
                        "ex_at": observation.ex_at,
                        "effective_at": observation.effective_at,
                        "share_ratio": _decimal_text(observation.share_ratio),
                        "cash_per_subject_unit": _decimal_text(
                            observation.cash_per_subject_unit
                        ),
                        "currency": observation.currency,
                    }
                )
                existing_observation = connection.execute(
                    "SELECT 1 FROM canonical.market_revision_metadata "
                    "WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing_observation is not None:
                    result.append(observation.action_id)
                    continue
                master = connection.execute(
                    "SELECT action_kind, subject_security_id, subject_instrument_id "
                    "FROM canonical.corporate_actions WHERE corporate_action_id = ?",
                    [observation.action_id.value],
                ).fetchone()
                expected = (
                    observation.kind.value,
                    observation.subject_security_id.value,
                    None
                    if observation.subject_instrument_id is None
                    else observation.subject_instrument_id.value,
                )
                if master is None:
                    sequence = advance_catalog(
                        connection,
                        change_kind="market.corporate_action_created",
                        entity_id=observation.action_id,
                        change_content_id=content_id,
                        recorded_at=context.recorded_at,
                    )
                    connection.execute(
                        "INSERT INTO canonical.corporate_actions VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            observation.action_id.value,
                            *expected,
                            sequence,
                            context.recorded_at,
                        ],
                    )
                    insert_event(
                        connection,
                        event_name="persistra.corporate_action.created",
                        aggregate_kind="persistra.aggregate.corporate_action",
                        aggregate_id=observation.action_id,
                        aggregate_sequence=1,
                        recorded_at=context.recorded_at,
                        payload={"corporate_action_id": observation.action_id},
                    )
                elif master != expected:
                    raise CorporateActionTermsError(
                        "corporate action identity relationships are immutable"
                    )
                else:
                    sequence = advance_catalog(
                        connection,
                        change_kind="market.corporate_action_ingested",
                        entity_id=observation.action_id,
                        change_content_id=content_id,
                        recorded_at=context.recorded_at,
                    )
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                connection.execute(
                    "INSERT INTO canonical.corporate_action_observations "
                    "(observation_id, corporate_action_id, action_status, ex_at, "
                    "effective_at, share_ratio, cash_per_subject_unit, currency, "
                    "available_at, ingested_at, catalog_sequence, content_id, "
                    "canonical_revision_id, source_action_key, resolution_method, "
                    "resolution_evidence_content_id, announced_date, announced_at, "
                    "declaration_date, ex_date, record_date, payable_date, payment_at, "
                    "effective_date, expiration_date, terms_basis, date_policy_content_id, "
                    "calendar_schedule_content_id, action_fingerprint_content_id, "
                    "reference_revision_ids_json, source_terms_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        revision_id,
                        observation.action_id.value,
                        observation.status.value,
                        observation.ex_at,
                        observation.effective_at,
                        observation.share_ratio,
                        observation.cash_per_subject_unit,
                        observation.currency,
                        observation.available_at,
                        context.recorded_at,
                        sequence,
                        str(content_id),
                        revision_id,
                        observation.source_action_key or str(revision_id),
                        observation.resolution_method,
                        str(observation.resolution_evidence_content_id),
                        observation.announced_date,
                        observation.announced_at,
                        observation.declaration_date,
                        observation.ex_date,
                        observation.record_date,
                        observation.payable_date,
                        observation.payment_at,
                        observation.effective_date,
                        observation.expiration_date,
                        observation.terms_basis,
                        str(observation.date_policy_content_id),
                        (
                            None
                            if observation.calendar_schedule_content_id is None
                            else str(observation.calendar_schedule_content_id)
                        ),
                        str(observation.action_fingerprint_content_id),
                        _canonical_json(list(observation.reference_revision_ids)),
                        _canonical_json(dict(observation.source_terms)),
                    ],
                )
                for leg in self._legs(observation):
                    connection.execute(
                        "INSERT INTO canonical.corporate_action_legs VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            revision_id,
                            leg.ordinal,
                            leg.kind.value,
                            (
                                None
                                if leg.target_security_id is None
                                else leg.target_security_id.value
                            ),
                            (
                                None
                                if leg.target_instrument_id is None
                                else leg.target_instrument_id.value
                            ),
                            leg.cash_per_subject_unit,
                            leg.quantity_per_subject_unit,
                            leg.currency,
                            leg.entitlement_code,
                            leg.terms_basis,
                            _canonical_json(dict(leg.details)),
                        ],
                    )
                _insert_market_metadata(
                    connection,
                    revision_id=revision_id,
                    source_id=(
                        None
                        if observation.source_id is None
                        else observation.source_id.value
                    ),
                    event_at=observation.announced_at,
                    available_at=observation.available_at,
                    availability_quality=observation.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=content_id,
                )
                result.append(observation.action_id)
            return tuple(result)

        return self._project.services.transactions.run("corporate_actions_ingest", operation)

    @staticmethod
    def _legs(observation: CorporateActionObservation) -> tuple[CorporateActionLeg, ...]:
        if observation.legs:
            return observation.legs
        if observation.cash_per_subject_unit is not None:
            from persistra.market.models import ActionLegKind

            return (
                CorporateActionLeg(
                    1,
                    ActionLegKind.CASH,
                    cash_per_subject_unit=observation.cash_per_subject_unit,
                    currency=observation.currency,
                    terms_basis=observation.terms_basis or "pre_action",
                ),
            )
        return ()

    def query(
        self,
        query: CorporateActionQuery | tuple[InstrumentId, ...],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        context: AsOfContext | None = None,
    ) -> pd.DataFrame:
        if isinstance(query, tuple):
            if start is None or end is None or context is None:
                raise MarketDataQueryError("action query range and context are required")
            request = CorporateActionQuery(query, start, end, context)
        else:
            request = query
        opened, sequence = market_for_context(self._project, request.context)
        cutoff_clause, parameters = cutoff_sql(request.context)
        status_clause = ""
        values: list[Any] = [
            [item.value for item in request.instruments],
            request.start,
            request.end,
            *parameters,
            sequence,
        ]
        if request.statuses:
            status_clause = "AND o.action_status IN (SELECT unnest(?)) "
            values.append([item.value for item in request.statuses])
        values.append(request.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT o.canonical_revision_id, a.corporate_action_id, "
            "a.subject_security_id, a.subject_instrument_id, m.source_id, "
            "o.source_action_key, a.action_kind, o.action_status, o.announced_date, "
            "o.announced_at, o.declaration_date, o.ex_date, o.ex_at, o.record_date, "
            "o.payable_date, o.payment_at, o.effective_date, o.effective_at, "
            "o.expiration_date, o.share_ratio, o.terms_basis, m.available_at, "
            "m.availability_quality, o.action_fingerprint_content_id, "
            "o.resolution_method "
            "FROM canonical.corporate_actions a JOIN "
            "canonical.corporate_action_observations o USING (corporate_action_id) "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE a.subject_instrument_id IN (SELECT unnest(?)) "
            "AND coalesce(o.effective_at, o.ex_at) >= ? "
            f"AND coalesce(o.effective_at, o.ex_at) < ? "
            f"AND m.{cutoff_clause.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? {status_clause}"
            "QUALIFY row_number() OVER (PARTITION BY a.corporate_action_id "
            "ORDER BY m.catalog_sequence DESC, o.canonical_revision_id) = 1 "
            "ORDER BY o.effective_at NULLS LAST, o.ex_at NULLS LAST, "
            "a.corporate_action_id, o.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > request.max_rows:
            raise MarketDataLimitError("action query exceeds its row ceiling")
        return build_frame(
            CORPORATE_ACTIONS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "corporate_action_id": str(row[1]),
                    "subject_security_id": str(row[2]),
                    "subject_instrument_id": (
                        None if row[3] is None else str(row[3])
                    ),
                    "source_id": None if row[4] is None else str(row[4]),
                    "source_action_key": row[5],
                    "action_kind": row[6],
                    "action_status": row[7],
                    "announced_date": row[8],
                    "announced_at": row[9],
                    "declaration_date": row[10],
                    "ex_date": row[11],
                    "ex_at": row[12],
                    "record_date": row[13],
                    "payable_date": row[14],
                    "payment_at": row[15],
                    "effective_date": row[16],
                    "effective_at": row[17],
                    "expiration_date": row[18],
                    "share_ratio": None if row[19] is None else float(row[19]),
                    "terms_basis": row[20],
                    "available_at": row[21],
                    "availability_quality": row[22],
                    "action_fingerprint_content_id": row[23],
                    "resolution_method": row[24],
                    "safety_status": (
                        "safe"
                        if row[22] in {"observed", "policy_derived"}
                        else "unsafe"
                    ),
                }
                for row in rows
            ],
        )

    def legs(self, revision_ids: tuple[UUID, ...]) -> pd.DataFrame:
        if not revision_ids:
            return build_frame(ACTION_LEGS_FRAME, [])
        markets = [
            item
            for item in self._project._databases  # pyright: ignore[reportPrivateUsage]
            if item.metadata.role is DatabaseRole.MARKET
        ]
        if len(markets) != 1:
            raise MarketDataQueryError(
                "action-leg lookup requires exactly one open market database"
            )
        opened = markets[0]
        rows = opened.connection.execute(
            "SELECT l.canonical_revision_id, o.corporate_action_id, l.leg_ordinal, "
            "l.leg_kind, l.target_security_id, l.target_instrument_id, "
            "l.cash_per_subject_unit, l.quantity_per_subject_unit, l.currency, "
            "l.entitlement_code, l.terms_basis, l.leg_details_json "
            "FROM canonical.corporate_action_legs l JOIN "
            "canonical.corporate_action_observations o USING (canonical_revision_id) "
            "WHERE l.canonical_revision_id IN (SELECT unnest(?)) "
            "ORDER BY l.canonical_revision_id, l.leg_ordinal",
            [list(revision_ids)],
        ).fetchall()
        return build_frame(
            ACTION_LEGS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "corporate_action_id": str(row[1]),
                    "leg_ordinal": int(row[2]),
                    "leg_kind": row[3],
                    "target_security_id": None if row[4] is None else str(row[4]),
                    "target_instrument_id": None if row[5] is None else str(row[5]),
                    "cash_per_subject_unit": (
                        None if row[6] is None else float(row[6])
                    ),
                    "quantity_per_subject_unit": (
                        None if row[7] is None else float(row[7])
                    ),
                    "currency": row[8],
                    "entitlement_code": row[9],
                    "terms_basis": row[10],
                    "leg_details": row[11],
                }
                for row in rows
            ],
        )


class AdjustmentPolicyService:
    """Immutable adjustment-policy registry owned by the research database."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: AdjustmentPolicyDefinition
    ) -> ResolvedAdjustmentPolicyRef:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "adjustment policy registration requires research_write mode"
            )
        content_id = scoped_content_id(
            {"schema": "persistra.adjustment.policy", "definition": definition}
        )
        encoded = canonical_bytes(definition).decode()

        def operation(context: TransactionContext) -> ResolvedAdjustmentPolicyRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT adjustment_policy_id, definition_content_id, definition_json "
                "FROM research.adjustment_policies WHERE qualified_name = ? "
                "AND policy_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded:
                    raise AdjustmentPolicyError("adjustment policy version conflicts")
                return ResolvedAdjustmentPolicyRef(
                    AdjustmentPolicyId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            prior = connection.execute(
                "SELECT adjustment_policy_id, policy_version FROM "
                "research.adjustment_policies WHERE qualified_name = ? "
                "ORDER BY policy_version DESC LIMIT 1",
                [str(definition.name)],
            ).fetchone()
            if prior is not None and int(prior[1]) + 1 != definition.version:
                raise AdjustmentPolicyError(
                    "adjustment policy versions must be contiguous"
                )
            policy_id = (
                AdjustmentPolicyId.new()
                if prior is None
                else AdjustmentPolicyId.parse(prior[0])
            )
            connection.execute(
                "INSERT INTO research.adjustment_policies VALUES "
                "(?, ?, ?, ?, ?, ?, ?)",
                [
                    policy_id.value,
                    definition.version,
                    str(definition.name),
                    definition.schema_version.value,
                    str(content_id),
                    encoded,
                    context.recorded_at,
                ],
            )
            insert_event(
                connection,
                event_name="persistra.adjustment.policy_registered",
                aggregate_kind="persistra.aggregate.adjustment_policy",
                aggregate_id=policy_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,
                payload={
                    "adjustment_policy_id": policy_id,
                    "definition_content_id": content_id,
                },
            )
            return ResolvedAdjustmentPolicyRef(
                policy_id, definition.version, content_id
            )

        return self._project.services.transactions.run(
            "adjustment_policy_register", operation
        )

    def resolve(
        self, reference: AdjustmentPolicyRef
    ) -> tuple[ResolvedAdjustmentPolicyRef, AdjustmentPolicyDefinition]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT adjustment_policy_id, definition_content_id, definition_json "
            "FROM research.adjustment_policies WHERE qualified_name = ? "
            "AND policy_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise AdjustmentPolicyError("adjustment policy is not registered")
        payload = json.loads(row[2])
        value = payload["value"] if "value" in payload else payload
        definition = AdjustmentPolicyDefinition(
            QualifiedName(value["name"]),
            int(value["version"]),
            AdjustmentPriceMode(value["mode"]),
            AdjustmentKnowledgeMode(value["knowledge_mode"]),
            QualifiedName(value["split_basis_policy"]),
            (
                None
                if value["cash_distribution_policy"] is None
                else QualifiedName(value["cash_distribution_policy"])
            ),
            QualifiedName(value["segment_break_policy"]),
        )
        return (
            ResolvedAdjustmentPolicyRef(
                AdjustmentPolicyId.parse(row[0]),
                reference.version,
                ContentId.parse(row[1]),
            ),
            definition,
        )


class AdjustmentService:
    """Point-in-time adjustment views and immutable materializations."""

    __slots__ = ("_bars", "_policies", "_project")

    def __init__(
        self,
        project: Project,
        bars: BarService,
        policies: AdjustmentPolicyService,
    ) -> None:
        self._project = project
        self._bars = bars
        self._policies = policies

    def view(
        self,
        request: AdjustmentViewRequest | None = None,
        *,
        bars: BarQuery | None = None,
        policy: AdjustmentPolicyRef | None = None,
        context: AsOfContext | None = None,
        anchor_at: datetime | None = None,
    ) -> AdjustmentView:
        resolved_policy: ResolvedAdjustmentPolicyRef | None = None
        policy_definition: AdjustmentPolicyDefinition | None = None
        if request is None:
            if bars is None or policy is None or context is None or anchor_at is None:
                raise MarketDataQueryError(
                    "adjustment view requires bars, policy, context, and anchor"
                )
            if bars.context != context:
                raise MarketDataQueryError(
                    "adjustment bar and outer contexts must be identical"
                )
            resolved_policy, policy_definition = self._policies.resolve(policy)
            request = AdjustmentViewRequest(
                bars, policy_definition.mode, anchor_at
            )
        return AdjustmentView(
            self._project,
            self._bars,
            request,
            resolved_policy,
            policy_definition,
        )


class AdjustmentView:
    """Lazily computed point-in-time daily adjustment view."""

    __slots__ = (
        "_bars",
        "_policy",
        "_policy_definition",
        "_project",
        "request",
    )

    def __init__(
        self,
        project: Project,
        bars: BarService,
        request: AdjustmentViewRequest,
        policy: ResolvedAdjustmentPolicyRef | None = None,
        policy_definition: AdjustmentPolicyDefinition | None = None,
    ) -> None:
        self._project = project
        self._bars = bars
        self.request = request
        self._policy = policy
        self._policy_definition = policy_definition

    def bars(self) -> pd.DataFrame:
        raw = self._bars.query(self.request.bars)
        output_columns = [
            *raw.columns,
            "adjusted_open",
            "adjusted_high",
            "adjusted_low",
            "adjusted_close",
            "adjusted_volume",
            "adjusted_vwap",
            "price_multiplier",
            "volume_multiplier",
            "adjustment_status",
            "reason_codes",
        ]
        if raw.empty:
            return pd.DataFrame(columns=output_columns)
        actions = self._action_rows()
        leg_amounts = self._cash_leg_amounts(actions)
        adjusted_rows: list[dict[str, Any]] = []
        for row in raw.to_dict("records"):
            price_factor = 1.0
            volume_factor = 1.0
            reasons: list[str] = []
            unavailable = False
            applicable: list[dict[str, Any]] = []
            for action in actions:
                action_at = (
                    action["ex_at"]
                    if pd.isna(action["effective_at"])
                    else action["effective_at"]
                )
                if (
                    action["subject_instrument_id"] == row["instrument_id"]
                    and row["interval_end"] <= action_at <= self.request.anchor_at
                    and action["action_status"]
                    != CorporateActionStatus.CANCELLED.value
                ):
                    applicable.append(action)
            for action in applicable:
                kind = CorporateActionKind(action["action_kind"])
                if kind in {
                    CorporateActionKind.SPLIT,
                    CorporateActionKind.REVERSE_SPLIT,
                } and self.request.mode in {
                    AdjustmentPriceMode.SPLIT,
                    AdjustmentPriceMode.TOTAL_RETURN,
                }:
                    ratio = float(action["share_ratio"])
                    price_factor *= 1.0 / ratio
                    volume_factor *= ratio
                elif kind in {
                    CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                    CorporateActionKind.SPECIAL_CASH_DIVIDEND,
                } and self.request.mode is AdjustmentPriceMode.TOTAL_RETURN:
                    reference_price = self._previous_close(
                        InstrumentId.parse(row["instrument_id"]),
                        action["ex_at"],
                    )
                    distribution = leg_amounts.get(
                        action["canonical_revision_id"]
                    )
                    if distribution is None:
                        unavailable = True
                        reasons.append("adjustment.action.unsupported")
                        break
                    if reference_price is None or reference_price <= distribution:
                        unavailable = True
                        reasons.append("adjustment.reference_price.missing")
                        break
                    price_factor *= (reference_price - distribution) / reference_price
            result = dict(row)
            if unavailable:
                result.update(
                    {
                        "adjusted_open": None,
                        "adjusted_high": None,
                        "adjusted_low": None,
                        "adjusted_close": None,
                        "adjusted_volume": None,
                        "adjusted_vwap": None,
                        "price_multiplier": None,
                        "volume_multiplier": None,
                        "adjustment_status": AdjustmentRowStatus.UNAVAILABLE.value,
                        "reason_codes": tuple(reasons),
                    }
                )
            else:
                state = (
                    AdjustmentRowStatus.RAW
                    if price_factor == 1.0 and volume_factor == 1.0
                    else AdjustmentRowStatus.ADJUSTED
                )
                result.update(
                    {
                        "adjusted_open": (
                            None if pd.isna(row["open"]) else row["open"] * price_factor
                        ),
                        "adjusted_high": (
                            None if pd.isna(row["high"]) else row["high"] * price_factor
                        ),
                        "adjusted_low": (
                            None if pd.isna(row["low"]) else row["low"] * price_factor
                        ),
                        "adjusted_close": (
                            None if pd.isna(row["close"]) else row["close"] * price_factor
                        ),
                        "adjusted_volume": row["volume"] * volume_factor,
                        "adjusted_vwap": (
                            None if pd.isna(row["vwap"]) else row["vwap"] * price_factor
                        ),
                        "price_multiplier": price_factor,
                        "volume_multiplier": volume_factor,
                        "adjustment_status": state.value,
                        "reason_codes": (),
                    }
                )
            adjusted_rows.append(cast("dict[str, Any]", result))
        return pd.DataFrame(adjusted_rows, columns=output_columns)

    def factors(self) -> pd.DataFrame:
        rows = self._action_rows()
        if not rows:
            return pd.DataFrame(
                columns=[
                    "corporate_action_id",
                    "instrument_id",
                    "effective_at",
                    "action_kind",
                    "input_content_id",
                ]
            )
        return pd.DataFrame(rows)[
            [
                "corporate_action_id",
                "subject_instrument_id",
                "effective_at",
                "action_kind",
                "canonical_revision_id",
            ]
        ].rename(
            columns={
                "subject_instrument_id": "instrument_id",
                "canonical_revision_id": "input_content_id",
            }
        )

    def materialize(self) -> AdjustmentMaterialization:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "adjustment materialization requires research_write mode"
            )
        if self._policy is None or self._policy_definition is None:
            raise AdjustmentMaterializationError(
                "materialization requires a registered adjustment policy"
            )
        context = self.request.bars.context
        if not isinstance(context.snapshot, CompositeSnapshotRef):
            raise AdjustmentMaterializationError(
                "materialization requires an exact composite snapshot"
            )
        policy = self._policy
        policy_definition = self._policy_definition
        composite_snapshot = context.snapshot
        raw_adjusted = self.bars()
        action_rows = self._action_rows()
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.adjustment.materialization",
                "policy": policy,
                "request": self.request,
                "raw_revision_ids": tuple(
                    raw_adjusted["canonical_revision_id"].astype(str)
                ),
                "actions": tuple(
                    action["canonical_revision_id"] for action in action_rows
                ),
            }
        )
        materialization_id = AdjustmentMaterializationId(
            UUID(bytes=execution_content_id.digest[:16])
        )
        factor_records = self._factor_records(materialization_id, action_rows)

        def operation(transaction: TransactionContext) -> AdjustmentMaterialization:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT adjustment_materialization_id FROM "
                "research.adjustment_materializations WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return AdjustmentMaterialization(
                    self._project,
                    AdjustmentMaterializationId.parse(existing[0]),
                )
            bar_query_content_id = scoped_content_id(self.request.bars)
            cutoff_content_id = scoped_content_id(
                {
                    "public_cutoff_at": context.public_cutoff_at,
                    "cutoff_mode": context.cutoff_mode,
                }
            )
            action_selection_id = scoped_content_id(
                tuple(
                    action["canonical_revision_id"] for action in action_rows
                )
            )
            safety_status = (
                "unsafe_retrospective"
                if policy_definition.knowledge_mode
                is AdjustmentKnowledgeMode.RETROSPECTIVE
                else "safe"
            )
            connection.execute(
                "INSERT INTO research.adjustment_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    policy.adjustment_policy_id.value,
                    policy.version,
                    composite_snapshot.composite_snapshot_id.value,
                    context.market_database,
                    str(bar_query_content_id),
                    str(cutoff_content_id),
                    context.project_cutoff_at,
                    self.request.anchor_at,
                    str(action_selection_id),
                    str(execution_content_id),
                    safety_status,
                    len(raw_adjusted),
                    len(factor_records),
                    transaction.recorded_at,
                ],
            )
            for record in factor_records:
                connection.execute(
                    "INSERT INTO research.adjustment_factors VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        materialization_id.value,
                        UUID(record["instrument_id"]),
                        record["effective_at"],
                        record["factor_ordinal"],
                        record["split_price_multiplier"],
                        record["cash_price_multiplier"],
                        record["volume_multiplier"],
                        record["cumulative_price_multiplier"],
                        record["cumulative_volume_multiplier"],
                        record["reference_price"],
                        _canonical_json(record["corporate_action_ids"]),
                        _canonical_json(record["input_revision_ids"]),
                        record["evidence_content_id"],
                    ],
                )
            for row in raw_adjusted.to_dict("records"):
                lineage_id = scoped_content_id(
                    {
                        "materialization": materialization_id,
                        "raw_revision": row["canonical_revision_id"],
                        "policy": policy,
                    }
                )
                reasons = list(row["reason_codes"])
                connection.execute(
                    "INSERT INTO research.adjusted_bars VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        materialization_id.value,
                        UUID(row["canonical_revision_id"]),
                        UUID(row["instrument_id"]),
                        row["interval_start"],
                        row["interval_end"],
                        row["session_date"],
                        row["adjusted_open"],
                        row["adjusted_high"],
                        row["adjusted_low"],
                        row["adjusted_close"],
                        row["adjusted_volume"],
                        row["adjusted_vwap"],
                        row["price_multiplier"],
                        row["volume_multiplier"],
                        row["adjustment_status"],
                        _canonical_json(reasons),
                        str(lineage_id),
                    ],
                )
            insert_event(
                connection,
                event_name="persistra.adjustment.materialization_completed",
                aggregate_kind="persistra.aggregate.adjustment_materialization",
                aggregate_id=materialization_id,
                aggregate_sequence=1,
                recorded_at=transaction.recorded_at,
                payload={
                    "adjustment_materialization_id": materialization_id,
                    "execution_content_id": execution_content_id,
                },
            )
            return AdjustmentMaterialization(self._project, materialization_id)

        return self._project.services.transactions.run(
            "adjustment_materialize", operation
        )

    def _factor_records(
        self,
        materialization_id: AdjustmentMaterializationId,
        actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        cash_amounts = self._cash_leg_amounts(actions)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for action in actions:
            instrument = action["subject_instrument_id"]
            if instrument is not None:
                grouped.setdefault(instrument, []).append(action)
        records: list[dict[str, Any]] = []
        for instrument, items in grouped.items():
            eligible = sorted(
                items,
                key=lambda action: (
                    action["effective_at"]
                    if not pd.isna(action["effective_at"])
                    else action["ex_at"],
                    action["corporate_action_id"],
                ),
            )
            components: list[dict[str, Any]] = []
            for action in eligible:
                effective_at = (
                    action["effective_at"]
                    if not pd.isna(action["effective_at"])
                    else action["ex_at"]
                )
                split = 1.0
                cash = 1.0
                volume = 1.0
                reference: float | None = None
                kind = CorporateActionKind(action["action_kind"])
                if kind in {
                    CorporateActionKind.SPLIT,
                    CorporateActionKind.REVERSE_SPLIT,
                    CorporateActionKind.STOCK_DIVIDEND,
                } and self.request.mode in {
                    AdjustmentPriceMode.SPLIT,
                    AdjustmentPriceMode.TOTAL_RETURN,
                }:
                    ratio = float(action["share_ratio"])
                    split = 1.0 / ratio
                    volume = ratio
                elif kind in {
                    CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                    CorporateActionKind.SPECIAL_CASH_DIVIDEND,
                    CorporateActionKind.ETF_DISTRIBUTION,
                } and self.request.mode is AdjustmentPriceMode.TOTAL_RETURN:
                    amount = cash_amounts.get(action["canonical_revision_id"])
                    reference = self._previous_close(
                        InstrumentId.parse(instrument), effective_at
                    )
                    if (
                        amount is not None
                        and reference is not None
                        and reference > amount
                    ):
                        cash = (reference - amount) / reference
                components.append(
                    {
                        "action": action,
                        "effective_at": effective_at,
                        "split": split,
                        "cash": cash,
                        "volume": volume,
                        "reference": reference,
                    }
                )
            cumulative_price = 1.0
            cumulative_volume = 1.0
            accumulated: list[tuple[float, float]] = []
            for component in reversed(components):
                cumulative_price *= component["split"] * component["cash"]
                cumulative_volume *= component["volume"]
                accumulated.append((cumulative_price, cumulative_volume))
            accumulated.reverse()
            for ordinal, (component, cumulative) in enumerate(
                zip(components, accumulated, strict=True), 1
            ):
                action = component["action"]
                evidence = scoped_content_id(
                    {
                        "materialization": materialization_id,
                        "action_revision": action["canonical_revision_id"],
                        "ordinal": ordinal,
                    }
                )
                records.append(
                    {
                        "adjustment_materialization_id": str(materialization_id),
                        "instrument_id": instrument,
                        "corporate_action_ids": [action["corporate_action_id"]],
                        "effective_at": component["effective_at"],
                        "factor_ordinal": ordinal,
                        "split_price_multiplier": component["split"],
                        "cash_price_multiplier": component["cash"],
                        "volume_multiplier": component["volume"],
                        "cumulative_price_multiplier": cumulative[0],
                        "cumulative_volume_multiplier": cumulative[1],
                        "reference_price": component["reference"],
                        "input_revision_ids": [action["canonical_revision_id"]],
                        "evidence_content_id": str(evidence),
                    }
                )
        return records

    def _action_rows(self) -> list[dict[str, Any]]:
        frame = self._project.services.market.actions.query(
            self.request.bars.instruments,
            start=self.request.bars.start,
            end=self.request.anchor_at,
            context=self.request.bars.context,
        )
        return cast("list[dict[str, Any]]", frame.to_dict("records"))

    def _cash_leg_amounts(self, actions: list[dict[str, Any]]) -> dict[str, float]:
        revision_ids = tuple(
            UUID(action["canonical_revision_id"])
            for action in actions
            if action["action_kind"]
            in {
                CorporateActionKind.ORDINARY_CASH_DIVIDEND.value,
                CorporateActionKind.SPECIAL_CASH_DIVIDEND.value,
                CorporateActionKind.ETF_DISTRIBUTION.value,
            }
        )
        if not revision_ids:
            return {}
        legs = self._project.services.market.actions.legs(revision_ids)
        return {
            cast("str", row["canonical_revision_id"]): float(
                row["cash_per_subject_unit"]
            )
            for row in legs.to_dict("records")
            if row["leg_kind"] == "cash"
            and not pd.isna(row["cash_per_subject_unit"])
        }

    def _previous_close(
        self, instrument: InstrumentId, effective_at: datetime
    ) -> float | None:
        opened, sequence = market_for_context(
            self._project, self.request.bars.context
        )
        cutoff_clause, parameters = cutoff_sql(self.request.bars.context)
        spec = self._project.services.market.bar_specs.resolve(
            self.request.bars.spec, context=self.request.bars.context
        )
        row = opened.connection.execute(
            "SELECT b.close_price FROM canonical.bars b "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE b.instrument_id = ? AND b.bar_spec_id = ? "
            "AND b.bar_spec_version = ? AND b.interval_end <= ? "
            f"AND b.bar_state = 'complete' AND "
            f"m.{cutoff_clause.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? "
            "QUALIFY row_number() OVER (PARTITION BY b.interval_start "
            "ORDER BY m.catalog_sequence DESC) = 1 "
            "ORDER BY b.interval_end DESC LIMIT 1",
            [
                instrument.value,
                spec.bar_spec_id.value,
                spec.version,
                effective_at,
                *parameters,
                sequence,
            ],
        ).fetchone()
        return None if row is None else float(Decimal(row[0]))


class AdjustmentMaterialization:
    """Public immutable handle for one persisted adjusted dataset."""

    __slots__ = ("_project", "materialization_id")

    def __init__(
        self, project: Project, materialization_id: AdjustmentMaterializationId
    ) -> None:
        self._project = project
        self.materialization_id = materialization_id

    def bars(self) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT adjustment_materialization_id, raw_canonical_revision_id, "
            "instrument_id, interval_start, interval_end, session_date, adjusted_open, "
            "adjusted_high, adjusted_low, adjusted_close, adjusted_volume, adjusted_vwap, "
            "price_multiplier, volume_multiplier, adjustment_status, reason_codes_json, "
            "lineage_content_id FROM research.adjusted_bars "
            "WHERE adjustment_materialization_id = ? "
            "ORDER BY interval_start, instrument_id, raw_canonical_revision_id",
            [self.materialization_id.value],
        ).fetchall()
        return build_frame(
            ADJUSTED_BARS_FRAME,
            [
                {
                    "adjustment_materialization_id": str(row[0]),
                    "raw_canonical_revision_id": str(row[1]),
                    "instrument_id": str(row[2]),
                    "interval_start": row[3],
                    "interval_end": row[4],
                    "session_date": row[5],
                    "adjusted_open": row[6],
                    "adjusted_high": row[7],
                    "adjusted_low": row[8],
                    "adjusted_close": row[9],
                    "adjusted_volume": row[10],
                    "adjusted_vwap": row[11],
                    "price_multiplier": row[12],
                    "volume_multiplier": row[13],
                    "adjustment_status": row[14],
                    "reason_codes": row[15],
                    "lineage_content_id": row[16],
                }
                for row in rows
            ],
        )

    def factors(self) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT adjustment_materialization_id, instrument_id, "
            "corporate_action_ids_json, effective_at, factor_ordinal, "
            "split_price_multiplier, cash_price_multiplier, volume_multiplier, "
            "cumulative_price_multiplier, cumulative_volume_multiplier, reference_price, "
            "input_revision_ids_json, evidence_content_id "
            "FROM research.adjustment_factors WHERE adjustment_materialization_id = ? "
            "ORDER BY instrument_id, effective_at, factor_ordinal",
            [self.materialization_id.value],
        ).fetchall()
        return build_frame(
            ADJUSTMENT_FACTORS_FRAME,
            [
                {
                    "adjustment_materialization_id": str(row[0]),
                    "instrument_id": str(row[1]),
                    "corporate_action_ids": row[2],
                    "effective_at": row[3],
                    "factor_ordinal": int(row[4]),
                    "split_price_multiplier": row[5],
                    "cash_price_multiplier": row[6],
                    "volume_multiplier": row[7],
                    "cumulative_price_multiplier": row[8],
                    "cumulative_volume_multiplier": row[9],
                    "reference_price": row[10],
                    "input_revision_ids": row[11],
                    "evidence_content_id": row[12],
                }
                for row in rows
            ],
        )
