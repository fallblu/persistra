"""Run and enforce the reviewed financial-invariant mutation baseline."""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "mutation-baseline.toml"


def _baseline() -> tuple[list[dict[str, str]], dict[str, str]]:
    document: dict[str, Any]
    with BASELINE_PATH.open("rb") as handle:
        document = tomllib.load(handle)
    if document.get("schema_version") != 1:
        raise ValueError("mutation baseline schema_version must equal 1")

    targets = document.get("targets")
    exclusions = document.get("equivalent_exclusions")
    if not isinstance(targets, list) or not targets:
        raise ValueError("mutation baseline must define at least one target")
    if not isinstance(exclusions, list):
        raise ValueError("mutation baseline equivalent_exclusions must be a list")

    checked_targets: list[dict[str, str]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("mutation baseline targets must be tables")
        pattern = target.get("pattern")
        invariant = target.get("invariant")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("mutation target patterns must not be empty")
        if not isinstance(invariant, str) or not invariant.strip():
            raise ValueError("mutation target invariants must not be empty")
        checked_targets.append({"pattern": pattern, "invariant": invariant})

    checked_exclusions: dict[str, str] = {}
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("equivalent mutation exclusions must be tables")
        name = exclusion.get("name")
        reason = exclusion.get("reason")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("equivalent mutation exclusion names must not be empty")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("equivalent mutation exclusions require a reason")
        if name in checked_exclusions:
            raise ValueError(f"duplicate equivalent mutation exclusion: {name}")
        checked_exclusions[name] = reason
    return checked_targets, checked_exclusions


def _results(mutmut: str) -> dict[str, str]:
    completed = subprocess.run(
        [mutmut, "results", "--all", "true"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    results: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if ": " not in stripped:
            continue
        name, status = stripped.rsplit(": ", 1)
        results[name] = status
    return results


def main() -> int:
    """Run the focused mutation targets and reject baseline regressions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-children", type=int, default=4)
    arguments = parser.parse_args()
    if arguments.max_children < 1:
        parser.error("--max-children must be positive")

    targets, exclusions = _baseline()
    mutmut = shutil.which("mutmut")
    if mutmut is None:
        raise RuntimeError("mutmut is not installed; sync the mutation dependency group")
    patterns = [target["pattern"] for target in targets]
    subprocess.run(
        [mutmut, "run", "--max-children", str(arguments.max_children), *patterns],
        cwd=ROOT,
        check=True,
    )

    all_results = _results(mutmut)
    selected = {
        name: status
        for name, status in all_results.items()
        if any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
    }
    missing = [
        pattern
        for pattern in patterns
        if not any(fnmatch.fnmatch(name, pattern) for name in selected)
    ]
    if missing:
        raise RuntimeError(f"mutation target patterns matched no mutants: {missing}")

    stale_exclusions = sorted(set(exclusions).difference(selected))
    invalid_exclusions = sorted(
        name for name in exclusions if selected.get(name) != "survived"
    )
    failures = sorted(
        (name, status)
        for name, status in selected.items()
        if status != "killed" and name not in exclusions
    )
    counts = Counter(selected.values())
    summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    print(f"Focused mutation baseline: {len(selected)} mutants ({summary})")
    if stale_exclusions:
        print(f"Stale equivalent exclusions: {', '.join(stale_exclusions)}")
    if invalid_exclusions:
        print(f"Equivalent exclusions no longer survive: {', '.join(invalid_exclusions)}")
    for name, status in failures:
        print(f"Unexpected mutation result: {name}: {status}")
    return 1 if stale_exclusions or invalid_exclusions or failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
