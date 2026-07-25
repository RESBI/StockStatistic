"""DataSource Protocol + adapter registry。"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class DataSource(Protocol):
    """数据源协议。"""
    name: str

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None): ...


ADAPTERS: dict = {}


def register_adapter(name: str):
    """adapter 注册装饰器。"""
    def decorator(cls):
        ADAPTERS[name] = cls
        return cls
    return decorator


def get_adapter(name: str):
    """获取 adapter 类。"""
    if name not in ADAPTERS:
        raise KeyError(f"Unknown adapter: {name}; available: {list(ADAPTERS.keys())}")
    return ADAPTERS[name]


def list_adapters() -> list:
    return list(ADAPTERS.keys())


__all__ = ["DataSource", "ADAPTERS", "register_adapter", "get_adapter", "list_adapters"]
