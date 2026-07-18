from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import select, delete, func

from ..models.ohlcv import OHLCV, SymbolRegistry
from .database import get_session


class OHLCVRepository:
    def upsert_many(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        with get_session() as session:
            for row in rows:
                existing = session.execute(
                    select(OHLCV).where(
                        OHLCV.symbol == row["symbol"],
                        OHLCV.ts == row["ts"],
                        OHLCV.timeframe == row["timeframe"],
                        OHLCV.source == row["source"],
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.open = row["open"]
                    existing.high = row["high"]
                    existing.low = row["low"]
                    existing.close = row["close"]
                    existing.volume = row["volume"]
                else:
                    session.add(OHLCV(**row))
            return len(rows)

    def query(
        self,
        symbol: str,
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
        limit: Optional[int] = None,
        order: str = "asc",
    ) -> pd.DataFrame:
        with get_session() as session:
            stmt = select(OHLCV).where(
                OHLCV.symbol == symbol,
                OHLCV.timeframe == timeframe,
            )
            if source:
                stmt = stmt.where(OHLCV.source == source)
            if start:
                stmt = stmt.where(OHLCV.ts >= start)
            if end:
                stmt = stmt.where(OHLCV.ts <= end)
            if order == "desc":
                stmt = stmt.order_by(OHLCV.ts.desc())
            else:
                stmt = stmt.order_by(OHLCV.ts.asc())
            if limit:
                stmt = stmt.limit(limit)

            result = session.execute(stmt).scalars().all()
            if not result:
                return pd.DataFrame()

            records = []
            for r in result:
                records.append({
                    "ts": r.ts,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "source": r.source,
                })
            df = pd.DataFrame(records)
            if not df.empty:
                df["ts"] = pd.to_datetime(df["ts"], utc=True)
                df = df.set_index("ts")
                # When order=desc, reverse to ascending for downstream consumers
                if order == "desc":
                    df = df.iloc[::-1]
            return df

    def count(self, symbol: Optional[str] = None) -> int:
        with get_session() as session:
            stmt = select(func.count()).select_from(OHLCV)
            if symbol:
                stmt = stmt.where(OHLCV.symbol == symbol)
            return session.execute(stmt).scalar()

    def delete_all(self):
        with get_session() as session:
            session.execute(delete(OHLCV))


class SymbolRepository:
    def upsert(self, symbol: str, asset_type: str, base_asset: str,
               quote_asset: str = None, description: str = None,
               sources: str = None):
        with get_session() as session:
            existing = session.get(SymbolRegistry, symbol)
            if existing:
                existing.asset_type = asset_type
                existing.base_asset = base_asset
                existing.quote_asset = quote_asset
                existing.description = description
                existing.sources = sources
            else:
                session.add(SymbolRegistry(
                    unified_symbol=symbol,
                    asset_type=asset_type,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    description=description,
                    sources=sources,
                ))

    def list_symbols(self, asset_type: Optional[str] = None) -> list[dict]:
        with get_session() as session:
            stmt = select(SymbolRegistry)
            if asset_type:
                stmt = stmt.where(SymbolRegistry.asset_type == asset_type)
            result = session.execute(stmt).scalars().all()
            return [
                {
                    "unified_symbol": r.unified_symbol,
                    "asset_type": r.asset_type,
                    "base_asset": r.base_asset,
                    "quote_asset": r.quote_asset,
                    "description": r.description,
                    "sources": r.sources.split(",") if r.sources else [],
                }
                for r in result
            ]

    def get(self, symbol: str) -> Optional[dict]:
        with get_session() as session:
            r = session.get(SymbolRegistry, symbol)
            if not r:
                return None
            return {
                "unified_symbol": r.unified_symbol,
                "asset_type": r.asset_type,
                "base_asset": r.base_asset,
                "quote_asset": r.quote_asset,
                "description": r.description,
                "sources": r.sources.split(",") if r.sources else [],
            }


ohlcv_repo = OHLCVRepository()
symbol_repo = SymbolRepository()
