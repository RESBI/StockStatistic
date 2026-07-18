from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_HTTP_PROXY = "http://127.0.0.1:8889"
DEFAULT_SOCKS5_PROXY = "socks5://127.0.0.1:1089"


@dataclass
class ProxyConfig:
    enabled: bool = False
    url: str = ""
    proxy_type: str = "http"  # "http" | "socks5"

    @classmethod
    def from_env(cls) -> "ProxyConfig":
        enabled = os.environ.get("STOCKSTAT_PROXY_ENABLED", "").lower() in ("1", "true", "yes", "on")
        proxy_type = os.environ.get("STOCKSTAT_PROXY_TYPE", "http").lower()
        url = os.environ.get("STOCKSTAT_PROXY_URL", "")

        if enabled and not url:
            url = DEFAULT_HTTP_PROXY if proxy_type == "http" else DEFAULT_SOCKS5_PROXY

        return cls(enabled=enabled, url=url, proxy_type=proxy_type)

    @property
    def proxies(self) -> dict | None:
        if not self.enabled:
            return None
        return {"http": self.url, "https": self.url}

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "url": self.url,
            "proxy_type": self.proxy_type,
        }


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "sqlite:///stockstat.db"
        )
    )
    redis_url: str = field(
        default_factory=lambda: os.environ.get("REDIS_URL", "")
    )
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8000")))
    cache_ttl: int = 300
    rate_limit_per_minute: int = 120
    default_source: str = field(
        default_factory=lambda: os.environ.get("STOCKSTAT_DEFAULT_SOURCE", "yfinance")
    )
    proxy: ProxyConfig = field(default_factory=ProxyConfig.from_env)
    admin_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "STOCKSTAT_ADMIN_ENABLED", "true"
        ).lower() in ("1", "true", "yes", "on")
    )
    dispatcher_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "STOCKSTAT_DISPATCHER_ENABLED", "false"
        ).lower() in ("1", "true", "yes", "on")
    )
    dispatcher_queue_backend: str = field(
        default_factory=lambda: os.environ.get("STOCKSTAT_DISPATCHER_QUEUE", "memory")
    )
    dispatcher_cache_size_mb: int = field(
        default_factory=lambda: int(os.environ.get("STOCKSTAT_DISPATCHER_CACHE_MB", "512"))
    )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls()

    def reload(self) -> "Settings":
        global settings
        settings = Settings.from_env()
        return settings


settings = Settings.from_env()
