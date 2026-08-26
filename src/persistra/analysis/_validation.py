"""Shared validation for analysis inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError


def numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy a wide frame after requiring finite, non-boolean numeric observations."""
    result = frame.copy(deep=True)
    if any(
        pd.api.types.is_bool_dtype(dtype) or not pd.api.types.is_numeric_dtype(dtype)
        for dtype in result.dtypes
    ):
        raise AnalysisError("all analysis columns must be non-boolean numeric values")
    values = result.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise AnalysisError("analysis input must not contain infinite values")
    return result
