"""ml_predict handler — 机器学习预测。"""
from __future__ import annotations
import base64
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec, CloudpickleCodec
from .._base import register


@register("ml_predict")
def handle_ml_predict(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    model_ref = cs.params.get("model_ref")
    if not model_ref or not model_ref.startswith("cloudpickle:"):
        raise ValueError("params.model_ref (cloudpickle:base64...) required")
    model = CloudpickleCodec().decode(base64.b64decode(model_ref[len("cloudpickle:"):]))
    X = np.asarray(data if data is not None else cs.params.get("X"), dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    predictions = model.predict(X)
    return {"predictions": predictions.tolist()}
