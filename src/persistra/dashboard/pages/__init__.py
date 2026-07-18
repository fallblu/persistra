"""Stable eight-page dashboard navigation contract."""

from __future__ import annotations

from enum import StrEnum


class DashboardPage(StrEnum):
    OVERVIEW = "Run overview"
    PERFORMANCE = "Performance and drawdowns"
    PORTFOLIO = "Positions and exposures"
    EXECUTION = "Orders and execution"
    ATTRIBUTION = "Attribution"
    DIAGNOSTICS = "Diagnostics"
    STUDIES = "Study and trial comparison"
    INSPECTION = "Data, feature, and provenance inspection"


PAGE_KEYS = {
    DashboardPage.OVERVIEW: "overview",
    DashboardPage.PERFORMANCE: "performance",
    DashboardPage.PORTFOLIO: "portfolio",
    DashboardPage.EXECUTION: "execution",
    DashboardPage.ATTRIBUTION: "attribution",
    DashboardPage.DIAGNOSTICS: "diagnostics",
    DashboardPage.STUDIES: "studies",
    DashboardPage.INSPECTION: "inspection",
}

__all__ = ["PAGE_KEYS", "DashboardPage"]
