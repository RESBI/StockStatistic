from __future__ import annotations

import os
from typing import Optional

from lark import Lark, Transformer, v_args

from .ast_nodes import (
    Field, Number, StringLit, NameRef, BinOp, FuncCall,
    SelectExpr, Source, Query,
)

_FIELDS = {"open", "high", "low", "close", "volume", "returns", "log_returns"}

_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar.lark")


class DSLTransformer(Transformer):
    def start(self, items):
        return items[0]

    def query(self, items):
        select_list = items[0]
        source = items[1]
        condition = None
        limit = None
        for item in items[2:]:
            if isinstance(item, tuple) and item[0] == "condition":
                condition = item[1]
            elif isinstance(item, int):
                limit = item
        return Query(select_list=select_list, source=source, condition=condition, limit=limit)

    def select_list(self, items):
        return list(items)

    def select_expr(self, items):
        expr = items[0]
        alias = None
        if len(items) > 1:
            alias = str(items[1])
        return SelectExpr(expr=expr, alias=alias)

    def source(self, items):
        strings = []
        for it in items:
            if isinstance(it, StringLit):
                strings.append(it.value)
            else:
                strings.append(str(it))
        symbol = strings[0]
        timeframe = strings[1] if len(strings) > 1 else "1d"
        start = strings[2] if len(strings) > 2 else None
        end = strings[3] if len(strings) > 3 else None
        return Source(symbol=symbol, timeframe=timeframe, start=start, end=end)

    def string(self, items):
        if isinstance(items[0], StringLit):
            return items[0].value
        return str(items[0])

    def expr(self, items):
        return items[0]

    def binop(self, items):
        op = str(items[1])
        return BinOp(op=op, left=items[0], right=items[2])

    def func_call(self, items):
        name = str(items[0])
        args = []
        kwargs = {}
        for item in items[1:]:
            if isinstance(item, tuple) and item[0] == "kwarg":
                kwargs[item[1]] = item[2]
            else:
                args.append(item)
        return FuncCall(name=name, args=args, kwargs=kwargs)

    def kwarg(self, items):
        return ("kwarg", str(items[0]), items[1])

    def name_ref(self, items):
        name = str(items[0])
        if name in _FIELDS:
            return Field(name=name)
        return NameRef(name=name)

    def number(self, items):
        return items[0]

    def literal_string(self, items):
        return items[0]

    def condition(self, items):
        return ("condition", BinOp(op=str(items[1]), left=items[0], right=items[2]))

    def NUMBER(self, token):
        return Number(value=float(token))

    def STRING(self, token):
        return StringLit(value=str(token)[1:-1])

    def INT(self, token):
        return int(token)

    def NAME(self, token):
        return str(token)


_parser: Optional[Lark] = None


def get_parser() -> Lark:
    global _parser
    if _parser is None:
        with open(_GRAMMAR_PATH, "r", encoding="utf-8") as f:
            grammar = f.read()
        _parser = Lark(grammar, parser="lalr", transformer=None, start="start")
    return _parser


def parse(dsl_string: str) -> Query:
    parser = get_parser()
    tree = parser.parse(dsl_string)
    transformer = DSLTransformer()
    return transformer.transform(tree)
