"""regime_detection handler — 市场状态识别。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("regime_detection")
def handle_regime_detection(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "change_point")
    n_regimes = cs.params.get("n_regimes", 2)
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    if method == "change_point":
        # 简单变点检测：基于均值变化
        returns = np.diff(x) / x[:-1] if len(x) > 1 else x
        if len(returns) < n_regimes * 5:
            return {"labels": [0] * len(x), "method": "change_point"}
        # 用 KMeans 聚类收益率
        from sklearn.cluster import KMeans
        features = returns.reshape(-1, 1)
        model = KMeans(n_clusters=n_regimes, random_state=42, n_init=10)
        labels = model.fit_predict(features)
        labels = np.concatenate([[0], labels]).tolist()
        # 计算每个 regime 的统计
        regime_stats = {}
        for r in range(n_regimes):
            mask = np.array(labels) == r
            if mask.sum() > 0:
                regime_stats[r] = {
                    "mean_return": float(returns[mask[1:]].mean()) if mask[1:].sum() > 0 else 0,
                    "volatility": float(returns[mask[1:]].std()) if mask[1:].sum() > 0 else 0,
                    "count": int(mask.sum()),
                }
        return {"labels": labels, "regime_stats": regime_stats, "method": "change_point"}
    elif method == "hmm":
        try:
            from hmmlearn.hmm import GaussianHMM
            returns = np.diff(x) / x[:-1] if len(x) > 1 else x
            model = GaussianHMM(n_components=n_regimes, random_state=42, n_iter=100)
            model.fit(returns.reshape(-1, 1))
            labels = model.predict(returns.reshape(-1, 1))
            labels = np.concatenate([[0], labels]).tolist()
            return {"labels": labels, "method": "hmm",
                    "transition_matrix": model.transmat_.tolist()}
        except ImportError:
            return {"error": "hmmlearn not installed", "method": "hmm"}
    raise ValueError(f"Unknown method: {method}")
