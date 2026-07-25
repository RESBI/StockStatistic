"""classification_metrics handler — 分类评估。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("classification_metrics")
def handle_classification_metrics(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    average = cs.params.get("average", "weighted")
    y_true = np.asarray(data["y_true"] if isinstance(data, dict) else cs.params.get("y_true"))
    y_pred = np.asarray(data["y_pred"] if isinstance(data, dict) else cs.params.get("y_pred"))
    from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                                  f1_score, roc_auc_score, confusion_matrix)
    result = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average=average, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average=average, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average=average, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }
    try:
        result["roc_auc"] = float(roc_auc_score(y_true, y_pred, multi_class="ovr", average=average))
    except Exception:
        result["roc_auc"] = None
    return result
