"""ArrowCodec — pyarrow IPC 表格数据编码。"""
from __future__ import annotations

import io
from typing import Any


class ArrowCodec:
    name = "arrow"
    media_type = "application/vnd.apache.arrow.file"

    def encode(self, data: Any) -> bytes:
        try:
            import pyarrow as pa
        except ImportError as e:
            raise ImportError(
                "ArrowCodec requires 'pyarrow'. "
                "Install with: pip install stockstat-foundation[arrow]"
            ) from e
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data, preserve_index=False)
        elif isinstance(data, pa.Table):
            table = data
        elif isinstance(data, dict):
            table = pa.Table.from_pydict(data)
        elif isinstance(data, list):
            table = pa.Table.from_pylist(data)
        else:
            raise TypeError(f"ArrowCodec cannot encode {type(data).__name__}")
        sink = io.BytesIO()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return sink.getvalue()

    def decode(self, raw: bytes) -> Any:
        try:
            import pyarrow as pa
        except ImportError as e:
            raise ImportError(
                "ArrowCodec requires 'pyarrow'. "
                "Install with: pip install stockstat-foundation[arrow]"
            ) from e
        import pandas as pd
        reader = pa.ipc.open_stream(raw)
        table = reader.read_all()
        return table.to_pandas()


__all__ = ["ArrowCodec"]
