"""
src/persistra/operations/io.py

Operations for loading and saving data.
"""
import pandas as pd
import os
from src.persistra.core.project import Operation
from src.persistra.core.objects import TimeSeries, StringParam, IntParam

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

        # Try to cast index_col to int if it looks like a number
        try:
            idx = int(index_col)
        except ValueError:
            idx = index_col

        df = pd.read_csv(filepath, index_col=idx, parse_dates=True)
        
        # Ensure it's a DataFrame, not a Series (for consistency)
        if isinstance(df, pd.Series):
            df = df.to_frame()

        return {'data': TimeSeries(df)}
