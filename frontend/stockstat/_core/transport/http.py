"""HTTP transport — V3 default cross-machine transport.

Uses httpx for REST communication between Client/Dispatcher/Worker.
Control-plane messages are JSON; data-plane uses base64-encoded bytes.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

from ..protocol.envelope import Envelope
from ..protocol import messages


class HttpTransport:
    """HTTP transport — REST + JSON for control plane.

    Maps Envelope types to REST endpoints via messages.TYPE_TO_PATH.
    For request-response patterns, sends POST and waits for reply.
    """

    name = "http"

    def __init__(self, base_url: str, *, timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def send(self, envelope: Envelope) -> None:
        """Fire-and-forget send."""
        path = messages.TYPE_TO_PATH.get(envelope.type, "/dispatch/message")
        self._client.post(
            f"{self._base_url}{path}",
            content=envelope.encode(),
            headers={"Content-Type": "application/json"},
        )

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        """Request-response: send and wait for reply."""
        path = messages.TYPE_TO_PATH.get(envelope.type, "/dispatch/message")
        resp = self._client.post(
            f"{self._base_url}{path}",
            content=envelope.encode(),
            headers={"Content-Type": "application/json"},
            timeout=timeout or self._timeout,
        )
        if resp.status_code == 204:
            return Envelope(type="task.ack", payload=None)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        # Response may be a real Envelope OR plain JSON (Dispatcher's reply)
        # Detect by checking for the "protocol" field
        try:
            import json
            d = json.loads(resp.content.decode("utf-8"))
            if isinstance(d, dict) and d.get("protocol") == "stockstat-rpc":
                return Envelope.decode(resp.content)
            # Plain JSON response — wrap as Envelope
            return Envelope(
                type=f"{envelope.type}.reply",
                reply_to=envelope.id,
                payload=d,
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fall back to wrapping the raw response
            return Envelope(
                type=f"{envelope.type}.reply",
                reply_to=envelope.id,
                payload=resp.content,
            )

    def send_data(self, data: bytes, content_type: str) -> str:
        """Send data inline as base64 (no separate data endpoint for HTTP)."""
        import base64
        return f"inline:{base64.b64encode(data).decode('ascii')}"

    def close(self) -> None:
        self._client.close()

    # ── Convenience methods for direct REST calls ─────────────

    def post_json(self, path: str, json_data: dict) -> dict:
        """Direct POST JSON (bypasses Envelope)."""
        resp = self._client.post(f"{self._base_url}{path}", json=json_data)
        if resp.status_code == 204:
            return {}
        resp.raise_for_status()
        return resp.json()

    def get_json(self, path: str, params: dict = None) -> dict:
        """Direct GET JSON (bypasses Envelope)."""
        resp = self._client.get(f"{self._base_url}{path}", params=params)
        if resp.status_code == 204:
            return {}
        resp.raise_for_status()
        return resp.json()
