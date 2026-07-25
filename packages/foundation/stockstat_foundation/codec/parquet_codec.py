"""ParquetCodec — pyarrow parquet 编码。"""
from __future__ import annotations

import io
from typing import Any


class ParquetCodec:
    name = "parquet"
    media_type = "application/vnd.apache.parquet"

    def encode(self, data: Any) -> bytes:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError(
                "ParquetCodec requires 'pyarrow'. "
                "Install with: pip install stockstat-foundation[arrow]"
            ) from e
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data, preserve_index=False)
        elif isinstance(data, pa.Table):
            table = data
        else:
            raise TypeError(f"ParquetCodec cannot encode {type(data).__name__}")
        sink = io.BytesIO()
        pq.write_table(table, sink)
        return sink.getvalue()

    def decode(self, raw: bytes) -> Any:
        try:
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError(
                "ParquetCodec requires 'pyarrow'. "
                "Install with: pip install stockstat-foundation[arrow]"
            ) from e
        table = pq.read_table(io.BytesIO(raw))
        return table.to_pandas()


__all__ = ["ParquetCodec"]
