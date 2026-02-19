"""
src/persistra/operations/__init__.py

Registry of all available operations.
The UI Node Browser will import 'REGISTRY' to populate its list.
"""

from typing import Dict, List, Optional, Type

from persistra.core.project import Operation


class OperationRegistry:
    """Central registry of all available operations.

    Provides ``register``, ``get``, ``all``, ``by_category``, and ``search``
    methods for discovering and retrieving operation classes.
    """

    def __init__(self):
        self._operations: Dict[str, Type[Operation]] = {}

    # ------------------------------------------------------------------
    # New API
    # ------------------------------------------------------------------

    def register(self, op_class: Type[Operation]):
        """Register an operation class.  Uses the *class name* as key.

        Can be used as a decorator::

            @REGISTRY.register
            class MyOp(Operation):
                ...
        """
        key = op_class.__name__
        if key in self._operations:
            raise ValueError(f"Duplicate operation name: {key}")
        self._operations[key] = op_class
        return op_class

    def get(self, name: str, default=None) -> Optional[Type[Operation]]:
        return self._operations.get(name, default)

    def all(self) -> Dict[str, Type[Operation]]:
        return dict(self._operations)

    def by_category(self) -> Dict[str, List[Type[Operation]]]:
        categories: Dict[str, List[Type[Operation]]] = {}
        for op in self._operations.values():
            categories.setdefault(op.category, []).append(op)
        return categories

    def search(self, query: str) -> List[Type[Operation]]:
        """Fuzzy search by name, description, and category."""
        query_lower = query.lower()
        results = []
        for op in self._operations.values():
            if (
                query_lower in op.name.lower()
                or query_lower in op.description.lower()
                or query_lower in op.category.lower()
            ):
                results.append(op)
        return results



# Global singleton
REGISTRY = OperationRegistry()

# ------------------------------------------------------------------
# Auto-register built-in operations
# ------------------------------------------------------------------

from .io import CSVLoader, ManualDataEntry, DataGenerator, CSVWriter  # noqa: E402
from .tda import SlidingWindow, RipsPersistence  # noqa: E402
from .tda import (  # noqa: E402
    AlphaPersistence,
    CechPersistence,
    CubicalPersistence,
    PersistenceLandscape,
    PersistenceImage,
    DiagramDistance,
)
from .viz import LinePlot, PersistencePlot  # noqa: E402
from .viz import (  # noqa: E402
    ScatterPlot,
    Histogram,
    PersistenceDiagramPlot,
    BarcodePlot,
    Heatmap,
    OverlayPlot,
    SubplotGrid,
    ThreeDScatter,
    InteractivePlot,
)
from .preprocessing import (  # noqa: E402
    Normalize,
    Differencing,
    Returns,
    LogTransform,
    LogReturns,
    RollingStatistics,
)
from .ml import (  # noqa: E402
    KMeansClustering,
    PCA,
    LinearRegressionOp,
    LogisticRegressionOp,
)
from .utility import ColumnSelector, MergeJoin, PythonExpression, ExportFigure  # noqa: E402

for _cls in [
    # I/O
    CSVLoader, ManualDataEntry, DataGenerator, CSVWriter,
    # Preprocessing
    Normalize, Differencing, Returns, LogTransform, LogReturns, RollingStatistics,
    # TDA
    SlidingWindow, RipsPersistence, AlphaPersistence, CechPersistence,
    CubicalPersistence, PersistenceLandscape, PersistenceImage, DiagramDistance,
    # ML
    KMeansClustering, PCA, LinearRegressionOp, LogisticRegressionOp,
    # Visualization
    LinePlot, PersistencePlot,
    ScatterPlot, Histogram, PersistenceDiagramPlot, BarcodePlot, Heatmap,
    OverlayPlot, SubplotGrid, ThreeDScatter, InteractivePlot,
    # Utility
    ColumnSelector, MergeJoin, PythonExpression, ExportFigure,
]:
    REGISTRY.register(_cls)


