"""Tier 2 — 经典统计检验 handlers。"""
from __future__ import annotations

from .correlation import handle_correlation
from .hypothesis import handle_hypothesis_test
from .bootstrap import handle_bootstrap
from .permutation import handle_permutation_test
from .chow import handle_chow_test
from .survival import handle_survival_analysis
from .ecdf import handle_ecdf
from .multiple_testing import handle_multiple_testing

__all__ = [
    "handle_correlation", "handle_hypothesis_test", "handle_bootstrap",
    "handle_permutation_test", "handle_chow_test", "handle_survival_analysis",
    "handle_ecdf", "handle_multiple_testing",
]
