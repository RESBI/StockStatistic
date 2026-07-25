"""CsvCodec — pandas CSV 编码。"""
from __future__ import annotations

import io
from typing import Any


class CsvCodec:
    name = "csv"
    media_type = "text/csv"

    def encode(self, data: Any) -> bytes:
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            buf = io.StringIO()
            data.to_csv(buf, index=False)
            return buf.getvalue().encode("utf-8")
        if isinstance(data, pd.Series):
            return data.to_csv(header=True).encode("utf-8")
        raise TypeError(f"CsvCodec can only encode DataFrame/Series, got {type(data).__name__}")

    def decode(self, raw: bytes) -> Any:
        import pandas as pd
        return pd.read_csv(io.BytesIO(raw))


__all__ = ["CsvCodec"]
