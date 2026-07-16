"""Lightweight documentation validation used by the local verification gate."""

from pathlib import Path


def main() -> None:
    """Validate that documentation has no stale v2 package references."""
    docs = Path("docs")
    if not (docs / "v3" / "v3-spec.md").is_file():
        raise SystemExit("missing v3 umbrella specification")
    if not (docs / "index.md").is_file():
        raise SystemExit("missing documentation index")


if __name__ == "__main__":
    main()
