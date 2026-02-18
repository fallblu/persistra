"""
src/persistra/operations/__init__.py

Registry of all available operations.
The UI Node Browser will import 'available_operations' to populate its list.
"""

from .io import CSVLoader
from .tda import SlidingWindow, RipsPersistence
from .viz import LinePlot, PersistencePlot

# A categorized dictionary for the UI TreeWidget
# Structure: { "Category Name": [Class1, Class2] }

OPERATIONS_REGISTRY = {
    "Input / Output": [
        CSVLoader
    ],
    "Transformation": [
        SlidingWindow,
    ],
    "TDA": [
        RipsPersistence
    ],
    "Visualization": [
        LinePlot,
        PersistencePlot
    ]
}

# Flat list if needed for lookups
ALL_OPERATIONS = [op for cat in OPERATIONS_REGISTRY.values() for op in cat]
