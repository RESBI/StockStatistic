"""Codec 层 — 7 个 Codec + 工厂函数。"""
from __future__ import annotations

from .json_codec import JsonCodec
from .raw_codec import RawCodec
from .csv_codec import CsvCodec
from .arrow_codec import ArrowCodec
from .parquet_codec import ParquetCodec
from .cloudpickle_codec import CloudpickleCodec
from .msgpack_codec import MsgpackCodec


def get_codec(name: str):
    """按名称获取 codec 实例。"""
    name = name.lower()
    if name == "json":
        return JsonCodec()
    if name == "arrow":
        return ArrowCodec()
    if name == "parquet":
        return ParquetCodec()
    if name == "csv":
        return CsvCodec()
    if name == "cloudpickle":
        return CloudpickleCodec()
    if name == "msgpack":
        return MsgpackCodec()
    if name == "raw":
        return RawCodec()
    raise ValueError(f"Unknown codec: {name}")


def get_codec_for_content_type(content_type: str):
    """按 MIME 自动选择 codec。"""
    ct = (content_type or "").lower()
    if ct == "application/json" or ct == "":
        return JsonCodec()
    if ct.startswith("application/vnd.apache.arrow"):
        return ArrowCodec()
    if ct.startswith("application/vnd.apache.parquet"):
        return ParquetCodec()
    if ct == "text/csv":
        return CsvCodec()
    if ct.startswith("application/vnd.python.cloudpickle"):
        return CloudpickleCodec()
    if ct == "application/msgpack":
        return MsgpackCodec()
    if ct == "application/octet-stream":
        return RawCodec()
    if ct.startswith("application/vnd.stockstat.result+"):
        return get_codec(ct.split("+", 1)[1])
    return JsonCodec()


__all__ = [
    "JsonCodec", "ArrowCodec", "ParquetCodec", "CsvCodec",
    "CloudpickleCodec", "MsgpackCodec", "RawCodec",
    "get_codec", "get_codec_for_content_type",
]
