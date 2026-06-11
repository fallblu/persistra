from __future__ import annotations

from importlib.util import find_spec as _find_spec

if any(_find_spec(_m) is None for _m in ("gudhi", "ripser", "persim")):
    raise ImportError("TDA features require the [tda] extra: pip install 'persistra[tda]'")

from .embedding import TakensEmbedding
from .persistence import VietorisRipsPersistence
from .rolling import RollingPersistenceFeatures
from .vectorization import BettiCurve, PersistenceEntropy, PersistenceImage

__all__ = [
    "BettiCurve",
    "PersistenceEntropy",
    "PersistenceImage",
    "RollingPersistenceFeatures",
    "TakensEmbedding",
    "VietorisRipsPersistence",
]
