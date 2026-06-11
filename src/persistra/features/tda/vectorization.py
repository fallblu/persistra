from __future__ import annotations

from typing import Any, cast

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


def _persistences(diagram: np.ndarray) -> np.ndarray:
    if diagram.size == 0:
        return np.empty(0, dtype=float)
    return diagram[:, 1] - diagram[:, 0]


def _as_diagram_list(X: Any, n_dims: int) -> list[np.ndarray]:
    diags = [np.asarray(d, dtype=float).reshape(-1, 2) for d in X]
    if len(diags) != n_dims:
        raise ValueError(f"expected {n_dims} diagrams, got {len(diags)}")
    return diags


class PersistenceEntropy(BaseEstimator, TransformerMixin):
    """Shannon entropy of normalized persistence lengths, per dimension."""

    def __init__(self, homology_dims: tuple[int, ...] = (0, 1)) -> None:
        self.homology_dims = tuple(homology_dims)

    def fit(self, X: Any, y: Any = None) -> PersistenceEntropy:
        return self

    def transform(self, X: Any) -> np.ndarray:
        diags = _as_diagram_list(X, len(self.homology_dims))
        out = np.zeros(len(self.homology_dims), dtype=float)
        for i, dgm in enumerate(diags):
            pers = _persistences(dgm)
            pers = pers[pers > 0]
            if pers.size == 0:
                continue
            total = pers.sum()
            if total <= 0:
                continue
            p = pers / total
            out[i] = float(-(p * np.log(p)).sum())
        return out


class BettiCurve(BaseEstimator, TransformerMixin):
    """Discretized Betti curve."""

    def __init__(self, homology_dims: tuple[int, ...] = (0, 1), n_bins: int = 50) -> None:
        if n_bins < 1:
            raise ValueError("n_bins must be >= 1")
        self.homology_dims = tuple(homology_dims)
        self.n_bins = n_bins
        self._grid: np.ndarray | None = None

    def fit(self, X: Any, y: Any = None) -> BettiCurve:
        diags = _as_diagram_list(X, len(self.homology_dims))
        self._grid = self._make_grid(diags)
        return self

    def transform(self, X: Any) -> np.ndarray:
        diags = _as_diagram_list(X, len(self.homology_dims))
        grid = self._grid if self._grid is not None else self._make_grid(diags)
        parts: list[np.ndarray] = []
        for dgm in diags:
            if dgm.size == 0:
                parts.append(np.zeros(self.n_bins, dtype=float))
                continue
            births = dgm[:, 0][:, None]
            deaths = dgm[:, 1][:, None]
            alive = (births <= grid[None, :]) & (grid[None, :] < deaths)
            parts.append(alive.sum(axis=0).astype(float))
        return np.concatenate(parts)

    def _make_grid(self, diags: list[np.ndarray]) -> np.ndarray:
        non_empty = [d for d in diags if d.size]
        if not non_empty:
            return np.linspace(0.0, 1.0, self.n_bins)
        all_pts = np.concatenate(non_empty)
        lo = float(all_pts[:, 0].min())
        hi = float(all_pts[:, 1].max())
        if hi <= lo:
            hi = lo + 1e-12
        return np.linspace(lo, hi, self.n_bins)


class PersistenceImage(BaseEstimator, TransformerMixin):
    """Flattened persistence images via persim's PersistenceImager."""

    def __init__(
        self,
        homology_dims: tuple[int, ...] = (0, 1),
        pixel_size: float = 0.1,
        bandwidth: float = 0.1,
    ) -> None:
        if pixel_size <= 0:
            raise ValueError("pixel_size must be > 0")
        if bandwidth <= 0:
            raise ValueError("bandwidth must be > 0")
        self.homology_dims = tuple(homology_dims)
        self.pixel_size = pixel_size
        self.bandwidth = bandwidth
        self._imagers: list[Any] | None = None
        self._sizes: list[int] | None = None

    def fit(self, X: Any, y: Any = None) -> PersistenceImage:
        diags = _as_diagram_list(X, len(self.homology_dims))
        imagers: list[Any] = []
        sizes: list[int] = []
        for dgm in diags:
            imgr = self._build_imager(dgm)
            imagers.append(imgr)
            sizes.append(int(imgr.resolution[0] * imgr.resolution[1]))
        self._imagers = imagers
        self._sizes = sizes
        return self

    def transform(self, X: Any) -> np.ndarray:
        diags = _as_diagram_list(X, len(self.homology_dims))
        if self._imagers is None or self._sizes is None:
            self.fit(diags)
        assert self._imagers is not None and self._sizes is not None
        parts: list[np.ndarray] = []
        for imgr, size, dgm in zip(self._imagers, self._sizes, diags, strict=True):
            arr = dgm if dgm.size else np.empty((0, 2), dtype=float)
            img = np.asarray(imgr.transform([arr])[0], dtype=float).ravel()
            if img.size != size:
                img = np.zeros(size, dtype=float)
            parts.append(img)
        return np.concatenate(parts) if parts else np.empty(0, dtype=float)

    def _build_imager(self, diagram: np.ndarray) -> Any:
        import persim  # type: ignore[import-untyped]

        imgr: Any = persim.PersistenceImager(  # pyright: ignore
            pixel_size=self.pixel_size,
            kernel_params={"sigma": self.bandwidth},
        )
        if diagram.size:
            imgr.fit([diagram])  # pyright: ignore
        b_range = cast("tuple[Any, Any]", imgr.birth_range)  # pyright: ignore
        p_range = cast("tuple[Any, Any]", imgr.pers_range)  # pyright: ignore
        b_lo, b_hi = float(b_range[0]), float(b_range[1])
        p_lo, p_hi = float(p_range[0]), float(p_range[1])
        if b_hi - b_lo < self.pixel_size:
            imgr.birth_range = (b_lo, b_lo + self.pixel_size)
        if p_hi - p_lo < self.pixel_size:
            imgr.pers_range = (p_lo, p_lo + self.pixel_size)
        return imgr  # pyright: ignore
