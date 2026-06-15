from importlib.metadata import version

import persistra


def test_version_matches_package_metadata():
    assert persistra.__version__ == version("persistra")
    assert persistra.__version__


def test_root_exports_intended_common_api():
    expected = {
        "Engine",
        "Result",
        "Portfolio",
        "PortfolioPolicy",
        "PortfolioConstraint",
        "FillDecision",
        "ExecutionTiming",
        "ExecutionModel",
        "IdealFill",
        "FixedCommission",
        "ProportionalSlippage",
        "VolumeImpact",
        "ParquetMarketData",
        "MarketData",
        "StreamingMarketData",
        "MarketDataWriter",
        "BarQuery",
        "ActionQuery",
        "UniverseQuery",
        "UniverseMembership",
        "AdjustmentPolicy",
        "coerce_adjustment_policy",
        "Strategy",
        "StrategyContext",
        "FactorStrategy",
        "CompositeStrategy",
        "EqualWeightRebalance",
        "BuyAndHold",
    }

    assert expected <= set(persistra.__all__)
    for name in expected:
        assert hasattr(persistra, name)


def test_provider_root_exports_removed():
    removed = {
        "build_active_universe",
        "build_point_in_time_universe",
        "build_universe",
        "ingest_actions",
        "ingest_aggregates",
        "ingest_flat_files",
        "make_client",
    }

    assert removed.isdisjoint(persistra.__all__)
    for name in removed:
        assert not hasattr(persistra, name)
