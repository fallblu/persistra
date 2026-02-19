"""
src/persistra/operations/tda/__init__.py

Operations for Topological Data Analysis (Sliding Windows, Persistence).
"""
import numpy as np
import pandas as pd
try:
    from ripser import ripser
except ImportError:
    # Fallback or mock for environments without ripser installed
    ripser = None

try:
    import gudhi
except ImportError:
    gudhi = None

try:
    import persim as _persim_mod
except ImportError:
    _persim_mod = None

from persistra.core.project import Operation
from persistra.core.objects import (
    TimeSeries, PersistenceDiagram, DataWrapper,
    IntParam, FloatParam, ChoiceParam,
)

# Minimal wrapper for PointClouds since it wasn't in objects.py
class PointCloud(DataWrapper):
    """Wraps a Numpy array representing a Point Cloud (N_samples x M_dimensions)."""
    def __init__(self, data, metadata=None):
        super().__init__(data, metadata)
        if not isinstance(data, np.ndarray):
            raise TypeError("Point Cloud data must be a numpy array")

class SlidingWindow(Operation):
    name = "Sliding Window"
    description = "Converts a Time Series into a Point Cloud (Takens' Embedding)."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'series', 'type': TimeSeries}]
        self.outputs = [{'name': 'cloud', 'type': PointCloud}]
        
        self.parameters = [
            IntParam('window_size', 'Window Size', default=10, min_val=2, max_val=1000),
            IntParam('step', 'Step Size', default=1, min_val=1, max_val=100)
        ]

    def execute(self, inputs, params, cancel_event=None):
        # Unwrap the dataframe
        df = inputs['series'].data
        
        # We assume single-variate time series for MVP. Take the first column.
        signal = df.iloc[:, 0].values
        
        dim = params['window_size']
        step = params['step']
        
        # Efficient sliding window using Numpy strides
        # Shape: (N_windows, Window_Size)
        N = signal.shape[0]
        if N < dim:
            raise ValueError(f"Time series length ({N}) is shorter than window size ({dim})")

        # Number of windows
        num_windows = (N - dim) // step + 1
        
        # Create strided array
        # This is a view, not a copy (very fast)
        shape = (num_windows, dim)
        strides = (signal.strides[0] * step, signal.strides[0])
        
        windowed_data = np.lib.stride_tricks.as_strided(
            signal, shape=shape, strides=strides
        ).copy() # Copy to ensure memory safety downstream

        return {'cloud': PointCloud(windowed_data)}


class RipsPersistence(Operation):
    name = "Rips Persistence"
    description = "Computes Persistent Homology using the Vietoris-Rips complex."
    category = "TDA"

    def __init__(self):
        super().__init__()
        # Accepts PointCloud (could also accept DistanceMatrix in future)
        self.inputs = [{'name': 'cloud', 'type': PointCloud}]
        self.outputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        
        self.parameters = [
            IntParam('max_dim', 'Max Homology Dimension', default=1, min_val=0, max_val=3),
            FloatParam('threshold', 'Max Distance Threshold', default=np.inf)
        ]

    def execute(self, inputs, params, cancel_event=None):
        if ripser is None:
            raise ImportError("The 'ripser' library is not installed.")

        cloud = inputs['cloud'].data
        max_dim = params['max_dim']
        thresh = params['threshold']

        # ripser returns dictionary: {'dgms': [array_H0, array_H1, ...], ...}
        result = ripser(cloud, maxdim=max_dim, thresh=thresh)
        diagrams = result['dgms']

        return {'diagram': PersistenceDiagram(diagrams)}


class AlphaPersistence(Operation):
    name = "Alpha Persistence"
    description = "Alpha complex persistence via gudhi."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'cloud', 'type': PointCloud}]
        self.outputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.parameters = [
            IntParam('max_dim', 'Max Homology Dimension', default=1, min_val=0, max_val=3),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if gudhi is None:
            raise ImportError("The 'gudhi' library is not installed. Install with: pip install persistra[tda]")
        cloud = inputs['cloud'].data
        max_dim = params['max_dim']
        alpha = gudhi.AlphaComplex(points=cloud.tolist())
        st = alpha.create_simplex_tree()
        st.compute_persistence()
        diagrams = [
            np.array(st.persistence_intervals_in_dimension(d))
            for d in range(max_dim + 1)
        ]
        # Ensure empty dimensions have shape (0, 2)
        diagrams = [d if d.size > 0 else np.empty((0, 2)) for d in diagrams]
        return {'diagram': PersistenceDiagram(diagrams)}


class CechPersistence(Operation):
    name = "Čech Persistence"
    description = "Čech complex persistence via gudhi (Rips-based approximation)."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'cloud', 'type': PointCloud}]
        self.outputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.parameters = [
            IntParam('max_dim', 'Max Homology Dimension', default=1, min_val=0, max_val=3),
            FloatParam('max_radius', 'Max Radius', default=1.0, min_val=0.0, max_val=1e6),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if gudhi is None:
            raise ImportError("The 'gudhi' library is not installed. Install with: pip install persistra[tda]")
        cloud = inputs['cloud'].data
        max_dim = params['max_dim']
        max_radius = params['max_radius']
        rips = gudhi.RipsComplex(points=cloud.tolist(), max_edge_length=max_radius)
        st = rips.create_simplex_tree(max_dimension=max_dim + 1)
        st.compute_persistence()
        diagrams = [
            np.array(st.persistence_intervals_in_dimension(d))
            for d in range(max_dim + 1)
        ]
        diagrams = [d if d.size > 0 else np.empty((0, 2)) for d in diagrams]
        return {'diagram': PersistenceDiagram(diagrams)}


class CubicalPersistence(Operation):
    name = "Cubical Persistence"
    description = "Cubical complex persistence via gudhi. For grid/image data."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'image', 'type': DataWrapper}]
        self.outputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.parameters = [
            IntParam('max_dim', 'Max Homology Dimension', default=1, min_val=0, max_val=3),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if gudhi is None:
            raise ImportError("The 'gudhi' library is not installed. Install with: pip install persistra[tda]")
        data = inputs['image'].data
        if not isinstance(data, np.ndarray):
            data = np.asarray(data)
        max_dim = params['max_dim']
        cc = gudhi.CubicalComplex(top_dimensional_cells=data.flatten(), dimensions=list(data.shape))
        cc.compute_persistence()
        diagrams = [
            np.array(cc.persistence_intervals_in_dimension(d))
            for d in range(max_dim + 1)
        ]
        diagrams = [d if d.size > 0 else np.empty((0, 2)) for d in diagrams]
        return {'diagram': PersistenceDiagram(diagrams)}


class PersistenceLandscape(Operation):
    name = "Persistence Landscape"
    description = "Vectorization of persistence diagrams into landscape functions."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.outputs = [{'name': 'landscape', 'type': DataWrapper}]
        self.parameters = [
            IntParam('num_landscapes', 'Num Landscapes', default=5, min_val=1, max_val=100),
            IntParam('resolution', 'Resolution', default=100, min_val=10, max_val=10000),
            IntParam('homology_dim', 'Homology Dimension', default=1, min_val=0, max_val=3),
        ]

    def execute(self, inputs, params, cancel_event=None):
        dgms = inputs['diagram'].data
        hom = params['homology_dim']
        num_l = params['num_landscapes']
        res = params['resolution']

        if hom >= len(dgms) or dgms[hom].size == 0:
            return {'landscape': DataWrapper(np.zeros((num_l, res)))}

        diagram = dgms[hom]
        births = diagram[:, 0]
        deaths = diagram[:, 1]
        finite = np.isfinite(deaths)
        births = births[finite]
        deaths = deaths[finite]

        if len(births) == 0:
            return {'landscape': DataWrapper(np.zeros((num_l, res)))}

        t_min = births.min()
        t_max = deaths.max()
        t = np.linspace(t_min, t_max, res)

        # Each feature gives a tent function: max(0, min(t-b, d-t))
        tent_values = np.maximum(0, np.minimum(
            t[np.newaxis, :] - births[:, np.newaxis],
            deaths[:, np.newaxis] - t[np.newaxis, :]
        ))

        # Sort descending at each t to get landscape layers
        sorted_vals = np.sort(tent_values, axis=0)[::-1]

        # Pad if fewer features than requested landscapes
        if sorted_vals.shape[0] < num_l:
            pad = np.zeros((num_l - sorted_vals.shape[0], res))
            sorted_vals = np.vstack([sorted_vals, pad])

        landscape = sorted_vals[:num_l]
        return {'landscape': DataWrapper(landscape)}


class PersistenceImage(Operation):
    name = "Persistence Image"
    description = "Vectorization via Gaussian-weighted persistence images."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.outputs = [{'name': 'image', 'type': DataWrapper}]
        self.parameters = [
            IntParam('resolution', 'Resolution', default=20, min_val=5, max_val=200),
            FloatParam('sigma', 'Sigma', default=0.1, min_val=0.001, max_val=10.0),
            IntParam('homology_dim', 'Homology Dimension', default=1, min_val=0, max_val=3),
        ]

    def execute(self, inputs, params, cancel_event=None):
        dgms = inputs['diagram'].data
        hom = params['homology_dim']
        res = params['resolution']
        sigma = params['sigma']

        if hom >= len(dgms) or dgms[hom].size == 0:
            return {'image': DataWrapper(np.zeros((res, res)))}

        diagram = dgms[hom]
        births = diagram[:, 0]
        deaths = diagram[:, 1]
        finite = np.isfinite(deaths)
        births = births[finite]
        deaths = deaths[finite]

        if len(births) == 0:
            return {'image': DataWrapper(np.zeros((res, res)))}

        persistence = deaths - births

        # Build a 2D grid over (birth, persistence)
        b_min, b_max = births.min(), births.max()
        p_min, p_max = 0.0, persistence.max()
        if b_max == b_min:
            b_max = b_min + 1.0
        if p_max == p_min:
            p_max = p_min + 1.0

        bx = np.linspace(b_min, b_max, res)
        py = np.linspace(p_min, p_max, res)
        BX, PY = np.meshgrid(bx, py)

        img = np.zeros((res, res))
        for b, p in zip(births, persistence):
            weight = p  # linear weighting by persistence
            img += weight * np.exp(-(((BX - b) ** 2 + (PY - p) ** 2) / (2 * sigma ** 2)))

        return {'image': DataWrapper(img)}


class DiagramDistance(Operation):
    name = "Diagram Distance"
    description = "Wasserstein or Bottleneck distance between two persistence diagrams."
    category = "TDA"

    def __init__(self):
        super().__init__()
        self.inputs = [
            {'name': 'diagram_a', 'type': PersistenceDiagram},
            {'name': 'diagram_b', 'type': PersistenceDiagram},
        ]
        self.outputs = [{'name': 'distance', 'type': DataWrapper}]
        self.parameters = [
            ChoiceParam('metric', 'Metric',
                        options=['wasserstein', 'bottleneck'], default='wasserstein'),
            IntParam('homology_dim', 'Homology Dimension', default=1, min_val=0, max_val=3),
            FloatParam('order', 'Order (Wasserstein)', default=2.0, min_val=1.0, max_val=100.0),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if _persim_mod is None:
            raise ImportError("The 'persim' library is not installed. Install with: pip install persistra[tda]")

        dgms_a = inputs['diagram_a'].data
        dgms_b = inputs['diagram_b'].data
        hom = params['homology_dim']
        metric = params['metric']

        a = dgms_a[hom] if hom < len(dgms_a) else np.empty((0, 2))
        b = dgms_b[hom] if hom < len(dgms_b) else np.empty((0, 2))

        if metric == 'wasserstein':
            dist = _persim_mod.wasserstein(a, b, order=params['order'])
        else:
            dist = _persim_mod.bottleneck(a, b)

        return {'distance': DataWrapper(float(dist))}