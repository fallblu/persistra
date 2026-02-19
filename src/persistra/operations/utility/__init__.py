"""
src/persistra/operations/utility/__init__.py

Utility operations: Column Selector, Merge/Join, Python Expression, Export Figure.
"""
import numpy as np
import pandas as pd

from persistra.core.objects import (
    BoolParam,
    ChoiceParam,
    DataWrapper,
    IntParam,
    StringParam,
    TimeSeries,
)
from persistra.core.project import Operation
from persistra.core.types import AnyType


class ColumnSelector(Operation):
    name = "Column Selector"
    description = "Picks specific columns from a DataFrame by name or index."
    category = "Utility"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'data', 'type': TimeSeries}]
        self.outputs = [{'name': 'data', 'type': TimeSeries}]
        self.parameters = [
            StringParam('columns', 'Columns (comma-separated)', default='0'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data
        cols_str = params['columns']
        parts = [c.strip() for c in cols_str.split(',') if c.strip()]

        # If all parts are digits, treat as integer indices
        if all(p.isdigit() for p in parts):
            indices = [int(p) for p in parts]
            selected = df.iloc[:, indices]
        else:
            selected = df[parts]

        if isinstance(selected, pd.Series):
            selected = selected.to_frame()

        return {'data': TimeSeries(selected)}


class MergeJoin(Operation):
    name = "Merge / Join"
    description = "Joins two DataFrames on a key column or index."
    category = "Utility"

    def __init__(self):
        super().__init__()
        self.inputs = [
            {'name': 'left', 'type': TimeSeries},
            {'name': 'right', 'type': TimeSeries},
        ]
        self.outputs = [{'name': 'data', 'type': TimeSeries}]
        self.parameters = [
            ChoiceParam('how', 'Join Type',
                        options=['inner', 'outer', 'left', 'right'], default='inner'),
            StringParam('on', 'On Column', default=''),
            BoolParam('left_index', 'Use Left Index', default=False),
            BoolParam('right_index', 'Use Right Index', default=False),
        ]

    def execute(self, inputs, params, cancel_event=None):
        left = inputs['left'].data
        right = inputs['right'].data
        how = params['how']
        on = params.get('on', '').strip() or None
        left_index = params.get('left_index', False)
        right_index = params.get('right_index', False)

        result = pd.merge(
            left, right, how=how, on=on,
            left_index=left_index, right_index=right_index,
        )
        return {'data': TimeSeries(result)}


class PythonExpression(Operation):
    name = "Python Expression"
    description = "User-supplied arbitrary Python code."
    category = "Utility"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'data', 'type': DataWrapper, 'required': False}]
        self.outputs = [{'name': 'result', 'type': DataWrapper}]
        self.parameters = [
            StringParam('code', 'Code', default="result = inputs.get('data')"),
        ]

    def execute(self, inputs, params, cancel_event=None):
        code = params['code']
        namespace = {
            "inputs": inputs,
            "params": params,
            "np": np,
            "pd": pd,
            "result": None,
        }
        exec(code, namespace)  # noqa: S102
        return {'result': namespace['result']}


class ExportFigure(Operation):
    name = "Export Figure"
    description = "Saves a Figure to disk (PNG/SVG/PDF)."
    category = "Utility"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'figure', 'type': DataWrapper}]
        self.parameters = [
            StringParam('filepath', 'File Path', default='figure.png'),
            ChoiceParam('format', 'Format', options=['png', 'svg', 'pdf'], default='png'),
            IntParam('dpi', 'DPI', default=150, min_val=50, max_val=600),
        ]

    def execute(self, inputs, params, cancel_event=None):
        fig_wrapper = inputs['figure']
        fig = fig_wrapper.data if isinstance(fig_wrapper, DataWrapper) else fig_wrapper
        filepath = params['filepath']
        fmt = params['format']
        dpi = params['dpi']
        fig.savefig(filepath, format=fmt, dpi=dpi, bbox_inches='tight')
        return {}
