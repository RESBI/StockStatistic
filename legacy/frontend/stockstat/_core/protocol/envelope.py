"""Protocol envelope — V2 §12.3 unified message envelope.

All node-to-node communication (Client -> Dispatcher, Dispatcher ->
Worker, Worker -> Dispatcher, Dispatcher -> Storage) is wrapped in an
Envelope. The envelope itself is always JSON- or Msgpack-serializable;
the payload may be bytes (Arrow / cloudpickle) decoded according to
``headers.content_type``.

Layered design (V2 §12.2):
- Codec layer (this file + _core/codec/): how bytes map to payloads
- Message layer (this file): how payloads are wrapped with metadata
- Transport layer (_core/transport/): how wrapped messages move

Any layer can be replaced independently. Adding a new transport (e.g.
gRPC) requires no changes to Envelope or Codec. Adding a new codec
(e.g. protobuf) requires no changes to Transport.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Default protocol identifier / version ──────────────────────
PROTOCOL_NAME = "stockstat-rpc"
PROTOCOL_VERSION = "1.0"


@dataclass
class Headers:
    """Envelope headers — V2 §12.3 ``headers`` field.

    Determines:
    - How payload is decoded (``content_type``, ``data_codec``,
      ``strategy_codec``)
    - How the message is routed (``priority``, ``trace_id``,
      ``data_ref``)
    - How the message is transmitted (``encoding``)
    - Protocol negotiation (``protocol_version``, ``accepted_codecs``,
      ``accepted_encodings``)
    """

    content_type: str = "application/json"
    data_codec: str = "arrow"  # arrow / json / parquet
    strategy_codec: str = "cloudpickle"  # cloudpickle / json / none
    encoding: str = "json"  # json / msgpack (control-plane encoding)
    priority: int = 0  # 0 normal / -1 high / 1 low
    timeout: int = 3600  # seconds
    trace_id: str = ""
    data_ref: str = ""  # shm://id / storage://symbol / inline:<base64>
    retry_count: int = 0
    # Protocol negotiation (V2 §12.12)
    protocol_version: str = PROTOCOL_VERSION
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
        if d is None:
            d = {}
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
            protocol_version=d.get("protocol_version", PROTOCOL_VERSION),
            accepted_codecs=list(d.get("accepted_codecs", [])),
            accepted_encodings=list(d.get("accepted_encodings", [])),
        )


@dataclass
class Envelope:
    """Unified message envelope — V2 §12.3.

    Wraps every inter-node message. The envelope is always JSON- or
    Msgpack-serializable; the payload may be raw bytes (Arrow /
    cloudpickle) decoded according to ``headers.content_type``.

    Fields:
        protocol: Always ``"stockstat-rpc"`` (protocol identifier)
        version: Protocol version (semver, e.g. ``"1.0"``)
        type: Message type (see :mod:`.messages`)
        id: Unique message UUID v4
        reply_to: Original message ID this is replying to (for async)
        headers: Metadata headers (see :class:`Headers`)
        payload: Message body (dict for control-plane; bytes for data)
    """

    protocol: str = PROTOCOL_NAME
    version: str = PROTOCOL_VERSION
    type: str = ""  # see messages.py for the type table
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    headers: Headers = field(default_factory=Headers)
    payload: Any = None  # dict (control) or bytes (data) or str

    def to_dict(self) -> dict:
        """JSON-serializable representation.

        Payload is preserved as-is if it's a dict/list/str/number;
        bytes payloads should be base64-encoded by the caller before
        putting into the dict (or carried out-of-band via ``data_ref``).
        """
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
            protocol=d.get("protocol", PROTOCOL_NAME),
            version=d.get("version", PROTOCOL_VERSION),
            type=d.get("type", ""),
            id=d.get("id") or str(uuid.uuid4()),
            reply_to=d.get("reply_to"),
            headers=Headers.from_dict(d.get("headers", {})),
            payload=d.get("payload"),
        )

    def encode(self) -> bytes:
        """Serialize envelope to bytes per ``headers.encoding``.

        - ``"json"`` (default): human-readable, works everywhere
        - ``"msgpack"``: compact binary (V2 §13.5, requires msgpack)

        Payload bytes (if any) are base64-encoded so the entire
        envelope remains a single JSON/Msgpack blob. For large data,
        use ``data_ref`` out-of-band transfer instead.
        """
        import base64

        d = self.to_dict()
        # base64-encode bytes payloads for transport
        if isinstance(d["payload"], (bytes, bytearray)):
            d["payload"] = base64.b64encode(d["payload"]).decode("ascii")
            d.setdefault("_payload_b64", True)

        encoding = self.headers.encoding
        if encoding == "msgpack":
            try:
                import msgpack  # type: ignore
            except ImportError as e:
                raise ImportError(
                    "msgpack encoding requires `pip install msgpack`"
                ) from e
            return msgpack.dumps(d, use_bin_type=True)
        # default: json
        return json.dumps(d, default=str).encode("utf-8")

    @classmethod
    def decode(cls, raw: bytes) -> "Envelope":
        """Deserialize envelope from bytes.

        Auto-detects JSON vs Msgpack by trying JSON first (cheaper
        than sniffing bytes), then falling back to Msgpack.
        """
        import base64

        # Try JSON first (default encoding)
        try:
            d = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                import msgpack  # type: ignore
            except ImportError as e:
                raise ValueError(
                    "Cannot decode envelope: not JSON and msgpack not installed"
                ) from e
            d = msgpack.loads(raw, raw=False)

        # Decode base64-encoded bytes payload
        if d.get("_payload_b64") and isinstance(d.get("payload"), str):
            d["payload"] = base64.b64decode(d["payload"])
            d.pop("_payload_b64", None)

        return cls.from_dict(d)

    def reply(self, type: str, payload: Any = None,
              content_type: str = "application/json") -> "Envelope":
        """Build a reply envelope with ``reply_to`` set to this envelope's id."""
        return Envelope(
            type=type,
            reply_to=self.id,
            headers=Headers(
                content_type=content_type,
                trace_id=self.headers.trace_id,
                protocol_version=self.headers.protocol_version,
            ),
            payload=payload,
        )
