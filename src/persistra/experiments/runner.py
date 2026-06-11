"""Internal helper that runs a single (params, factory, engine_builder) tuple."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from persistra.core.engine import Engine
    from persistra.core.result import Result
    from persistra.strategy.base import Strategy

__all__ = ["_run_one"]


def _run_one(
    params: dict[str, Any],
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    engine_builder: Callable[..., Engine],
    output_dir: str | Path | None,
    builder_kwargs: dict[str, Any] | None = None,
) -> Result:
    """Build the strategy + engine for one parameter set and run it.

    Lives at module scope so joblib's loky backend can pickle it. The engine is
    deterministic, so no seed is forwarded; ``params`` is recorded in the run's
    persisted metadata via ``meta_extra``.
    """
    strategy = strategy_factory(params)
    kwargs = dict(builder_kwargs or {})
    engine = engine_builder(strategy, **kwargs)
    return engine.run(output_dir=output_dir, meta_extra={"params": params})
