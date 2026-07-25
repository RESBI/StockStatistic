"""HttpTransport — REST + JSON 控制面。"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional

from ..protocol import messages
from ..protocol.envelope import Envelope


class HttpTransport:
    """HTTP 传输 — REST + JSON 控制面。"""
    name = "http"

    def __init__(self, base_url: str, *, timeout: int = 30, http_client=None):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if http_client is not None:
            self._client = http_client
        else:
            import httpx
            self._client = httpx.Client(timeout=timeout)
        self._closed = False

    def send(self, envelope: Envelope) -> None:
        path = messages.TYPE_TO_PATH.get(envelope.type, "/dispatch/message")
        self._client.post(
            f"{self._base_url}{path}",
            content=envelope.encode(),
            headers={"Content-Type": "application/json"},
        )

    def receive(self, timeout: Optional[float] = None):
        raise NotImplementedError("HttpTransport is request/response only; use request()")

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        path = messages.TYPE_TO_PATH.get(envelope.type, "/dispatch/message")
        resp = self._client.post(
            f"{self._base_url}{path}",
            content=envelope.encode(),
            headers={"Content-Type": "application/json"},
            timeout=timeout or self._timeout,
        )
        return self._parse_response(resp, envelope)

    def reply(self, original: Envelope, reply: Envelope) -> None:
        # HTTP 是请求/响应模式，reply 通过同步响应返回，无需显式调用
        self.send(reply)

    def _parse_response(self, resp, original: Envelope) -> Envelope:
        content = resp.content
        try:
            d = json.loads(content.decode("utf-8"))
            if isinstance(d, dict) and d.get("protocol") == "stockstat-rpc":
                return Envelope.decode(content)
            return Envelope(
                type=f"{original.type}.reply",
                reply_to=original.id,
                headers=__import__(
                    "stockstat_foundation.protocol.envelope", fromlist=["Headers"]
                ).Headers(trace_id=original.headers.trace_id),
                payload=d,
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Envelope(
                type=f"{original.type}.reply",
                reply_to=original.id,
                payload=content,
            )

    def send_data(self, data: bytes, content_type: str) -> str:
        return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        if data_ref.startswith("http://") or data_ref.startswith("https://"):
            resp = self._client.get(data_ref)
            return resp.content
        raise ValueError(f"Unknown data_ref for HttpTransport: {data_ref}")

    def post_json(self, path: str, json_data: Any) -> dict:
        resp = self._client.post(f"{self._base_url}{path}", json=json_data)
        return resp.json()

    def get_json(self, path: str, params: Any = None) -> dict:
        resp = self._client.get(f"{self._base_url}{path}", params=params)
        return resp.json()

    def get_bytes(self, path: str, params: Any = None) -> bytes:
        resp = self._client.get(f"{self._base_url}{path}", params=params)
        return resp.content

    def close(self) -> None:
        if not self._closed:
            self._client.close()
            self._closed = True


__all__ = ["HttpTransport"]
