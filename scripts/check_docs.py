"""Lightweight documentation validation used by the local verification gate."""

from pathlib import Path


def main() -> None:
    """Validate required public documentation and release-boundary statements."""
    docs = Path("docs")
    required = (
        docs / "index.md",
        docs / "guide.md",
        docs / "migration-guide.md",
        docs / "release-readiness.md",
        docs / "adr" / "0001-adopt-streamlit-dashboard.md",
        docs / "v3" / "v3-spec.md",
        docs / "v3" / "phase-plan.md",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing required documentation: {', '.join(missing)}")
    index = (docs / "index.md").read_text(encoding="utf-8")
    stale = ("phase-4 simulator", "assigned to later phases")
    if any(value in index for value in stale):
        raise SystemExit("documentation index contains stale implementation status")
    readiness = (docs / "release-readiness.md").read_text(encoding="utf-8")
    if "human-controlled" not in readiness or "static" not in readiness:
        raise SystemExit("release boundary documentation is incomplete")


if __name__ == "__main__":
    main()
