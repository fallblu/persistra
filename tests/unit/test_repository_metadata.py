from __future__ import annotations

import collections
import json
import re
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GITHUB = REPOSITORY_ROOT / ".github"
FORM_NAMES = {"bug.yml", "feature.yml", "general.yml"}
DEFAULT_LABELS = {"bug", "documentation", "enhancement", "question"}


def test_repository_profile_is_specific_and_bounded() -> None:
    profile = json.loads((GITHUB / "repository.json").read_text(encoding="utf-8"))
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    assert profile == {
        "description": (
            "Typed Python library for point-in-time financial research, portfolio construction, "
            "and deterministic trading replay"
        ),
        "homepage": "https://fallblu.github.io/persistra/",
        "topics": [
            "backtesting",
            "economic-data",
            "financial-data",
            "market-data",
            "portfolio-optimization",
            "python",
            "quantitative-finance",
            "systematic-trading",
        ],
        "has_projects": False,
        "has_wiki": False,
    }
    assert len(profile["topics"]) == len(set(profile["topics"]))
    assert project["project"]["description"] == profile["description"]
    assert "point-in-time financial research, portfolio construction" in readme


def test_label_manifest_covers_stable_planning_dimensions() -> None:
    labels = json.loads((GITHUB / "labels.json").read_text(encoding="utf-8"))
    names = [label["name"] for label in labels]
    categories = collections.Counter(label["category"] for label in labels)

    assert len(names) == len(set(names))
    assert categories == {"component": 8, "priority": 4, "effort": 3}
    assert all(re.fullmatch(r"[0-9a-f]{6}", label["color"]) for label in labels)
    assert all(label["description"].strip() for label in labels)


def test_issue_forms_reference_known_labels_and_require_evidence() -> None:
    directory = GITHUB / "ISSUE_TEMPLATE"
    forms = {
        path.name: path
        for path in directory.glob("*.yml")
        if path.name != "config.yml"
    }
    labels = json.loads((GITHUB / "labels.json").read_text(encoding="utf-8"))
    allowed_labels = DEFAULT_LABELS | {label["name"] for label in labels}

    assert set(forms) == FORM_NAMES
    for name, path in forms.items():
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^name: .+$", text), name
        assert re.search(r"(?m)^description: .+$", text), name
        assert "\nbody:\n" in text, name
        assert "validations:\n      required: true" in text, name
        label_match = re.search(r"(?m)^labels: \[(.*)\]$", text)
        assert label_match is not None, name
        assigned = set(json.loads(f"[{label_match.group(1)}]"))
        assert assigned <= allowed_labels, name
        ids = re.findall(r"(?m)^    id: ([a-z0-9-]+)$", text)
        assert len(ids) == len(set(ids)), name

    bug = forms["bug.yml"].read_text(encoding="utf-8")
    feature = forms["feature.yml"].read_text(encoding="utf-8")
    general = forms["general.yml"].read_text(encoding="utf-8")
    for field in ("scope", "reproduction", "provenance", "acceptance", "testing"):
        assert f"    id: {field}" in bug
    for field in ("problem", "proposal", "provenance", "acceptance", "testing"):
        assert f"    id: {field}" in feature
    for field in ("context", "outcome", "provenance", "testing"):
        assert f"    id: {field}" in general

    combined = "\n".join(path.read_text(encoding="utf-8") for path in forms.values())
    assert "priority:" not in combined
    assert "effort:" not in combined

    config = (directory / "config.yml").read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in config
    assert ".github/SECURITY.md" in config


def test_pull_request_template_preserves_required_sections() -> None:
    pull_request = (GITHUB / "pull_request_template.md").read_text(encoding="utf-8")

    assert pull_request.count("## Summary") == 1
    assert pull_request.count("## Test plan") == 1
