from __future__ import annotations

from typing import Any, Literal, cast

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


class VietorisRipsPersistence(BaseEstimator, TransformerMixin):
    """Point cloud → persistence diagrams via Vietoris-Rips filtration."""

    def __init__(
        self,
        homology_dims: tuple[int, ...] = (0, 1),
        max_edge_length: float | None = None,
        backend: Literal["ripser", "gudhi"] = "ripser",
    ) -> None:
        if not homology_dims:
            raise ValueError("homology_dims must be non-empty")
        if any(d < 0 for d in homology_dims):
            raise ValueError("homology dimensions must be >= 0")
        if backend not in ("ripser", "gudhi"):
            raise ValueError(f"unknown backend: {backend!r}")
        self.homology_dims = tuple(homology_dims)
        self.max_edge_length = max_edge_length
        self.backend = backend

    def fit(self, X: Any, y: Any = None) -> VietorisRipsPersistence:
        return self

    def transform(self, X: Any) -> list[np.ndarray]:
        points = np.asarray(X, dtype=float)
        if points.ndim != 2 or points.shape[0] == 0:
            return [np.empty((0, 2), dtype=float) for _ in self.homology_dims]
        if self.backend == "ripser":
            return self._ripser(points)
        return self._gudhi(points)

    def _ripser(self, points: np.ndarray) -> list[np.ndarray]:
        import ripser as _ripser_mod  # type: ignore[import-untyped]

        ripser_lib: Any = _ripser_mod
        kwargs: dict[str, Any] = {"maxdim": max(self.homology_dims)}
        if self.max_edge_length is not None:
            kwargs["thresh"] = float(self.max_edge_length)
        res = cast("dict[str, Any]", ripser_lib.ripser(points, **kwargs))
        dgms = cast("list[np.ndarray]", res["dgms"])
        out: list[np.ndarray] = []
        for d in self.homology_dims:
            arr = dgms[d] if d < len(dgms) else np.empty((0, 2), dtype=float)
            finite = arr[np.isfinite(arr[:, 1])] if arr.size else arr
            out.append(np.asarray(finite, dtype=float).reshape(-1, 2))
        return out

    def _gudhi(self, points: np.ndarray) -> list[np.ndarray]:
        import gudhi  # type: ignore[import-untyped]

        max_edge = float(self.max_edge_length) if self.max_edge_length is not None else float("inf")
        rips = gudhi.RipsComplex(points=points, max_edge_length=max_edge)  # pyright: ignore
        st: Any = rips.create_simplex_tree(max_dimension=max(self.homology_dims) + 1)  # pyright: ignore
        st.compute_persistence()  # pyright: ignore
        out: list[np.ndarray] = []
        for d in self.homology_dims:
            pairs = st.persistence_intervals_in_dimension(d)  # pyright: ignore
            arr = np.asarray(pairs, dtype=float).reshape(-1, 2)
            if arr.size:
                arr = arr[np.isfinite(arr[:, 1])]
            out.append(arr.reshape(-1, 2))
        return out
