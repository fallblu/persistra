"""Two-source precedence selection, fail-closed binding, and retraction masking."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from builders.synthetic import (
    DUAL_DATASET,
    PRIMARY_SOURCE,
    SECONDARY_SOURCE,
    dual_dataset_definition,
    dual_header,
    dual_record,
    dual_retraction,
    secondary_source_definition,
    source_definition,
)
from support.env import NOW
from support.ids import contract_id

from persistra.catalog import RevisionEffect, SourcePrecedencePolicy, SourcePriority
from persistra.domain import QualifiedName
from persistra.errors import SourcePrecedencePolicyError

if TYPE_CHECKING:
    from persistra import Project

pytestmark = pytest.mark.contract

_FAR = NOW + timedelta(days=3650)


def _register(project: Project) -> None:
    project.services.catalog.sources.register(source_definition())
    project.services.catalog.sources.register(secondary_source_definition())
    project.services.catalog.datasets.register(dual_dataset_definition())


def _select(project: Project):  # type: ignore[no-untyped-def]
    snapshot = project.services.snapshots.create()
    return project.services.snapshots.select(
        DUAL_DATASET, snapshot=snapshot, public_cutoff=_FAR, project_cutoff=_FAR
    )


@contract_id("V3-P03-12.4-UNBOUND-FAILS-CLOSED")
def test_multi_source_without_binding_fails_closed(project: Project) -> None:
    _register(project)
    project.services.ingestion.submit(
        dual_header(PRIMARY_SOURCE, "p1"), (dual_record("100", "p-1"),)
    )
    with pytest.raises(SourcePrecedencePolicyError):
        _select(project)


def _install_binding(project: Project) -> None:
    ref = project.services.catalog.precedence_policies.install(
        SourcePrecedencePolicy(
            name=QualifiedName("example.dual_precedence"),
            version=1,
            dataset=DUAL_DATASET,
            priorities=(
                SourcePriority(PRIMARY_SOURCE, 0),
                SourcePriority(SECONDARY_SOURCE, 1),
            ),
        )
    )
    project.services.catalog.precedence_policies.bind(DUAL_DATASET, ref)


@contract_id("V3-P03-12.4-LOWEST-PRIORITY-WINS")
def test_lowest_priority_source_wins(project: Project) -> None:
    _register(project)
    _install_binding(project)
    project.services.ingestion.submit(
        dual_header(PRIMARY_SOURCE, "p1"), (dual_record("100", "p-1"),)
    )
    project.services.ingestion.submit(
        dual_header(SECONDARY_SOURCE, "s1"), (dual_record("200", "s-1"),)
    )
    selection = _select(project)
    assert len(selection.observations) == 1
    assert dict(selection.observations[0].payload)["value"] == "100"


@contract_id("V3-P03-12.4-RETRACTION-MASKS-LOWER")
def test_winning_retraction_masks_lower_source(project: Project) -> None:
    _register(project)
    _install_binding(project)
    project.services.ingestion.submit(
        dual_header(PRIMARY_SOURCE, "p1"), (dual_record("100", "p-1"),)
    )
    project.services.ingestion.submit(
        dual_header(SECONDARY_SOURCE, "s1"), (dual_record("200", "s-1"),)
    )
    primary_id = project.services.catalog.sources.resolve(PRIMARY_SOURCE).source_id
    head = next(
        observation.revision_id
        for observation in project.services.catalog.revisions.history(DUAL_DATASET)
        if observation.source_id == primary_id
        and observation.effect is RevisionEffect.UPSERT
    )
    project.services.ingestion.submit(
        dual_header(PRIMARY_SOURCE, "p-retract"), (dual_retraction(head, "p-retract"),)
    )
    selection = _select(project)
    assert selection.observations == ()
    assert "retracted" in {audit.state for audit in selection.audits}
