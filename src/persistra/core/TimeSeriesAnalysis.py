import os

import pandas as pd
import numpy as np

from persistra.core.DatasetAnalysis import DatasetAnalysis
from . import DATADIR


class TimeSeriesAnalysis(DatasetAnalysis):

    def __init__(self, data=pd.read_csv(os.path.join(DATADIR, "test_dataset.csv"), index_col="Date", dtype={"^ndx":np.float64, "^spx":np.float64, "^dji":np.float64}, parse_dates=True, date_format="%Y-%m-%d"), label="Prices"):
        super().__init__()
        self.df[label] = data
        self.df["returns"] = data.diff().dropna()
        self.df["log returns"] = np.log(data.diff().dropna())


