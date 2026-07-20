from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np

from .ast_nodes import (
    Field, Number, StringLit, NameRef, BinOp, FuncCall,
    SelectExpr, Source, Query,
)
from .parser import parse
from ..indicators import trend, oscillator, volatility, statistics


_BUILTIN_FUNCS = {
    "ma": lambda x, window=20: trend.ma(x, window),
    "ema": lambda x, window=12: trend.ema(x, window),
    "macd": lambda x, fast=12, slow=26, signal=9: trend.macd(x, fast, slow, signal),
    "rsi": lambda x, window=14: oscillator.rsi(x, window),
    "std": lambda x, window=20: volatility.std(x, window),
    "atr": lambda high, low, close, window=14: volatility.atr(high, low, close, window),
    "bollinger": lambda x, window=20, k=2.0: volatility.bollinger(x, window, k),
    "corr": lambda x, y: statistics.corr(x, y),
    "returns": lambda x: statistics.returns(x),
    "log_returns": lambda x: statistics.log_returns(x),
    "max": lambda x: x.max() if hasattr(x, "max") else max(x),
    "min": lambda x: x.min() if hasattr(x, "min") else min(x),
    "mean": lambda x: x.mean() if hasattr(x, "mean") else sum(x) / len(x),
    "sum": lambda x: x.sum() if hasattr(x, "sum") else sum(x),
    "count": lambda x: len(x),
}


class Evaluator:
    def __init__(self, client=None):
        self._client = client

    def eval(self, dsl_string: str) -> pd.DataFrame | dict:
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
            symbol=source.symbol,
            start=source.start,
            end=source.end,
            timeframe=source.timeframe,
        )

    def _eval_expr(self, expr, df: pd.DataFrame):
        if isinstance(expr, Field):
            if expr.name in ("open", "high", "low", "close", "volume"):
                return df[expr.name]
            elif expr.name == "returns":
                return statistics.returns(df["close"])
            elif expr.name == "log_returns":
                return statistics.log_returns(df["close"])
            raise KeyError(f"Unknown field: {expr.name}")

        if isinstance(expr, Number):
            if expr.value == int(expr.value):
                return int(expr.value)
            return expr.value

        if isinstance(expr, StringLit):
            return expr.value

        if isinstance(expr, NameRef):
            return expr.name

        if isinstance(expr, BinOp):
            left = self._eval_expr(expr.left, df)
            right = self._eval_expr(expr.right, df)
            if expr.op == "+":
                return left + right
            elif expr.op == "-":
                return left - right
            elif expr.op == "*":
                return left * right
            elif expr.op == "/":
                return left / right
            elif expr.op == ">":
                return left > right
            elif expr.op == "<":
                return left < right
            elif expr.op == ">=":
                return left >= right
            elif expr.op == "<=":
                return left <= right
            elif expr.op == "==":
                return left == right
            elif expr.op == "!=":
                return left != right

        if isinstance(expr, FuncCall):
            args = [self._eval_expr(a, df) for a in expr.args]
            kwargs = {k: self._eval_expr(v, df) for k, v in expr.kwargs.items()}

            if expr.name in _BUILTIN_FUNCS:
                return _BUILTIN_FUNCS[expr.name](*args, **kwargs)

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


def execute(dsl_string: str, client=None) -> pd.DataFrame | dict:
    evaluator = Evaluator(client=client)
    return evaluator.eval(dsl_string)
