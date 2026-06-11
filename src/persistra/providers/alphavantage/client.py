from __future__ import annotations

import functools
import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://www.alphavantage.co/query"


@functools.cache
def _load_dotenv_if_available() -> None:
    """Best-effort load of a local .env file. No-op if python-dotenv is absent."""
    try:
        from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
    except ImportError:
        return
    load_dotenv()


class AlphaVantageClient:
    """Small JSON client for Alpha Vantage REST endpoints."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = float(timeout)

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET a JSON Alpha Vantage response with ``apikey`` added."""
        request_params = dict(params)
        request_params["apikey"] = self.api_key
        url = f"{self.base_url}?{urlencode(request_params)}"
        request = Request(url, headers={"User-Agent": "persistra"})
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise RuntimeError("Alpha Vantage returned a non-object JSON payload")
        return data


def make_client(api_key: str | None = None, **kwargs: Any) -> AlphaVantageClient:
    """Construct an ``AlphaVantageClient``.

    With ``api_key=None``, this loads a local ``.env`` file if python-dotenv is
    installed and then reads ``ALPHAVANTAGE_API_KEY`` from the environment.
    """
    if api_key is None:
        _load_dotenv_if_available()
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if api_key is None:
        raise ValueError("ALPHAVANTAGE_API_KEY is not set")
    return AlphaVantageClient(api_key=api_key, **kwargs)
