"""
src/persistra/operations/io/__init__.py

Operations for loading and saving data.
"""
import pandas as pd
import os
from persistra.core.project import Operation
from persistra.core.objects import TimeSeries, StringParam, IntParam

class CSVLoader(Operation):
    name = "CSV Loader"
    description = "Loads a CSV file into a Time Series."
    category = "Input"

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

    def execute(self, inputs, params):
        filepath = params['filepath']
        index_col = params['index_col']

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        # Logic:
        # 1. If None, pass it through (Pandas uses default RangeIndex).
        # 2. If it looks like an int (e.g. "0"), convert it to int.
        # 3. Otherwise, use the string value (e.g. "Date").
        
        if index_col is None:
            idx = None
        else:
            try:
                idx = int(index_col)
            except (ValueError, TypeError):
                # ValueError: index_col is "Date" (cannot cast to int)
                # TypeError: index_col is incompatible
                idx = index_col

        # Load CSV
        # Note: We must handle the case where idx is None explicitly if strictly needed,
        # but pandas read_csv(index_col=None) works perfectly.
        df = pd.read_csv(filepath, index_col=idx, parse_dates=True)
        
        # Ensure it's a DataFrame, not a Series (for consistency)
        if isinstance(df, pd.Series):
            df = df.to_frame()

        return {'data': TimeSeries(df)}