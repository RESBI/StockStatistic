"""DSL engine with auto-reflection from the PluginRegistry.

v2.0 replaces v1.7's manually-maintained ``_BUILTIN_FUNCS`` dict with
automatic reflection: the DSL engine reads all registered indicator
plugins from the PluginRegistry and exposes them as DSL functions.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

# Import AST node types at module level (used by _eval_expr)
from ...dsl.ast_nodes import (
    Field, Number, StringLit, NameRef, BinOp, FuncCall,
    SelectExpr, Source, Query,
)


def build_dsl_functions_from_registry(registry: Any) -> dict[str, Callable]:
    """Build a DSL function table from all registered indicators.

    Each indicator plugin's ``func`` is wrapped to accept both
    positional and keyword arguments (DSL supports both).
    """
    funcs: dict[str, Callable] = {}
    for item in registry.list("indicators"):
        plugin = item["plugin"]
        name = item["name"]
        funcs[name] = plugin.func
    return funcs


class DslEngine:
    """v2.0 DSL engine with registry-based function discovery.

    Delegates parsing to the v1.7 lark-based parser, but sources
    its function table from the PluginRegistry instead of a hardcoded
    dict.
    """

    def __init__(self, registry: Any, client: Any = None) -> None:
        self._registry = registry
        self._client = client
        self._functions = build_dsl_functions_from_registry(registry)

    def refresh(self) -> None:
        """Re-build the function table from the registry."""
        self._functions = build_dsl_functions_from_registry(self._registry)

    def list_functions(self) -> list[str]:
        return list(self._functions.keys())

    def get_function(self, name: str) -> Optional[Callable]:
        return self._functions.get(name)

    def eval(self, dsl_string: str) -> pd.DataFrame | dict:
        """Evaluate a DSL query string.

        Uses the v1.7 parser + evaluator, but with the registry-sourced
        function table injected.
        """
        from ...dsl.parser import parse
        query = parse(dsl_string)
        return self._eval_query(query)

    def _eval_query(self, query: Query) -> pd.DataFrame | dict:
        df = self._load_source(query.source)
        if query.condition:
            mask = self._eval_expr(query.condition, df)
            df = df[mask]
        if query.limit:
            df = df.tail(query.limit)

        results = {}
        for sel in query.select_list:
            val = self._eval_expr(sel.expr, df)
            col_name = sel.alias or self._expr_name(sel.expr)
            results[col_name] = val

        out = pd.DataFrame(results)
        out.index = df.index
        return out

    def _load_source(self, source: Source) -> pd.DataFrame:
        if self._client is None:
            raise RuntimeError("No client connected for data loading")
        return self._client.ohlcv(
            symbol=source.symbol, start=source.start,
            end=source.end, timeframe=source.timeframe,
        )

    def _eval_expr(self, expr, df: pd.DataFrame):
        if isinstance(expr, Field):
            if expr.name in ("open", "high", "low", "close", "volume"):
                return df[expr.name]
            elif expr.name == "returns":
                from ...indicators.statistics import returns
                return returns(df["close"])
            elif expr.name == "log_returns":
                from ...indicators.statistics import log_returns
                return log_returns(df["close"])
            raise KeyError(f"Unknown field: {expr.name}")

        if isinstance(expr, Number):
            return int(expr.value) if expr.value == int(expr.value) else expr.value

        if isinstance(expr, StringLit):
            return expr.value

        if isinstance(expr, NameRef):
            return expr.name

        if isinstance(expr, BinOp):
            left = self._eval_expr(expr.left, df)
            right = self._eval_expr(expr.right, df)
            ops = {"+": lambda a, b: a + b, "-": lambda a, b: a - b,
                   "*": lambda a, b: a * b, "/": lambda a, b: a / b,
                   ">": lambda a, b: a > b, "<": lambda a, b: a < b,
                   ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
                   "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
            return ops[expr.op](left, right)

        if isinstance(expr, FuncCall):
            args = [self._eval_expr(a, df) for a in expr.args]
            kwargs = {k: self._eval_expr(v, df) for k, v in expr.kwargs.items()}
            if expr.name in self._functions:
                return self._functions[expr.name](*args, **kwargs)
            raise KeyError(f"Unknown function: {expr.name}")

        raise TypeError(f"Cannot evaluate: {type(expr)}")

    def _expr_name(self, expr) -> str:
        if isinstance(expr, Field):
            return expr.name
        if isinstance(expr, FuncCall):
            return f"{expr.name}_result"
        if isinstance(expr, BinOp):
            return f"{self._expr_name(expr.left)}_{expr.op}_{self._expr_name(expr.right)}"
        return str(expr)
