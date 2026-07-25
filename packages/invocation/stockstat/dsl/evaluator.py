"""DSL Evaluator — 求值 DSL AST。"""
from __future__ import annotations

from typing import Any, Optional

from .parser import DslParser, CallNode, NumberNode, StringNode, IdentifierNode


class DslEngine:
    """策略 DSL 引擎。

    用法：
        result = client.run_dsl(
            "backtest(buy_and_hold, initial_cash=10000)",
            data=btc_data,
        )
    """

    def __init__(self, client):
        self._client = client
        self._parser = DslParser()

    def evaluate(self, expression: str, data=None, **kwargs) -> Any:
        ast = self._parser.parse(expression)
        return self._eval(ast, data=data, **kwargs)

    def compile_strategy(self, expression: str) -> str:
        """编译 DSL 为 cloudpickle 策略引用。"""
        from stockstat_foundation import cloudpickle_dumps

        def strategy(i, bar, d, ctx):
            # 简化：DSL 编译的策略直接返回 None（占位）
            return None

        # 根据 DSL 构建真正的策略
        ast = self._parser.parse(expression)
        if ast.name == "buy_and_hold":
            def strategy(i, bar, d, ctx):
                if i == 0:
                    from stockstat_compute import Signal
                    return Signal(timestamp=bar["timestamp"], symbol="DSL", side="buy")
                return None
        elif ast.name == "ma_cross":
            short = self._eval(ast.kwargs.get("short", NumberNode(5)))
            long = self._eval(ast.kwargs.get("long", NumberNode(20)))
            def strategy(i, bar, d, ctx, _short=short, _long=long):
                if i < _long:
                    return None
                s = d["close"].iloc[i - _short:i + 1].mean()
                l = d["close"].iloc[i - _long:i + 1].mean()
                ps = d["close"].iloc[i - _short - 1:i].mean()
                pl = d["close"].iloc[i - _long - 1:i].mean()
                from stockstat_compute import Signal
                if ps <= pl and s > l:
                    return Signal(timestamp=bar["timestamp"], symbol="DSL", side="buy")
                if ps >= pl and s < l:
                    return Signal(timestamp=bar["timestamp"], symbol="DSL", side="sell")
                return None
        return f"cloudpickle:{cloudpickle_dumps(strategy)}"

    def _eval(self, node, data=None, **kwargs) -> Any:
        if isinstance(node, NumberNode):
            return node.value
        if isinstance(node, StringNode):
            return node.value
        if isinstance(node, IdentifierNode):
            # 查找上下文变量
            if node.name == "data":
                return data
            return node.name
        if isinstance(node, CallNode):
            return self._eval_call(node, data=data, **kwargs)
        if isinstance(node, list):
            return [self._eval(n) for n in node]
        return node

    def _eval_call(self, node: CallNode, data=None, **kwargs) -> Any:
        name = node.name
        args = [self._eval(a) for a in node.args]
        kw = {k: self._eval(v) for k, v in node.kwargs.items()}

        if name == "backtest":
            strat_ref = self.compile_strategy(node.args[0] if node.args else "buy_and_hold()")
            return self._client.backtest(data=data, strategy=_decode_strategy(strat_ref), **kw)
        if name == "indicator":
            indicator_name = args[0] if args else kw.get("name", "ma")
            return self._client.compute._dispatch_indicator(indicator_name, data, **kw)
        if name == "buy_and_hold":
            return "buy_and_hold"
        if name == "ma_cross":
            return ("ma_cross", args, kw)
        # 未知函数：尝试作为 indicator 调用
        return self._client.compute._dispatch_indicator(name, data, **kw)


def _decode_strategy(ref: str):
    if ref.startswith("cloudpickle:"):
        from stockstat_foundation import cloudpickle_loads
        return cloudpickle_loads(ref)
    return ref


__all__ = ["DslEngine"]
