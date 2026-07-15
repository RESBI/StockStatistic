from __future__ import annotations

from typing import Callable, Any

_REGISTRY: dict[str, dict] = {}


def indicator(name: str, category: str = "custom"):
    def decorator(func: Callable) -> Callable:
        _REGISTRY[name] = {"func": func, "category": category, "name": name}
        return func
    return decorator


def get_indicator(name: str) -> dict | None:
    return _REGISTRY.get(name)


def list_indicators() -> list[dict]:
    return [{"name": v["name"], "category": v["category"]} for v in _REGISTRY.values()]


def register(name: str, func: Callable, category: str = "custom"):
    _REGISTRY[name] = {"func": func, "category": category, "name": name}


def call_indicator(name: str, **kwargs) -> Any:
    entry = _REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"Indicator '{name}' not registered")
    return entry["func"](**kwargs)
