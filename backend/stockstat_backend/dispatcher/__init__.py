"""V3 Dispatcher — task scheduling, data prefetch, and worker management.

Mounts on a FastAPI app (like AdminPlugin) to provide:
  /dispatch/submit       — Client submits TaskSpec
  /dispatch/status/{id}  — Client queries task status
  /dispatch/result/{id}  — Client fetches task result
  /dispatch/cancel/{id}  — Client cancels task
  /dispatch/assign       — Worker pulls task assignment
  /dispatch/complete     — Worker posts result
  /dispatch/register     — Worker registers on startup
  /dispatch/heartbeat    — Worker sends heartbeat
  /dispatch/cluster      — Client queries cluster topology
"""
from .plugin import DispatcherPlugin
from .core import Dispatcher

__all__ = ["DispatcherPlugin", "Dispatcher"]
