"""MsgpackCodec — 高效控制面编码。"""
from __future__ import annotations

from typing import Any


class MsgpackCodec:
    name = "msgpack"
    media_type = "application/msgpack"

    def encode(self, data: Any) -> bytes:
        try:
            import msgpack
        except ImportError as e:
            raise ImportError(
                "MsgpackCodec requires 'msgpack'. "
                "Install with: pip install stockstat-foundation[msgpack]"
            ) from e
        return msgpack.dumps(data, use_bin_type=True)

    def decode(self, raw: bytes) -> Any:
        try:
            import msgpack
        except ImportError as e:
            raise ImportError(
                "MsgpackCodec requires 'msgpack'. "
                "Install with: pip install stockstat-foundation[msgpack]"
            ) from e
        return msgpack.loads(raw, raw=False)


__all__ = ["MsgpackCodec"]
