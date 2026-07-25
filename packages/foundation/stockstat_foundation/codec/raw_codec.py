"""RawCodec — 二进制透传。"""
from __future__ import annotations

from typing import Any


class RawCodec:
    name = "raw"
    media_type = "application/octet-stream"

    def encode(self, data: Any) -> bytes:
        if isinstance(data, str):
            return data.encode("utf-8")
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        raise TypeError(f"RawCodec cannot encode {type(data).__name__}")

    def decode(self, raw: bytes) -> Any:
        return bytes(raw)


__all__ = ["RawCodec"]
