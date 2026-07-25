"""Pytest configuration shared across V3 test modules.

Adds the worker/ and backend/ package roots to sys.path so that
``stockstat_compute`` and ``stockstat_backend`` can be imported
without ``pip install -e``.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_BACKEND = os.path.join(_PROJECT_ROOT, "backend")
_WORKER = os.path.join(_PROJECT_ROOT, "worker")

for path in (_BACKEND, _WORKER):
    if path not in sys.path:
        sys.path.insert(0, path)
