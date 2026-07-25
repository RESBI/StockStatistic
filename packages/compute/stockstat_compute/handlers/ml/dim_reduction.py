"""dimension_reduction handler — 降维。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("dimension_reduction")
def handle_dimension_reduction(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "pca")
    n_components = cs.params.get("n_components", 2)
    X = np.asarray(data if isinstance(data, (list, np.ndarray)) else data.get("X", []), dtype=float)
    if method == "pca":
        from sklearn.decomposition import PCA
        model = PCA(n_components=min(n_components, X.shape[1]))
        transformed = model.fit_transform(X)
        return {"transformed": transformed.tolist(),
                "explained_variance": model.explained_variance_ratio_.tolist(),
                "components": model.components_.tolist()}
    elif method == "tsne":
        from sklearn.manifold import TSNE
        model = TSNE(n_components=n_components, random_state=42)
        transformed = model.fit_transform(X)
        return {"transformed": transformed.tolist(), "method": "tsne"}
    elif method == "ica":
        from sklearn.decomposition import FastICA
        model = FastICA(n_components=min(n_components, X.shape[1]), random_state=42)
        transformed = model.fit_transform(X)
        return {"transformed": transformed.tolist(), "method": "ica"}
    raise ValueError(f"Unknown method: {method}")
