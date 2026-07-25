"""CloudpickleCodec — 策略闭包编码。"""
from __future__ import annotations

from typing import Any


class CloudpickleCodec:
    name = "cloudpickle"
    media_type = "application/vnd.python.cloudpickle"

    def encode(self, data: Any) -> bytes:
        try:
            import cloudpickle
        except ImportError as e:
            raise ImportError(
                "CloudpickleCodec requires 'cloudpickle'. "
                "Install with: pip install stockstat-foundation[cloudpickle]"
            ) from e
        return cloudpickle.dumps(data)

    def decode(self, raw: bytes) -> Any:
        try:
            import cloudpickle
        except ImportError as e:
            raise ImportError(
                "CloudpickleCodec requires 'cloudpickle'. "
                "Install with: pip install stockstat-foundation[cloudpickle]"
            ) from e
        return cloudpickle.loads(raw)


def cloudpickle_dumps(data: Any) -> str:
    """便捷函数 — 返回 base64 编码的 cloudpickle 字符串（用于 strategy_ref）。"""
    import base64
    return base64.b64encode(CloudpickleCodec().encode(data)).decode("ascii")


def cloudpickle_loads(ref: str) -> Any:
    """便捷函数 — 从 'cloudpickle:base64...' 或纯 base64 解码。"""
    import base64
    if ref.startswith("cloudpickle:"):
        ref = ref[len("cloudpickle:"):]
    return CloudpickleCodec().decode(base64.b64decode(ref))


__all__ = ["CloudpickleCodec", "cloudpickle_dumps", "cloudpickle_loads"]
