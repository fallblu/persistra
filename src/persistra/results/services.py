"""Bounded normalized run-result queries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pandas as pd

from persistra.domain import ContentId
from persistra.errors import ResultQueryLimitError, VectorizedSimulationError
from persistra.results.models import RunSummary
from persistra.simulation import RunRecordId, VectorizedSimulationId

if TYPE_CHECKING:
    from persistra.project import Project


class ResultService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def get(self, run_id: RunRecordId) -> RunHandle:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT vectorized_simulation_id, execution_content_id, "
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
                VectorizedSimulationId.parse(row[0]),
                ContentId.parse(row[1]),
                ContentId.parse(row[2]),
                int(row[3]),
                int(row[4]),
                tuple(json.loads(row[5])),
            ),
        )


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
            "SELECT f.fill_ordinal, f.decision_at, f.execution_at, f.instrument_id, "
            "f.side, f.quantity, f.reference_price_usd, f.fill_price_usd, "
            "f.commission_usd, f.slippage_usd, f.fill_content_id FROM "
            "simulation_data.synthetic_fills f JOIN simulation.vectorized_runs r "
            "USING (vectorized_simulation_id) WHERE r.run_record_id = ? "
            "ORDER BY f.fill_ordinal",
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
            "SELECT t.book_sequence, t.transaction_kind, t.effective_at, "
            "t.source_content_id, p.posting_ordinal, p.posting_book, p.account_code, "
            "p.commodity, p.amount, p.instrument_id FROM simulation.vectorized_runs r "
            "JOIN accounting.journal_transactions t USING (accounting_book_id) "
            "JOIN journal_data.journal_postings p USING (journal_transaction_id) "
            "WHERE r.run_record_id = ? ORDER BY t.book_sequence, p.posting_ordinal",
            max_rows,
        )

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
