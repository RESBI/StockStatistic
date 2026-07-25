"""JsonCodec — 标准库 JSON。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class JsonCodec:
    name = "json"
    media_type = "application/json"

    def encode(self, data: Any) -> bytes:
        return json.dumps(data, default=_default).encode("utf-8")

    def decode(self, raw: bytes) -> Any:
        if isinstance(raw, str):
            return json.loads(raw)
        return json.loads(raw.decode("utf-8"))


def _default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, (set, frozenset)):
        return list(o)
    if isinstance(o, bytes):
        import base64
        return base64.b64encode(o).decode("ascii")
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)


__all__ = ["JsonCodec"]
