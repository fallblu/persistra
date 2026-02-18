import unittest
import pandas as pd
import numpy as np
import tempfile
import os

from src.persistra.operations.io import CSVLoader
from src.persistra.operations.tda import SlidingWindow, PointCloud
from src.persistra.core.objects import TimeSeries

class TestOperations(unittest.TestCase):

    def test_csv_loader(self):
        """Test loading a CSV into a TimeSeries object."""
        # Create dummy CSV
        df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as tmp:
            df.to_csv(tmp.name, index=False)
            tmp_path = tmp.name

        try:
            op = CSVLoader()
            # Set params directly
            params = {'filepath': tmp_path, 'index_col': None}
            # Execute
            result = op.execute({}, params)
            
            self.assertIn('data', result)
            self.assertIsInstance(result['data'], TimeSeries)
            pd.testing.assert_frame_equal(result['data'].data, df)
            
        finally:
            os.remove(tmp_path)

    def test_sliding_window(self):
        """Test Takens' Embedding logic."""
        # Input: Series [0, 1, 2, 3, 4, 5]
        data = pd.DataFrame({'val': [0, 1, 2, 3, 4, 5]})
        ts = TimeSeries(data)
        
        op = SlidingWindow()
        
        # Case 1: Window=3, Step=1
        # Expected: [[0,1,2], [1,2,3], [2,3,4], [3,4,5]]
        params = {'window_size': 3, 'step': 1}
        result = op.execute({'series': ts}, params)
        
        cloud = result['cloud'].data
        expected = np.array([
            [0, 1, 2],
            [1, 2, 3],
            [2, 3, 4],
            [3, 4, 5]
        ])
        
        np.testing.assert_array_equal(cloud, expected)
        
        # Case 2: Window=3, Step=2
        # Expected: [[0,1,2], [2,3,4]]
        params = {'window_size': 3, 'step': 2}
        result = op.execute({'series': ts}, params)
        
        cloud = result['cloud'].data
        expected = np.array([
            [0, 1, 2],
            [2, 3, 4]
        ])
        np.testing.assert_array_equal(cloud, expected)

if __name__ == '__main__':
    unittest.main()
