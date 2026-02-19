"""
src/persistra/operations/__init__.py

Registry of all available operations.
The UI Node Browser will import 'OPERATIONS_REGISTRY' to populate its list.
"""

from .io import CSVLoader
from .tda import SlidingWindow, RipsPersistence
from .viz import LinePlot, PersistencePlot

# A flat dictionary keyed by operation class name for direct lookup.
# Structure: { "ClassName": Class }

OPERATIONS_REGISTRY = {
    "CSVLoader": CSVLoader,
    "SlidingWindow": SlidingWindow,
    "RipsPersistence": RipsPersistence,
    "LinePlot": LinePlot,
    "PersistencePlot": PersistencePlot,
}

# Flat list if needed for lookups
ALL_OPERATIONS = list(OPERATIONS_REGISTRY.values())
