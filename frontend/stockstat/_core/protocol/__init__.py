"""Protocol layer — V2 §12.2 message layer.

Defines the unified Envelope (message wrapper) and message type table.
The protocol layer sits between Codec (encoding) and Transport
(transmission); any layer can be replaced independently.
"""
from .envelope import Envelope, Headers, PROTOCOL_NAME, PROTOCOL_VERSION
from . import messages

__all__ = [
    "Envelope", "Headers",
    "PROTOCOL_NAME", "PROTOCOL_VERSION",
    "messages",
]
