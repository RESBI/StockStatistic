from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    host: str = "localhost"
    port: int = 8000
    api_key: str = ""
    timeout: int = 30
    cache_enabled: bool = True
    use_https: bool = False

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.environ.get("STOCKSTAT_HOST", "localhost"),
            port=int(os.environ.get("STOCKSTAT_PORT", "8000")),
            api_key=os.environ.get("STOCKSTAT_API_KEY", ""),
            timeout=int(os.environ.get("STOCKSTAT_TIMEOUT", "30")),
            use_https=os.environ.get("STOCKSTAT_USE_HTTPS", "").lower() in ("1", "true", "yes"),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
