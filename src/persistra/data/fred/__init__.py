"""Focused FRED and ALFRED series support."""

from persistra.data.fred.client import FredClient
from persistra.data.fred.transport import FredTransport

__all__ = ["FredClient", "FredTransport"]
