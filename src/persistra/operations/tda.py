"""
src/persistra/operations/tda.py

Operations for Topological Data Analysis (Sliding Windows, Persistence).
"""
import numpy as np
import pandas as pd
try:
    from ripser import ripser
except ImportError:
    # Fallback or mock for environments without ripser installed
    ripser = None

from persistra.core.project import Operation
from persistra.core.objects import TimeSeries, PersistenceDiagram, DataWrapper, IntParam, FloatParam

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
    category = "Transformation"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'series', 'type': TimeSeries}]
        self.outputs = [{'name': 'cloud', 'type': PointCloud}]
        
        self.parameters = [
            IntParam('window_size', 'Window Size', default=10, min_val=2, max_val=1000),
            IntParam('step', 'Step Size', default=1, min_val=1, max_val=100)
        ]

    def execute(self, inputs, params):
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

    def execute(self, inputs, params):
        if ripser is None:
            raise ImportError("The 'ripser' library is not installed.")

        cloud = inputs['cloud'].data
        max_dim = params['max_dim']
        thresh = params['threshold']

        # ripser returns dictionary: {'dgms': [array_H0, array_H1, ...], ...}
        result = ripser(cloud, maxdim=max_dim, thresh=thresh)
        diagrams = result['dgms']

        return {'diagram': PersistenceDiagram(diagrams)}
