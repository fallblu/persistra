"""Monthly next-open vectorized simulation over immutable targets."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, localcontext
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.accounting import (
    DividendFacts,
    SettlementFacts,
    SettlementObligationId,
    SplitFacts,
    TradeFillFacts,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    AccountingInvariantError,
    CapabilityUnavailableError,
    VectorizedSimulationError,
    VectorizedSimulationRequestError,
)
from persistra.market import BarQuery, BarState, CorporateActionKind, CorporateActionStatus
from persistra.portfolio import ConstructionStatus
from persistra.reference import InstrumentId
from persistra.results.publication import (
    findings_json,
    publish_accounting_rows,
    publish_vectorized_rows,
)
from persistra.simulation.event_services import EventSimulationService
from persistra.simulation.models import (
    CapacityAction,
    FidelityProfileId,
    QuantityPolicy,
    RunRecordId,
    VectorizedRunRef,
    VectorizedSimulationId,
    VectorizedSimulationPlan,
    VectorizedSimulationRequest,
)

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.accounting.services import AccountingService
    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project

_Q = Decimal("0.000000000001")
_BPS = Decimal("10000")


def _q(value: Decimal, *, rounding: str = ROUND_HALF_EVEN) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_Q, rounding=rounding)


class VectorizedSimulationService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def plan(self, request: VectorizedSimulationRequest) -> VectorizedSimulationPlan:
        self._project._guard()  # pyright: ignore[reportPrivateUsage]
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        target = connection.execute(
            "SELECT execution_content_id, output_manifest_content_id, decision_count "
            "FROM portfolio.construction_results WHERE "
            "portfolio_construction_result_id = ?",
            [request.construction_result_id.value],
        ).fetchone()
        if target is None:
            raise VectorizedSimulationRequestError("construction result is missing")
        safety = self._project.services.portfolio.decision_inputs.for_artifact(
            "portfolio_construction_result", request.construction_result_id
        )
        if safety != request.decision_inputs:
            raise VectorizedSimulationRequestError(
                "simulation decision inputs do not match the construction result"
            )
        self._project.services.portfolio.decision_inputs.validate(
            safety, request.unsafe_override
        )
        if request.market_context.market_database not in {None, request.market_database}:
            raise VectorizedSimulationRequestError(
                "request market database conflicts with as-of context"
            )
        if int(target[2]) > request.execution.max_decisions:
            raise VectorizedSimulationRequestError("simulation exceeds max_decisions")
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.simulation.vectorized_execution@1",
                "request": request,
                "target_execution": target[0],
                "target_manifest": target[1],
                "decision_count": int(target[2]),
                "timing": "next_session_open",
                "fidelity": "vectorized_no_orders",
            }
        )
        return VectorizedSimulationPlan(request, execution_content_id)

    def run(self, plan: VectorizedSimulationPlan) -> VectorizedRun:
        self._require_write()
        expected = self.plan(plan.request)
        if expected.execution_content_id != plan.execution_content_id:
            raise VectorizedSimulationRequestError("simulation plan content does not verify")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT vectorized_simulation_id FROM simulation.vectorized_runs "
            "WHERE execution_content_id = ?",
            [str(plan.execution_content_id)],
        ).fetchone()
        if existing is not None:
            return self.get(VectorizedSimulationId.parse(existing[0]))
        market = self._load_market_inputs(plan.request)

        def operation(context: TransactionContext) -> VectorizedRun:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._execute(active, context, plan, market)

        return self._project.services.transactions.run("vectorized_simulation_run", operation)

    def get(self, simulation_id: VectorizedSimulationId) -> VectorizedRun:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT run_record_id, execution_content_id, result_manifest_content_id, "
            "decision_count, fill_count FROM simulation.vectorized_runs "
            "WHERE vectorized_simulation_id = ?",
            [simulation_id.value],
        ).fetchone()
        if row is None:
            raise VectorizedSimulationError("vectorized simulation is missing")
        return VectorizedRun(
            self._project,
            VectorizedRunRef(
                simulation_id,
                RunRecordId.parse(row[0]),
                ContentId.parse(row[1]),
                ContentId.parse(row[2]),
                int(row[3]),
                int(row[4]),
            ),
        )

    def _load_market_inputs(
        self, request: VectorizedSimulationRequest
    ) -> dict[str, pd.DataFrame]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        decisions = connection.execute(
            "SELECT decision_at, status FROM portfolio.target_decisions WHERE "
            "portfolio_construction_result_id = ? ORDER BY decision_at",
            [request.construction_result_id.value],
        ).fetchdf()
        weights = connection.execute(
            "SELECT decision_at, instrument_id, target_weight FROM "
            "portfolio.target_weights WHERE portfolio_construction_result_id = ? "
            "ORDER BY decision_at, instrument_id",
            [request.construction_result_id.value],
        ).fetchdf()
        if decisions.empty:
            raise VectorizedSimulationRequestError("construction result has no decisions")
        instruments = tuple(
            InstrumentId.parse(value)
            for value in sorted({str(value) for value in weights["instrument_id"]})
        )
        start = decisions["decision_at"].min().to_pydatetime()
        end = decisions["decision_at"].max().to_pydatetime() + timedelta(days=14)
        bars = self._project.services.market.bars.query(
            BarQuery(
                instruments,
                request.bar_spec,
                start,
                end,
                request.market_context,
                include_partial=False,
                include_no_trade=True,
                max_rows=max(10_000, len(instruments) * (len(decisions) + 20)),
            )
        )
        actions = self._project.services.market.actions.query(
            instruments,
            start=request.opening.effective_at,
            end=end,
            context=request.market_context,
        )
        return {
            "actions": actions,
            "bars": bars,
            "decisions": decisions,
            "weights": weights,
        }

    def _execute(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        plan: VectorizedSimulationPlan,
        market: dict[str, pd.DataFrame],
    ) -> VectorizedRun:
        accounting: AccountingService = self._project.services.accounting
        book = accounting._create_book(  # pyright: ignore[reportPrivateUsage]
            connection, context, plan.request.opening
        )
        book_id = book.reference.accounting_book_id
        simulation_id = VectorizedSimulationId.new()
        run_id = RunRecordId.new()
        decisions = market["decisions"]
        weights = market["weights"]
        bars = market["bars"]
        actions = market["actions"]
        fills: list[tuple[Any, ...]] = []
        rebalances: list[tuple[Any, ...]] = []
        targets: list[tuple[Any, ...]] = []
        equity: list[tuple[Any, ...]] = []
        positions: list[tuple[Any, ...]] = []
        cash_rows: list[tuple[Any, ...]] = []
        cost_rows: list[tuple[Any, ...]] = []
        checkpoints: list[tuple[Any, ...]] = []
        action_cursor: set[str] = set()
        opening_root = scoped_content_id(
            {
                "schema": "persistra.results.opening_sample@1",
                "opening": plan.request.opening,
            }
        )
        equity.append(
            (
                run_id.value,
                1,
                plan.request.opening.effective_at,
                1,
                _q(plan.request.opening.cash_usd),
                Decimal(0),
                Decimal(0),
                "complete",
                str(opening_root),
            )
        )
        cash_rows.append(
            (
                run_id.value,
                1,
                plan.request.opening.effective_at,
                _q(plan.request.opening.cash_usd),
                str(opening_root),
            )
        )
        fill_ordinal = 0
        sample_ordinal = 1
        for decision_ordinal, decision in enumerate(
            decisions.itertuples(index=False), 1
        ):
            decision_at = pd.Timestamp(cast("Any", decision.decision_at)).to_pydatetime()
            decision_weights = weights[weights["decision_at"] == decision.decision_at]
            if decision.status != ConstructionStatus.COMPLETED.value:
                rebalances.append(
                    (
                        simulation_id.value,
                        decision_at,
                        None,
                        "target_failed",
                        None,
                        "simulation.target.failed",
                        str(
                            scoped_content_id(
                                {
                                    "schema": "persistra.simulation.rebalance@1",
                                    "decision_at": decision_at,
                                    "state": "target_failed",
                                }
                            )
                        ),
                    )
                )
                if plan.request.execution.target_failure == "skip_decision":
                    continue
                raise VectorizedSimulationError("failed target stops simulation")
            asset_ids = {
                str(item) for item in decision_weights["instrument_id"].tolist()
            }
            held_ids = set(self._position_map(connection, book_id))
            all_ids = sorted(asset_ids | held_ids)
            execution_bars = self._next_bars(bars, all_ids, decision_at)
            if set(execution_bars) != set(all_ids):
                raise VectorizedSimulationError("next-open execution price is unavailable")
            execution_at = max(row["interval_start"] for row in execution_bars.values())
            self._apply_actions(
                connection,
                context,
                accounting,
                book_id,
                actions,
                action_cursor,
                execution_at,
            )
            current = self._position_map(connection, book_id)
            cash = accounting._cash(connection, book_id)  # pyright: ignore[reportPrivateUsage]
            reference = {
                instrument: Decimal(str(execution_bars[instrument]["open"]))
                for instrument in all_ids
            }
            if any(price <= 0 for price in reference.values()):
                raise VectorizedSimulationError("execution price must be positive")
            nav = cash + sum(
                (quantity * reference[instrument] for instrument, quantity in current.items()),
                Decimal(0),
            )
            target_weights = {
                str(row.instrument_id): Decimal(str(row.target_weight))
                for row in decision_weights.itertuples(index=False)
            }
            target_quantities = {
                instrument: self._target_quantity(
                    nav
                    * target_weights.get(instrument, Decimal(0))
                    / reference[instrument],
                    plan,
                )
                for instrument in all_ids
            }
            deltas = {
                instrument: target_quantities[instrument]
                - current.get(instrument, Decimal(0))
                for instrument in all_ids
            }
            threshold = nav * plan.request.execution.rebalance_threshold_bps / _BPS
            deltas = {
                instrument: (
                    Decimal(0)
                    if abs(delta * reference[instrument]) < threshold
                    else self._capacity_delta(
                        bars,
                        instrument,
                        decision_at,
                        delta,
                        plan,
                    )
                )
                for instrument, delta in deltas.items()
            }
            sell_deltas = {
                instrument: delta for instrument, delta in deltas.items() if delta < 0
            }
            buy_deltas = {
                instrument: delta for instrument, delta in deltas.items() if delta > 0
            }
            for instrument, delta in sell_deltas.items():
                fill_ordinal += 1
                fill = self._fill(
                    accounting,
                    connection,
                    context,
                    book_id,
                    plan,
                    decision_at,
                    execution_at,
                    InstrumentId.parse(instrument),
                    "sell",
                    -delta,
                    reference[instrument],
                    fill_ordinal,
                )
                fills.append((simulation_id.value, *fill))
                cost_rows.extend(self._cost_rows(run_id, fill_ordinal, fill))
            buy_scale = self._buy_scale(
                accounting._cash(connection, book_id),  # pyright: ignore[reportPrivateUsage]
                buy_deltas,
                reference,
                plan,
            )
            for instrument, delta in buy_deltas.items():
                quantity = _q(delta * buy_scale, rounding=ROUND_DOWN)
                if quantity <= 0:
                    continue
                fill_ordinal += 1
                fill = self._fill(
                    accounting,
                    connection,
                    context,
                    book_id,
                    plan,
                    decision_at,
                    execution_at,
                    InstrumentId.parse(instrument),
                    "buy",
                    quantity,
                    reference[instrument],
                    fill_ordinal,
                )
                fills.append((simulation_id.value, *fill))
                cost_rows.extend(self._cost_rows(run_id, fill_ordinal, fill))
            final_positions = self._position_map(connection, book_id)
            filled_by_instrument = {
                str(fill[3]): Decimal(str(fill[5]))
                * (Decimal(1) if fill[4] == "buy" else Decimal(-1))
                for fill in fills
                if fill[1] == decision_at
            }
            for instrument in all_ids:
                initial = current.get(instrument, Decimal(0))
                filled = filled_by_instrument.get(instrument, Decimal(0))
                targets.append(
                    (
                        run_id.value,
                        decision_at,
                        InstrumentId.parse(instrument).value,
                        float(target_weights.get(instrument, Decimal(0))),
                        target_quantities[instrument],
                        final_positions.get(instrument, Decimal(0)),
                        _q(target_quantities[instrument] - (initial + filled)),
                    )
                )
            cash = accounting._cash(connection, book_id)  # pyright: ignore[reportPrivateUsage]
            market_values = {
                instrument: quantity * reference[instrument]
                for instrument, quantity in final_positions.items()
            }
            final_nav = _q(cash + sum(market_values.values(), Decimal(0)))
            sample_ordinal += 1
            prefix = int(
                connection.execute(
                    "SELECT max(book_sequence) FROM accounting.journal_transactions "
                    "WHERE accounting_book_id = ?",
                    [book_id.value],
                ).fetchone()[0]
            )
            sample_root = scoped_content_id(
                {
                    "schema": "persistra.results.equity_sample@1",
                    "run": run_id,
                    "decision_at": decision_at,
                    "execution_at": execution_at,
                    "journal_prefix": prefix,
                    "nav": final_nav,
                    "positions": final_positions,
                    "cash": cash,
                }
            )
            if (
                decision_ordinal % plan.request.execution.checkpoint_every == 0
                or decision_ordinal == len(decisions)
            ):
                checkpoint_content_id = scoped_content_id(
                    {
                        "schema": "persistra.simulation.checkpoint@1",
                        "execution": plan.execution_content_id,
                        "decision_ordinal": decision_ordinal,
                        "journal_prefix": prefix,
                        "sample": sample_root,
                        "positions": final_positions,
                        "cash": cash,
                    }
                )
                checkpoints.append(
                    (
                        simulation_id.value,
                        len(checkpoints) + 1,
                        decision_ordinal,
                        prefix,
                        str(checkpoint_content_id),
                    )
                )
            equity.append(
                (
                    run_id.value,
                    sample_ordinal,
                    execution_at,
                    prefix,
                    final_nav,
                    _q(sum((abs(value) for value in market_values.values()), Decimal(0))),
                    _q(sum(market_values.values(), Decimal(0))),
                    "complete",
                    str(sample_root),
                )
            )
            cash_rows.append(
                (run_id.value, sample_ordinal, execution_at, _q(cash), str(sample_root))
            )
            for instrument, quantity in sorted(final_positions.items()):
                positions.append(
                    (
                        run_id.value,
                        sample_ordinal,
                        execution_at,
                        InstrumentId.parse(instrument).value,
                        quantity,
                        reference[instrument],
                        _q(quantity * reference[instrument]),
                        str(sample_root),
                    )
                )
            rebalances.append(
                (
                    simulation_id.value,
                    decision_at,
                    execution_at,
                    "completed",
                    nav,
                    None,
                    str(
                        scoped_content_id(
                            {
                                "schema": "persistra.simulation.rebalance@1",
                                "decision_at": decision_at,
                                "execution_at": execution_at,
                                "nav": nav,
                                "targets": target_quantities,
                            }
                        )
                    ),
                )
            )
        reconciliation = accounting._reconcile(connection, book_id)  # pyright: ignore[reportPrivateUsage]
        if not reconciliation.balanced:
            raise AccountingInvariantError("completed simulation journal does not reconcile")
        returns = self._returns(run_id, equity)
        result_manifest = scoped_content_id(
            {
                "schema": "persistra.results.vectorized_manifest@1",
                "execution": plan.execution_content_id,
                "decision_input_manifest": plan.request.decision_inputs.manifest_content_id,
                "unsafe_override": plan.request.unsafe_override,
                "reconciliation": reconciliation,
                "equity": equity,
                "returns": returns,
                "targets": targets,
                "fills": fills,
                "costs": cost_rows,
            }
        )
        connection.execute(
            "INSERT INTO simulation.vectorized_runs VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                simulation_id.value,
                run_id.value,
                book_id.value,
                plan.request.construction_result_id.value,
                str(plan.execution_content_id),
                str(result_manifest),
                len(decisions),
                fill_ordinal,
                "completed",
                context.recorded_at,
            ],
        )
        tainted, safety_findings = (
            self._project.services.portfolio.decision_inputs.validate(
                plan.request.decision_inputs, plan.request.unsafe_override
            )
        )
        fidelity = {
            "profile_kind": "vectorized",
            "bar_resolution": "session",
            "execution_timing": "next_session_open",
            "order_model": "not_modeled_vectorized",
            "partial_fill_model": "not_modeled_vectorized",
            "capacity_action": plan.request.execution.capacity_action.value,
            "quantity_policy": plan.request.execution.quantity_policy.value,
            "settlement": "explicit_t0_reclassification",
            "accounting": "reconciled_double_entry",
            "decision_input_tainted": tainted,
            "safety_findings": safety_findings,
        }
        fidelity_content_id = scoped_content_id(
            {"schema": "persistra.simulation.fidelity_profile@1", "profile": fidelity}
        )
        fidelity_id = FidelityProfileId.new()
        connection.execute(
            "INSERT INTO simulation.fidelity_profiles VALUES (?, ?, ?, ?)",
            [
                fidelity_id.value,
                str(fidelity_content_id),
                json.dumps(fidelity, sort_keys=True),
                context.recorded_at,
            ],
        )
        if not checkpoints:
            raise VectorizedSimulationError("completed simulation has no checkpoint")
        connection.executemany(
            "INSERT INTO simulation.simulation_checkpoints VALUES (?, ?, ?, ?, ?)",
            checkpoints,
        )
        connection.execute(
            "INSERT INTO simulation.vectorized_run_hardening VALUES (?, ?, ?, ?)",
            [
                simulation_id.value,
                fidelity_id.value,
                checkpoints[-1][4],
                (
                    "eligible"
                    if plan.request.execution.capacity_action is CapacityAction.CLIP
                    else "ineligible"
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO simulation_data.rebalance_decisions VALUES "
            "(?, ?, ?, ?, ?, ?, ?)",
            rebalances,
        )
        if fills:
            connection.executemany(
                "INSERT INTO simulation_data.synthetic_fills VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                fills,
            )
        findings = (
            "simulation.vectorized.no_orders",
            "accounting.dividend.immediate_payment",
            f"simulation.capacity.{plan.request.execution.capacity_action.value}",
            *safety_findings,
        )
        connection.execute(
            "INSERT INTO results.run_records "
            "(run_record_id, vectorized_simulation_id, execution_content_id, "
            "result_manifest_content_id, decision_count, fill_count, "
            "fidelity_findings_json, created_at, run_kind, accounting_book_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'vectorized', ?)",
            [
                run_id.value,
                simulation_id.value,
                str(plan.execution_content_id),
                str(result_manifest),
                len(decisions),
                fill_ordinal,
                findings_json(findings),
                context.recorded_at,
                book_id.value,
            ],
        )
        self._project.services.portfolio.decision_inputs.bind(
            artifact_kind="vectorized_simulation",
            artifact_id=simulation_id,
            manifest=plan.request.decision_inputs,
            override=plan.request.unsafe_override,
            created_at=context.recorded_at,
        )
        self._project.services.portfolio.decision_inputs.bind(
            artifact_kind="run_record",
            artifact_id=run_id,
            manifest=plan.request.decision_inputs,
            override=plan.request.unsafe_override,
            created_at=context.recorded_at,
        )
        connection.executemany(
            "INSERT INTO result_data.equity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            equity,
        )
        if returns:
            connection.executemany(
                "INSERT INTO result_data.returns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                returns,
            )
        if positions:
            connection.executemany(
                "INSERT INTO result_data.positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                positions,
            )
        connection.executemany(
            "INSERT INTO result_data.cash VALUES (?, ?, ?, ?, ?)", cash_rows
        )
        if targets:
            connection.executemany(
                "INSERT INTO result_data.targets VALUES (?, ?, ?, ?, ?, ?, ?)", targets
            )
        if cost_rows:
            connection.executemany(
                "INSERT INTO result_data.cost_components VALUES (?, ?, ?, ?, ?, ?)",
                cost_rows,
            )
        publish_accounting_rows(connection, run_id, book_id)
        publish_vectorized_rows(connection, run_id, simulation_id, findings)
        return VectorizedRun(
            self._project,
            VectorizedRunRef(
                simulation_id,
                run_id,
                plan.execution_content_id,
                result_manifest,
                len(decisions),
                fill_ordinal,
            ),
        )

    def _apply_actions(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        accounting: AccountingService,
        book_id: Any,
        actions: pd.DataFrame,
        cursor: set[str],
        through: datetime,
    ) -> None:
        revision_ids = tuple(
            UUID(str(value)) for value in actions["canonical_revision_id"]
        )
        legs = self._project.services.market.actions.legs(revision_ids)
        cash_by_revision = {
            str(row["canonical_revision_id"]): Decimal(
                str(row["cash_per_subject_unit"])
            )
            for row in legs.to_dict("records")
            if row["leg_kind"] == "cash"
            and not pd.isna(row["cash_per_subject_unit"])
        }
        for action in actions.itertuples(index=False):
            revision_id = str(action.canonical_revision_id)
            effective = pd.Timestamp(
                cast(
                    "Any",
                    action.effective_at
                    if not pd.isna(action.effective_at)
                    else action.ex_at,
                )
            )
            if (
                revision_id in cursor
                or pd.isna(effective)
                or effective.to_pydatetime() > through
                or action.action_status == CorporateActionStatus.CANCELLED.value
            ):
                continue
            kind = CorporateActionKind(action.action_kind)
            instrument = InstrumentId.parse(action.subject_instrument_id)
            source = ContentId.from_bytes(revision_id.encode())
            if kind in {CorporateActionKind.SPLIT, CorporateActionKind.REVERSE_SPLIT}:
                accounting._apply_split(  # pyright: ignore[reportPrivateUsage]
                    connection,
                    context,
                    book_id,
                    SplitFacts(
                        source,
                        instrument,
                        effective.to_pydatetime(),
                        Decimal(str(action.share_ratio)),
                    ),
                )
            elif kind in {
                CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                CorporateActionKind.SPECIAL_CASH_DIVIDEND,
                CorporateActionKind.ETF_DISTRIBUTION,
            }:
                accounting._apply_dividend(  # pyright: ignore[reportPrivateUsage]
                    connection,
                    context,
                    book_id,
                    DividendFacts(
                        source,
                        instrument,
                        effective.to_pydatetime(),
                        cash_by_revision[revision_id],
                    ),
                )
            cursor.add(revision_id)

    def _fill(
        self,
        accounting: AccountingService,
        connection: ManagedConnection,
        context: TransactionContext,
        book_id: Any,
        plan: VectorizedSimulationPlan,
        decision_at: datetime,
        execution_at: datetime,
        instrument: InstrumentId,
        side: str,
        quantity: Decimal,
        reference: Decimal,
        ordinal: int,
    ) -> tuple[Any, ...]:
        slippage_rate = plan.request.execution.slippage_bps / _BPS
        fill_price = _q(
            reference
            * (Decimal(1) + slippage_rate if side == "buy" else Decimal(1) - slippage_rate)
        )
        notional = _q(quantity * fill_price)
        commission = _q(notional * plan.request.execution.commission_bps / _BPS)
        slippage = _q(quantity * abs(fill_price - reference))
        source = scoped_content_id(
            {
                "schema": "persistra.simulation.synthetic_fill@1",
                "execution": plan.execution_content_id,
                "ordinal": ordinal,
                "decision_at": decision_at,
                "execution_at": execution_at,
                "instrument": instrument,
                "side": side,
                "quantity": quantity,
                "reference": reference,
                "fill_price": fill_price,
                "commission": commission,
            }
        )
        transaction_id = accounting._apply_trade(  # pyright: ignore[reportPrivateUsage]
            connection,
            context,
            book_id,
            TradeFillFacts(
                source,
                instrument,
                execution_at,
                execution_at,
                quantity if side == "buy" else -quantity,
                fill_price,
                commission,
                slippage,
            ),
        )
        obligation = connection.execute(
            "SELECT settlement_obligation_id FROM accounting.settlement_obligations "
            "WHERE trade_transaction_id = ?",
            [transaction_id.value],
        ).fetchone()
        if obligation is None:
            raise AccountingInvariantError("fill settlement obligation is missing")
        settlement_source = scoped_content_id(
            {
                "schema": "persistra.simulation.synthetic_fill_settlement@1",
                "fill": source,
            }
        )
        accounting._apply_settlement(  # pyright: ignore[reportPrivateUsage]
            connection,
            context,
            book_id,
            SettlementFacts(
                settlement_source,
                execution_at,
                SettlementObligationId.parse(obligation[0]),
            ),
        )
        return (
            ordinal,
            decision_at,
            execution_at,
            instrument.value,
            side,
            quantity,
            reference,
            fill_price,
            commission,
            slippage,
            str(source),
        )

    def _buy_scale(
        self,
        cash: Decimal,
        deltas: dict[str, Decimal],
        prices: dict[str, Decimal],
        plan: VectorizedSimulationPlan,
    ) -> Decimal:
        multiplier = (
            Decimal(1) + plan.request.execution.slippage_bps / _BPS
        ) * (
            Decimal(1) + plan.request.execution.commission_bps / _BPS
        )
        required = sum(
            (quantity * prices[instrument] * multiplier for instrument, quantity in deltas.items()),
            Decimal(0),
        )
        if required <= cash or required == 0:
            return Decimal(1)
        if plan.request.execution.insufficient_cash == "fail":
            raise VectorizedSimulationError("rebalance has insufficient cash")
        rounding_reserve = Decimal(2 * len(deltas)) * _Q
        return max(Decimal(0), (cash - rounding_reserve) / required)

    @staticmethod
    def _target_quantity(
        quantity: Decimal, plan: VectorizedSimulationPlan
    ) -> Decimal:
        if plan.request.execution.quantity_policy is QuantityPolicy.WHOLE_SHARE_DOWN:
            return quantity.quantize(Decimal(1), rounding=ROUND_DOWN)
        return _q(quantity, rounding=ROUND_DOWN)

    @staticmethod
    def _capacity_delta(
        bars: pd.DataFrame,
        instrument: str,
        decision_at: datetime,
        delta: Decimal,
        plan: VectorizedSimulationPlan,
    ) -> Decimal:
        policy = plan.request.execution
        if (
            policy.capacity_action is CapacityAction.IGNORE_WITH_WARNING
            or policy.participation_limit is None
        ):
            return delta
        history = bars[
            (bars["instrument_id"] == instrument)
            & (bars["interval_end"] <= decision_at)
            & (bars["bar_state"] == BarState.COMPLETE.value)
            & bars["volume"].notna()
        ]
        available = (
            Decimal(0)
            if history.empty
            else _q(
                Decimal(str(history.iloc[-1]["volume"])) * policy.participation_limit,
                rounding=ROUND_DOWN,
            )
        )
        if abs(delta) <= available:
            return delta
        if policy.capacity_action is CapacityAction.FAIL:
            raise VectorizedSimulationError("rebalance exceeds causal capacity")
        return available if delta > 0 else -available

    @staticmethod
    def _next_bars(
        bars: pd.DataFrame, instruments: list[str], decision_at: datetime
    ) -> dict[str, pd.Series[Any]]:
        result: dict[str, pd.Series[Any]] = {}
        for instrument in instruments:
            eligible = bars[
                (bars["instrument_id"] == instrument)
                & (bars["interval_start"] > decision_at)
                & (bars["bar_state"] == BarState.COMPLETE.value)
                & bars["open"].notna()
            ]
            if not eligible.empty:
                result[instrument] = eligible.iloc[0]
        return result

    @staticmethod
    def _position_map(
        connection: ManagedConnection, book_id: Any
    ) -> dict[str, Decimal]:
        rows = connection.execute(
            "SELECT cast(p.instrument_id AS VARCHAR), sum(p.amount) FROM "
            "journal_data.journal_postings p JOIN accounting.journal_transactions t "
            "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
            "AND p.account_code = 'position' GROUP BY p.instrument_id "
            "HAVING sum(p.amount) <> 0 ORDER BY p.instrument_id",
            [book_id.value],
        ).fetchall()
        return {str(row[0]): Decimal(str(row[1])) for row in rows}

    @staticmethod
    def _cost_rows(
        run_id: RunRecordId, ordinal: int, fill: tuple[Any, ...]
    ) -> list[tuple[Any, ...]]:
        source = fill[-1]
        return [
            (run_id.value, ordinal, "commission", fill[8], "observed", source),
            (run_id.value, ordinal, "slippage", fill[9], "modeled", source),
        ]

    @staticmethod
    def _returns(
        run_id: RunRecordId, equity: list[tuple[Any, ...]]
    ) -> list[tuple[Any, ...]]:
        result: list[tuple[Any, ...]] = []
        for ordinal in range(1, len(equity)):
            opening = Decimal(str(equity[ordinal - 1][4]))
            closing = Decimal(str(equity[ordinal][4]))
            value = None if opening <= 0 else float(closing / opening - Decimal(1))
            state = "invalid_base" if value is None else "computed"
            root = scoped_content_id(
                {
                    "schema": "persistra.results.return@1",
                    "run": run_id,
                    "ordinal": ordinal,
                    "opening": opening,
                    "closing": closing,
                }
            )
            result.append(
                (
                    run_id.value,
                    ordinal,
                    equity[ordinal - 1][2],
                    equity[ordinal][2],
                    opening,
                    closing,
                    value,
                    state,
                    str(root),
                )
            )
        return result

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "vectorized simulation requires research_write mode"
            )


class SimulationService:
    __slots__ = ("event", "vectorized")

    def __init__(self, project: Project) -> None:
        self.event = EventSimulationService(project)
        self.vectorized = VectorizedSimulationService(project)


class VectorizedRun:
    __slots__ = ("_project", "reference")

    def __init__(self, project: Project, reference: VectorizedRunRef) -> None:
        self._project = project
        self.reference = reference

    @property
    def id(self) -> RunRecordId:
        return self.reference.run_record_id

    def result(self) -> Any:
        return self._project.services.results.get(self.reference.run_record_id)
