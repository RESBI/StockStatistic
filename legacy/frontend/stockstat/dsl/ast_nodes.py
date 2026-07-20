from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Field:
    name: str


@dataclass
class Number:
    value: float


@dataclass
class StringLit:
    value: str


@dataclass
class NameRef:
    name: str


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass
class FuncCall:
    name: str
    args: list
    kwargs: dict


@dataclass
class SelectExpr:
    expr: Any
    alias: Optional[str] = None


@dataclass
class Source:
    symbol: str
    timeframe: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass
class Query:
    select_list: list
    source: Source
    condition: Optional[Any] = None
    limit: Optional[int] = None
