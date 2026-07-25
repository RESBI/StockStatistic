"""test_codec.py — 7 个 Codec / 工厂函数 / 优雅降级 (30 项)。"""
from __future__ import annotations

import io

import pytest

from stockstat_foundation.codec import (
    JsonCodec, ArrowCodec, ParquetCodec, CsvCodec,
    CloudpickleCodec, MsgpackCodec, RawCodec,
    get_codec, get_codec_for_content_type,
)
from stockstat_foundation.codec.cloudpickle_codec import cloudpickle_dumps, cloudpickle_loads


class TestJsonCodec:
    def test_encode_decode_dict(self):
        c = JsonCodec()
        raw = c.encode({"x": 1, "y": [1, 2, 3]})
        assert isinstance(raw, bytes)
        d = c.decode(raw)
        assert d == {"x": 1, "y": [1, 2, 3]}

    def test_encode_decode_nested(self):
        c = JsonCodec()
        d = {"a": {"b": {"c": [1, 2, 3]}}, "n": None}
        assert c.decode(c.encode(d)) == d

    def test_media_type(self):
        assert JsonCodec().media_type == "application/json"
        assert JsonCodec().name == "json"

    def test_datetime_serialization(self):
        from datetime import datetime
        c = JsonCodec()
        d = {"ts": datetime(2024, 1, 1, 12, 0, 0)}
        restored = c.decode(c.encode(d))
        assert "2024-01-01T12:00:00" in restored["ts"]


class TestRawCodec:
    def test_encode_bytes(self):
        c = RawCodec()
        raw = c.encode(b"binary data")
        assert raw == b"binary data"
        assert c.decode(raw) == b"binary data"

    def test_encode_str(self):
        c = RawCodec()
        assert c.encode("hello") == b"hello"

    def test_media_type(self):
        assert RawCodec().media_type == "application/octet-stream"


class TestCsvCodec:
    def test_dataframe_roundtrip(self):
        import pandas as pd
        c = CsvCodec()
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        raw = c.encode(df)
        assert b"a,b" in raw
        df2 = c.decode(raw)
        assert list(df2["a"]) == [1, 2, 3]

    def test_media_type(self):
        assert CsvCodec().media_type == "text/csv"


class TestArrowCodec:
    def test_dataframe_roundtrip(self):
        import pandas as pd
        c = ArrowCodec()
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        raw = c.encode(df)
        assert isinstance(raw, bytes)
        df2 = c.decode(raw)
        assert list(df2["a"]) == [1, 2, 3]
        assert list(df2["b"]) == ["x", "y", "z"]

    def test_large_dataframe(self):
        import pandas as pd
        import numpy as np
        c = ArrowCodec()
        df = pd.DataFrame({"x": np.arange(10000), "y": np.random.rand(10000)})
        raw = c.encode(df)
        df2 = c.decode(raw)
        assert len(df2) == 10000

    def test_dict_input(self):
        c = ArrowCodec()
        raw = c.encode({"a": [1, 2, 3], "b": [4, 5, 6]})
        df2 = c.decode(raw)
        assert list(df2["a"]) == [1, 2, 3]

    def test_media_type(self):
        assert "arrow" in ArrowCodec().media_type


class TestParquetCodec:
    def test_roundtrip(self):
        import pandas as pd
        c = ParquetCodec()
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        raw = c.encode(df)
        df2 = c.decode(raw)
        assert list(df2["a"]) == [1, 2, 3]


class TestCloudpickleCodec:
    def test_roundtrip_simple(self):
        c = CloudpickleCodec()
        raw = c.encode({"x": 1})
        assert c.decode(raw) == {"x": 1}

    def test_closure_serialization(self):
        c = CloudpickleCodec()
        def my_strategy(x): return x * 2 + 1
        raw = c.encode(my_strategy)
        restored = c.decode(raw)
        assert restored(5) == 11

    def test_dumps_loads_helpers(self):
        def f(a, b): return a + b
        ref = cloudpickle_dumps(f)
        assert ref.startswith("") or len(ref) > 0
        restored = cloudpickle_loads(f"cloudpickle:{ref}")
        assert restored(2, 3) == 5

    def test_media_type(self):
        assert "cloudpickle" in CloudpickleCodec().media_type


class TestMsgpackCodec:
    def test_roundtrip(self):
        c = MsgpackCodec()
        raw = c.encode({"x": 1, "y": "hello", "z": [1, 2, 3]})
        d = c.decode(raw)
        assert d["x"] == 1
        assert d["y"] == "hello"
        assert d["z"] == [1, 2, 3]

    def test_compact_vs_json(self):
        import json
        c = MsgpackCodec()
        data = {"x": 1, "y": "hello", "z": [1, 2, 3, 4, 5]}
        mp_size = len(c.encode(data))
        json_size = len(json.dumps(data).encode("utf-8"))
        # msgpack 通常更紧凑
        assert mp_size <= json_size

    def test_media_type(self):
        assert MsgpackCodec().media_type == "application/msgpack"


class TestCodecFactory:
    def test_get_codec_by_name(self):
        assert get_codec("json").name == "json"
        assert get_codec("arrow").name == "arrow"
        assert get_codec("cloudpickle").name == "cloudpickle"
        assert get_codec("msgpack").name == "msgpack"
        assert get_codec("raw").name == "raw"
        assert get_codec("csv").name == "csv"
        assert get_codec("parquet").name == "parquet"

    def test_get_codec_unknown(self):
        with pytest.raises(ValueError):
            get_codec("nonexistent")

    def test_get_codec_for_content_type_json(self):
        c = get_codec_for_content_type("application/json")
        assert c.name == "json"

    def test_get_codec_for_content_type_arrow(self):
        c = get_codec_for_content_type("application/vnd.apache.arrow.file")
        assert c.name == "arrow"

    def test_get_codec_for_content_type_cloudpickle(self):
        c = get_codec_for_content_type("application/vnd.python.cloudpickle")
        assert c.name == "cloudpickle"

    def test_get_codec_for_content_type_msgpack(self):
        c = get_codec_for_content_type("application/msgpack")
        assert c.name == "msgpack"

    def test_get_codec_for_content_type_csv(self):
        c = get_codec_for_content_type("text/csv")
        assert c.name == "csv"

    def test_get_codec_for_content_type_octet(self):
        c = get_codec_for_content_type("application/octet-stream")
        assert c.name == "raw"

    def test_get_codec_for_content_type_empty_falls_back_json(self):
        c = get_codec_for_content_type("")
        assert c.name == "json"

    def test_get_codec_for_stockstat_result(self):
        c = get_codec_for_content_type("application/vnd.stockstat.result+arrow")
        assert c.name == "arrow"


class TestCodecProtocolConformance:
    def test_all_codecs_have_name_and_media_type(self):
        for codec_cls in [JsonCodec, ArrowCodec, ParquetCodec, CsvCodec,
                          CloudpickleCodec, MsgpackCodec, RawCodec]:
            c = codec_cls()
            assert hasattr(c, "name")
            assert hasattr(c, "media_type")
            assert hasattr(c, "encode")
            assert hasattr(c, "decode")

    def test_codec_protocol_runtime_checkable(self):
        from stockstat_foundation import Codec
        c = JsonCodec()
        assert isinstance(c, Codec)
