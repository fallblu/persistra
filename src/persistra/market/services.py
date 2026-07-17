"""Project-owned daily market data and point-in-time adjustment services."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog.services import advance_catalog, insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    BarSpecError,
    CapabilityUnavailableError,
    CorporateActionTermsError,
    MarketDataLimitError,
    MarketDataQueryError,
)
from persistra.market.models import (
    AdjustmentPriceMode,
    AdjustmentRowStatus,
    AdjustmentViewRequest,
    BarQuery,
    BarSpecDefinition,
    BarSpecId,
    BarSpecRef,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionObservation,
    CorporateActionStatus,
    DailyBar,
    ResolvedBarSpecRef,
    TradingStatus,
    TradingStatusObservation,
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


class MarketService:
    """Daily market capability group."""

    __slots__ = ("actions", "adjustments", "bar_specs", "bars", "status")

    def __init__(self, project: Project) -> None:
        self.bar_specs = BarSpecService(project)
        self.bars = BarService(project, self.bar_specs)
        self.status = TradingStatusService(project)
        self.actions = CorporateActionService(project)
        self.adjustments = AdjustmentService(project, self.bars)


class BarSpecService:
    """Daily regular-session bar specification registry."""

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
            spec_id = BarSpecId.new()
            sequence = advance_catalog(
                connection,
                change_kind="market.bar_spec_registered",
                entity_id=spec_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.bar_specs VALUES (?, ?, ?, ?, ?, ?)",
                [
                    spec_id.value,
                    definition.version,
                    str(definition.name),
                    str(content_id),
                    encoded,
                    sequence,
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
                    "SELECT definition_content_id FROM canonical.bar_specs "
                    "WHERE bar_spec_id = ? AND bar_spec_version = ?",
                    [bar.spec.bar_spec_id.value, bar.spec.version],
                ).fetchone()
                if spec is None or spec[0] != str(bar.spec.definition_content_id):
                    raise BarSpecError("bar references an unknown specification")
                calendar = connection.execute(
                    "SELECT open_at, close_at FROM canonical.calendar_dates "
                    "WHERE calendar_id = ? AND calendar_version = ? "
                    "AND calendar_date = ? AND is_session",
                    [
                        bar.calendar.calendar_id.value,
                        bar.calendar.version,
                        bar.session_date,
                    ],
                ).fetchone()
                if calendar is None or calendar != (bar.interval_start, bar.interval_end):
                    raise MarketDataQueryError("daily bar is not aligned to its calendar")
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.market.daily_bar",
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
                    }
                )
                existing = connection.execute(
                    "SELECT bar_id FROM canonical.bars WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    identifiers.append(existing[0])
                    continue
                bar_id = _occurrence_id(content_id)
                sequence = advance_catalog(
                    connection,
                    change_kind="market.bar_ingested",
                    entity_id=bar.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.bars VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        bar_id,
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
                    ],
                )
                identifiers.append(bar_id)
            return tuple(identifiers)

        return self._project.services.transactions.run("daily_bars_ingest", operation)

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
            *cutoff_parameters,
            sequence,
            states,
            query.max_rows + 1,
        ]
        rows = opened.connection.execute(
            "SELECT bar_id, instrument_id, interval_start, interval_end, session_date, "
            "bar_state, currency, open_price, high_price, low_price, close_price, "
            "volume, trade_count, available_at, ingested_at, catalog_sequence, content_id "
            "FROM canonical.bars WHERE bar_spec_id = ? AND bar_spec_version = ? "
            "AND instrument_id IN (SELECT unnest(?)) AND interval_start >= ? "
            f"AND interval_end <= ? AND {cutoff_clause} AND catalog_sequence <= ? "
            "AND bar_state IN (SELECT unnest(?)) "
            "QUALIFY row_number() OVER (PARTITION BY instrument_id, interval_start, "
            "interval_end ORDER BY catalog_sequence DESC) = 1 "
            "ORDER BY interval_start, instrument_id LIMIT ?",
            parameters,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("bar query exceeds its row ceiling")
        columns = [
            "bar_id",
            "instrument_id",
            "interval_start",
            "interval_end",
            "session_date",
            "bar_state",
            "currency",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_count",
            "available_at",
            "ingested_at",
            "catalog_sequence",
            "content_id",
        ]
        frame = pd.DataFrame(rows, columns=columns)
        for column in ("bar_id", "instrument_id", "content_id"):
            frame[column] = frame[column].astype("string")
        for column in ("interval_start", "interval_end", "available_at", "ingested_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame

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
            "bar_id": row["bar_id"],
            "close": row["close"],
        }


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
                    "SELECT status_id FROM canonical.trading_status WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if existing is not None:
                    result.append(existing[0])
                    continue
                status_id = _occurrence_id(content_id)
                sequence = advance_catalog(
                    connection,
                    change_kind="market.trading_status_ingested",
                    entity_id=observation.instrument_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                connection.execute(
                    "INSERT INTO canonical.trading_status VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        status_id,
                        observation.instrument_id.value,
                        observation.status.value,
                        observation.effective_at,
                        observation.effective_to,
                        observation.available_at,
                        context.recorded_at,
                        sequence,
                        str(content_id),
                    ],
                )
                result.append(status_id)
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
            "SELECT status FROM canonical.trading_status WHERE instrument_id = ? "
            f"AND effective_at <= ? AND (effective_to IS NULL OR ? < effective_to) "
            f"AND {cutoff_clause} AND catalog_sequence <= ? "
            "ORDER BY catalog_sequence DESC LIMIT 1",
            [instrument.value, instant, instant, *parameters, sequence],
        ).fetchone()
        return None if row is None else TradingStatus(row[0])


class CorporateActionService:
    """Supported split and cash-dividend observation service."""

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
                    "SELECT 1 FROM canonical.corporate_action_observations "
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
                sequence = advance_catalog(
                    connection,
                    change_kind="market.corporate_action_ingested",
                    entity_id=observation.action_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                expected = (
                    observation.kind.value,
                    observation.subject_security_id.value,
                    None
                    if observation.subject_instrument_id is None
                    else observation.subject_instrument_id.value,
                )
                if master is None:
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
                connection.execute(
                    "INSERT INTO canonical.corporate_action_observations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        _occurrence_id(content_id),
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
                    ],
                )
                result.append(observation.action_id)
            return tuple(result)

        return self._project.services.transactions.run("corporate_actions_ingest", operation)

    def query(
        self,
        instruments: tuple[InstrumentId, ...],
        *,
        start: datetime,
        end: datetime,
        context: AsOfContext,
    ) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, context)
        cutoff_clause, parameters = cutoff_sql(context)
        rows = opened.connection.execute(
            "SELECT a.corporate_action_id, a.action_kind, a.subject_instrument_id, "
            "o.action_status, o.ex_at, o.effective_at, o.share_ratio, "
            "o.cash_per_subject_unit, o.currency, o.available_at, o.content_id "
            "FROM canonical.corporate_actions a JOIN "
            "canonical.corporate_action_observations o USING (corporate_action_id) "
            "WHERE a.subject_instrument_id IN (SELECT unnest(?)) "
            "AND coalesce(o.effective_at, o.ex_at) >= ? "
            f"AND coalesce(o.effective_at, o.ex_at) <= ? AND {cutoff_clause} "
            "AND o.catalog_sequence <= ? QUALIFY row_number() OVER "
            "(PARTITION BY a.corporate_action_id ORDER BY o.catalog_sequence DESC) = 1 "
            "ORDER BY coalesce(o.effective_at, o.ex_at), a.corporate_action_id",
            [[item.value for item in instruments], start, end, *parameters, sequence],
        ).fetchall()
        columns = [
            "corporate_action_id",
            "action_kind",
            "instrument_id",
            "action_status",
            "ex_at",
            "effective_at",
            "share_ratio",
            "cash_per_subject_unit",
            "currency",
            "available_at",
            "content_id",
        ]
        frame = pd.DataFrame(rows, columns=columns)
        for column in ("corporate_action_id", "instrument_id", "content_id"):
            frame[column] = frame[column].astype("string")
        for column in ("ex_at", "effective_at", "available_at"):
            frame[column] = pd.to_datetime(frame[column], utc=True)
        return frame


class AdjustmentService:
    """Nonpersistent point-in-time adjustment view service."""

    __slots__ = ("_bars", "_project")

    def __init__(self, project: Project, bars: BarService) -> None:
        self._project = project
        self._bars = bars

    def view(self, request: AdjustmentViewRequest) -> AdjustmentView:
        return AdjustmentView(self._project, self._bars, request)


class AdjustmentView:
    """Lazily computed point-in-time daily adjustment view."""

    __slots__ = ("_bars", "_project", "request")

    def __init__(
        self, project: Project, bars: BarService, request: AdjustmentViewRequest
    ) -> None:
        self._project = project
        self._bars = bars
        self.request = request

    def bars(self) -> pd.DataFrame:
        raw = self._bars.query(self.request.bars)
        output_columns = [
            *raw.columns,
            "adjusted_open",
            "adjusted_high",
            "adjusted_low",
            "adjusted_close",
            "adjusted_volume",
            "price_multiplier",
            "volume_multiplier",
            "adjustment_status",
            "reason_codes",
        ]
        if raw.empty:
            return pd.DataFrame(columns=output_columns)
        actions = self._action_rows()
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
                    action["instrument_id"] == row["instrument_id"]
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
                    distribution = float(action["cash_per_subject_unit"])
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
                "instrument_id",
                "effective_at",
                "action_kind",
                "content_id",
            ]
        ].rename(columns={"content_id": "input_content_id"})

    def _action_rows(self) -> list[dict[str, Any]]:
        frame = self._project.services.market.actions.query(
            self.request.bars.instruments,
            start=self.request.bars.start,
            end=self.request.anchor_at,
            context=self.request.bars.context,
        )
        return cast("list[dict[str, Any]]", frame.to_dict("records"))

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
            "SELECT close_price FROM canonical.bars WHERE instrument_id = ? "
            "AND bar_spec_id = ? AND bar_spec_version = ? AND interval_end <= ? "
            f"AND bar_state = 'complete' AND {cutoff_clause} AND catalog_sequence <= ? "
            "QUALIFY row_number() OVER (PARTITION BY interval_start "
            "ORDER BY catalog_sequence DESC) = 1 ORDER BY interval_end DESC LIMIT 1",
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
