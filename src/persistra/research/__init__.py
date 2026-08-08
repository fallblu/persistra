"""Point-in-time research transforms with explicit temporal policy."""

from persistra.research.evaluation import (
    adjust_pvalues,
    compare_benchmark,
    information_coefficients,
    quantile_portfolios,
    summarize_groups,
)
from persistra.research.features import build_feature_panel, select_vintage
from persistra.research.labels import forward_returns
from persistra.research.manifest import (
    create_research_manifest,
    environment_versions,
    identify_artifact,
    manifest_from_json,
    manifest_to_json,
    read_research_manifest,
    write_research_manifest,
)
from persistra.research.model import (
    ArtifactIdentity,
    BenchmarkComparison,
    DatasetScope,
    FeaturePanel,
    FeaturePolicy,
    FeatureSpec,
    ForwardReturnLabels,
    GroupSignalResult,
    InformationCoefficientResult,
    MultipleTestingResult,
    QuantilePortfolioResult,
    ResearchManifest,
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
from persistra.research.transforms import (
    clip_cross_section,
    neutralize_cross_section,
    rank_cross_section,
    standardize_cross_section,
)

__all__ = [
    "ArtifactIdentity",
    "BenchmarkComparison",
    "DatasetScope",
    "FeaturePanel",
    "FeaturePolicy",
    "FeatureSpec",
    "ForwardReturnLabels",
    "GroupSignalResult",
    "InformationCoefficientResult",
    "MultipleTestingResult",
    "QuantilePortfolioResult",
    "ResearchManifest",
    "ResearchSummary",
    "TemporalSplit",
    "VintageSelection",
    "adjust_pvalues",
    "build_feature_panel",
    "clip_cross_section",
    "compare_benchmark",
    "create_research_manifest",
    "environment_versions",
    "expanding_window_splits",
    "forward_returns",
    "identify_artifact",
    "information_coefficients",
    "manifest_from_json",
    "manifest_to_json",
    "neutralize_cross_section",
    "quantile_portfolios",
    "rank_cross_section",
    "read_research_manifest",
    "rolling_window_splits",
    "select_vintage",
    "standardize_cross_section",
    "summarize_groups",
    "summarize_regimes",
    "validate_temporal_split",
    "write_research_manifest",
]
