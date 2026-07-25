"""Codec protocol — serialization for data transfer."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Codec(Protocol):
    """Abstract serialization codec.

    Implementations: JsonCodec, CsvCodec, ArrowCodec, ParquetCodec.
    """
    name: str
    media_type: str

    def encode(self, data: Any) -> bytes: ...
    def decode(self, raw: bytes) -> Any: ...
