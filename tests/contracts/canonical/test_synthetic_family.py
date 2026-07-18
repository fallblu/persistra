"""Bind the synthetic custom dataset to the generic contract suite (spec 03 §6.2)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from builders.synthetic import (
    SyntheticFamilyHarness,
    dataset_definition,
    source_definition,
)
from support.families import FamilyContractSuite, FamilyHarness
from support.ids import contract_id

from persistra.domain import QualifiedName
from persistra.errors import CatalogDefinitionError

if TYPE_CHECKING:
    from persistra import Project

pytestmark = pytest.mark.contract


class TestSyntheticFamily(FamilyContractSuite):
    """Run every generic family contract against the synthetic custom dataset."""

    @pytest.fixture
    def harness(self) -> FamilyHarness:
        return SyntheticFamilyHarness()


@contract_id("V3-P03-6.2-RESERVED-PREFIX")
def test_reserved_owner_prefix_is_rejected(project: Project) -> None:
    project.services.catalog.sources.register(source_definition())
    reserved = replace(dataset_definition(), name=QualifiedName("persistra.market.custom"))
    with pytest.raises(CatalogDefinitionError, match="reserved"):
        project.services.catalog.datasets.register(reserved)
    allowed = project.services.catalog.datasets.register(reserved, allow_reserved=True)
    assert allowed.version == 1
