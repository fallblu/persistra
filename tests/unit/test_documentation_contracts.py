"""Documentation contract drift tests."""

from pathlib import Path

from scripts.check_docs import schema_reference_failures


def test_schema_reference_matches_every_runtime_contract() -> None:
    reference = Path("docs/reference/schemas.md").read_text(encoding="utf-8")

    assert schema_reference_failures(reference) == []


def test_schema_reference_reports_actionable_drift_fixture() -> None:
    reference = Path("docs/reference/schemas.md").read_text(encoding="utf-8")
    drifted = reference.replace("| `price` | `float64` |", "| `price` | `Float64` |", 1)
    drifted = drifted.replace(
        "- Identity key: `provider`, `provider_symbol`",
        "- Identity key: `provider_symbol`",
        1,
    )
    drifted = drifted.replace("`positive-price`, ", "", 1)

    failures = schema_reference_failures(drifted)

    assert "latest-quotes" in "\n".join(failures)
    assert any("price dtype differs" in failure for failure in failures)
    assert any("identity key differ" in failure for failure in failures)
    assert any("invariants differ" in failure for failure in failures)
