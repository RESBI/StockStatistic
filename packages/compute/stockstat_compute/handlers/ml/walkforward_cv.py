"""walkforward_cv handler — 前向验证交叉验证。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("walkforward_cv")
def handle_walkforward_cv(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    train_size = cs.params.get("train_size", 0.6)
    n_folds = cs.params.get("n_folds", 5)
    X = np.asarray(data["X"] if isinstance(data, dict) else cs.params.get("X"), dtype=float)
    y = np.asarray(data["y"] if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    n = len(X)
    fold_size = n // (n_folds + 1)
    if fold_size < 10:
        return {"fold_scores": [], "mean": 0, "error": "insufficient data"}
    scores = []
    for i in range(n_folds):
        train_end = (i + 1) * fold_size
        test_end = min(train_end + fold_size, n)
        if test_end <= train_end:
            break
        X_train, X_test = X[:train_end], X[train_end:test_end]
        y_train, y_test = y[:train_end], y[train_end:test_end]
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X_train, y_train)
        score = model.score(X_test, y_test)
        scores.append(float(score))
        if on_progress:
            on_progress(i + 1, n_folds)
    return {"fold_scores": scores, "mean": float(np.mean(scores)) if scores else 0.0,
            "std": float(np.std(scores)) if scores else 0.0, "n_folds": len(scores)}
