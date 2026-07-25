"""feature_importance handler — 特征重要性。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
import pandas as pd
from stockstat_foundation import TaskSpec
from .._base import register


@register("feature_importance")
def handle_feature_importance(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "gini")
    X = np.asarray(data["X"] if isinstance(data, dict) else cs.params.get("X"), dtype=float)
    y = np.asarray(data["y"] if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    feature_names = cs.params.get("feature_names", list(range(X.shape[1])))
    if method in ("gini", "gain"):
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        importances = model.feature_importances_
    elif method == "permutation":
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.inspection import permutation_importance
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        result = permutation_importance(model, X, y, n_repeats=5, random_state=42)
        importances = result.importances_mean
    elif method == "mutual_info":
        from sklearn.feature_selection import mutual_info_regression
        importances = mutual_info_regression(X, y)
    else:
        raise ValueError(f"Unknown method: {method}")
    df = pd.DataFrame({"feature": feature_names, "importance": importances})
    df = df.sort_values("importance", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    return df
