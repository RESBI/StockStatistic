"""Pytest 配置 — 让 tests 能 import V3.1 包。"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["foundation", "storage", "compute", "invocation", "dispatcher"]:
    p = os.path.join(_ROOT, "packages", pkg)
    if p not in sys.path:
        sys.path.insert(0, p)
