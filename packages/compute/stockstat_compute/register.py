"""register — 硬件检测（psutil）。"""
from __future__ import annotations

import platform
from typing import Optional


def detect_hardware() -> dict:
    """检测 CPU/mem/GPU/disk/OS/Python。"""
    try:
        import psutil
    except ImportError:
        return {
            "cpu": {"model": platform.processor(), "cores_logical": None},
            "memory": {},
            "gpu": {"devices": []},
            "disk": {},
            "os": platform.platform(),
            "python_version": platform.python_version(),
        }

    cpu = {
        "model": platform.processor(),
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(logical=True),
        "threads": psutil.cpu_count(logical=True),
        "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
    }
    mem = psutil.virtual_memory()
    memory = {
        "total_gb": mem.total / (1024 ** 3),
        "available_gb": mem.available / (1024 ** 3),
    }
    try:
        disk = psutil.disk_usage("/")
        disk_info = {
            "total_gb": disk.total / (1024 ** 3),
            "available_gb": disk.free / (1024 ** 3),
        }
    except Exception:
        disk_info = {}
    return {
        "cpu": cpu,
        "memory": memory,
        "gpu": {"devices": _detect_gpu()},
        "disk": disk_info,
        "os": platform.platform(),
        "python_version": platform.python_version(),
    }


def get_current_load() -> dict:
    """获取当前负载（心跳用）。"""
    try:
        import psutil
    except ImportError:
        return {}
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_used_gb": mem.used / (1024 ** 3),
        "memory_available_gb": mem.available / (1024 ** 3),
        "gpu_percent": [],
        "gpu_memory_used_gb": [],
    }


def _detect_gpu() -> list:
    """检测 NVIDIA GPU（可选）。"""
    try:
        import pynvml
        pynvml.nvmlInit()
        devices = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            devices.append({"model": name, "vram_gb": 0})
        pynvml.nvmlShutdown()
        return devices
    except Exception:
        return []


__all__ = ["detect_hardware", "get_current_load"]
