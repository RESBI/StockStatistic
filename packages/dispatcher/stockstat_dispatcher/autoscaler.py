"""Autoscaler 指标（已在 core.py 实现，此处保留模块）。"""
from __future__ import annotations


def get_autoscaler_metrics(dispatcher) -> dict:
    """获取 Autoscaler 指标。"""
    return dispatcher.autoscaler_metrics()


__all__ = ["get_autoscaler_metrics"]
