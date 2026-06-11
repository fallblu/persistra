from __future__ import annotations

import importlib.metadata as _md


def captured_versions() -> dict[str, str]:
    """Return a mapping of package-name -> version for every installed distribution.

    Silently skips any distribution that fails metadata lookup. Never raises.
    """
    result: dict[str, str] = {}
    try:
        for dist in _md.distributions():
            try:
                name = dist.metadata["Name"]
                if name:
                    result[name] = dist.version
            except Exception:
                pass
    except Exception:
        pass
    return result
