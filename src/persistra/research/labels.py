"""Forward research labels built separately from feature construction."""

from __future__ import annotations

import pandas as pd

from persistra._validation import require_integer
from persistra.research._validation import datetime_index, numeric_frame
from persistra.research.model import ForwardReturnLabels


def forward_returns(levels: pd.DataFrame, *, horizon: int) -> ForwardReturnLabels:
    """Construct forward simple returns over an observation-count horizon."""
    horizon = require_integer(horizon, name="horizon", minimum=1)
    data = numeric_frame(levels, positive=True)
    index = datetime_index(data.index, name="level index")
    labels = data.shift(-horizon).divide(data) - 1
    ends = pd.Series(index=index, dtype=index.dtype, name="label_end")
    if horizon < len(index):
        ends.iloc[:-horizon] = index[horizon:]
    return ForwardReturnLabels(labels, ends, horizon)
