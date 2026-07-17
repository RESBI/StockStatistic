"""Codec implementations — serialization for data transfer."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd


class JsonCodec:
    """JSON codec for DataFrames and dicts.

    Satisfies the :class:`Codec` protocol.
    """
    name = "json"
    media_type = "application/json"

    def encode(self, data: Any) -> bytes:
        if isinstance(data, pd.DataFrame):
            # Reset index, convert to records, then JSON
            records = data.reset_index().to_dict(orient="records")
            # Convert timestamps to ISO strings
            for rec in records:
                for k, v in list(rec.items()):
                    if isinstance(v, pd.Timestamp):
                        rec[k] = v.isoformat()
            return json.dumps(records, default=str).encode("utf-8")
        return json.dumps(data, default=str).encode("utf-8")

    def decode(self, raw: bytes) -> Any:
        return json.loads(raw.decode("utf-8"))


class CsvCodec:
    """CSV codec for DataFrames.

    Satisfies the :class:`Codec` protocol.
    """
    name = "csv"
    media_type = "text/csv"

    def encode(self, data: Any) -> bytes:
        if isinstance(data, pd.DataFrame):
            return data.to_csv().encode("utf-8")
        if isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
            return df.to_csv().encode("utf-8")
        return str(data).encode("utf-8")

    def decode(self, raw: bytes) -> Any:
        from io import StringIO
        return pd.read_csv(StringIO(raw.decode("utf-8")), index_col=0)


class ArrowCodec:
    """Apache Arrow IPC codec for zero-copy DataFrame transfer.

    Satisfies the :class:`Codec` protocol. Requires ``pyarrow``
    (already a core dependency).
    """
    name = "arrow"
    media_type = "application/vnd.apache.arrow.file"

    def encode(self, data: Any) -> bytes:
        import pyarrow as pa
        import pyarrow.ipc as ipc

        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data, preserve_index=True)
        elif isinstance(data, dict):
            table = pa.Table.from_pylist(data)
        else:
            raise TypeError(f"ArrowCodec cannot encode {type(data)}")

        sink = pa.BufferOutputStream()
        with ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return sink.getvalue().to_pybytes()

    def decode(self, raw: bytes) -> Any:
        import pyarrow as pa
        import pyarrow.ipc as ipc

        reader = ipc.open_stream(pa.BufferReader(raw))
        table = reader.read_all()
        return table.to_pandas()


class ParquetCodec:
    """Parquet codec for columnar file storage.

    Satisfies the :class:`Codec` protocol. Requires ``pyarrow``.
    """
    name = "parquet"
    media_type = "application/vnd.apache.parquet"

    def encode(self, data: Any) -> bytes:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data, preserve_index=True)
        elif isinstance(data, dict):
            table = pa.Table.from_pylist(data)
        else:
            raise TypeError(f"ParquetCodec cannot encode {type(data)}")

        sink = pa.BufferOutputStream()
        pq.write_table(table, sink)
        return sink.getvalue().to_pybytes()

    def decode(self, raw: bytes) -> Any:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pq.read_table(pa.BufferReader(raw))
        return table.to_pandas()


# Registry of codecs
_CODECS: dict[str, Any] = {
    "json": JsonCodec,
    "csv": CsvCodec,
    "arrow": ArrowCodec,
    "parquet": ParquetCodec,
}


def get_codec(name: str) -> Any:
    """Get a codec instance by name."""
    cls = _CODECS.get(name)
    if cls is None:
        raise KeyError(f"Unknown codec: '{name}'. Available: {list(_CODECS.keys())}")
    return cls()


def available_codecs() -> list[str]:
    """List available codec names."""
    return list(_CODECS.keys())
