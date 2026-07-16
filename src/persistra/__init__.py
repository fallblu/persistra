"""Persistra v3 public package surface."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("persistra")
except PackageNotFoundError:  # pragma: no cover - editable installs provide metadata
    __version__ = "0+unknown"

__all__ = ["__version__"]
