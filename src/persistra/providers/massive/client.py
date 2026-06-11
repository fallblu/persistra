from __future__ import annotations

import functools
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massive import RESTClient


@functools.cache
def _load_dotenv_if_available() -> None:
    """Best-effort load of a local .env file. No-op if python-dotenv is absent. Runs once."""
    try:
        from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
    except ImportError:
        return
    load_dotenv()


def make_client(api_key: str | None = None, **kwargs: Any) -> RESTClient:
    """Construct a Massive ``RESTClient``.

    With ``api_key=None``, the factory resolves the key itself: it attempts a
    best-effort load of a local ``.env`` file (only if ``python-dotenv`` is
    installed) and then reads the ``MASSIVE_API_KEY`` environment variable.
    Extra keyword args (e.g. ``trace=True``) pass straight through to
    ``RESTClient``.
    """
    from massive import RESTClient

    if api_key is None:
        _load_dotenv_if_available()
        api_key = os.getenv("MASSIVE_API_KEY")
    return RESTClient(api_key=api_key, **kwargs)
