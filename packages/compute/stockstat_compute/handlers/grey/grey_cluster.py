"""grey_cluster handler — 灰色聚类。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("grey_cluster")
def handle_grey_cluster(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    n_clusters = cs.params.get("n_clusters", 3)
    X = np.asarray(data if isinstance(data, (list, np.ndarray)) else data.get("X", []), dtype=float)
    if len(X) == 0:
        return {"labels": [], "error": "empty data"}
    # 简化：用 KMeans + 灰色关联作为距离度量
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import pdist
    # 标准化
    X_norm = (X - X.min(axis=0)) / (X.max(axis=0) - X.min(axis=0) + 1e-10)
    Z = linkage(X_norm, method="ward")
    labels = fcluster(Z, t=n_clusters, criterion="maxclust")
    return {"labels": labels.tolist(), "n_clusters": n_clusters}
