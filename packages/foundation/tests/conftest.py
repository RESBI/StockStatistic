"""Pytest 配置 — 让 tests 能 import foundation 包。"""
import sys
import os

# 添加 packages 路径作为 fallback（即使没 pip install -e 也能跑）
_here = os.path.dirname(os.path.abspath(__file__))
_foundation_path = os.path.normpath(os.path.join(_here, "..", "..", "packages", "foundation"))
if _foundation_path not in sys.path:
    sys.path.insert(0, _foundation_path)
