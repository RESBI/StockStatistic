"""Envelope 信封 — 所有节点间通信的统一包装。"""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Headers:
    """消息头 — 元数据。"""
    content_type: str = "application/json"
    data_codec: str = "arrow"
    strategy_codec: str = "cloudpickle"
    encoding: str = "json"
    priority: int = 0
    timeout: int = 3600
    trace_id: str = ""
    data_ref: str = ""
    retry_count: int = 0
    protocol_version: str = "1.0"
    accepted_codecs: list = field(default_factory=list)
    accepted_encodings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "content_type": self.content_type,
            "data_codec": self.data_codec,
            "strategy_codec": self.strategy_codec,
            "encoding": self.encoding,
            "priority": self.priority,
            "timeout": self.timeout,
            "trace_id": self.trace_id,
            "data_ref": self.data_ref,
            "retry_count": self.retry_count,
            "protocol_version": self.protocol_version,
            "accepted_codecs": list(self.accepted_codecs),
            "accepted_encodings": list(self.accepted_encodings),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Headers":
        return cls(
            content_type=d.get("content_type", "application/json"),
            data_codec=d.get("data_codec", "arrow"),
            strategy_codec=d.get("strategy_codec", "cloudpickle"),
            encoding=d.get("encoding", "json"),
            priority=int(d.get("priority", 0)),
            timeout=int(d.get("timeout", 3600)),
            trace_id=d.get("trace_id", ""),
            data_ref=d.get("data_ref", ""),
            retry_count=int(d.get("retry_count", 0)),
            protocol_version=d.get("protocol_version", "1.0"),
            accepted_codecs=list(d.get("accepted_codecs", [])),
            accepted_encodings=list(d.get("accepted_encodings", [])),
        )


@dataclass
class Envelope:
    """统一消息信封。"""
    protocol: str = "stockstat-rpc"
    version: str = "1.0"
    type: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    headers: Headers = field(default_factory=Headers)
    payload: Any = None

    def to_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "type": self.type,
            "id": self.id,
            "reply_to": self.reply_to,
            "headers": self.headers.to_dict(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Envelope":
        return cls(
            protocol=d.get("protocol", "stockstat-rpc"),
            version=d.get("version", "1.0"),
            type=d.get("type", ""),
            id=d.get("id") or str(uuid.uuid4()),
            reply_to=d.get("reply_to"),
            headers=Headers.from_dict(d.get("headers", {})),
            payload=d.get("payload"),
        )

    def encode(self) -> bytes:
        """按 headers.encoding 选择序列化方式（json / msgpack）。"""
        d = self.to_dict()
        payload = d.get("payload")
        if isinstance(payload, (bytes, bytearray)):
            d["payload"] = base64.b64encode(payload).decode("ascii")
            d["_payload_b64"] = True
        if self.headers.encoding == "msgpack":
            try:
                import msgpack
            except ImportError as e:
                raise ImportError(
                    "msgpack not installed. Install with: pip install stockstat-foundation[msgpack]"
                ) from e
            return msgpack.dumps(d, use_bin_type=True)
        return json.dumps(d, default=str).encode("utf-8")

    @classmethod
    def decode(cls, raw: bytes) -> "Envelope":
        """自动检测 JSON vs Msgpack。"""
        d: dict
        try:
            d = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                import msgpack
            except ImportError as e:
                raise ImportError(
                    "msgpack not installed but message appears to be msgpack-encoded. "
                    "Install with: pip install stockstat-foundation[msgpack]"
                ) from e
            d = msgpack.loads(raw, raw=False)
        if d.get("_payload_b64") and isinstance(d.get("payload"), str):
            d["payload"] = base64.b64decode(d["payload"])
            d.pop("_payload_b64", None)
        return cls.from_dict(d)

    def reply(self, type: str, payload: Any = None,
              content_type: str = "application/json") -> "Envelope":
        """构建回复信封，reply_to 设为当前信封的 id。"""
        return Envelope(
            type=type,
            reply_to=self.id,
            headers=Headers(
                content_type=content_type,
                trace_id=self.headers.trace_id,
                protocol_version=self.headers.protocol_version,
                encoding=self.headers.encoding,
            ),
            payload=payload,
        )

    def is_reply(self) -> bool:
        return self.reply_to is not None


__all__ = ["Envelope", "Headers"]
