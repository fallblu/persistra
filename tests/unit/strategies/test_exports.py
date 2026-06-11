def test_builtin_strategies_importable_from_top_level():
    from persistra import (  # noqa: F401
        BuyAndHold,
        CrossSectionalMomentum,
        EqualWeightRebalance,
        MeanReversion,
        SMACrossover,
        VolTargetedEqualWeight,
    )
