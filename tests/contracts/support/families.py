"""Per-family contract harness and the generic parametrized suite.

A canonical family binds :class:`FamilyHarness` to its public ingestion and query
APIs. :class:`FamilyContractSuite` is a mixin of generic tests that every bound
family must pass: retry idempotency, pinned-query byte-immutability under later
ingestion, revision-selection monotonicity in the public cutoff, public/project
cutoff separation, correction-availability independence, retraction masking,
partial quarantine plus remediation, and frame-contract compliance.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from persistra.catalog import BatchStatus, DatasetRef
from persistra.domain.frames import FrameContract, validate_frame
from support.env import NOW
from support.ids import contract_id

if TYPE_CHECKING:
    from datetime import datetime

    import pandas as pd

    from persistra import Project
    from persistra.catalog import BatchResult, QuarantineId

_FAR_FUTURE = NOW + timedelta(days=3650)


@dataclass(frozen=True, slots=True)
class FamilyQuery:
    """A byte-stable projection of a family query used by the generic suite."""

    canonical: bytes
    row_count: int
    audit_states: tuple[str, ...]
    heads: tuple[tuple[str, str], ...]
    frame: pd.DataFrame | None


class FamilyHarness(ABC):
    """Binds one canonical family's public APIs for the generic contract suite."""

    label: str
    frame_contract: FrameContract | None = None
    #: availability instant carried by the initial revision.
    initial_available_at: datetime = NOW
    #: independent availability instant carried by the correction revision.
    correction_available_at: datetime = NOW + timedelta(days=2)

    @abstractmethod
    def register(self, project: Project) -> None:
        """Register the family's source(s) and dataset in a fresh project."""

    @abstractmethod
    def dataset(self) -> DatasetRef:
        """Return the family's dataset reference."""

    @abstractmethod
    def ingest_initial(self, project: Project) -> BatchResult:
        """Ingest the initial revision under a stable submission key."""

    @abstractmethod
    def ingest_correction(self, project: Project) -> BatchResult:
        """Ingest a correction to the initial natural key with its own availability."""

    @abstractmethod
    def ingest_retraction(self, project: Project) -> BatchResult:
        """Retract the current head revision of the initial natural key."""

    @abstractmethod
    def ingest_invalid_group(self, project: Project) -> BatchResult:
        """Ingest one batch mixing a valid record with an invalid one."""

    @abstractmethod
    def remediate(self, project: Project, quarantine_id: QuarantineId) -> BatchResult:
        """Remediate a quarantined record with a valid replacement."""

    @abstractmethod
    def pin_snapshot(self, project: Project) -> object:
        """Create and return an immutable market snapshot at the current state."""

    @abstractmethod
    def query(
        self,
        project: Project,
        *,
        snapshot: object,
        public_cutoff: datetime,
        project_cutoff: datetime,
    ) -> FamilyQuery:
        """Run the family's pinned point-in-time query, returning a stable projection."""

    def revision_ordinals(self, project: Project) -> dict[str, int]:
        """Map each revision ID to its per-natural-key ordinal from immutable history."""
        history = project.services.catalog.revisions.history(self.dataset())
        ordinals: dict[str, int] = {}
        counts: dict[str, int] = {}
        for observation in history:
            key = json.dumps(observation.natural_key, sort_keys=True)
            index = counts.get(key, 0)
            ordinals[observation.revision_id.to_wire()] = index
            counts[key] = index + 1
        return ordinals


class FamilyContractSuite:
    """Generic contract tests inherited by each family's ``Test*`` module class."""

    @pytest.fixture
    def harness(self) -> FamilyHarness:
        raise NotImplementedError

    @contract_id("V3-P18-9.1-INGEST-IDEMPOTENT")
    def test_retry_idempotency(self, harness: FamilyHarness, project: Project) -> None:
        harness.register(project)
        first = harness.ingest_initial(project)
        second = harness.ingest_initial(project)
        assert first.status in {BatchStatus.COMMITTED, BatchStatus.COMMITTED_WITH_QUARANTINE}
        assert first == second

    @contract_id("V3-P18-9.1-PINNED-IMMUTABLE")
    def test_pinned_query_byte_immutability(
        self, harness: FamilyHarness, project: Project
    ) -> None:
        harness.register(project)
        harness.ingest_initial(project)
        snapshot = harness.pin_snapshot(project)
        before = harness.query(
            project, snapshot=snapshot, public_cutoff=_FAR_FUTURE, project_cutoff=_FAR_FUTURE
        )
        harness.ingest_correction(project)
        harness.ingest_retraction(project)
        after = harness.query(
            project, snapshot=snapshot, public_cutoff=_FAR_FUTURE, project_cutoff=_FAR_FUTURE
        )
        assert before.canonical == after.canonical
        assert before.row_count >= 1

    @contract_id("V3-P04-4.3-CUTOFF-SEPARATION")
    def test_public_project_cutoff_separation(
        self, harness: FamilyHarness, project: Project
    ) -> None:
        harness.register(project)
        harness.ingest_initial(project)
        snapshot = harness.pin_snapshot(project)
        project_blind = harness.query(
            project,
            snapshot=snapshot,
            public_cutoff=_FAR_FUTURE,
            project_cutoff=NOW - timedelta(days=1),
        )
        both = harness.query(
            project, snapshot=snapshot, public_cutoff=_FAR_FUTURE, project_cutoff=_FAR_FUTURE
        )
        assert project_blind.row_count == 0
        assert both.row_count >= 1

    @contract_id("V3-P05-5.3-CORRECTION-AVAILABILITY")
    def test_correction_availability_independence(
        self, harness: FamilyHarness, project: Project
    ) -> None:
        harness.register(project)
        harness.ingest_initial(project)
        harness.ingest_correction(project)
        snapshot = harness.pin_snapshot(project)
        before_correction = harness.query(
            project,
            snapshot=snapshot,
            public_cutoff=harness.correction_available_at - timedelta(microseconds=1),
            project_cutoff=_FAR_FUTURE,
        )
        after_correction = harness.query(
            project,
            snapshot=snapshot,
            public_cutoff=harness.correction_available_at,
            project_cutoff=_FAR_FUTURE,
        )
        assert before_correction.row_count >= 1
        assert before_correction.heads != after_correction.heads

    @contract_id("V3-P03-13-RETRACTION-MASK")
    def test_retraction_masks_head(self, harness: FamilyHarness, project: Project) -> None:
        harness.register(project)
        harness.ingest_initial(project)
        harness.ingest_retraction(project)
        snapshot = harness.pin_snapshot(project)
        selected = harness.query(
            project, snapshot=snapshot, public_cutoff=_FAR_FUTURE, project_cutoff=_FAR_FUTURE
        )
        assert selected.row_count == 0
        assert "retracted" in selected.audit_states

    @contract_id("V3-P03-14-PARTIAL-REMEDIATION")
    def test_partial_quarantine_and_remediation(
        self, harness: FamilyHarness, project: Project
    ) -> None:
        harness.register(project)
        result = harness.ingest_invalid_group(project)
        assert result.counts.quarantined >= 1
        assert result.counts.accepted_new >= 1
        assert result.status is BatchStatus.COMMITTED_WITH_QUARANTINE
        rows = project.services.ingestion.quarantine.list(batch_id=result.batch_id)
        assert rows
        harness.remediate(project, rows[0].quarantine_id)
        history = project.services.ingestion.quarantine.remediation_history(
            rows[0].quarantine_id
        )
        assert history.state == "resolved_new"

    @contract_id("V3-P05-16-FRAME-CONTRACT")
    def test_frame_contract_compliance(
        self, harness: FamilyHarness, project: Project
    ) -> None:
        if harness.frame_contract is None:
            pytest.skip("family does not publish a frame contract")
        harness.register(project)
        harness.ingest_initial(project)
        snapshot = harness.pin_snapshot(project)
        populated = harness.query(
            project, snapshot=snapshot, public_cutoff=_FAR_FUTURE, project_cutoff=_FAR_FUTURE
        )
        assert populated.frame is not None
        validate_frame(harness.frame_contract, populated.frame)
        empty = harness.query(
            project,
            snapshot=snapshot,
            public_cutoff=NOW - timedelta(days=1),
            project_cutoff=NOW - timedelta(days=1),
        )
        assert empty.frame is not None
        assert len(empty.frame) == 0
        validate_frame(harness.frame_contract, empty.frame)

    @contract_id("V3-P18-9.1-REVISION-MONOTONIC")
    @settings(
        max_examples=25,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(offsets=st.lists(st.integers(min_value=-1, max_value=3), min_size=2, max_size=6))
    def test_revision_selection_monotonic_in_public_cutoff(
        self, harness: FamilyHarness, project: Project, offsets: list[int]
    ) -> None:
        harness.register(project)
        harness.ingest_initial(project)
        harness.ingest_correction(project)
        snapshot = harness.pin_snapshot(project)
        ordinals = harness.revision_ordinals(project)
        cutoffs = sorted(NOW + timedelta(days=offset) for offset in offsets)
        previous: dict[str, int] = {}
        for cutoff in cutoffs:
            result = harness.query(
                project, snapshot=snapshot, public_cutoff=cutoff, project_cutoff=_FAR_FUTURE
            )
            current = {key: ordinals[revision] for key, revision in result.heads}
            for key, ordinal in previous.items():
                assert key in current
                assert current[key] >= ordinal
            previous = current
