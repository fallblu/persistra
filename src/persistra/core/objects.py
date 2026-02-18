"""
src/persistra/core/objects.py

Defines the data types that flow through the graph (Wrappers) and the 
configuration parameters for Nodes.
"""
import pandas as pd
import numpy as np
from typing import Any, Optional, List, Union
from dataclasses import dataclass, field

# --- Data Wrappers ( The "Currency" ) ---

class DataWrapper:
    """Base class for all data flowing between nodes."""
    def __init__(self, data: Any, metadata: Optional[dict] = None):
        self.data = data
        self.metadata = metadata or {}

    def validate(self) -> bool:
        """Override to implement specific validation logic."""
        return True

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

class TimeSeries(DataWrapper):
    """Wraps a Pandas Series or DataFrame representing time-series data."""
    def __init__(self, data: Union[pd.Series, pd.DataFrame], metadata: dict = None):
        super().__init__(data, metadata)
        if not isinstance(data, (pd.Series, pd.DataFrame)):
            raise TypeError("TimeSeries data must be a pandas Series or DataFrame")

class DistanceMatrix(DataWrapper):
    """Wraps a square numpy array representing pairwise distances."""
    def __init__(self, data: np.ndarray, metadata: dict = None):
        super().__init__(data, metadata)
        if not isinstance(data, np.ndarray) or data.ndim != 2 or data.shape[0] != data.shape[1]:
            raise ValueError("DistanceMatrix must be a square numpy array")

class PersistenceDiagram(DataWrapper):
    """Wraps TDA persistence diagrams (e.g., from ripser)."""
    def __init__(self, data: list, metadata: dict = None):
        # data is typically a list of (birth, death) tuples or numpy arrays
        super().__init__(data, metadata)


# --- Parameters ( The "Knobs" ) ---

@dataclass
class Parameter:
    name: str
    label: str
    value: Any = None
    default: Any = None
    
    def __post_init__(self):
        if self.value is None:
            self.value = self.default

class IntParam(Parameter):
    """Integer parameter with min/max bounds."""
    def __init__(self, name: str, label: str, default: int, min_val: int = 0, max_val: int = 100):
        super().__init__(name, label, default=default)
        self.min_val = min_val
        self.max_val = max_val

class FloatParam(Parameter):
    """Float parameter with bounds."""
    def __init__(self, name: str, label: str, default: float, min_val: float = 0.0, max_val: float = 1.0):
        super().__init__(name, label, default=default)
        self.min_val = min_val
        self.max_val = max_val

class StringParam(Parameter):
    """Simple text input."""
    pass

class ChoiceParam(Parameter):
    """Dropdown selection."""
    def __init__(self, name: str, label: str, options: List[str], default: str):
        super().__init__(name, label, default=default)
        self.options = options
        if default not in options:
            raise ValueError(f"Default '{default}' is not in options: {options}")

class BoolParam(Parameter):
    """Checkbox toggle."""
    def __init__(self, name: str, label: str, default: bool = False):
        super().__init__(name, label, default=default)
