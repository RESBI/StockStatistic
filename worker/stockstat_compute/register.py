"""Hardware detection — V2 §12.13.2 Worker registration payload.

Detects CPU, memory, GPU, disk, OS, and Python version.
Requires ``psutil`` (included in stockstat-compute dependencies).
"""
from __future__ import annotations

import platform


def detect_hardware() -> dict:
    """Detect local hardware configuration."""
    import psutil

    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu": {
            "model": platform.processor() or "unknown",
            "cores_physical": psutil.cpu_count(logical=False) or 1,
            "cores_logical": psutil.cpu_count(logical=True) or 1,
            "threads": psutil.cpu_count(logical=True) or 1,
            "freq_mhz": int(cpu_freq.current) if cpu_freq else 0,
        },
        "memory": {
            "total_gb": round(mem.total / 1024**3, 1),
            "available_gb": round(mem.available / 1024**3, 1),
        },
        "gpu": {"devices": _detect_gpu()},
        "disk": {
            "total_gb": round(disk.total / 1024**3, 1),
            "available_gb": round(disk.free / 1024**3, 1),
        },
        "os": platform.platform(),
        "python_version": platform.python_version(),
    }


def get_current_load() -> dict:
    """Get current system load for heartbeat."""
    import psutil
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    gpu_percent, gpu_mem = _get_gpu_load()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_used_gb": round(mem.used / 1024**3, 1),
        "memory_available_gb": round(mem.available / 1024**3, 1),
        "gpu_percent": gpu_percent,
        "gpu_memory_used_gb": gpu_mem,
        "disk_available_gb": round(disk.free / 1024**3, 1),
    }


def _detect_gpu() -> list:
    """Detect NVIDIA GPUs via nvidia-smi or pynvml."""
    try:
        import pynvml
        pynvml.nvmlInit()
        devices = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            devices.append({
                "model": name,
                "vram_gb": round(pynvml.nvmlDeviceGetMemoryInfo(handle).total / 1024**3, 1),
                "cuda_version": "unknown",
            })
        pynvml.nvmlShutdown()
        return devices
    except Exception:
        return []


def _get_gpu_load():
    """Get GPU utilization percentages."""
    try:
        import pynvml
        pynvml.nvmlInit()
        percents = []
        mem_used = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            percents.append(float(util.gpu))
            mem_used.append(round(mem.used / 1024**3, 1))
        pynvml.nvmlShutdown()
        return percents, mem_used
    except Exception:
        return [], []
