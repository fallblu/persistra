from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


class TakensEmbedding(BaseEstimator, TransformerMixin):
    """Embed a 1-D series into R^dim via time-delay embedding."""

    def __init__(self, dim: int = 3, lag: int = 1, stride: int = 1) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        if lag < 1:
            raise ValueError("lag must be >= 1")
        if stride < 1:
            raise ValueError("stride must be >= 1")
        self.dim = dim
        self.lag = lag
        self.stride = stride

    def fit(self, X: Any, y: Any = None) -> TakensEmbedding:
        return self

    def transform(self, X: Any) -> np.ndarray:
        series = np.asarray(X, dtype=float).ravel()
        span = (self.dim - 1) * self.lag
        if series.size <= span:
            return np.empty((0, self.dim), dtype=float)
        starts = np.arange(0, series.size - span, self.stride)
        cols = [series[starts + k * self.lag] for k in range(self.dim)]
        return np.column_stack(cols)
