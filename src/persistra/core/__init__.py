from os.path import dirname, join as joinpath

DATADIR = joinpath(dirname(__file__), 'data')

from .DatasetAnalysis import *
from .TimeSeriesAnalysis import *

__all__ = [
        "DatasetAnalysis",
        "TimeSeriesAnalysis",
        ]
