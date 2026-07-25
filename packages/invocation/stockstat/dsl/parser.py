"""DSL Parser — 简单的策略表达式解析器。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class CallNode:
    """函数调用节点。"""
    name: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)


@dataclass
class NumberNode:
    value: float


@dataclass
class StringNode:
    value: str


@dataclass
class IdentifierNode:
    name: str


class DslParser:
    """简单 DSL 解析器 — 支持 func(arg1, arg2, key=value) 形式。"""

    def parse(self, expression: str) -> CallNode:
        expression = expression.strip()
        if not expression:
            raise ValueError("Empty expression")
        return self._parse_call(expression)

    def _parse_call(self, s: str) -> CallNode:
        s = s.strip()
        # 匹配 func_name(args)
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*$", s, re.DOTALL)
        if not m:
            raise ValueError(f"Invalid expression: {s}")
        name = m.group(1)
        args_str = m.group(2).strip()
        args, kwargs = self._parse_args(args_str)
        return CallNode(name=name, args=args, kwargs=kwargs)

    def _parse_args(self, s: str) -> tuple:
        if not s:
            return [], {}
        args = []
        kwargs = {}
        # 简单分割（不处理嵌套括号）
        parts = self._split_args(s)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 嵌套调用（含括号）优先处理，避免误判其中的 =
            if "(" in part:
                args.append(self._parse_value(part))
                continue
            # 列表/字典
            if part.startswith("[") or part.startswith("{"):
                args.append(self._parse_value(part))
                continue
            # key=value
            if "=" in part:
                key, _, value = part.partition("=")
                kwargs[key.strip()] = self._parse_value(value.strip())
            else:
                args.append(self._parse_value(part))
        return args, kwargs

    def _split_args(self, s: str) -> list:
        """按逗号分割，处理嵌套括号。"""
        parts = []
        depth = 0
        current = ""
        for c in s:
            if c in "([{":
                depth += 1
                current += c
            elif c in ")]}":
                depth -= 1
                current += c
            elif c == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += c
        if current.strip():
            parts.append(current)
        return parts

    def _parse_value(self, s: str) -> Any:
        s = s.strip()
        # 数字
        try:
            return NumberNode(float(s))
        except ValueError:
            pass
        # 字符串
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return StringNode(s[1:-1])
        # 标识符
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", s):
            return IdentifierNode(s)
        # 嵌套调用
        if "(" in s:
            return self._parse_call(s)
        # 列表
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].strip()
            if not inner:
                return []
            items = self._split_args(inner)
            return [self._parse_value(i.strip()) for i in items]
        # 默认返回字符串
        return StringNode(s)


__all__ = ["DslParser", "CallNode", "NumberNode", "StringNode", "IdentifierNode"]
