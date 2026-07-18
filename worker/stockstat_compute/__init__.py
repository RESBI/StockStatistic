"""stockstat-compute — V3 Worker package.

A Worker is a process that:
1. Registers with a Dispatcher (hardware info + capabilities)
2. Polls for task assignments
3. Executes tasks using stockstat's compute core
4. Posts results back to the Dispatcher
5. Sends periodic heartbeats

Usage:
    stockstat-compute worker --dispatcher-url http://localhost:8000
"""
from .worker import Worker
from .executor import TaskExecutor

__version__ = "3.0.0"
__all__ = ["Worker", "TaskExecutor"]
