"""
src/persistra/operations/preprocessing/__init__.py

Preprocessing operations for data transformation.
"""
import numpy as np
import pandas as pd

from persistra.core.objects import ChoiceParam, IntParam, TimeSeries
from persistra.core.project import Operation, SocketDef
from persistra.core.types import ConcreteType


class Normalize(Operation):
    name = "Normalize"
    description = "Min-max or z-score normalization."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.parameters = [
            ChoiceParam('method', 'Method', options=['min-max', 'z-score'], default='min-max'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        method = params['method']
        numeric = df.select_dtypes(include='number')
        if method == 'min-max':
            mn = numeric.min()
            mx = numeric.max()
            rng = mx - mn
            rng[rng == 0] = 1.0
            df[numeric.columns] = (numeric - mn) / rng
        elif method == 'z-score':
            mean = numeric.mean()
            std = numeric.std()
            std[std == 0] = 1.0
            df[numeric.columns] = (numeric - mean) / std
        return {'data': TimeSeries(df)}


class Differencing(Operation):
    name = "Differencing"
    description = "First or Nth-order differencing."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.parameters = [
            IntParam('order', 'Order', default=1, min_val=1, max_val=10),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        order = params['order']
        df = df.diff(periods=order).dropna()
        return {'data': TimeSeries(df)}


class Returns(Operation):
    name = "Returns"
    description = "Simple returns: (x[t] - x[t-1]) / x[t-1]."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        df = df.pct_change().dropna()
        return {'data': TimeSeries(df)}


class LogTransform(Operation):
    name = "Log Transform"
    description = "Element-wise natural or base-10 log."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.parameters = [
            ChoiceParam('base', 'Base', options=['natural', 'base10'], default='natural'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        numeric = df.select_dtypes(include='number')
        if (numeric <= 0).any().any():
            raise ValueError("Log transform requires all values to be positive.")
        if params['base'] == 'natural':
            df[numeric.columns] = np.log(numeric)
        else:
            df[numeric.columns] = np.log10(numeric)
        return {'data': TimeSeries(df)}


class LogReturns(Operation):
    name = "Log Returns"
    description = "log(x[t] / x[t-1])."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        numeric = df.select_dtypes(include='number')
        df[numeric.columns] = np.log(numeric / numeric.shift(1))
        df = df.dropna()
        return {'data': TimeSeries(df)}


class RollingStatistics(Operation):
    name = "Rolling Statistics"
    description = "Rolling mean, std, min, max, sum, median."
    category = "Preprocessing"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.parameters = [
            IntParam('window', 'Window Size', default=10, min_val=2, max_val=10000),
            ChoiceParam(
                'statistic', 'Statistic',
                options=['mean', 'std', 'min', 'max', 'sum', 'median'],
                default='mean',
            ),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data.copy()
        window = params['window']
        stat = params['statistic']
        roller = df.rolling(window)
        result = getattr(roller, stat)()
        result = result.dropna()
        return {'data': TimeSeries(result)}
