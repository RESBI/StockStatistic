"""ml_train handler — 机器学习训练。"""
from __future__ import annotations
import base64
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec, CloudpickleCodec
from .._base import register


@register("ml_train")
def handle_ml_train(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    model_type = cs.params.get("model_type", "random_forest")
    cv = cs.params.get("cv", 5)
    X = np.asarray(data["X"] if isinstance(data, dict) else cs.params.get("X"), dtype=float)
    y = np.asarray(data["y"] if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    is_classifier = cs.params.get("task", "regression") == "classification"
    if model_type == "random_forest":
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
        hyperparams = cs.params.get("hyperparams", {"n_estimators": 100, "random_state": 42})
        model = (RandomForestClassifier if is_classifier else RandomForestRegressor)(**hyperparams)
    elif model_type == "gbdt":
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
        model = (GradientBoostingClassifier if is_classifier else GradientBoostingRegressor)()
    elif model_type in ("ridge", "lasso", "linear"):
        from sklearn.linear_model import Ridge, Lasso, LinearRegression
        if model_type == "ridge":
            model = Ridge()
        elif model_type == "lasso":
            model = Lasso()
        else:
            model = LinearRegression()
    else:
        raise ValueError(f"Unknown model_type: {model_type}")
    from sklearn.model_selection import cross_val_score
    scores = cross_val_score(model, X, y, cv=min(cv, len(X)))
    model.fit(X, y)
    model_bytes = CloudpickleCodec().encode(model)
    result = {
        "model_ref": f"cloudpickle:{base64.b64encode(model_bytes).decode('ascii')}",
        "cv_scores": scores.tolist(), "cv_mean": float(scores.mean()),
        "cv_std": float(scores.std()), "model_type": model_type,
    }
    if hasattr(model, "feature_importances_"):
        feature_names = cs.params.get("feature_names", list(range(X.shape[1])))
        result["feature_importance"] = dict(zip(feature_names, model.feature_importances_.tolist()))
    return result
