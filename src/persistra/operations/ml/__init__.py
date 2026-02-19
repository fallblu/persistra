"""
src/persistra/operations/ml/__init__.py

Machine Learning operations wrapping scikit-learn.
"""
import numpy as np

from persistra.core.objects import DataWrapper, FloatParam, IntParam
from persistra.core.project import Operation, SocketDef
from persistra.core.types import ConcreteType

try:
    import sklearn  # noqa: F401
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


def _to_array(wrapper):
    """Convert a DataWrapper's data to a numpy array."""
    import pandas as pd
    data = wrapper.data if isinstance(wrapper, DataWrapper) else wrapper
    if isinstance(data, (pd.DataFrame, pd.Series)):
        return data.values
    return np.asarray(data)


class KMeansClustering(Operation):
    name = "K-Means Clustering"
    description = "K-Means clustering via scikit-learn."
    category = "Machine Learning"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [
            SocketDef('labels', ConcreteType(DataWrapper)),
            SocketDef('centroids', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            IntParam('n_clusters', 'Num Clusters', default=3, min_val=2, max_val=100),
            IntParam('max_iter', 'Max Iterations', default=300, min_val=1, max_val=10000),
            IntParam('random_state', 'Random Seed', default=42, min_val=0, max_val=2**31 - 1),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is not installed. Install with: pip install persistra[ml]")
        from sklearn.cluster import KMeans

        X = _to_array(inputs['data'])
        km = KMeans(
            n_clusters=params['n_clusters'],
            max_iter=params['max_iter'],
            random_state=params['random_state'],
            n_init='auto',
        )
        km.fit(X)
        return {
            'labels': DataWrapper(km.labels_),
            'centroids': DataWrapper(km.cluster_centers_),
        }


class PCA(Operation):
    name = "PCA"
    description = "Principal Component Analysis via scikit-learn."
    category = "Machine Learning"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [
            SocketDef('transformed', ConcreteType(DataWrapper)),
            SocketDef('components', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            IntParam('n_components', 'Num Components', default=2, min_val=1, max_val=100),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is not installed. Install with: pip install persistra[ml]")
        from sklearn.decomposition import PCA as _PCA

        X = _to_array(inputs['data'])
        pca = _PCA(n_components=params['n_components'])
        transformed = pca.fit_transform(X)
        return {
            'transformed': DataWrapper(transformed),
            'components': DataWrapper(pca.components_),
        }


class LinearRegressionOp(Operation):
    name = "Linear Regression"
    description = "Linear regression via scikit-learn."
    category = "Machine Learning"

    def __init__(self):
        super().__init__()
        self.inputs = [
            SocketDef('X', ConcreteType(DataWrapper)),
            SocketDef('y', ConcreteType(DataWrapper)),
        ]
        self.outputs = [
            SocketDef('predictions', ConcreteType(DataWrapper)),
            SocketDef('coefficients', ConcreteType(DataWrapper)),
            SocketDef('r_squared', ConcreteType(DataWrapper)),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is not installed. Install with: pip install persistra[ml]")
        from sklearn.linear_model import LinearRegression

        X = _to_array(inputs['X'])
        y = _to_array(inputs['y']).ravel()
        model = LinearRegression()
        model.fit(X, y)
        preds = model.predict(X)
        r2 = model.score(X, y)
        return {
            'predictions': DataWrapper(preds),
            'coefficients': DataWrapper(model.coef_),
            'r_squared': DataWrapper(float(r2)),
        }


class LogisticRegressionOp(Operation):
    name = "Logistic Regression"
    description = "Logistic regression via scikit-learn."
    category = "Machine Learning"

    def __init__(self):
        super().__init__()
        self.inputs = [
            SocketDef('X', ConcreteType(DataWrapper)),
            SocketDef('y', ConcreteType(DataWrapper)),
        ]
        self.outputs = [
            SocketDef('predictions', ConcreteType(DataWrapper)),
            SocketDef('probabilities', ConcreteType(DataWrapper)),
            SocketDef('accuracy', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            FloatParam('C', 'Regularization (C)', default=1.0, min_val=0.001, max_val=1000.0),
            IntParam('max_iter', 'Max Iterations', default=100, min_val=1, max_val=10000),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is not installed. Install with: pip install persistra[ml]")
        from sklearn.linear_model import LogisticRegression

        X = _to_array(inputs['X'])
        y = _to_array(inputs['y']).ravel()
        model = LogisticRegression(C=params['C'], max_iter=params['max_iter'])
        model.fit(X, y)
        preds = model.predict(X)
        probs = model.predict_proba(X)
        acc = model.score(X, y)
        return {
            'predictions': DataWrapper(preds),
            'probabilities': DataWrapper(probs),
            'accuracy': DataWrapper(float(acc)),
        }
