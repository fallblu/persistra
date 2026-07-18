"""Deterministic bar-observation event simulator with immutable order history."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, localcontext
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.accounting import (
    AccountingBookId,
    BorrowAuthorizationFacts,
    SettlementFacts,
    SettlementObligationId,
    TradeFillFacts,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    AccountingInvariantError,
    CapabilityUnavailableError,
    EventSimulationError,
    EventSimulationRequestError,
    ResearchResultLimitError,
)
from persistra.logging import StructuredLogEntry, persist_run_logs
from persistra.market import BarQuery, BarState
from persistra.results.publication import (
    findings_json,
    publish_accounting_rows,
    publish_exposures,
    publish_findings,
)
from persistra.simulation.event_models import (
    EventRunRef,
    EventSimulationId,
    EventSimulationPlan,
    EventSimulationRequest,
    FillId,
    OrderId,
    OrderSide,
    OrderSpec,
    OrderStatus,
)
from persistra.simulation.models import RunRecordId
from persistra.simulation.order_kernels import (
    eligible_reference,
    fok_capacity_rejected,
    remainder_outcome,
    unavailable_reference_outcome,
)
from persistra.simulation.result_kernels import event_valuation_rows

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.results.services import RunHandle

_Q = Decimal("0.000000000001")
_BPS = Decimal("10000")


def _q(value: Decimal, *, rounding: str = ROUND_HALF_EVEN) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_Q, rounding=rounding)


class EventSimulationService:
    """Plan, execute, and query deterministic event-simulation occurrences."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def plan(self, request: EventSimulationRequest) -> EventSimulationPlan:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        self._project.services.portfolio.decision_inputs.validate(
            request.decision_inputs, request.unsafe_override
        )
        if request.market_context.market_database not in {None, request.market_database}:
            raise EventSimulationRequestError(
                "request market database conflicts with as-of context"
            )
        return EventSimulationPlan(
            request,
            scoped_content_id(
                {
                    "schema": "persistra.simulation.event_execution@1",
                    "request": request,
                    "clock": "effective_priority_stable_sequence",
                    "fidelity": "bar_observation_event",
                }
            ),
        )

    def run(self, plan: EventSimulationPlan) -> EventRun:
        self._require_write()
        if self.plan(plan.request).execution_content_id != plan.execution_content_id:
            raise EventSimulationRequestError("event simulation plan does not verify")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT event_simulation_id FROM simulation.event_runs "
            "WHERE execution_content_id = ?",
            [str(plan.execution_content_id)],
        ).fetchone()
        if existing is not None:
            return self.get(EventSimulationId.parse(existing[0]))
        request = plan.request
        instruments = tuple(
            sorted(
                {order.instrument_id for order in request.orders},
                key=lambda item: str(item.value),
            )
        )
        bars = self._project.services.market.bars.query(
            BarQuery(
                instruments,
                request.bar_spec,
                min(order.eligibility_at for order in request.orders),
                request.horizon_at,
                request.market_context,
                include_partial=False,
                include_no_trade=True,
                max_rows=max(10_000, len(instruments) * 10_000),
            )
        )

        def operation(context: TransactionContext) -> EventRun:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._execute(active, context, plan, bars)

        return self._project.services.transactions.run("event_simulation_run", operation)

    def get(self, simulation_id: EventSimulationId) -> EventRun:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT e.accounting_book_id, e.execution_content_id, "
            "r.result_manifest_content_id, e.event_count, e.order_count, "
            "e.fill_count, r.run_record_id FROM simulation.event_runs e JOIN "
            "results.run_records r USING (event_simulation_id) "
            "WHERE e.event_simulation_id = ?",
            [simulation_id.value],
        ).fetchone()
        if row is None:
            raise EventSimulationError("event simulation is missing")
        return EventRun(
            self._project,
            EventRunRef(
                simulation_id,
                RunRecordId.parse(row[6]),
                AccountingBookId.parse(row[0]),
                ContentId.parse(row[1]),
                ContentId.parse(row[2]),
                int(row[3]),
                int(row[4]),
                int(row[5]),
            ),
        )

    def _execute(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        plan: EventSimulationPlan,
        bars: pd.DataFrame,
    ) -> EventRun:
        request = plan.request
        accounting = self._project.services.accounting
        book = accounting._create_book(  # pyright: ignore[reportPrivateUsage]
            connection, context, request.opening
        )
        book_id = book.reference.accounting_book_id
        simulation_id = EventSimulationId.new()
        run_id = RunRecordId.new()
        rng = random.Random(request.execution.seed)
        order_rows: list[tuple[Any, ...]] = []
        transition_rows: list[tuple[Any, ...]] = []
        fill_rows: list[tuple[Any, ...]] = []
        raw_events: list[tuple[datetime, int, int, str, Any]] = []
        order_ids: dict[str, OrderId] = {}
        specs: dict[OrderId, OrderSpec] = {}
        status: dict[OrderId, OrderStatus] = {}
        remaining: dict[OrderId, Decimal] = {}
        transition_counts: dict[OrderId, int] = {}
        stable = 0

        if request.execution.short_borrow_quantity:
            for instrument in sorted(
                {order.instrument_id for order in request.orders},
                key=lambda item: str(item.value),
            ):
                accounting._authorize_borrow(  # pyright: ignore[reportPrivateUsage]
                    connection,
                    context,
                    book_id,
                    BorrowAuthorizationFacts(
                        scoped_content_id(
                            {
                                "schema": "persistra.simulation.event_borrow@1",
                                "execution": plan.execution_content_id,
                                "instrument": instrument,
                            }
                        ),
                        instrument,
                        request.opening.effective_at,
                        request.horizon_at,
                        request.execution.short_borrow_quantity,
                    ),
                )

        for sequence, spec in enumerate(
            sorted(request.orders, key=lambda item: (item.submitted_at, item.client_key)),
            1,
        ):
            order_id = OrderId.new()
            order_ids[spec.client_key] = order_id
            specs[order_id] = spec
            remaining[order_id] = _q(spec.quantity)
            status[order_id] = OrderStatus.ACCEPTED
            parent = (
                None
                if spec.replaces_client_key is None
                else order_ids[spec.replaces_client_key]
            )
            order_content_id = scoped_content_id(
                {
                    "schema": "persistra.simulation.order@1",
                    "execution": plan.execution_content_id,
                    "sequence": sequence,
                    "spec": spec,
                    "parent": parent,
                }
            )
            order_rows.append(
                (
                    simulation_id.value,
                    order_id.value,
                    sequence,
                    spec.client_key,
                    spec.instrument_id.value,
                    spec.side.value,
                    spec.quantity,
                    spec.order_type.value,
                    spec.time_in_force.value,
                    spec.submitted_at,
                    spec.eligibility_at,
                    spec.limit_price,
                    spec.stop_price,
                    None if parent is None else parent.value,
                    str(order_content_id),
                )
            )
            for order_status, priority in (
                (OrderStatus.CREATED, 50),
                (OrderStatus.SUBMITTED, 60),
                (OrderStatus.ACCEPTED, 70),
            ):
                stable += 1
                self._transition(
                    simulation_id,
                    order_id,
                    spec.submitted_at,
                    order_status,
                    None,
                    Decimal(0),
                    spec.quantity,
                    transition_counts,
                    transition_rows,
                )
                raw_events.append(
                    (spec.submitted_at, priority, stable, f"order_{order_status.value}", order_id)
                )

        ordered_bars = bars[
            bars["bar_state"].eq(BarState.COMPLETE.value)
        ].sort_values(["interval_end", "instrument_id"])
        settlement_schedule = _settlement_schedule(
            ordered_bars, request.execution.settlement_sessions
        )
        fill_sequence = 0
        for bar in ordered_bars.itertuples(index=False):
            # A complete bar's high, low, close, and volume are not causally available
            # at its opening instant. Until the engine has distinct open/intrabar/close
            # occurrences, commit every bar-derived outcome at the bar-completion
            # boundary. This deliberately prefers coarse timing over look-ahead.
            effective_at = pd.Timestamp(cast("Any", bar.interval_end)).to_pydatetime()
            if effective_at > request.horizon_at:
                break
            for obligation_id in self._settle_due(
                connection,
                context,
                accounting,
                book_id,
                effective_at,
            ):
                stable += 1
                raw_events.append(
                    (
                        effective_at,
                        30,
                        stable,
                        "settlement_completed",
                        obligation_id,
                    )
                )
            instrument = str(bar.instrument_id)
            stable += 1
            raw_events.append((effective_at, 50, stable, "bar_complete_observed", None))
            for order_id, spec in specs.items():
                if status[order_id] not in {OrderStatus.ACCEPTED, OrderStatus.ACTIVE}:
                    continue
                if spec.cancel_at is not None and spec.cancel_at <= effective_at:
                    status[order_id] = OrderStatus.CANCELLED
                    stable += 1
                    self._transition_current(
                        simulation_id,
                        order_id,
                        spec.cancel_at,
                        OrderStatus.CANCELLED,
                        "strategy_cancel",
                        spec,
                        remaining,
                        transition_counts,
                        transition_rows,
                    )
                    raw_events.append(
                        (spec.cancel_at, 80, stable, "order_cancelled", order_id)
                    )
                    continue
                if spec.eligibility_at > effective_at:
                    continue
                if status[order_id] is OrderStatus.ACCEPTED:
                    if spec.replaces_client_key is not None:
                        parent = order_ids[spec.replaces_client_key]
                        if status[parent] in {OrderStatus.ACCEPTED, OrderStatus.ACTIVE}:
                            status[parent] = OrderStatus.REPLACED
                            self._transition_current(
                                simulation_id,
                                parent,
                                effective_at,
                                OrderStatus.REPLACED,
                                "child_activated",
                                specs[parent],
                                remaining,
                                transition_counts,
                                transition_rows,
                            )
                    status[order_id] = OrderStatus.ACTIVE
                    stable += 1
                    self._transition_current(
                        simulation_id,
                        order_id,
                        effective_at,
                        OrderStatus.ACTIVE,
                        None,
                        spec,
                        remaining,
                        transition_counts,
                        transition_rows,
                    )
                    raw_events.append(
                        (effective_at, 90, stable, "order_activated", order_id)
                    )
            active = [
                order_id
                for order_id, spec in specs.items()
                if status[order_id] is OrderStatus.ACTIVE
                and str(spec.instrument_id.value) == instrument
            ]
            if not active:
                continue
            volume = Decimal(str(bar.volume))
            capacity = _q(
                volume * request.execution.participation_limit, rounding=ROUND_DOWN
            )
            for order_id in active:
                spec = specs[order_id]
                reference = eligible_reference(spec, bar, rng, request.execution.ambiguity)
                if reference is None:
                    unavailable = unavailable_reference_outcome(spec.time_in_force)
                    if unavailable is not None:
                        terminal, terminal_reason = unavailable
                        status[order_id] = terminal
                        self._transition_current(
                            simulation_id,
                            order_id,
                            effective_at,
                            terminal,
                            terminal_reason,
                            spec,
                            remaining,
                            transition_counts,
                            transition_rows,
                        )
                    continue
                requested = remaining[order_id]
                if fok_capacity_rejected(spec.time_in_force, requested, capacity):
                    status[order_id] = OrderStatus.CANCELLED
                    self._transition_current(
                        simulation_id,
                        order_id,
                        effective_at,
                        OrderStatus.CANCELLED,
                        "fok_capacity",
                        spec,
                        remaining,
                        transition_counts,
                        transition_rows,
                    )
                    continue
                quantity = min(requested, capacity)
                if quantity > 0:
                    fill_sequence += 1
                    fill_id = FillId.new()
                    side_sign = Decimal(1) if spec.side is OrderSide.BUY else Decimal(-1)
                    spread = _q(
                        quantity * reference * request.execution.spread_bps / _BPS
                    )
                    slippage = _q(
                        quantity * reference * request.execution.slippage_bps / _BPS
                    )
                    impact = _q(
                        quantity * reference * request.execution.impact_bps / _BPS
                    )
                    adjustment = (
                        request.execution.spread_bps
                        + request.execution.slippage_bps
                        + request.execution.impact_bps
                    ) / _BPS
                    fill_price = _q(reference * (Decimal(1) + side_sign * adjustment))
                    fee = _q(
                        quantity * fill_price * request.execution.fee_bps / _BPS
                    )
                    fill_content_id = scoped_content_id(
                        {
                            "schema": "persistra.simulation.event_fill@1",
                            "execution": plan.execution_content_id,
                            "sequence": fill_sequence,
                            "order": order_id,
                            "effective_at": effective_at,
                            "quantity": quantity,
                            "reference": reference,
                            "fill_price": fill_price,
                            "costs": (spread, slippage, impact, fee),
                        }
                    )
                    settlement_at = settlement_schedule.get(
                        (str(spec.instrument_id.value), effective_at)
                    )
                    if settlement_at is None:
                        raise EventSimulationError(
                            "market session coverage cannot resolve fill settlement"
                        )
                    transaction_id = accounting._apply_trade(  # pyright: ignore[reportPrivateUsage]
                        connection,
                        context,
                        book_id,
                        TradeFillFacts(
                            fill_content_id,
                            spec.instrument_id,
                            effective_at,
                            settlement_at,
                            side_sign * quantity,
                            fill_price,
                            fee,
                            spread + slippage + impact,
                        ),
                    )
                    obligation = connection.execute(
                        "SELECT settlement_obligation_id FROM "
                        "accounting.settlement_obligations WHERE trade_transaction_id = ?",
                        [transaction_id.value],
                    ).fetchone()
                    if obligation is None:
                        raise AccountingInvariantError(
                            "event fill settlement obligation is missing"
                        )
                    obligation_id = SettlementObligationId.parse(obligation[0])
                    stable += 1
                    raw_events.append(
                        (
                            effective_at,
                            125,
                            stable,
                            "settlement_obligation_created",
                            obligation_id,
                        )
                    )
                    if request.execution.settlement_sessions == 0:
                        accounting._apply_settlement(  # pyright: ignore[reportPrivateUsage]
                            connection,
                            context,
                            book_id,
                            SettlementFacts(
                                scoped_content_id(
                                    {
                                        "schema": (
                                            "persistra.simulation.event_settlement@1"
                                        ),
                                        "obligation": obligation_id,
                                    }
                                ),
                                effective_at,
                                obligation_id,
                            ),
                        )
                        stable += 1
                        raw_events.append(
                            (
                                effective_at,
                                130,
                                stable,
                                "settlement_completed",
                                obligation_id,
                            )
                        )
                    remaining[order_id] = _q(requested - quantity)
                    capacity = _q(capacity - quantity)
                    fill_rows.append(
                        (
                            simulation_id.value,
                            fill_id.value,
                            fill_sequence,
                            order_id.value,
                            effective_at,
                            spec.instrument_id.value,
                            spec.side.value,
                            quantity,
                            reference,
                            fill_price,
                            spread,
                            slippage,
                            impact,
                            fee,
                            str(fill_content_id),
                        )
                    )
                    stable += 1
                    raw_events.append((effective_at, 120, stable, "fill", fill_id))
                if remaining[order_id] == 0:
                    status[order_id] = OrderStatus.FILLED
                    self._transition_current(
                        simulation_id,
                        order_id,
                        effective_at,
                        OrderStatus.FILLED,
                        None,
                        spec,
                        remaining,
                        transition_counts,
                        transition_rows,
                    )
                elif (
                    remainder := remainder_outcome(spec.time_in_force)
                ) is not None:
                    terminal, terminal_reason = remainder
                    status[order_id] = terminal
                    self._transition_current(
                        simulation_id,
                        order_id,
                        effective_at,
                        terminal,
                        terminal_reason,
                        spec,
                        remaining,
                        transition_counts,
                        transition_rows,
                    )

        for order_id, spec in specs.items():
            if status[order_id] in {OrderStatus.ACCEPTED, OrderStatus.ACTIVE}:
                status[order_id] = OrderStatus.EXPIRED
                self._transition_current(
                    simulation_id,
                    order_id,
                    request.horizon_at,
                    OrderStatus.EXPIRED,
                    "run_horizon",
                    spec,
                    remaining,
                    transition_counts,
                    transition_rows,
                )
                stable += 1
                raw_events.append(
                    (request.horizon_at, 190, stable, "order_expired", order_id)
                )

        reconciliation = accounting._reconcile(connection, book_id)  # pyright: ignore[reportPrivateUsage]
        if not reconciliation.balanced:
            raise AccountingInvariantError("event simulation journal does not reconcile")
        event_rows: list[tuple[Any, ...]] = []
        for event_sequence, event in enumerate(
            sorted(raw_events, key=lambda item: (item[0], item[1], item[2])), 1
        ):
            effective_at, priority, stable_sequence, kind, aggregate = event
            event_content_id = scoped_content_id(
                {
                    "schema": "persistra.simulation.event_occurrence@1",
                    "execution": plan.execution_content_id,
                    "sequence": event_sequence,
                    "effective_at": effective_at,
                    "priority": priority,
                    "stable_sequence": stable_sequence,
                    "kind": kind,
                    "aggregate": aggregate,
                }
            )
            event_rows.append(
                (
                    simulation_id.value,
                    event_sequence,
                    effective_at,
                    priority,
                    kind,
                    None if aggregate is None else aggregate.value,
                    str(event_content_id),
                )
            )
        checkpoint = scoped_content_id(
            {
                "schema": "persistra.simulation.event_checkpoint@1",
                "execution": plan.execution_content_id,
                "decision_input_manifest": request.decision_inputs.manifest_content_id,
                "unsafe_override": request.unsafe_override,
                "events": event_rows,
                "orders": order_rows,
                "transitions": transition_rows,
                "fills": fill_rows,
                "journal": reconciliation.journal_content_id,
            }
        )
        tainted, safety_findings = (
            self._project.services.portfolio.decision_inputs.validate(
                request.decision_inputs, request.unsafe_override
            )
        )
        fidelity = {
            "profile_kind": "event",
            "observation_resolution": "bar",
            "bar_fact_availability": "interval_end",
            "ambiguity": request.execution.ambiguity.value,
            "capacity": "stable_sequence_shared_participation",
            "partial_fills": True,
            "queue_claim": "none",
            "settlement": (
                f"effective_t_plus_{request.execution.settlement_sessions}_"
                "market_session_proxy"
            ),
            "replay_status": "eligible",
            "decision_input_tainted": tainted,
            "safety_findings": safety_findings,
        }
        equity_rows, return_rows, position_rows, cash_rows = event_valuation_rows(
            connection,
            run_id=run_id,
            book_id=book_id,
            opening_at=request.opening.effective_at,
            opening_cash=request.opening.cash_usd,
            horizon_at=request.horizon_at,
            bars=bars,
            journal_content_id=reconciliation.journal_content_id,
        )
        findings = (
            "simulation.event.bar_timing_coarse",
            "accounting.settlement.market_session_proxy",
            *safety_findings,
        )
        result_manifest = scoped_content_id(
            {
                "schema": "persistra.results.event_manifest@1",
                "execution": plan.execution_content_id,
                "decision_input_manifest": request.decision_inputs.manifest_content_id,
                "checkpoint": checkpoint,
                "fidelity": fidelity,
                "equity": equity_rows,
                "returns": return_rows,
                "positions": position_rows,
                "cash": cash_rows,
                "orders": order_rows,
                "transitions": transition_rows,
                "fills": fill_rows,
                "events": event_rows,
                "journal": reconciliation.journal_content_id,
            }
        )
        connection.execute(
            "INSERT INTO simulation.event_runs VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?)",
            [
                simulation_id.value,
                book_id.value,
                str(plan.execution_content_id),
                len(event_rows),
                len(order_rows),
                len(fill_rows),
                json.dumps(fidelity, sort_keys=True),
                str(checkpoint),
                context.recorded_at,
            ],
        )
        self._project.services.portfolio.decision_inputs.bind(
            artifact_kind="event_simulation",
            artifact_id=simulation_id,
            manifest=request.decision_inputs,
            override=request.unsafe_override,
            created_at=context.recorded_at,
        )
        self._project.services.portfolio.decision_inputs.bind(
            artifact_kind="run_record",
            artifact_id=run_id,
            manifest=request.decision_inputs,
            override=request.unsafe_override,
            created_at=context.recorded_at,
        )
        connection.executemany(
            "INSERT INTO simulation_data.event_occurrences VALUES (?, ?, ?, ?, ?, ?, ?)",
            event_rows,
        )
        connection.executemany(
            "INSERT INTO simulation_data.orders VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            order_rows,
        )
        connection.executemany(
            "INSERT INTO simulation_data.order_transitions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            transition_rows,
        )
        if fill_rows:
            connection.executemany(
                "INSERT INTO simulation_data.event_fills VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                fill_rows,
            )
        decision_count = len({order.eligibility_at for order in request.orders})
        connection.execute(
            "INSERT INTO results.run_records "
            "(run_record_id, vectorized_simulation_id, execution_content_id, "
            "result_manifest_content_id, decision_count, fill_count, "
            "fidelity_findings_json, created_at, event_simulation_id, run_kind, "
            "accounting_book_id) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'event', ?)",
            [
                run_id.value,
                str(plan.execution_content_id),
                str(result_manifest),
                decision_count,
                len(fill_rows),
                findings_json(findings),
                context.recorded_at,
                simulation_id.value,
                book_id.value,
            ],
        )
        persist_run_logs(
            connection,
            run_id,
            context.recorded_at,
            (
                StructuredLogEntry(
                    "info",
                    "simulation.event",
                    "simulation.event.started",
                    "simulation.run.started",
                    {
                        "execution_content_id": str(plan.execution_content_id),
                        "order_count": len(order_rows),
                    },
                ),
                StructuredLogEntry(
                    "info",
                    "simulation.event",
                    "simulation.event.completed",
                    "simulation.run.completed",
                    {
                        "result_manifest_content_id": str(result_manifest),
                        "event_count": len(event_rows),
                        "fill_count": len(fill_rows),
                        "finding_count": len(findings),
                    },
                ),
            ),
        )
        connection.executemany(
            "INSERT INTO result_data.equity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            equity_rows,
        )
        connection.executemany(
            "INSERT INTO result_data.returns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            return_rows,
        )
        if position_rows:
            connection.executemany(
                "INSERT INTO result_data.positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                position_rows,
            )
        connection.executemany(
            "INSERT INTO result_data.cash VALUES (?, ?, ?, ?, ?)",
            cash_rows,
        )
        connection.executemany(
            "INSERT INTO result_data.orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id.value,
                    row[2],
                    row[1],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[14],
                )
                for row in order_rows
            ],
        )
        connection.executemany(
            "INSERT INTO result_data.order_transitions "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id.value,
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                )
                for row in transition_rows
            ],
        )
        connection.executemany(
            "INSERT INTO result_data.lifecycle_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (run_id.value, *row[1:])
                for row in event_rows
            ],
        )
        if fill_rows:
            connection.executemany(
                "INSERT INTO result_data.fills VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id.value,
                        row[2],
                        row[3],
                        None,
                        row[4],
                        row[5],
                        row[6],
                        row[7],
                        row[8],
                        row[9],
                        row[13],
                        row[11],
                        row[12],
                        row[10],
                        row[14],
                    )
                    for row in fill_rows
                ],
            )
            cost_rows = [
                (
                    run_id.value,
                    row[2],
                    component,
                    row[index],
                    "computed",
                    row[14],
                )
                for row in fill_rows
                for component, index in (
                    ("spread", 10),
                    ("slippage", 11),
                    ("impact", 12),
                    ("fee", 13),
                )
            ]
            connection.executemany(
                "INSERT INTO result_data.cost_components VALUES (?, ?, ?, ?, ?, ?)",
                cost_rows,
            )
        publish_accounting_rows(connection, run_id, book_id)
        publish_exposures(connection, run_id)
        publish_findings(connection, run_id, findings)
        return EventRun(
            self._project,
            EventRunRef(
                simulation_id,
                run_id,
                book_id,
                plan.execution_content_id,
                result_manifest,
                len(event_rows),
                len(order_rows),
                len(fill_rows),
            ),
        )

    @staticmethod
    def _transition(
        simulation_id: EventSimulationId,
        order_id: OrderId,
        effective_at: datetime,
        status: OrderStatus,
        reason: str | None,
        cumulative: Decimal,
        remaining: Decimal,
        counts: dict[OrderId, int],
        rows: list[tuple[Any, ...]],
    ) -> None:
        sequence = counts.get(order_id, 0) + 1
        counts[order_id] = sequence
        content_id = scoped_content_id(
            {
                "schema": "persistra.simulation.order_transition@1",
                "order": order_id,
                "sequence": sequence,
                "effective_at": effective_at,
                "status": status.value,
                "reason": reason,
                "cumulative": cumulative,
                "remaining": remaining,
            }
        )
        rows.append(
            (
                simulation_id.value,
                order_id.value,
                sequence,
                effective_at,
                status.value,
                reason,
                cumulative,
                remaining,
                str(content_id),
            )
        )

    def _transition_current(
        self,
        simulation_id: EventSimulationId,
        order_id: OrderId,
        effective_at: datetime,
        status: OrderStatus,
        reason: str | None,
        spec: OrderSpec,
        remaining: dict[OrderId, Decimal],
        counts: dict[OrderId, int],
        rows: list[tuple[Any, ...]],
    ) -> None:
        self._transition(
            simulation_id,
            order_id,
            effective_at,
            status,
            reason,
            _q(spec.quantity - remaining[order_id]),
            remaining[order_id],
            counts,
            rows,
        )

    @staticmethod
    def _settle_due(
        connection: ManagedConnection,
        context: TransactionContext,
        accounting: Any,
        book_id: AccountingBookId,
        through: datetime,
    ) -> tuple[SettlementObligationId, ...]:
        rows = connection.execute(
            "SELECT settlement_obligation_id, due_at FROM "
            "accounting.settlement_obligations WHERE accounting_book_id = ? "
            "AND status = 'open' AND due_at <= ? "
            "ORDER BY due_at, settlement_obligation_id",
            [book_id.value, through],
        ).fetchall()
        settled: list[SettlementObligationId] = []
        for raw_id, due_at in rows:
            obligation_id = SettlementObligationId.parse(raw_id)
            accounting._apply_settlement(  # pyright: ignore[reportPrivateUsage]
                connection,
                context,
                book_id,
                SettlementFacts(
                    scoped_content_id(
                        {
                            "schema": "persistra.simulation.event_settlement@1",
                            "obligation": obligation_id,
                            "due_at": due_at,
                        }
                    ),
                    due_at,
                    obligation_id,
                ),
            )
            settled.append(obligation_id)
        return tuple(settled)

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "event simulation requires research_write mode"
            )


@dataclass(frozen=True, slots=True)
class EventRun:
    _project: Project
    reference: EventRunRef

    @property
    def id(self) -> RunRecordId:
        return self.reference.run_record_id

    def result(self) -> RunHandle:
        """Return the engine-independent normalized result handle."""
        return self._project.services.results.get(self.reference.run_record_id)

    def events(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame(
            "event_occurrences", "event_sequence", max_rows=max_rows
        )

    def orders(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("orders", "stable_sequence", max_rows=max_rows)

    def transitions(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame(
            "order_transitions", "order_id, transition_sequence", max_rows=max_rows
        )

    def fills(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("event_fills", "fill_sequence", max_rows=max_rows)

    def journal(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._project.services.accounting.get(
            self.reference.accounting_book_id
        ).journal(max_rows=max_rows)

    def _frame(self, table: str, order_by: str, *, max_rows: int) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            f"SELECT * FROM simulation_data.{table} "
            f"WHERE event_simulation_id = ? ORDER BY {order_by} LIMIT ?",
            [self.reference.event_simulation_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("event simulation frame exceeds max_rows")
        return frame


def _settlement_schedule(
    bars: pd.DataFrame,
    settlement_sessions: int,
) -> dict[tuple[str, datetime], datetime]:
    schedule: dict[tuple[str, datetime], datetime] = {}
    for instrument, frame in bars.groupby("instrument_id", sort=True):
        instants = tuple(
            pd.Timestamp(value).to_pydatetime()
            for value in frame["interval_end"].drop_duplicates().sort_values()
        )
        for index, effective_at in enumerate(instants):
            due_index = index + settlement_sessions
            if due_index < len(instants):
                schedule[(str(instrument), effective_at)] = instants[due_index]
    return schedule
