"""StorageBackendImpl — Foundation StorageBackend Protocol 实现。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd

from ..models.ohlcv import OHLCV, SymbolMetadata
from .orm import OrmSession


class StorageBackendImpl:
    """StorageBackend Protocol 实现 — 供 Dispatcher 直连访问。

    当 Dispatcher 与 Storage 同进程部署时，Dispatcher 可直接调用此实现，
    绕过 HTTP，零网络开销。
    """
    name = "sqlalchemy"

    def __init__(self, orm_session: OrmSession):
        self._orm = orm_session

    @property
    def orm(self) -> OrmSession:
        return self._orm

    def fetch_ohlcv(self, symbols, timeframe: str,
                    start: Optional[str] = None, end: Optional[str] = None,
                    source: Optional[str] = None) -> Any:
        """查询 OHLCV 数据，返回 DataFrame（单 symbol）或 dict（多 symbol）。"""
        if isinstance(symbols, str):
            symbols = [symbols]
        with self._orm.session_scope() as session:
            query = session.query(OHLCV).filter(
                OHLCV.symbol.in_(list(symbols)),
                OHLCV.timeframe == timeframe,
            )
            if start:
                query = query.filter(OHLCV.timestamp >= _parse_dt(start))
            if end:
                query = query.filter(OHLCV.timestamp <= _parse_dt(end))
            query = query.order_by(OHLCV.symbol, OHLCV.timestamp)
            rows = query.all()

        if not rows:
            if len(symbols) > 1:
                return {sym: pd.DataFrame() for sym in symbols}
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        records = [
            {"symbol": r.symbol, "timestamp": r.timestamp,
             "open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume}
            for r in rows
        ]
        df = pd.DataFrame(records)
        if len(symbols) > 1:
            result = {}
            for sym in symbols:
                sub = df[df.symbol == sym].drop("symbol", axis=1).reset_index(drop=True)
                result[sym] = sub
            return result
        return df.drop("symbol", axis=1).reset_index(drop=True)

    def ingest_ohlcv(self, symbol: str, timeframe: str, data: Any) -> int:
        """写入 OHLCV 数据，返回写入行数。"""
        records = _normalize_ohlcv_records(symbol, timeframe, data)
        if not records:
            return 0
        with self._orm.session_scope() as session:
            for r in records:
                session.merge(r)
            session.commit()
        return len(records)

    def list_symbols(self) -> list:
        """列出所有标的。"""
        with self._orm.session_scope() as session:
            rows = session.query(SymbolMetadata.symbol).all()
            if rows:
                return [r[0] for r in rows]
            # fallback：从 OHLCV 表中 distinct
            rows = session.query(OHLCV.symbol).distinct().all()
            return [r[0] for r in rows]

    def get_metadata(self, symbol: str) -> dict:
        """获取标的元数据。"""
        import json
        with self._orm.session_scope() as session:
            row = session.query(SymbolMetadata).filter_by(symbol=symbol).first()
            if row is None:
                # 尝试从 OHLCV 推导
                first = session.query(OHLCV).filter_by(symbol=symbol).order_by(OHLCV.timestamp).first()
                last = session.query(OHLCV).filter_by(symbol=symbol).order_by(OHLCV.timestamp.desc()).first()
                if first is None:
                    return {}
                return {
                    "symbol": symbol,
                    "first_seen": first.timestamp.isoformat() if first.timestamp else None,
                    "last_updated": last.timestamp.isoformat() if last and last.timestamp else None,
                    "metadata": {},
                }
            return {
                "symbol": row.symbol,
                "name": row.name,
                "exchange": row.exchange,
                "asset_class": row.asset_class,
                "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
            }

    def upsert_metadata(self, symbol: str, *, name: Optional[str] = None,
                        exchange: Optional[str] = None,
                        asset_class: Optional[str] = None,
                        metadata: Optional[dict] = None) -> None:
        """更新或插入标的元数据。"""
        import json
        with self._orm.session_scope() as session:
            row = session.query(SymbolMetadata).filter_by(symbol=symbol).first()
            now = datetime.utcnow()
            if row is None:
                row = SymbolMetadata(
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    asset_class=asset_class,
                    first_seen=now,
                    last_updated=now,
                    metadata_json=json.dumps(metadata) if metadata else None,
                )
                session.add(row)
            else:
                if name is not None:
                    row.name = name
                if exchange is not None:
                    row.exchange = exchange
                if asset_class is not None:
                    row.asset_class = asset_class
                if metadata is not None:
                    row.metadata_json = json.dumps(metadata)
                row.last_updated = now
            session.commit()

    def stats(self) -> dict:
        """返回存储统计信息。"""
        from sqlalchemy import func
        with self._orm.session_scope() as session:
            total_rows = session.query(func.count(OHLCV.symbol)).scalar() or 0
            symbol_count = session.query(func.count(func.distinct(OHLCV.symbol))).scalar() or 0
            timeframe_count = session.query(func.count(func.distinct(OHLCV.timeframe))).scalar() or 0
        return {
            "total_rows": int(total_rows),
            "symbol_count": int(symbol_count),
            "timeframe_count": int(timeframe_count),
        }


def _parse_dt(s) -> datetime:
    if isinstance(s, datetime):
        return s
    if isinstance(s, (int, float)):
        return datetime.utcfromtimestamp(float(s))
    try:
        return pd.Timestamp(s).to_pydatetime()
    except Exception:
        return datetime.utcnow()


def _normalize_ohlcv_records(symbol: str, timeframe: str, data: Any) -> list:
    """将 DataFrame / list[dict] / list[OHLCV] 统一转换为 OHLCV 记录。"""
    if isinstance(data, pd.DataFrame):
        records = []
        for _, row in data.iterrows():
            ts = row.get("timestamp") or row.get("Timestamp") or row.get("Date") or row.name
            ts_dt = _parse_dt(ts)
            records.append(OHLCV(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts_dt,
                open=float(row["open"] if "open" in row else row["Open"]),
                high=float(row["high"] if "high" in row else row["High"]),
                low=float(row["low"] if "low" in row else row["Low"]),
                close=float(row["close"] if "close" in row else row["Close"]),
                volume=float(row.get("volume", row.get("Volume", 0)) or 0),
            ))
        return records
    if isinstance(data, list):
        records = []
        for item in data:
            if isinstance(item, OHLCV):
                records.append(item)
            elif isinstance(item, dict):
                ts = item.get("timestamp") or item.get("Timestamp")
                records.append(OHLCV(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=_parse_dt(ts),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume", 0)),
                ))
        return records
    if isinstance(data, OHLCV):
        return [data]
    return []


__all__ = ["StorageBackendImpl"]
