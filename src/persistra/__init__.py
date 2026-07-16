"""Persistra v3 public package surface."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("persistra")
except PackageNotFoundError:  # pragma: no cover - editable installs provide metadata
    __version__ = "0+unknown"

from persistra.config import ProjectOverrides
from persistra.db import ProjectMode
from persistra.project import Project

__all__ = ["Project", "ProjectMode", "ProjectOverrides", "__version__"]
