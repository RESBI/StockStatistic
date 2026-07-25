"""Config — 全局配置（环境变量 + 配置文件合并）。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_str(name: str, default: Optional[str]) -> Optional[str]:
    v = os.environ.get(name)
    return v if v else default


@dataclass
class Config:
    """全局配置 — 环境变量 + 配置文件合并。"""
    # Invocation
    client_mode: str = "online"
    default_backend: str = "local"

    # Dispatcher
    dispatcher_url: Optional[str] = None
    dispatcher_enabled: bool = False
    dispatcher_queue: str = "memory"
    dispatcher_cache_dir: Optional[str] = None
    dispatcher_cache_size_mb: int = 512

    # Storage
    storage_url: Optional[str] = None
    database_url: str = "sqlite:///stockstat.db"
    admin_enabled: bool = False
    scheduler_enabled: bool = False

    # Compute
    worker_concurrency: Optional[int] = None
    worker_alias: Optional[str] = None
    worker_preemptable: bool = False

    # Transport
    transport_timeout: int = 30
    redis_url: Optional[str] = None

    # Protocol
    protocol_version: str = "1.0"
    default_encoding: str = "json"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            client_mode=_env_str("STOCKSTAT_CLIENT_MODE", "online") or "online",
            default_backend=_env_str("STOCKSTAT_DEFAULT_BACKEND", "local") or "local",
            dispatcher_url=_env_str("STOCKSTAT_DISPATCHER_URL", None),
            dispatcher_enabled=_env_bool("STOCKSTAT_DISPATCHER_ENABLED", False),
            dispatcher_queue=_env_str("STOCKSTAT_DISPATCHER_QUEUE", "memory") or "memory",
            dispatcher_cache_dir=_env_str("STOCKSTAT_DISPATCHER_CACHE_DIR", None),
            dispatcher_cache_size_mb=_env_int("STOCKSTAT_DISPATCHER_CACHE_SIZE_MB", 512),
            storage_url=_env_str("STOCKSTAT_STORAGE_URL", None),
            database_url=_env_str("STOCKSTAT_DATABASE_URL", "sqlite:///stockstat.db") or "sqlite:///stockstat.db",
            admin_enabled=_env_bool("STOCKSTAT_ADMIN_ENABLED", False),
            scheduler_enabled=_env_bool("STOCKSTAT_SCHEDULER_ENABLED", False),
            worker_concurrency=_env_int("STOCKSTAT_WORKER_CONCURRENCY", 0) or None,
            worker_alias=_env_str("STOCKSTAT_WORKER_ALIAS", None),
            worker_preemptable=_env_bool("STOCKSTAT_WORKER_PREEMPTABLE", False),
            transport_timeout=_env_int("STOCKSTAT_TRANSPORT_TIMEOUT", 30),
            redis_url=_env_str("STOCKSTAT_REDIS_URL", None),
            protocol_version=_env_str("STOCKSTAT_PROTOCOL_VERSION", "1.0") or "1.0",
            default_encoding=_env_str("STOCKSTAT_DEFAULT_ENCODING", "json") or "json",
        )

    @classmethod
    def from_file(cls, path: str) -> "Config":
        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    raise ImportError(
                        "TOML config files require Python 3.11+ or 'tomli' package"
                    )
            with open(path, "rb") as fb:
                data = tomllib.load(fb)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self, **overrides) -> "Config":
        d = asdict(self)
        d.update(overrides)
        return Config(**d)


__all__ = ["Config"]
