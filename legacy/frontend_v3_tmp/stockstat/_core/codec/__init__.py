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


class CloudpickleCodec:
    """cloudpickle codec for Python closures (strategies, callables).

    Satisfies the :class:`Codec` protocol. Requires ``cloudpickle``
    (V3 optional extra: ``pip install stockstat[compute]``).

    Used for serializing user-supplied strategy functions / objects
    that may capture closures — JSON cannot represent these.
    """

    name = "cloudpickle"
    media_type = "application/vnd.python.cloudpickle"

    def encode(self, data: Any) -> bytes:
        import cloudpickle  # type: ignore
        return cloudpickle.dumps(data)

    def decode(self, raw: bytes) -> Any:
        import cloudpickle  # type: ignore
        return cloudpickle.loads(raw)


class MsgpackCodec:
    """MessagePack codec for compact control-plane messages (V2 §13.5).

    Satisfies the :class:`Codec` protocol. Requires ``msgpack``
    (V3 optional extra: ``pip install msgpack``).

    Used as an alternative to JSON for high-frequency small messages
    (e.g. heartbeats). ~60% smaller than JSON for typical payloads.
    """

    name = "msgpack"
    media_type = "application/msgpack"

    def encode(self, data: Any) -> bytes:
        import msgpack  # type: ignore
        return msgpack.dumps(data, use_bin_type=True)

    def decode(self, raw: bytes) -> Any:
        import msgpack  # type: ignore
        return msgpack.loads(raw, raw=False)


class RawCodec:
    """Pass-through codec for raw bytes (binary blobs, already-encoded data)."""

    name = "raw"
    media_type = "application/octet-stream"

    def encode(self, data: Any) -> bytes:
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode("utf-8")
        raise TypeError(f"RawCodec cannot encode {type(data)}")

    def decode(self, raw: bytes) -> Any:
        return raw


# Registry of codecs
_CODECS: dict[str, Any] = {
    "json": JsonCodec,
    "csv": CsvCodec,
    "arrow": ArrowCodec,
    "parquet": ParquetCodec,
    "cloudpickle": CloudpickleCodec,
    "msgpack": MsgpackCodec,
    "raw": RawCodec,
}


def get_codec(name: str) -> Any:
    """Get a codec instance by name."""
    cls = _CODECS.get(name)
    if cls is None:
        raise KeyError(f"Unknown codec: '{name}'. Available: {list(_CODECS.keys())}")
    return cls()


def get_codec_for_content_type(content_type: str) -> Any:
    """Get a codec instance by MIME content type.

    Useful for decoding Envelope payloads where ``headers.content_type``
    indicates the encoding but the caller hasn't picked a codec name.
    """
    ct = content_type.lower()
    if ct == CT_JSON or ct == "application/vnd.stockstat.task+json":
        return JsonCodec()
    if ct.startswith("application/vnd.apache.arrow"):
        return ArrowCodec()
    if ct.startswith("application/vnd.apache.parquet"):
        return ParquetCodec()
    if ct.startswith("application/vnd.python.cloudpickle") or "cloudpickle" in ct:
        return CloudpickleCodec()
    if ct == "application/msgpack" or "msgpack" in ct:
        return MsgpackCodec()
    if ct == "application/octet-stream":
        return RawCodec()
    if ct.startswith("application/vnd.stockstat.result+"):
        # result+arrow / result+cloudpickle / result+json
        sub = ct.split("+", 1)[1]
        return get_codec(sub)
    # Fallback: try JSON
    return JsonCodec()


def available_codecs() -> list[str]:
    """List available codec names."""
    return list(_CODECS.keys())


# Content-type constants (mirror protocol.messages for convenience)
CT_JSON = "application/json"
CT_ARROW = "application/vnd.apache.arrow.file"
CT_PARQUET = "application/vnd.apache.parquet"
CT_CLOUDPICKLE = "application/vnd.python.cloudpickle"
CT_MSGPACK = "application/msgpack"
CT_OCTET = "application/octet-stream"
