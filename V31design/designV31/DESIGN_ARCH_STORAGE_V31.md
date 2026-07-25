# DESIGN_ARCH_STORAGE_V31 — 存储端架构设计

> **模块**：Storage（存储端）
> **版本**：v3.1
> **日期**：2026-07-24
> **状态**：设计稿
> **关联**：
> - [DESIGN_ARCH_V31.md](DESIGN_ARCH_V31.md) — 总设计
> - [DESIGN_ARCH_FOUNDATION_V31.md](DESIGN_ARCH_FOUNDATION_V31.md) — 基础层
>
> **核心使命**：提供 OHLCV 数据的**持久化、查询、采集**能力，作为 V3.1 四角色架构的"数据仓库"。Storage 在计算期间**完全空闲**（仅被 Dispatcher 预取 1 次），不参与计算调度。

---

## 目录

1. [模块定位与边界](#1-模块定位与边界)
2. [内部结构](#2-内部结构)
3. [数据模型](#3-数据模型)
4. [StorageBackend 实现](#4-storagebackend-实现)
5. [REST API](#5-rest-api)
6. [数据采集 Adapters](#6-数据采集-adapters)
7. [数据规范化 Normalizer](#7-数据规范化-normalizer)
8. [调度器 Scheduler](#8-调度器-scheduler)
9. [Admin 管理面板](#9-admin-管理面板)
10. [缓存层](#10-缓存层)
11. [部署形态](#11-部署形态)
12. [测试体系](#12-测试体系)

---

## 1. 模块定位与边界

### 1.1 Storage 是什么

Storage 是 V3.1 的**数据仓库**，承载：

- **OHLCV 持久化**：SQLAlchemy + SQLite/PostgreSQL
- **数据查询**：REST API `/api/v1/ohlcv`
- **数据采集**：Binance / YFinance 适配器
- **数据规范化**：不同源的字段映射、时区对齐
- **定时采集**：Scheduler 定时拉取最新数据
- **管理面板**：Admin Web UI
- **StorageBackend 实现**：供 Dispatcher/Compute 直连访问

### 1.2 Storage 不是什么

| 不是 | 理由 |
|------|------|
| 不含计算逻辑 | 无 BacktestEngine/indicators |
| 不含任务调度 | 由 Dispatcher 负责 |
| 不含用户接口 | 无 Client SDK（Invocation 负责） |
| 不感知 task_type | 只存取 OHLCV 数据 |

### 1.3 与 V3 的关键差异

| 维度 | V3 | V3.1 |
|------|----|------|
| 包归属 | `backend/stockstat_backend/` | **独立包 `stockstat-backend`** |
| 与 Dispatcher 关系 | Dispatcher 嵌入 backend | Dispatcher 独立包，松耦合 |
| StorageBackend | 无 | **新增 Protocol 实现**，供 Dispatcher 直连 |
| Admin | 嵌入 backend | 保留，可独立启用 |

### 1.4 核心设计原则

> **Storage 在计算期间完全空闲**：
> - Dispatcher 一次性预取数据（`data.fetch` 1 次）
> - Worker 不直接访问 Storage（除非 `storage_ref` 策略）
> - 用户查询与 Worker 数据拉取不竞争带宽
>
> **数据路径与控制路径分离**（COMPUTE_OFFLOAD_PLAN_V2_CN §1.2）

---

## 2. 内部结构

```
packages/storage/stockstat_backend/
├── __init__.py                  # 导出 StorageApp, StorageBackend
├── app.py                       # StorageApp（FastAPI 应用工厂）
├── config.py                    # 存储配置
├── models/                      # SQLAlchemy 模型
│   ├── __init__.py
│   └── ohlcv.py                 # OHLCV 模型
├── storage/                     # 存储层
│   ├── __init__.py
│   ├── backend.py               # StorageBackend 实现（Foundation Protocol）
│   ├── orm.py                   # SQLAlchemy ORM 封装
│   └── cache.py                 # 查询缓存
├── api/                         # REST API 路由
│   ├── __init__.py
│   ├── ohlcv.py                 # /api/v1/ohlcv
│   ├── symbols.py               # /api/v1/symbols
│   ├── health.py                # /health
└── ingest.py                    # /api/v1/ingest
├── adapters/                    # 数据源适配器
│   ├── __init__.py
│   ├── base.py                  # DataSource Protocol
│   ├── binance.py               # Binance 适配器
│   └── yfinance.py              # YFinance 适配器
├── normalizer/                  # 数据规范化
│   ├── __init__.py
│   └── schema.py                # 字段映射 / 时区对齐
├── scheduler/                   # 定时采集
│   ├── __init__.py
│   └── collector.py             # 定时采集器
├── plugins/
│   └── admin/                   # Admin 管理面板
│       ├── __init__.py
│       ├── router.py            # /admin/api/*
│       └── static/              # Admin SPA 静态文件
└── cli.py                       # stockstat-backend CLI
```

### 2.1 依赖关系

```mermaid
graph TB
    subgraph "Storage（本模块）"
        APP[StorageApp]
        ORM[ORM Layer]
        BE[StorageBackend]
        API[REST API]
        ADP[Adapters]
        NORM[Normalizer]
        SCH[Scheduler]
        ADM[Admin Panel]
    end

    subgraph "Foundation"
        F[StorageBackend Protocol<br/>ArrowCodec]
    end

    subgraph "Dispatcher"
        D[Dispatcher]
    end

    subgraph "Invocation"
        C[Client DataClient]
    end

    subgraph "外部数据源"
        BIN[Binance API]
        YF[YFinance API]
    end

    APP --> ORM
    APP --> API
    APP --> ADM
    ORM --> BE
    BE -->|实现| F
    API --> ORM
    ADP --> BIN
    ADP --> YF
    ADP --> NORM
    NORM --> ORM
    SCH --> ADP

    D -.->|data.fetch / Protocol| BE
    C -.->|HTTP /api/v1/ohlcv| API

    style APP fill:#e8f5e9,stroke:#388e3c,stroke-width:3px
    style F fill:#e1f5ff,stroke:#0288d1
    style D fill:#f3e5f5,stroke:#7b1fa2
    style C fill:#fff3e0,stroke:#f57c00
```

---

## 3. 数据模型

### 3.1 OHLCV 模型

```python
# models/ohlcv.py
from sqlalchemy import Column, String, DateTime, Float, Integer, Index
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OHLCV(Base):
    """OHLCV K 线数据模型。

    主键：(symbol, timeframe, timestamp) 复合主键，避免重复插入。
    """
    __tablename__ = "ohlcv"

    symbol = Column(String(32), primary_key=True)
    timeframe = Column(String(8), primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_ohlcv_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
        Index("ix_ohlcv_ts", "timestamp"),
    )


class SymbolMetadata(Base):
    """标的元数据。"""
    __tablename__ = "symbol_metadata"

    symbol = Column(String(32), primary_key=True)
    name = Column(String(128))
    exchange = Column(String(32))
    asset_class = Column(String(32))  # crypto/stock/forex/commodity
    first_seen = Column(DateTime)
    last_updated = Column(DateTime)
    metadata_json = Column(String)  # JSON 字符串
```

### 3.2 数据库选择

| 数据库 | 适用 | 配置 |
|--------|------|------|
| SQLite | 单机、≤10 并发用户、开发 | `sqlite:///stockstat.db`（默认） |
| PostgreSQL | 多用户、高并发、生产 | `postgresql://user:pass@host/db` |
| MySQL | 兼容性需求 | `mysql+pymysql://user:pass@host/db` |

**WAL 模式**（SQLite）：
```python
# 启用 WAL 提升并发读
engine = create_engine("sqlite:///stockstat.db",
                       connect_args={"check_same_thread": False})
@event.listens_for(engine, "connect")
def set_wal(dbapi_conn, conn_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

---

## 4. StorageBackend 实现

### 4.1 实现 Foundation 的 StorageBackend Protocol

```python
# storage/backend.py
from stockstat_foundation import StorageBackend
from stockstat_foundation.protocol.task import DataSpec


class StorageBackendImpl:
    """StorageBackend Protocol 实现 — 供 Dispatcher 直连访问。

    当 Dispatcher 与 Storage 同进程部署时，Dispatcher 可直接调用此实现，
    绕过 HTTP，零网络开销。
    """
    name = "sqlalchemy"

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def fetch_ohlcv(self, symbols: list[str], timeframe: str,
                    start: Optional[str] = None, end: Optional[str] = None,
                    source: Optional[str] = None) -> Any:
        """查询 OHLCV 数据，返回 DataFrame。"""
        import pandas as pd
        from ..models.ohlcv import OHLCV

        with self._session_factory() as session:
            query = session.query(OHLCV).filter(
                OHLCV.symbol.in_(symbols),
                OHLCV.timeframe == timeframe,
            )
            if start:
                query = query.filter(OHLCV.timestamp >= start)
            if end:
                query = query.filter(OHLCV.timestamp <= end)
            query = query.order_by(OHLCV.symbol, OHLCV.timestamp)
            rows = query.all()

        if not rows:
            return pd.DataFrame()

        # 转换为 DataFrame
        df = pd.DataFrame([
            {"symbol": r.symbol, "timestamp": r.timestamp,
             "open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume}
            for r in rows
        ])
        # 多 symbol 时返回 dict
        if len(symbols) > 1:
            return {sym: df[df.symbol == sym].drop("symbol", axis=1)
                    for sym in symbols}
        return df.drop("symbol", axis=1)

    def ingest_ohlcv(self, symbol: str, timeframe: str, data: Any) -> int:
        """写入 OHLCV 数据，返回写入行数。"""
        from ..models.ohlcv import OHLCV
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            records = []
            for _, row in data.iterrows():
                records.append(OHLCV(
                    symbol=symbol, timeframe=timeframe,
                    timestamp=row["timestamp"],
                    open=row["open"], high=row["high"],
                    low=row["low"], close=row["close"],
                    volume=row["volume"],
                ))
        else:
            records = data

        with self._session_factory() as session:
            for r in records:
                session.merge(r)  # upsert
            session.commit()
        return len(records)

    def list_symbols(self) -> list[str]:
        from ..models.ohlcv import SymbolMetadata
        with self._session_factory() as session:
            rows = session.query(SymbolMetadata.symbol).all()
            return [r[0] for r in rows]

    def get_metadata(self, symbol: str) -> dict:
        from ..models.ohlcv import SymbolMetadata
        with self._session_factory() as session:
            row = session.query(SymbolMetadata).filter_by(symbol=symbol).first()
            if row is None:
                return {}
            import json
            return {
                "symbol": row.symbol,
                "name": row.name,
                "exchange": row.exchange,
                "asset_class": row.asset_class,
                "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
            }
```

---

## 5. REST API

### 5.1 路由表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/ohlcv` | GET | 查询 OHLCV（Arrow 响应） |
| `/api/v1/ohlcv` | POST | 写入 OHLCV（Arrow 请求体） |
| `/api/v1/symbols` | GET | 列出所有标的 |
| `/api/v1/symbols/{symbol}` | GET | 标的元数据 |
| `/api/v1/ingest` | POST | 从数据源采集并写入 |
| `/health` | GET | 健康检查 |
| `/admin/api/*` | GET | Admin 面板 API |

### 5.2 OHLCV 查询实现

```python
# api/ohlcv.py
from fastapi import APIRouter, Query, Response, HTTPException
from stockstat_foundation import ArrowCodec

router = APIRouter()


@router.get("/api/v1/ohlcv")
async def get_ohlcv(
    symbol: str = Query(..., description="标的符号，逗号分隔多标的"),
    timeframe: str = Query("1d"),
    start: str = Query(None),
    end: str = Query(None),
    source: str = Query(None),
):
    """查询 OHLCV 数据，返回 Arrow IPC 二进制。"""
    from ..storage.backend import StorageBackendImpl
    backend = StorageBackendImpl(get_session_factory())
    symbols = [s.strip() for s in symbol.split(",")]
    df = backend.fetch_ohlcv(symbols, timeframe, start, end, source)
    if df.empty:
        raise HTTPException(404, "No data found")
    arrow_bytes = ArrowCodec().encode(df)
    return Response(content=arrow_bytes,
                    media_type="application/vnd.apache.arrow.file")


@router.post("/api/v1/ohlcv")
async def post_ohlcv(
    req: Request,
    x_symbol: str = Header(...),
    x_timeframe: str = Header(...),
):
    """写入 OHLCV 数据，请求体为 Arrow IPC。"""
    from ..storage.backend import StorageBackendImpl
    body = await req.body()
    df = ArrowCodec().decode(body)
    backend = StorageBackendImpl(get_session_factory())
    rows = backend.ingest_ohlcv(x_symbol, x_timeframe, df)
    return {"rows_written": rows}
```

---

## 6. 数据采集 Adapters

### 6.1 DataSource Protocol

```python
# adapters/base.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class DataSource(Protocol):
    """数据源协议。"""
    name: str

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> "pd.DataFrame": ...
```

### 6.2 Binance 适配器

```python
# adapters/binance.py
class BinanceAdapter:
    """Binance 行情数据适配器。"""
    name = "binance"

    def __init__(self, *, api_key: str = "", api_secret: str = "",
                 testnet: bool = False):
        self._base_url = "https://testnet.binance.vision" if testnet else "https://api.binance.com"
        self._api_key = api_key
        self._api_secret = api_secret

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> "pd.DataFrame":
        """从 Binance 拉取 K 线数据。"""
        import httpx
        import pandas as pd
        from datetime import datetime

        params = {"symbol": symbol, "interval": timeframe, "limit": 1000}
        if start:
            params["startTime"] = int(pd.Timestamp(start).timestamp() * 1000)
        if end:
            params["endTime"] = int(pd.Timestamp(end).timestamp() * 1000)

        resp = httpx.get(f"{self._base_url}/api/v3/klines", params=params)
        resp.raise_for_status()
        data = resp.json()

        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]


ADAPTERS = {
    "binance": BinanceAdapter,
    "yfinance": YFinanceAdapter,
}
```

### 6.3 YFinance 适配器

```python
# adapters/yfinance.py
class YFinanceAdapter:
    """YFinance 适配器 — 股票/ETF 数据。"""
    name = "yfinance"

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> "pd.DataFrame":
        import yfinance as yf
        import pandas as pd

        # timeframe 映射：1d → 1d, 1h → 60m, 5m → 5m
        interval = timeframe
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval)
        df = df.reset_index()
        df = df.rename(columns={"Date": "timestamp", "Datetime": "timestamp"})
        return df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low",
                     "Close": "close", "Volume": "volume"}
        )
```

---

## 7. 数据规范化 Normalizer

### 7.1 字段映射

```python
# normalizer/schema.py
class Normalizer:
    """数据规范化 — 不同源的字段映射、时区对齐。"""

    SCHEMA_MAP = {
        "binance": {
            "timestamp": "timestamp",
            "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        },
        "yfinance": {
            "timestamp": "timestamp",
            "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        },
    }

    def normalize(self, df, source: str) -> "pd.DataFrame":
        """规范化 DataFrame。"""
        mapping = self.SCHEMA_MAP.get(source, {})
        df = df.rename(columns=mapping)
        # 时区对齐：统一为 UTC
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
        # 去重
        df = df.drop_duplicates(subset=["timestamp"])
        return df
```

---

## 8. 调度器 Scheduler

### 8.1 定时采集

```python
# scheduler/collector.py
import threading
import time


class ScheduledCollector:
    """定时数据采集器。"""

    def __init__(self, storage_backend, adapters: dict, interval: int = 3600):
        self._storage = storage_backend
        self._adapters = adapters
        self._interval = interval
        self._subscriptions: list[dict] = []
        self._thread = None
        self._running = False

    def subscribe(self, symbol: str, timeframe: str, source: str = "binance"):
        """订阅定时采集。"""
        self._subscriptions.append({
            "symbol": symbol, "timeframe": timeframe, "source": source,
        })

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            for sub in self._subscriptions:
                try:
                    adapter = self._adapters[sub["source"]]()
                    df = adapter.fetch_ohlcv(sub["symbol"], sub["timeframe"])
                    self._storage.ingest_ohlcv(sub["symbol"], sub["timeframe"], df)
                except Exception as e:
                    # 记录错误，继续下一次
                    pass
            time.sleep(self._interval)
```

---

## 9. Admin 管理面板

### 9.1 Admin 路由

```python
# plugins/admin/router.py
from fastapi import APIRouter

router = APIRouter(prefix="/admin/api")


@router.get("/symbols")
async def list_symbols():
    """列出所有标的（含元数据）。"""
    ...


@router.get("/ohlcv/stats")
async def ohlcv_stats():
    """OHLCV 数据统计（每个 symbol+timeframe 的行数、时间范围）。"""
    ...


@router.get("/ingest/history")
async def ingest_history(limit: int = 100):
    """采集历史记录。"""
    ...


@router.get("/health")
async def health():
    """系统健康检查。"""
    ...


@router.get("/dispatcher/cluster")
async def dispatcher_cluster():
    """Dispatcher 集群拓扑（若 Dispatcher 插件启用）。"""
    ...


@router.get("/dispatcher/tasks")
async def dispatcher_tasks(limit: int = 100, state: str = None):
    """Dispatcher 任务历史。"""
    ...
```

### 9.2 Admin SPA

Admin 前端为静态 SPA（可选）：
- 标的列表 + 元数据
- OHLCV 数据预览
- 采集任务管理
- Dispatcher 集群监控（若启用）
- 任务历史 + 统计

---

## 10. 缓存层

### 10.1 查询缓存

```python
# storage/cache.py
class QueryCache:
    """查询缓存 — 减少 Storage 数据库压力。"""
    def __init__(self, max_size_mb: int = 128):
        self._cache: dict[str, Any] = {}
        self._max_size = max_size_mb * 1024 * 1024
        self._current_size = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._cache.get(key)

    def put(self, key: str, value: Any):
        with self._lock:
            # 简化：按 key 数量限制
            if len(self._cache) > 100:
                self._cache.clear()
            self._cache[key] = value
```

---

## 11. 部署形态

### 11.1 独立 Storage 服务（场景 B/C/D）

```bash
# 启动 Storage
stockstat-backend serve --host 0.0.0.0 --port 8000

# 环境变量
STOCKSTAT_DATABASE_URL=postgresql://user:pass@db/stockstat
STOCKSTAT_ADMIN_ENABLED=true
```

### 11.2 Storage + Dispatcher 同机（场景 C）

```bash
# 启动 Storage + Dispatcher 插件
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_DISPATCHER_QUEUE=memory \
stockstat-backend serve --host 0.0.0.0 --port 8000

# Dispatcher 直接使用 StorageBackendImpl（绕过 HTTP）
```

### 11.3 Storage + Dispatcher + Admin

```bash
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_ADMIN_ENABLED=true \
stockstat-backend serve --host 0.0.0.0 --port 8000
```

### 11.4 StorageApp 工厂

```python
# app.py
class StorageApp:
    """Storage FastAPI 应用工厂。"""

    @staticmethod
    def create(config: Optional[Config] = None) -> "FastAPI":
        from fastapi import FastAPI
        config = config or Config.from_env()

        app = FastAPI(title="StockStat Storage")
        # 数据库引擎
        engine = create_engine(config.database_url)
        SessionFactory = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)

        # StorageBackend 实现
        backend = StorageBackendImpl(SessionFactory)
        app.state.storage_backend = backend

        # 路由
        from .api.ohlcv import router as ohlcv_router
        from .api.symbols import router as symbols_router
        from .api.health import router as health_router
        app.include_router(ohlcv_router)
        app.include_router(symbols_router)
        app.include_router(health_router)

        # 可选：Dispatcher 插件
        if config.dispatcher_enabled:
            from stockstat_dispatcher import DispatcherPlugin
            DispatcherPlugin.mount(app, storage_app=app,
                                   queue_backend=config.dispatcher_queue,
                                   redis_url=config.redis_url)
            # Dispatcher 直连 StorageBackend
            app.state.dispatcher._storage_backend = backend

        # 可选：Admin 面板
        if config.admin_enabled:
            from .plugins.admin.router import router as admin_router
            app.include_router(admin_router)

        # 可选：定时采集
        if config.scheduler_enabled:
            from .scheduler.collector import ScheduledCollector
            collector = ScheduledCollector(backend, ADAPTERS)
            app.state.collector = collector
            collector.start()

        return app
```

### 11.5 Docker

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: stockstat
      POSTGRES_USER: stockstat
      POSTGRES_PASSWORD: secret

  api:
    build: ./packages/storage
    command: stockstat-backend serve --host 0.0.0.0 --port 8000
    environment:
      STOCKSTAT_DATABASE_URL: postgresql://stockstat:secret@db/stockstat
      STOCKSTAT_ADMIN_ENABLED: "true"
      STOCKSTAT_DISPATCHER_ENABLED: "true"
    ports: ["8000:8000"]
    depends_on: [db]
```

---

## 12. 测试体系

### 12.1 测试分层

| 测试文件 | 测试数 | 覆盖 |
|---------|--------|------|
| `test_models.py` | 15 | OHLCV 模型 / 复合主键 / 索引 |
| `test_storage_backend.py` | 25 | fetch_ohlcv / ingest / list_symbols / metadata |
| `test_api_ohlcv.py` | 20 | GET/POST /api/v1/ohlcv / Arrow 编解码 |
| `test_api_symbols.py` | 10 | /api/v1/symbols |
| `test_adapters.py` | 15 | Binance / YFinance 适配器（mock） |
| `test_normalizer.py` | 10 | 字段映射 / 时区对齐 |
| `test_scheduler.py` | 8 | 定时采集 / 订阅 |
| `test_admin.py` | 12 | Admin 路由 |
| `test_app.py` | 10 | StorageApp 工厂 / 插件加载 |
| **合计** | **125** | |

### 12.2 关键测试场景

```python
# OHLCV 写入查询
backend = StorageBackendImpl(session_factory)
df = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
    "open": range(10), "high": range(10),
    "low": range(10), "close": range(10), "volume": range(10),
})
backend.ingest_ohlcv("BTC/USDT", "1d", df)
result = backend.fetch_ohlcv(["BTC/USDT"], "1d")
assert len(result) == 10

# Arrow API roundtrip
client = TestClient(app)
resp = client.get("/api/v1/ohlcv", params={"symbol": "BTC/USDT", "timeframe": "1d"})
df = ArrowCodec().decode(resp.content)
assert len(df) == 10

# Binance 适配器（mock）
with patch("httpx.get") as mock_get:
    mock_get.return_value.json.return_value = [...]
    adapter = BinanceAdapter()
    df = adapter.fetch_ohlcv("BTC/USDT", "1d")
    assert len(df) > 0

# StorageBackend Protocol 检查
from stockstat_foundation import StorageBackend
assert isinstance(backend, StorageBackend)  # runtime_checkable
```

---

## 13. 总结

Storage 是 V3.1 的**数据仓库**，承载：

| 能力 | 实现 |
|------|------|
| OHLCV 持久化 | SQLAlchemy + SQLite/PostgreSQL |
| 数据查询 | REST API + Arrow 响应 |
| 数据采集 | Binance / YFinance 适配器 |
| 数据规范化 | 字段映射 + 时区对齐 |
| 定时采集 | ScheduledCollector |
| StorageBackend | Foundation Protocol 实现（供 Dispatcher 直连） |
| Admin 面板 | Web UI + REST API |
| 查询缓存 | QueryCache |

**核心设计原则**：
1. **计算期间完全空闲** — Storage 只被 Dispatcher 预取 1 次
2. **松耦合 Dispatcher** — HTTP 或 StorageBackend Protocol
3. **独立部署** — 可单独运行，也可加载 Dispatcher 插件
4. **数据规范化** — 统一多源数据格式

**与 V3 的关键差异**：
- V3 嵌入 backend + Dispatcher → V3.1 Storage **独立包**，Dispatcher 松耦合
- V3 无 StorageBackend Protocol → V3.1 **新增**，支持 Dispatcher 直连
- V3 的 Admin 嵌入 → V3.1 保留，可独立启用

---

*本文件定义 Storage 模块的完整架构。Dispatcher 集成见 [DESIGN_ARCH_DISPATCHER_V31.md](DESIGN_ARCH_DISPATCHER_V31.md)，整体架构见 [DESIGN_ARCH_V31.md](DESIGN_ARCH_V31.md)。*
