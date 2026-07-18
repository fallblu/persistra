"""Validate one isolated optional-dependency installation."""

from __future__ import annotations

import importlib.util
import sys

_EXPECTED = {
    "base": (),
    "research": ("sqlglot",),
    "search": ("optuna",),
    "optimize": ("cvxpy",),
    "viz": ("plotly",),
    "dashboard": ("plotly", "streamlit"),
    "static": (),
}
_OPTIONAL_MODULES = frozenset(
    module for modules in _EXPECTED.values() for module in modules
)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in _EXPECTED:
        raise SystemExit("usage: check_optional_install.py EXTRA")
    extra = sys.argv[1]
    import persistra
    import persistra.dashboard
    import persistra.portfolio
    import persistra.research
    import persistra.viz

    del persistra
    required = frozenset(_EXPECTED[extra])
    missing = sorted(
        module for module in required if importlib.util.find_spec(module) is None
    )
    leaked = sorted(
        module
        for module in _OPTIONAL_MODULES - required
        if importlib.util.find_spec(module) is not None
    )
    if missing or leaked:
        raise SystemExit(
            f"optional dependency isolation failed: missing={missing}, leaked={leaked}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
