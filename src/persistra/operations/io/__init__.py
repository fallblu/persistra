"""
src/persistra/operations/io/__init__.py

Operations for loading and saving data.
"""
import json
import os

import numpy as np
import pandas as pd

from persistra.core.objects import (
    BoolParam,
    ChoiceParam,
    FloatParam,
    IntParam,
    StringParam,
    TimeSeries,
)
from persistra.core.project import Operation


class CSVLoader(Operation):
    name = "CSV Loader"
    description = "Loads a CSV file into a Time Series."
    category = "Input / Output"

    def __init__(self):
        super().__init__()
        # Outputs
        self.outputs = [{'name': 'data', 'type': TimeSeries}]

        # Parameters
        self.parameters = [
            StringParam(name='filepath', label='File Path', default='data.csv'),
            StringParam(name='index_col', label='Index Column', default='0'),
            # Future: Add Delimiter, Header, etc.
        ]

    def execute(self, inputs, params, cancel_event=None):
        filepath = params['filepath']
        index_col = params['index_col']

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        if index_col is None:
            idx = None
        else:
            try:
                idx = int(index_col)
            except (ValueError, TypeError):
                idx = index_col

        df = pd.read_csv(filepath, index_col=idx, parse_dates=True)

        if isinstance(df, pd.Series):
            df = df.to_frame()

        return {'data': TimeSeries(df)}


class ManualDataEntry(Operation):
    name = "Manual Data Entry"
    description = "Editable spreadsheet in the Viz Panel; outputs a DataFrame."
    category = "Input / Output"

    def __init__(self):
        super().__init__()
        self.outputs = [{'name': 'data', 'type': TimeSeries}]
        self.parameters = [
            StringParam(
                name='table_json',
                label='Table Data (JSON)',
                default='{"columns":["A","B"],"data":[[1,2],[3,4],[5,6]]}',
            ),
        ]

    def execute(self, inputs, params, cancel_event=None):
        raw = params.get('table_json', '{}')
        payload = json.loads(raw)
        df = pd.DataFrame(payload.get('data', []), columns=payload.get('columns', []))
        return {'data': TimeSeries(df)}


class DataGenerator(Operation):
    name = "Data Generator"
    description = (
        "Synthetic signals: sine, cosine, white noise, random walk, "
        "Brownian motion, statistical distributions, sphere sampling."
    )
    category = "Input / Output"

    def __init__(self):
        super().__init__()
        self.outputs = [{'name': 'data', 'type': TimeSeries}]
        self.parameters = [
            ChoiceParam(
                'signal_type', 'Signal Type',
                options=[
                    'sine', 'cosine', 'white_noise', 'random_walk',
                    'brownian', 'distribution', 'sphere',
                ],
                default='sine',
            ),
            IntParam('length', 'Length', default=500, min_val=2, max_val=100000),
            FloatParam('frequency', 'Frequency', default=1.0, min_val=0.001, max_val=1000.0),
            FloatParam('amplitude', 'Amplitude', default=1.0, min_val=0.0, max_val=1e6),
            FloatParam('mean', 'Mean', default=0.0, min_val=-1e6, max_val=1e6),
            FloatParam('std', 'Std Dev', default=1.0, min_val=0.0, max_val=1e6),
            IntParam('dimensions', 'Dimensions (sphere)', default=3, min_val=2, max_val=100),
            IntParam('seed', 'Random Seed', default=42, min_val=0, max_val=2**31 - 1),
        ]

    def execute(self, inputs, params, cancel_event=None):
        sig = params['signal_type']
        n = params['length']
        rng = np.random.default_rng(params['seed'])

        if sig == 'sine':
            t = np.linspace(0, 2 * np.pi * params['frequency'], n)
            data = params['amplitude'] * np.sin(t)
            df = pd.DataFrame({'sine': data})
        elif sig == 'cosine':
            t = np.linspace(0, 2 * np.pi * params['frequency'], n)
            data = params['amplitude'] * np.cos(t)
            df = pd.DataFrame({'cosine': data})
        elif sig == 'white_noise':
            data = rng.normal(params['mean'], params['std'], size=n)
            df = pd.DataFrame({'noise': data})
        elif sig == 'random_walk':
            steps = rng.normal(params['mean'], params['std'], size=n)
            data = np.cumsum(steps)
            df = pd.DataFrame({'random_walk': data})
        elif sig == 'brownian':
            steps = rng.normal(0, params['std'] * np.sqrt(1.0 / n), size=n)
            data = np.cumsum(steps)
            df = pd.DataFrame({'brownian': data})
        elif sig == 'distribution':
            data = rng.normal(params['mean'], params['std'], size=n)
            df = pd.DataFrame({'distribution': data})
        elif sig == 'sphere':
            dims = params['dimensions']
            raw = rng.normal(size=(n, dims))
            norms = np.linalg.norm(raw, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            points = raw / norms
            df = pd.DataFrame(points, columns=[f"d{i}" for i in range(dims)])
        else:
            raise ValueError(f"Unknown signal type: {sig}")

        return {'data': TimeSeries(df)}


class CSVWriter(Operation):
    name = "CSV Writer"
    description = "Export a DataFrame to a CSV file at a specified path."
    category = "Input / Output"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'data', 'type': TimeSeries}]
        self.parameters = [
            StringParam(name='filepath', label='File Path', default='output.csv'),
            BoolParam(name='include_index', label='Include Index', default=True),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data
        filepath = params['filepath']
        include_index = params.get('include_index', True)
        df.to_csv(filepath, index=include_index)
        return {}
