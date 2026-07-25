"""ResultSerializer — 结果序列化器。"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from stockstat_foundation.codec import ArrowCodec, CsvCodec, JsonCodec, CloudpickleCodec


class ResultSerializer:
    """结果序列化 — 支持多种格式导出。"""

    @staticmethod
    def to_json(result: Any) -> str:
        """序列化为 JSON。"""
        if hasattr(result, "to_dict"):
            return json.dumps(result.to_dict(), default=str)
        if isinstance(result, pd.DataFrame):
            return result.to_json(orient="records")
        return json.dumps(result, default=str)

    @staticmethod
    def to_csv(result: Any) -> str:
        """序列化为 CSV。"""
        if isinstance(result, pd.DataFrame):
            return result.to_csv(index=False)
        if isinstance(result, pd.Series):
            return result.to_csv(header=True)
        return str(result)

    @staticmethod
    def to_arrow(result: Any) -> bytes:
        """序列化为 Arrow IPC。"""
        return ArrowCodec().encode(result)

    @staticmethod
    def to_parquet(result: Any) -> bytes:
        from stockstat_foundation.codec import ParquetCodec
        return ParquetCodec().encode(result)

    @staticmethod
    def to_cloudpickle(result: Any) -> bytes:
        return CloudpickleCodec().encode(result)

    @staticmethod
    def save(result: Any, path: str, format: str = "json") -> None:
        """保存到文件。"""
        format = format.lower()
        if format == "json":
            content = ResultSerializer.to_json(result)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        elif format == "csv":
            content = ResultSerializer.to_csv(result)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        elif format in ("arrow", "parquet"):
            content = (ResultSerializer.to_arrow if format == "arrow"
                        else ResultSerializer.to_parquet)(result)
            with open(path, "wb") as f:
                f.write(content)
        else:
            raise ValueError(f"Unknown format: {format}")


__all__ = ["ResultSerializer"]
