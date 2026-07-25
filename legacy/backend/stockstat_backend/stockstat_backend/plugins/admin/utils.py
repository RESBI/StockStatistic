"""Utility functions for admin plugin."""
from __future__ import annotations

import os


def mask_db_url(url: str) -> str:
    """Mask password in database URL for display."""
    if "@" in url and "://" in url:
        scheme = url.split("://")[0]
        rest = url.split("://", 1)[1]
        if ":" in rest.split("@")[0]:
            user = rest.split(":")[0]
            return f"{scheme}://{user}:***@{rest.split('@', 1)[1]}"
    return url


def get_disk_usage(path: str) -> tuple[int, int, int]:
    """Get (total, free, used) bytes for the given path. Cross-platform."""
    if hasattr(os, "statvfs"):
        # Unix/Linux/macOS
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        return total, free, used
    else:
        # Windows
        import ctypes
        free_bytes = ctypes.c_ulonglong(0)
        total_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(path),
            ctypes.pointer(free_bytes),
            ctypes.pointer(total_bytes),
            None,
        )
        total = total_bytes.value
        free = free_bytes.value
        used = total - free
        return total, free, used
