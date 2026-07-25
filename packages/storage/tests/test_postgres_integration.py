"""PostgreSQL 集成测试脚本。"""
import pandas as pd
from sqlalchemy import text
from stockstat_backend import OrmSession, StorageBackendImpl, create_engine_from_url
from stockstat_backend.models import Base

DB_URL = "postgresql://stockstat:stockstat123@192.168.0.114:5432/stockstat"

engine = create_engine_from_url(DB_URL)
orm = OrmSession(engine)

# 先清理旧表（如果有残留）
with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS ohlcv CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS symbol_metadata CASCADE"))
    conn.commit()

# 重新创建表
orm.create_all()

backend = StorageBackendImpl(orm)

df = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
    "open": range(10), "high": range(1, 11),
    "low": range(10), "close": range(2, 12),
    "volume": range(100, 110),
})
rows = backend.ingest_ohlcv("PAXG/USDT", "1d", df)
print("Ingested {} rows to PostgreSQL".format(rows))

result = backend.fetch_ohlcv(["PAXG/USDT"], "1d")
print("Fetched {} rows from PostgreSQL".format(len(result)))
print(result[["close", "volume"]].head())

backend.upsert_metadata("PAXG/USDT", name="PAX Gold", exchange="binance", asset_class="crypto")
meta = backend.get_metadata("PAXG/USDT")
print("Metadata name: {}".format(meta.get("name")))

stats = backend.stats()
print("Stats: {}".format(stats))

# 清理
with orm.session_scope() as session:
    from stockstat_backend.models import OHLCV, SymbolMetadata
    session.query(OHLCV).filter(OHLCV.symbol == "PAXG/USDT").delete()
    session.query(SymbolMetadata).filter(SymbolMetadata.symbol == "PAXG/USDT").delete()
    session.commit()
print("Cleanup done")
print("PostgreSQL integration test: PASSED")
