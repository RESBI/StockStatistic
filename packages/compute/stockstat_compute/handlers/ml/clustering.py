"""clustering handler — 聚类分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("clustering")
def handle_clustering(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "kmeans")
    n_clusters = cs.params.get("n_clusters", 3)
    X = np.asarray(data if isinstance(data, (list, np.ndarray)) else data.get("X", []), dtype=float)
    if method == "kmeans":
        from sklearn.cluster import KMeans
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = model.fit_predict(X)
        centroids = model.cluster_centers_
        from sklearn.metrics import silhouette_score
        sil = silhouette_score(X, labels) if len(set(labels)) > 1 else 0.0
        return {"labels": labels.tolist(), "centroids": centroids.tolist(),
                "silhouette": float(sil), "inertia": float(model.inertia_)}
    elif method == "hierarchical":
        from scipy.cluster.hierarchy import linkage, fcluster
        Z = linkage(X, method="ward")
        labels = fcluster(Z, t=n_clusters, criterion="maxclust")
        return {"labels": labels.tolist(), "method": "hierarchical"}
    elif method == "dbscan":
        from sklearn.cluster import DBSCAN
        model = DBSCAN(eps=cs.params.get("eps", 0.5), min_samples=cs.params.get("min_samples", 5))
        labels = model.fit_predict(X)
        return {"labels": labels.tolist(), "method": "dbscan"}
    raise ValueError(f"Unknown method: {method}")
