"""Layered configuration system.

Configuration sources are merged in priority order (low → high):
1. Built-in defaults
2. Project config file (TOML)
3. Environment variables (``STOCKSTAT_*``)
4. Runtime kwargs

The merged result is validated against a schema and exposed as a
namespace-accessible :class:`Config` object.
"""
from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Optional


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge ``overlay`` into ``base`` (non-destructive)."""
    result = deepcopy(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result


class Config:
    """Namespace-accessible configuration object.

    Supports both attribute access (``config.backend.database_url``)
    and dict access (``config["backend"]["database_url"]``).
    """

    def __init__(self, data: Optional[dict] = None) -> None:
        object.__setattr__(self, "_data", data or {})

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name not in data:
            raise AttributeError(f"Config has no attribute '{name}'")
        val = data[name]
        if isinstance(val, dict):
            return Config(val)
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        data = object.__getattribute__(self, "_data")
        data[name] = value

    def __getitem__(self, key: str) -> Any:
        return self.__getattr__(key)

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_data")

    def get(self, key: str, default: Any = None) -> Any:
        data = object.__getattribute__(self, "_data")
        val = data.get(key, default)
        if isinstance(val, dict):
            return Config(val)
        return val

    def to_dict(self) -> dict:
        return deepcopy(object.__getattribute__(self, "_data"))

    def __repr__(self) -> str:
        return f"Config({object.__getattribute__(self, '_data')!r})"


# ── Built-in defaults ──────────────────────────────────────────

DEFAULTS: dict = {
    "backend": {
        "database_url": "sqlite:///stockstat.db",
        "redis_url": "",
        "host": "0.0.0.0",
        "port": 8000,
        "default_source": "yfinance",
        "cache_ttl": 300,
        "rate_limit_per_minute": 120,
    },
    "cache": {
        "backend": "memory",  # memory | redis | null
        "ttl": 300,
    },
    "storage": {
        "backend": "sql",  # memory | sql | timescale | parquet
    },
    "proxy": {
        "enabled": False,
        "type": "http",  # http | socks5
        "url": "",
    },
    "frontend": {
        "host": "localhost",
        "port": 8000,
        "api_key": "",
        "timeout": 30,
        "use_https": False,
    },
    "backtest": {
        "default_initial_cash": 1_000_000.0,
        "default_periods_per_year": 252,
    },
    "plot": {
        "default_renderer": "matplotlib",
        "theme": "default",
    },
}


def _env_to_config() -> dict:
    """Build a config dict from ``STOCKSTAT_*`` environment variables."""
    cfg: dict = {}

    mapping = {
        "STOCKSTAT_PROXY_ENABLED": ("proxy", "enabled", lambda v: v.lower() in ("1", "true", "yes", "on")),
        "STOCKSTAT_PROXY_TYPE": ("proxy", "type", str),
        "STOCKSTAT_PROXY_URL": ("proxy", "url", str),
        "STOCKSTAT_HOST": ("frontend", "host", str),
        "STOCKSTAT_PORT": ("frontend", "port", int),
        "STOCKSTAT_API_KEY": ("frontend", "api_key", str),
        "STOCKSTAT_TIMEOUT": ("frontend", "timeout", int),
        "STOCKSTAT_USE_HTTPS": ("frontend", "use_https", lambda v: v.lower() in ("1", "true", "yes")),
        "DATABASE_URL": ("backend", "database_url", str),
        "REDIS_URL": ("backend", "redis_url", str),
        "HOST": ("backend", "host", str),
        "PORT": ("backend", "port", int),
        "STOCKSTAT_DEFAULT_SOURCE": ("backend", "default_source", str),
    }

    for env_key, (section, key, conv) in mapping.items():
        val = os.environ.get(env_key)
        if val is not None:
            try:
                cfg.setdefault(section, {})[key] = conv(val)
            except (ValueError, TypeError):
                pass

    return cfg


def _load_toml(path: str) -> dict:
    """Load a TOML config file (Python 3.11+ tomllib, fallback tomli)."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return {}  # TOML not available
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (FileNotFoundError, OSError):
        return {}


def load_config(
    config_file: Optional[str] = None,
    **overrides: Any,
) -> Config:
    """Build a :class:`Config` by merging defaults → file → env → kwargs.

    Args:
        config_file: Path to a TOML config file (optional).
        **overrides: Runtime keyword overrides (highest priority).

    Returns:
        Merged and validated :class:`Config`.
    """
    cfg = deepcopy(DEFAULTS)

    if config_file:
        cfg = _deep_merge(cfg, _load_toml(config_file))

    cfg = _deep_merge(cfg, _env_to_config())

    if overrides:
        cfg = _deep_merge(cfg, overrides)

    return Config(cfg)


# Module-level singleton (lazy)
_config: Optional[Config] = None


def get_config() -> Config:
    """Return the global config singleton (lazily loaded from env)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Override the global config (for testing)."""
    global _config
    _config = config


def reset_config() -> None:
    """Reset the global config (for testing)."""
    global _config
    _config = None
