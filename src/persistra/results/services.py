"""This module contains the bounded normalized run-result queries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    ResultQueryLimitError,
    VectorizedSimulationError,
)
from persistra.results.exports import ExportService
from persistra.results.models import AnnotationId, RunSummary

if TYPE_CHECKING:
    from persistra.project import Project
    from persistra.simulation import RunRecordId


class ResultService:
    __slots__ = ("_project", "exports")

    def __init__(self, project: Project) -> None:
        self._project = project
        self.exports = ExportService(project)

    def list(self, *, max_rows: int = 10_000) -> pd.DataFrame:
        if max_rows <= 0:
            raise ResultQueryLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT r.run_record_id, r.execution_content_id, "
            "r.result_manifest_content_id, r.decision_count, r.fill_count, "
            "coalesce(t.retention_state, 'active') AS retention_state, r.created_at "
            "FROM results.run_records r LEFT JOIN results.run_retention t "
            "USING (run_record_id) ORDER BY r.created_at, r.run_record_id LIMIT ?",
            [max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResultQueryLimitError("run repository rows exceed max_rows")
        for column in ("run_record_id", "execution_content_id", "result_manifest_content_id"):
            frame[column] = frame[column].astype("string")
        frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
        return frame

    def annotate(
        self, run_id: RunRecordId, note: str, *, tags: tuple[str, ...] = ()
    ) -> AnnotationId:
        self._require_write()
        if not note or tuple(sorted(set(tags))) != tags:
            raise ResultQueryLimitError("annotation note or tags are invalid")
        self.get(run_id)
        annotation_id = AnnotationId.new()

        def operation(context: Any) -> AnnotationId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "INSERT INTO results.annotations VALUES (?, ?, 1, ?, ?, ?)",
                [
                    annotation_id.value,
                    run_id.value,
                    note,
                    json.dumps(tags),
                    context.recorded_at,
                ],
            )
            return annotation_id

        return self._project.services.transactions.run("result_annotate", operation)

    def annotations(self, run_id: RunRecordId, *, max_rows: int = 10_000) -> pd.DataFrame:
        self.get(run_id)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT annotation_id, revision, note, tags_json, created_at FROM "
            "results.annotations WHERE run_record_id = ? "
            "ORDER BY created_at, annotation_id, revision LIMIT ?",
            [run_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResultQueryLimitError("annotation rows exceed max_rows")
        return frame

    def archive(self, run_id: RunRecordId) -> None:
        self._set_retention(run_id, "archived")

    def request_deletion(self, run_id: RunRecordId) -> None:
        self._require_write()
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        referenced = connection.execute(
            "SELECT 1 FROM analysis.artifacts WHERE run_record_id = ? LIMIT 1",
            [run_id.value],
        ).fetchone()
        if referenced is not None:
            raise ResultQueryLimitError(
                "run deletion is blocked by immutable analysis references"
            )
        self._set_retention(run_id, "deletion_requested")

    def get(self, run_id: RunRecordId) -> RunHandle:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT run_kind, coalesce(cast(vectorized_simulation_id AS VARCHAR), "
            "cast(event_simulation_id AS VARCHAR)), execution_content_id, "
            "result_manifest_content_id, decision_count, fill_count, "
            "fidelity_findings_json FROM results.run_records WHERE run_record_id = ?",
            [run_id.value],
        ).fetchone()
        if row is None:
            raise VectorizedSimulationError("run result is missing")
        return RunHandle(
            self._project,
            RunSummary(
                run_id,
                str(row[0]),
                str(row[1]),
                ContentId.parse(row[2]),
                ContentId.parse(row[3]),
                int(row[4]),
                int(row[5]),
                tuple(json.loads(row[6])),
            ),
        )

    def _set_retention(self, run_id: RunRecordId, state: str) -> None:
        self._require_write()
        self.get(run_id)

        def operation(context: Any) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "INSERT INTO results.run_retention VALUES (?, ?, 1, ?) "
                "ON CONFLICT (run_record_id) DO UPDATE SET "
                "retention_state = excluded.retention_state, "
                "revision = run_retention.revision + 1, updated_at = excluded.updated_at",
                [run_id.value, state, context.recorded_at],
            )

        self._project.services.transactions.run("result_retention_set", operation)

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("result mutation requires research_write mode")


class RunHandle:
    __slots__ = ("_project", "_summary")

    def __init__(self, project: Project, summary: RunSummary) -> None:
        self._project = project
        self._summary = summary

    @property
    def id(self) -> RunRecordId:
        return self._summary.run_record_id

    def summary(self) -> RunSummary:
        return self._summary

    def equity(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT sample_ordinal, valued_at, journal_prefix_sequence, nav_usd, "
            "gross_exposure_usd, net_exposure_usd, state, source_content_id "
            "FROM result_data.equity WHERE run_record_id = ? ORDER BY sample_ordinal",
            max_rows,
        )

    def returns(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT return_ordinal, interval_start, interval_end, opening_nav_usd, "
            "closing_nav_usd, return_value, state, source_content_id FROM "
            "result_data.returns WHERE run_record_id = ? ORDER BY return_ordinal",
            max_rows,
        )

    def positions(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT sample_ordinal, valued_at, instrument_id, quantity, mark_price_usd, "
            "market_value_usd, source_content_id FROM result_data.positions "
            "WHERE run_record_id = ? ORDER BY sample_ordinal, instrument_id",
            max_rows,
        )

    def cash(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT sample_ordinal, valued_at, cash_usd, source_content_id FROM "
            "result_data.cash WHERE run_record_id = ? ORDER BY sample_ordinal",
            max_rows,
        )

    def targets(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT decision_at, instrument_id, target_weight, target_quantity, "
            "filled_quantity, shortfall_quantity FROM result_data.targets "
            "WHERE run_record_id = ? ORDER BY decision_at, instrument_id",
            max_rows,
        )

    def fills(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT fill_ordinal, order_id, decision_at, execution_at, "
            "instrument_id, side, quantity, reference_price_usd, fill_price_usd, "
            "fee_usd, slippage_usd, impact_usd, spread_usd, source_content_id "
            "FROM result_data.fills WHERE run_record_id = ? ORDER BY fill_ordinal",
            max_rows,
        )

    def costs(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT fill_ordinal, component_kind, amount_usd, state, source_content_id "
            "FROM result_data.cost_components WHERE run_record_id = ? "
            "ORDER BY fill_ordinal, component_kind",
            max_rows,
        )

    def journal(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._query(
            "SELECT t.book_sequence, t.journal_transaction_id, t.transaction_kind, "
            "t.effective_at, t.source_content_id, p.posting_ordinal, "
            "p.posting_book, p.account_code, p.commodity, p.amount, p.instrument_id "
            "FROM result_data.journal_transactions t JOIN "
            "result_data.journal_postings p USING (run_record_id, book_sequence) "
            "WHERE t.run_record_id = ? ORDER BY t.book_sequence, p.posting_ordinal",
            max_rows,
        )

    def rebalances(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table(
            "rebalance_decisions", "decision_ordinal", max_rows
        )

    def trade_intents(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("trade_intents", "intent_ordinal", max_rows)

    def orders(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("orders", "order_ordinal", max_rows)

    def order_transitions(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table(
            "order_transitions", "order_id, transition_ordinal", max_rows
        )

    def events(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("lifecycle_events", "event_ordinal", max_rows)

    def settlements(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("settlements", "settlement_ordinal", max_rows)

    def lots(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("lots", "lot_ordinal", max_rows)

    def lot_events(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table(
            "lot_events", "inventory_lot_id, event_ordinal", max_rows
        )

    def borrow(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("borrow", "borrow_ordinal", max_rows)

    def exposures(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table(
            "exposures", "sample_ordinal, exposure_kind, exposure_key", max_rows
        )

    def quality(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table(
            "quality_findings", "finding_ordinal", max_rows
        )

    def cash_flows(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        return self._result_table("cash_flows", "cash_flow_ordinal", max_rows)

    def logs(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        return self._result_table("logs", "log_ordinal", max_rows)

    def fidelity(self) -> tuple[str, ...]:
        return self._summary.fidelity_findings

    def provenance(self) -> dict[str, str]:
        return {
            "execution_content_id": str(self._summary.execution_content_id),
            "result_manifest_content_id": str(self._summary.result_manifest_content_id),
        }

    def _query(self, sql: str, max_rows: int) -> pd.DataFrame:
        if max_rows < 1:
            raise ResultQueryLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(sql + " LIMIT ?", [self.id.value, max_rows + 1]).fetchdf()
        if len(frame) > max_rows:
            raise ResultQueryLimitError("result rows exceed max_rows")
        for column in frame.columns:
            if column.endswith("_id"):
                frame[column] = frame[column].astype("string")
            if column.endswith("_at") or column in {"interval_start", "interval_end"}:
                frame[column] = pd.to_datetime(frame[column], utc=True)
        return frame

    def _result_table(
        self, table: str, order_by: str, max_rows: int
    ) -> pd.DataFrame:
        return self._query(
            f"SELECT * EXCLUDE (run_record_id) FROM result_data.{table} "
            f"WHERE run_record_id = ? ORDER BY {order_by}",
            max_rows,
        )
