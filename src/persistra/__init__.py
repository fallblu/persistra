"""Persistra provides primary market and economic data research tools."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("persistra")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]
