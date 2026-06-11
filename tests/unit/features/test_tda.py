import numpy as np
import pytest

ripser = pytest.importorskip("ripser")  # whole module skips if [tda] not installed


def test_vietoris_rips_produces_persistence_diagrams():
    from persistra.features.tda.persistence import VietorisRipsPersistence

    rng = np.random.default_rng(0)
    cloud = rng.standard_normal((30, 2))
    # transform expects a 2-D array (T, n_features) directly
    diagrams = VietorisRipsPersistence(homology_dims=(0, 1)).fit_transform(cloud)
    # Returns one diagram per homology dimension
    assert len(diagrams) == 2


def test_persistence_rejects_empty_homology_dims():
    from persistra.features.tda.persistence import VietorisRipsPersistence

    with pytest.raises(ValueError):
        VietorisRipsPersistence(homology_dims=())
