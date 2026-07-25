"""Pytest 配置。"""
import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
for pkg in ["foundation", "dispatcher"]:
    p = os.path.normpath(os.path.join(_here, "..", "..", "packages", pkg))
    if p not in sys.path:
        sys.path.insert(0, p)
