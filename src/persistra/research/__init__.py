"""Point-in-time research transforms with explicit temporal policy."""

from persistra.research.features import build_feature_panel, select_vintage
from persistra.research.labels import forward_returns
from persistra.research.model import (
    FeaturePanel,
    FeaturePolicy,
    FeatureSpec,
    ForwardReturnLabels,
    ResearchSummary,
    TemporalSplit,
    VintageSelection,
)
from persistra.research.splits import (
    expanding_window_splits,
    rolling_window_splits,
    validate_temporal_split,
)
from persistra.research.summary import summarize_regimes

__all__ = [
    "FeaturePanel",
    "FeaturePolicy",
    "FeatureSpec",
    "ForwardReturnLabels",
    "ResearchSummary",
    "TemporalSplit",
    "VintageSelection",
    "build_feature_panel",
    "expanding_window_splits",
    "forward_returns",
    "rolling_window_splits",
    "select_vintage",
    "summarize_regimes",
    "validate_temporal_split",
]
