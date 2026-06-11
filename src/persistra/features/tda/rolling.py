"""Rolling persistence features for the FactorStrategy feature pipeline."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from .embedding import TakensEmbedding
from .persistence import VietorisRipsPersistence
from .vectorization import BettiCurve, PersistenceEntropy, PersistenceImage

_VECTORIZER_NAMES = ("entropy", "betti", "image")


class RollingPersistenceFeatures(BaseEstimator, TransformerMixin):
    """Rolling persistent-homology features for a multi-symbol price matrix.

    For each symbol, the most recent ``window`` finite observations are
    time-delay embedded and passed through Vietoris-Rips persistence and
    a chosen vectorizer to produce one feature row per symbol. Symbols
    with fewer than ``window`` finite observations receive an all-NaN
    row — ``LinearSignal`` will then skip them naturally.

    Output column names follow ``tda__<vectorizer>_h<dim>`` (entropy) or
    ``tda__<vectorizer>_h<dim>_<i>`` (betti, image). These names are
    load-bearing: downstream ``LinearSignal`` looks features up by name.

    Computation is ``O(window * n_symbols)`` per call; parallelizing
    across symbols is deferred to a later release.

    Parameters
    ----------
    window : int
        Number of trailing observations per symbol used to build the
        point cloud.
    embedding_dim : int
        Takens embedding dimension.
    lag : int
        Takens embedding lag.
    homology_dims : tuple[int, ...]
        Homology dimensions to compute (e.g. ``(0, 1)``).
    vectorizer : {"entropy", "betti", "image"}
        Which diagram-to-vector transform to apply.
    backend : {"ripser", "gudhi"}
        Persistence engine.
    **vectorizer_kwargs : Any
        Forwarded to the chosen vectorizer (e.g. ``n_bins`` for betti,
        ``pixel_size``/``bandwidth`` for image).

    Input shape:  ``(lookback, n_symbols)`` close-price matrix.
    Output shape: ``(n_symbols, n_features)``.
    """

    def __init__(
        self,
        window: int = 60,
        embedding_dim: int = 3,
        lag: int = 1,
        homology_dims: tuple[int, ...] = (0, 1),
        vectorizer: Literal["entropy", "betti", "image"] = "entropy",
        backend: Literal["ripser", "gudhi"] = "ripser",
        **vectorizer_kwargs: Any,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        if vectorizer not in _VECTORIZER_NAMES:
            raise ValueError(f"vectorizer must be one of {_VECTORIZER_NAMES}")
        self.window = window
        self.embedding_dim = embedding_dim
        self.lag = lag
        self.homology_dims = tuple(homology_dims)
        self.vectorizer: Literal["entropy", "betti", "image"] = vectorizer
        self.backend: Literal["ripser", "gudhi"] = backend
        self.vectorizer_kwargs = dict(vectorizer_kwargs)
        self._feature_count: int | None = None
        self._per_dim_sizes: list[int] | None = None

    def fit(self, X: Any, y: Any = None) -> RollingPersistenceFeatures:
        return self

    def transform(self, X: Any) -> np.ndarray:
        arr = np.asarray(X, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2:
            raise ValueError(f"expected 1-D or 2-D input, got shape {arr.shape}")
        _t, n_sym = arr.shape

        diagrams_per_symbol: list[list[np.ndarray] | None] = []
        for j in range(n_sym):
            col = arr[:, j]
            series = col[np.isfinite(col)]
            if series.size < self.window:
                diagrams_per_symbol.append(None)
                continue
            series = series[-self.window :]
            cloud = TakensEmbedding(dim=self.embedding_dim, lag=self.lag).transform(series)
            if cloud.shape[0] < 2:
                diagrams_per_symbol.append(None)
                continue
            diagrams = VietorisRipsPersistence(
                homology_dims=self.homology_dims, backend=self.backend
            ).transform(cloud)
            diagrams_per_symbol.append(diagrams)

        vectorizer = self._build_fitted_vectorizer(diagrams_per_symbol)
        n_features = self._resolve_feature_count(vectorizer, diagrams_per_symbol)

        rows = np.full((n_sym, n_features), np.nan, dtype=float)
        for j, dgms in enumerate(diagrams_per_symbol):
            if dgms is None:
                continue
            vec = np.asarray(vectorizer.transform(dgms), dtype=float).ravel()
            if vec.size != n_features:
                continue
            rows[j] = vec
        return rows

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        names: list[str] = []
        per_dim = self._per_dim_sizes or self._infer_per_dim_sizes()
        for d, size in zip(self.homology_dims, per_dim, strict=True):
            if self.vectorizer == "entropy":
                names.append(f"tda__entropy_h{d}")
            else:
                for i in range(size):
                    names.append(f"tda__{self.vectorizer}_h{d}_{i}")
        return np.asarray(names, dtype=object)

    def _build_fitted_vectorizer(self, diagrams_per_symbol: list[list[np.ndarray] | None]) -> Any:
        non_empty = [d for d in diagrams_per_symbol if d is not None]
        if self.vectorizer == "entropy":
            return PersistenceEntropy(homology_dims=self.homology_dims)
        if self.vectorizer == "betti":
            n_bins = int(self.vectorizer_kwargs.get("n_bins", 50))
            v = BettiCurve(homology_dims=self.homology_dims, n_bins=n_bins)
            if non_empty:
                v.fit(self._union_per_dim(non_empty))
            return v
        # image
        v = PersistenceImage(homology_dims=self.homology_dims, **self.vectorizer_kwargs)
        if non_empty:
            v.fit(self._union_per_dim(non_empty))
        return v

    def _union_per_dim(self, diagrams_per_symbol: list[list[np.ndarray]]) -> list[np.ndarray]:
        per_dim: list[np.ndarray] = []
        for i in range(len(self.homology_dims)):
            chunks = [d[i] for d in diagrams_per_symbol if d[i].size]
            per_dim.append(np.concatenate(chunks) if chunks else np.empty((0, 2), dtype=float))
        return per_dim

    def _resolve_feature_count(
        self,
        vectorizer: Any,
        diagrams_per_symbol: list[list[np.ndarray] | None],
    ) -> int:
        if self.vectorizer == "entropy":
            self._per_dim_sizes = [1] * len(self.homology_dims)
            self._feature_count = len(self.homology_dims)
            return self._feature_count
        if self.vectorizer == "betti":
            n_bins = int(self.vectorizer_kwargs.get("n_bins", 50))
            self._per_dim_sizes = [n_bins] * len(self.homology_dims)
            self._feature_count = n_bins * len(self.homology_dims)
            return self._feature_count
        # image — read sizes off the fitted imagers
        sizes = getattr(vectorizer, "_sizes", None)
        if not sizes:
            # All symbols had insufficient data; fall back to 1 pixel per dim.
            sizes = [1] * len(self.homology_dims)
        self._per_dim_sizes = list(sizes)
        self._feature_count = int(sum(sizes))
        return self._feature_count

    def _infer_per_dim_sizes(self) -> list[int]:
        if self.vectorizer == "entropy":
            return [1] * len(self.homology_dims)
        if self.vectorizer == "betti":
            n_bins = int(self.vectorizer_kwargs.get("n_bins", 50))
            return [n_bins] * len(self.homology_dims)
        return [1] * len(self.homology_dims)
