# StockStat — Programmable Financial Instrument Statistical Computing Platform Design Report

> **Version**: v2.0
> **Date**: 2026-07-18
> **Status**: Implemented (five-layer architecture: Universal Core / Financial Domain / Visualization / Interface / Application; storage backend, computation frontend, DSL auto-reflection, signal processing & nonlinear dynamics module, backtest subsystem, pluggable execution model, CLI, offline mode)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Overall Architecture (Five Layers)](#2-overall-architecture-five-layers)
3. [Layer 0: Universal Core _core](#3-layer-0-universal-core-_core)
4. [Layer 1: Financial Domain _domain](#4-layer-1-financial-domain-_domain)
5. [Layer 2: Visualization _viz](#5-layer-2-visualization-_viz)
6. [Layer 3: Interface _api](#6-layer-3-interface-_api)
7. [Layer 4: Application app](#7-layer-4-application-app)
8. [Storage Backend Design](#8-storage-backend-design)
9. [Scripting Language Design](#9-scripting-language-design)
10. [API Specification](#10-api-specification)
11. [Backtest Subsystem Design](#11-backtest-subsystem-design)
12. [Management Interfaces](#12-management-interfaces)
13. [Test System](#13-test-system)
14. [Technology Stack](#14-technology-stack)
15. [Deployment](#15-deployment)
16. [Project Structure](#16-project-structure)
17. [Development Roadmap](#17-development-roadmap)
- [Appendix A: Data Source Compatibility Matrix](#appendix-a-data-source-compatibility-matrix)
- [Appendix B: OHLCV Data Volume Estimation](#appendix-b-ohlcv-data-volume-estimation)
- [Appendix C: v1.7 vs v2.0 Item-by-Item Comparison](#appendix-c-v17-vs-v20-item-by-item-comparison)
- [Appendix D: Backtest Phase Documentation Index](#appendix-d-backtest-phase-documentation-index)

---

## 1. Project Overview

### 1.1 Project Goals

Build a **user-programmable** stock/cryptocurrency statistical computing platform with core capabilities:

- **Unified data access**: Compatible with multiple data sources through a single unified interface
- **Programmable computation**: Users write logic via Python library or custom DSL
- **Frontend-backend separation**: Storage backend as an independently deployable service; computation frontend as a library with configurable connections
- **Plugin-based extensibility**: Data sources, indicators, cost models, fill models, execution models, and renderers are all plugins with auto-discovery
- **Offline mode**: Frontend can run without a backend, using local storage directly

### 1.2 Design Principles

| Principle | Description |
|-----------|-------------|
| **Universal base** | The core layer (`_core`) is domain-agnostic and reusable for any time-series scenario |
| **Domain layering** | Financial logic (`_domain`) builds on the universal base; never depends upward on the interface layer |
| **Plugin-first** | All extension points go through a unified PluginRegistry with `entry_points` auto-discovery |
| **Event-driven** | Unifies historical replay and real-time streaming under one event model |
| **Protocol-first** | Layers communicate via Protocols; implementations are replaceable with no hardcoded if-else |
| **Zero hard dependency in core** | Compute/backtest core depends only on pandas/numpy/scipy; matplotlib, optuna, PyWavelets, lark are optional extras |
| **Backward compatibility** | v1.7 public API works with zero modifications; `_core`/`_domain`/`_viz`/`_api` are internal (underscore-prefixed) |

### 1.3 Core Feature List

All features implemented:

- Multi-source data access (yfinance direct / ccxt [Binance, Coinbase] / synthetic data)
- OHLCV normalized storage (default SQLite, optional TimescaleDB via Docker)
- Unified REST API querying (JSON / CSV)
- Python computation library (pandas/numpy/scipy integration)
- Expression DSL (SQL-like, based on lark; v2.0 auto-reflects functions from PluginRegistry)
- Built-in technical indicator library (MA / EMA / MACD / RSI / KDJ / ATR / Bollinger / Beta / Sharpe / VaR ...)
- Signal processing & nonlinear dynamics module (CWT / spectral entropy / grey relation / GM(1,1) / transfer entropy / Hurst / sample entropy / permutation entropy)
- Custom indicator registration (v2.0 unified as IndicatorPlugin protocol)
- Computation result export (JSON / CSV / DataFrame)
- Optional visualization layer (protocol-based, unified PlotSpec + ChartProfile; supports heatmap / log axes / subplots / themes)
- Backtest subsystem (multi-instrument / multi-tf / pluggable execution model / visualization / analysis tools / batch backtesting)
- **CLI** (serve / ingest / query / plugins / indicators)
- **Offline mode** (V2Client with local Storage, no HTTP needed)
- In-memory cache (TTL=300s; v2.0 supports Null/Memory/Redis switching)

---

## 2. Overall Architecture (Five Layers)

### 2.1 Five-Layer Architecture Overview

```mermaid
graph TB
    subgraph "Layer 4: Application app/"
        APP_CLI[CLI<br/>serve/ingest/query/plugins]
        APP_SERVER[API Server]
    end

    subgraph "Layer 3: Interface _api/"
        API_DSL[DSL Engine<br/>auto-reflects registry]
        API_CLIENT[V2Client<br/>online + offline mode]
    end

    subgraph "Layer 2: Visualization _viz/"
        VIZ_SPEC[Unified PlotSpec + ChartProfile]
        VIZ_RENDER[Renderer Plugins<br/>Null / Matplotlib]
        VIZ_THEME[Theme System<br/>default / dark / publication]
    end

    subgraph "Layer 1: Financial Domain _domain/"
        DOM_MODEL[Domain Models<br/>OHLCV / Symbol / Quote / Trade]
        DOM_SRC[Data Source Plugins<br/>yfinance / ccxt / synthetic]
        DOM_IND[Indicator Plugins<br/>22 built-in indicators]
        DOM_BT[Backtest Component Plugins<br/>Cost / Fill / Execution]
        DOM_SCHED[Scheduler]
    end

    subgraph "Layer 0: Universal Core _core/"
        CORE_CONTRACT[Protocol Contracts<br/>6 Protocols]
        CORE_PLUGIN[PluginRegistry]
        CORE_CONFIG[Layered Config]
        CORE_EVENT[EventBus + EventReplay]
        CORE_STORAGE[Storage Backend<br/>Memory / SQL]
        CORE_CACHE[Cache Backend<br/>Null / Memory / Redis]
        CORE_CODEC[Codec<br/>JSON / CSV / Arrow / Parquet]
        CORE_LOG[Structured Logging]
        CORE_ERR[Error Classification]
    end

    subgraph "v1.7 Compatibility Layer (public API unchanged)"
        COMPAT[client.py / compute/ / indicators/<br/>backtest/ / plot/ / dsl/ / data_access/ / export/]
    end

    APP_CLI --> API_DSL
    APP_CLI --> API_CLIENT
    APP_SERVER --> COMPAT
    API_DSL --> DOM_IND
    API_CLIENT --> DOM_MODEL

    DOM_MODEL --> VIZ_SPEC
    DOM_IND --> VIZ_SPEC
    DOM_BT --> VIZ_SPEC
    VIZ_SPEC --> VIZ_RENDER

    DOM_SRC --> CORE_PLUGIN
    DOM_IND --> CORE_PLUGIN
    DOM_BT --> CORE_PLUGIN
    VIZ_RENDER --> CORE_PLUGIN

    COMPAT -.->|re-export| DOM_IND
    COMPAT -.->|re-export| DOM_BT
    COMPAT -.->|forward| CORE_STORAGE
```

### 2.2 Inter-Layer Dependency Rules

```mermaid
graph LR
    L4["Layer 4 Application"] --> L3["Layer 3 Interface"]
    L3 --> L2["Layer 2 Visualization"]
    L3 --> L1["Layer 1 Domain"]
    L2 --> L0["Layer 0 Core"]
    L1 --> L0
    L1 -.->|cross-layer forbidden| L3
    L0 -.->|does not depend upward| L1
```

**Iron rules**:
1. Upper layers depend on lower layers; lower layers are unaware of upper layers
2. Layers communicate via Protocols; no concrete implementation imports
3. Cross-layer forbidden: domain cannot call api directly
4. v1.7 compatibility layer (`client.py` etc.) keeps public API unchanged; internals may forward to new architecture

### 2.3 Data Flow

```mermaid
sequenceDiagram
    participant User as User
    participant CLI as CLI / Python Client
    participant API as Interface Layer
    participant Domain as Domain Layer
    participant Core as Core Layer
    participant BE as Storage Backend
    participant Src as Data Source

    Note over BE,Src: Stage 1: Data ingestion (on-demand)
    User->>CLI: stockstat ingest BTC/USDT
    CLI->>API: POST /api/v1/ingest
    API->>BE: trigger adapter
    BE->>Src: fetch_ohlcv(symbol, range)
    Src-->>BE: raw data
    BE->>BE: normalize → store → clear cache

    Note over User,Domain: Stage 2: Computation (online or offline)
    User->>CLI: client.ohlcv() / client.compute.ma()
    CLI->>API: GET /api/v1/ohlcv (online) or local Storage (offline)
    API-->>CLI: normalized OHLCV
    CLI->>Domain: call indicator plugin
    Domain-->>User: result (DataFrame/JSON)
```

---

## 3. Layer 0: Universal Core _core

> **Design principle**: Completely domain-agnostic. Handles time-series, storage, caching, serialization, plugins, events, and configuration primitives.

### 3.1 Protocol Contracts contracts/

Defines all cross-layer communication Protocols (`typing.Protocol`), no implementations:

| Protocol | Responsibility |
|----------|---------------|
| `Plugin` | Universal plugin protocol (name / version / category / initialize / shutdown / health_check) |
| `StorageBackend` | Storage backend (query / write / upsert / delete / count / schema / health_check) |
| `CacheBackend` | Cache backend (get / set / delete / exists / clear / health_check) |
| `Codec` | Serialization codec (encode / decode / media_type) |
| `Renderer` | Renderer (render / show / savefig / available) |
| `EventSubscriber` / `EventPublisher` | Event subscribe/publish |

### 3.2 Plugin Registry plugin/

**Core capabilities**: namespace partitioning, `entry_points` auto-discovery, explicit registration, dependency declaration, lifecycle management, metadata queries.

**vs v1.7**: v1.7 adapters used `if-elif` hardcoded routing (4 branches), indicators used a module-level `_REGISTRY` dict (no namespaces/metadata); v2.0 unifies everything into one registry.

### 3.3 Layered Configuration config/

Sources merged in priority (low → high): built-in defaults → config file (`stockstat.toml`) → environment variables (`STOCKSTAT_*`) → runtime kwargs. All v1.7 environment variables are 100% compatible.

### 3.4 Event Bus + Data Stream events/

| Component | Responsibility |
|-----------|---------------|
| `EventBus` | In-process pub/sub with topic-based routing; synchronous dispatch |
| `Event` | Immutable event object (topic / payload / timestamp / source) |
| `EventReplay` | Reads historical data from storage and replays as events (basis for backtesting) |

**Key design**: Backtest = `EventReplay` reads historical bars → publishes to EventBus → strategy subscribes. Strategy code does not distinguish historical vs real-time.

### 3.5 Storage Backend storage/

| Implementation | Use case |
|---------------|---------|
| `MemoryStorage` | Testing / tiny datasets |
| `SQLStorage` | Default (SQLite / PostgreSQL), bridges v1.7 SQLAlchemy ORM via `_compat.py` |
| `TimescaleStorage` | Massive time-series (Docker, optional Hypertable) |
| `ParquetStorage` | Offline analysis (read-only snapshots) |

### 3.6 Cache cache/

| Implementation | Description |
|---------------|-------------|
| `NullCache` | No caching (testing) |
| `MemoryCache` | In-process TTL cache (default) |
| `RedisCache` | Distributed cache (auto-selected by `config.cache.backend`) |

### 3.7 Codec codec/

| Codec | media_type |
|-------|------------|
| `JsonCodec` | `application/json` |
| `CsvCodec` | `text/csv` |
| `ArrowCodec` | `application/vnd.apache.arrow.file` |
| `ParquetCodec` | `application/vnd.apache.parquet` |

### 3.8 Logging & Errors

| Component | Responsibility |
|-----------|---------------|
| `StructuredLogger` | JSON structured logging with context binding (`bind(symbol="BTC/USDT")`) |
| `AppError` | Exception base class with error code, context, recoverable flag |
| Error subclasses | `DataNotFoundError` / `SymbolNotFoundError` / `AdapterError` / `InvalidParamsError` / `RateLimitedError` / `LookaheadError` / `PluginNotFoundError` |

---

## 4. Layer 1: Financial Domain _domain

### 4.1 Domain Models models/

| Model | Description |
|-------|-------------|
| `OHLCV` | Single bar (symbol / ts / OHLCV / source / timeframe) |
| `Symbol` | Registered symbol (unified_symbol / asset_type / base / quote / sources) |
| `Quote` | Real-time quote (bid / ask / mid auto-calculated) |
| `Trade` | Executed trade (price / qty / side) |

Provides `df_to_ohlcv_list()` / `ohlcv_list_to_df()` bidirectional conversion. Storage-decoupled (not ORM-bound).

### 4.2 Data Source Plugins sources/

`DataSourcePlugin` wraps v1.7 adapters, registered to the `sources` namespace.

| Adapter | name | Network | Purpose |
|---------|------|---------|---------|
| `YahooDirectAdapter` | `yfinance` | Yes | Direct Yahoo Finance API (route default) |
| `CcxtAdapter` | `binance` / `coinbase` | Yes | Via ccxt |
| `SyntheticAdapter` | `synthetic` | No | Fixed-seed synthetic data (offline testing) |

**Route aliases**: API accepts `source=binance`, internally maps to `CcxtAdapter("binance")`. Auto-detects when unspecified: `/` → binance, else → yfinance.

### 4.3 Indicator Plugins indicators/

`IndicatorPlugin` protocol wraps v1.7 indicator functions, registered to `indicators` namespace. 22 built-in indicators auto-registered:

| Category | Indicators |
|----------|-----------|
| Trend | ma / ema / macd |
| Oscillator | rsi / kdj |
| Volatility | std / atr / bollinger |
| Statistics | corr / beta / sharpe / max_drawdown / var / returns / log_returns |
| Nonlinear | wavelet_decompose / spectral_entropy / grey_relation / gm11_predict / transfer_entropy / hurst_dfa / sample_entropy / permutation_entropy |

**Key improvement**: v1.7 required 3 changes per new indicator (function → ComputeEngine method → DSL `_BUILTIN_FUNCS`); v2.0 requires only writing one `IndicatorPlugin` and registering it — ComputeEngine and DSL auto-discover.

### 4.4 Backtest Component Plugins backtest/

`BacktestComponentPlugin` wraps v1.7 components, registered to respective namespaces:

| Namespace | Count | List |
|-----------|-------|------|
| `cost_models` | 8 | Percent / Fixed / Tiered / Min / StampDuty / Zero / MakerTaker / Binance |
| `fill_models` | 7 | NextOpen / NextClose / ThisClose / VWAP / WorstPrice / IntrabarLimit / IntrabarFillModel |
| `execution_models` | 2 | NextBarExecution / IntrabarExecution |

### 4.5 Scheduler scheduler/

v1.7 was an empty stub; v2.0 provides a functional implementation:

- **on-demand**: `trigger_now(symbol, source, ...)` — immediate
- **cron**: `schedule_cron(symbol, cron_expr, ...)` — recurring
- **incremental**: `schedule_incremental(symbol, interval_hours=24)` — incremental update

---

## 5. Layer 2: Visualization _viz

### 5.1 Unified Spec System

v2.0 unifies v1.7's `PlotSpec` + `BacktestChartSpec` dual-track into a single `PlotSpec` + `ChartProfile` presets:

| Component | Responsibility |
|-----------|---------------|
| `PlotSpec` | Backend-agnostic plot spec (series / subplots / markers / log axes / heatmap / figsize / theme) |
| `SeriesSpec` | Single data series (kind: line/bar/scatter/fill/histogram/heatmap) |
| `SubplotSpec` | Subplot panel |
| `ChartProfile` | Named preset that builds a PlotSpec from a BacktestResult |

**6 built-in ChartProfiles**: equity_curve / drawdown / trades_overlay / returns_distribution / monthly_heatmap / dashboard

### 5.2 Renderer Plugins

| Renderer | Status |
|----------|--------|
| `NullRenderer` | ✅ Zero-dependency fallback |
| `MatplotlibRenderer` | ✅ Lazy import |
| `PlotlyRenderer` | Planned (registry entry point reserved) |

### 5.3 Theme System

| Theme | Style |
|-------|-------|
| `default` | White background, standard colors |
| `dark` | Dark background |
| `publication` | Academic publication style (small font) |

Supports `register_theme()` for custom themes.

---

## 6. Layer 3: Interface _api

### 6.1 DSL Auto-Reflection dsl/

`DslEngine` auto-loads all registered indicators from `PluginRegistry` as DSL functions, replacing v1.7's manually-maintained `_BUILTIN_FUNCS` dict.

```python
engine = DslEngine(registry, client=client)
result = engine.eval('SELECT close, ma(close, 20) AS ma20 FROM ohlcv("BTC/USDT", "1d", ...)')
```

Call `engine.refresh()` after registering new indicators to make them DSL-available.

### 6.2 V2Client (Online + Offline)

```python
# Online mode (connects to backend HTTP)
client = V2Client(mode="online", host="192.168.1.100", port=8000)

# Offline mode (local Storage, no backend needed)
client = V2Client(mode="offline", storage=MemoryStorage())
```

Offline mode supports `ohlcv()` / `compute` / `run_dsl()` / `backtest()` / `plot` — all run locally.

---

## 7. Layer 4: Application app

### 7.1 CLI

```bash
stockstat serve --host 0.0.0.0 --port 8000     # Start API server
stockstat ingest BTC/USDT --source binance      # Ingest from CLI
stockstat query BTC/USDT --limit 5              # Query and output
stockstat plugins --namespace indicators        # List registered plugins
stockstat indicators --category nonlinear       # List indicators by category
```

### 7.2 Server Entry

`stockstat serve` is equivalent to `python -m uvicorn stockstat_backend.app:app`.

---

## 8. Storage Backend Design

### 8.1 Data Source Adapter Layer

Adapters follow a plugin-based design, each subclassing `DataSourceAdapter`.

**Adapter instantiation** (`api/routes.py`):

```python
def _get_adapter(source: str):
    if source not in _adapters:
        proxies = settings.proxy.proxies
        if source == "yfinance":
            _adapters[source] = YahooDirectAdapter(proxy=proxies)
        elif source == "binance":
            _adapters[source] = CcxtAdapter("binance", proxies=proxies)
        elif source == "coinbase":
            _adapters[source] = CcxtAdapter("coinbase", proxies=proxies)
        elif source == "synthetic":
            _adapters[source] = SyntheticAdapter()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    return _adapters[source]
```

### 8.2 Proxy Support

| Env var | Default | Description |
|---------|---------|-------------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | Proxy type: `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | (auto by type) | Proxy URL |

### 8.3 Data Normalization Layer

`normalize_ohlcv()` unifies heterogeneous raw data: timezone to UTC, field validation (OHLCV required), dropna cleaning.

**Unified data model** (SQLAlchemy ORM `OHLCV` table):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `Integer PK` | Auto-increment primary key |
| `symbol` | `String(50)` | Unified symbol |
| `ts` | `DateTime(tz=True)` | UTC timestamp |
| `open/high/low/close` | `Float` | OHLC |
| `volume` | `Float` | Volume |
| `source` | `String(50)` | Data source |
| `timeframe` | `String(10)` | Period |
| `ingested_at` | `DateTime(tz=True)` | Ingestion timestamp |

**Unique constraint**: `(symbol, ts, timeframe, source)` composite unique, ensuring upsert idempotency.

### 8.4 Storage Engine

| Deployment mode | `DATABASE_URL` | Characteristics |
|-----------------|----------------|-----------------|
| **Default (local dev)** | `sqlite:///stockstat.db` | Zero external dependency, **data persists across restarts** |
| **Custom path** | `sqlite:////data/stockstat.db` | Custom database file location (see table below) |
| **Docker production** | `postgresql://...@db:5432/stockstat` | TimescaleDB + volume persistence |

**`DATABASE_URL` path rules**:

| `DATABASE_URL` value | Actual storage location |
|---|---|
| `sqlite:///stockstat.db` (default) | `stockstat.db` in the current working directory |
| `sqlite:////data/stockstat.db` | `/data/stockstat.db` (absolute path, 4 slashes) |
| `sqlite:///../data/stockstat.db` | `data/` in the parent directory (relative path) |
| `postgresql://user:pwd@host:5432/db` | Remote PostgreSQL database |

> The SQLite URL format is `sqlite:///` + path. Absolute paths start with `/`, so the concatenation yields 4 slashes: `sqlite:////abs/path`.

Session management: module-level singletons `_engine` + `_SessionLocal`, lazily initialized; `get_session()` context manager auto commit/rollback/close.

### 8.5 Cache Strategy

Default `InMemoryCache` (TTL=300s). `cache.clear()` after successful `POST /api/v1/ingest`. v2.0's `RedisCache` can be enabled via `config.cache.backend = "redis"`.

### 8.6 Scheduler

v2.0 provides a functional scheduler (on-demand / cron / incremental). Current ingestion mode remains on-demand — users explicitly request via `POST /api/v1/ingest` or `client.ingest(...)`.

---

## 9. Scripting Language Design

A **dual-mode** programmable interface: Python library (full-featured) + DSL (lightweight declarative).

### 9.1 DSL Grammar (actual implemented BNF summary)

```
query       : "SELECT" select_list "FROM" source ("WHERE" condition)? ("LIMIT" INT)?
source      : "ohlcv" "(" string ("," string)* ")"
?expr       : expr OP expr | func_call | NAME | NUMBER | STRING
func_call   : NAME "(" (expr ("," expr)*)? ("," kwarg)* ")"
```

> **Capability boundary**: Only supports `SELECT ... FROM ... WHERE ... LIMIT`. Does not support `GROUP BY` / `ORDER BY` / `CASE WHEN`.

### 9.2 DSL Built-in Functions (v2.0 auto-reflection)

v2.0's `DslEngine` auto-loads all registered indicators from `PluginRegistry`. Currently available DSL functions:

| Category | Functions |
|----------|----------|
| Trend | `ma` / `ema` / `macd` |
| Oscillator | `rsi` |
| Volatility | `std` / `atr` / `bollinger` |
| Statistics | `corr` |
| Transform | `returns` / `log_returns` |
| Aggregation | `max` / `min` / `mean` / `sum` / `count` |

---

## 10. API Specification

### 10.1 REST API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check (includes proxy status) |
| `/api/v1/proxy` | GET | Get proxy configuration |
| `/api/v1/sources` | GET | List data sources (includes proxy status) |
| `/api/v1/ingest` | POST | Trigger data ingestion |
| `/api/v1/ohlcv` | GET | Query OHLCV data (json/csv) |
| `/api/v1/symbols` | GET | List registered symbols |
| `/api/v1/symbols/{symbol}` | GET | Symbol detail |

### 10.2 Core API — GET /api/v1/ohlcv

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | yes | Unified symbol |
| `source` | string | no | Data source; auto-detected when omitted |
| `start` / `end` | string | no | Time range |
| `timeframe` | string | no | Default `1d` |
| `limit` | int | no | Max rows |
| `format` | string | no | `json` (default) / `csv` |

### 10.3 Core API — POST /api/v1/ingest

Triggers backend ingestion and storage. Clears cache on success. Response: `{"symbol": "AAPL", "source": "yfinance", "ingested": 250}`

---

## 11. Backtest Subsystem Design

> The backtest subsystem lives in `stockstat.backtest` (v1.7 compatibility layer); components are registered to `PluginRegistry` in v2.0.

### 11.1 Design Goals

| Goal | Description |
|------|-------------|
| Configurable | Custom strategies, multi-instrument groups, multi-timeframe bars, reuse compute-library indicators |
| Programmability first | `Strategy` base class + `@strategy` decorator + `IntrabarMixin` |
| Zero hard dependency | Core depends only on pandas/numpy; optuna/matplotlib are extras |
| Lookahead protection | `on_bar(t)` can only access `≤ t` data; default `t+1` open fill |
| Pluggable execution | `ExecutionModel` ABC: `NextBarExecution` (default) / `IntrabarExecution` |
| Backward compatible | All new params have defaults; existing code needs zero modification |

### 11.2 Core Interface Signature

```python
class BacktestEngine:
    def __init__(self,
                 data: dict,                            # {symbol: {tf: df}} or Universe
                 strategy: Strategy,
                 initial_cash: float = 1_000_000.0,
                 cost_model: Optional[CostModel] = None,    # defaults to PercentCost()
                 fill_model: Optional[FillModel] = None,    # defaults to NextOpenFill()
                 benchmark: Optional[str] = None,
                 trade_on: str = "open",
                 allow_short: bool = False,
                 lookahead_audit: bool = False,
                 seed: int = 0,
                 compute_engine: Optional[ComputeEngine] = None,
                 periods_per_year: Optional[int] = None,
                 execution_model: Optional[ExecutionModel] = None): ...
    def run(self) -> BacktestResult: ...
```

### 11.3 Cost & Fill Models

**Cost models** (8 types, registered to `cost_models` namespace): PercentCost / FixedCost / TieredCost / MinCost / StampDutyCost / ZeroCost / MakerTakerCost / BinanceCost (4 presets)

**Fill models** (7 types, registered to `fill_models` namespace): NextOpenFill / NextCloseFill / ThisCloseFill / VWAPFill / WorstPriceFill / IntrabarLimitFill / IntrabarFillModel

### 11.4 Pluggable Execution Model

`ExecutionModel` decides how orders fill within a bar. `IntrabarExecution` resolves 5 structural gaps:

| Gap | Resolution |
|-----|------------|
| Gap-1 Fill-time tracking | `Fill.sub_bar_ts` + `Fill.sub_bar_index` |
| Gap-2 Same-bar entry+exit | Full lifecycle within parent bar |
| Gap-3 Post-fill exit scan | `define_exits()` + `_scan_exits()` |
| Gap-4 Both-fill→double-cancel | `register_oco_mutual()` |
| Gap-5 SL before TP | `Order.priority` field |

### 11.5 Backtest Visualization

9 chart types: `equity_curve` / `drawdown` / `trades_overlay` / `returns_distribution` / `monthly_heatmap` / `yearly_returns` / `parameter_heatmap` / `underwater_curve` / `dashboard`.

### 11.6 Analysis Tools

- `BacktestAnalyzer`: subperiod / regime / rolling / trade_analysis_by_exit
- `StrategyBatchRunner`: multi-strategy × multi-fee batch backtesting
- `fee_sweep()` / `maker_taker_sweep()`
- `dca_equity()` DCA benchmark

---

## 12. Management Interfaces

### 12.1 TUI Terminal Management Interface

`stockstat tui` provides an interactive terminal interface for browsing and managing data on the Storage Server. No Python scripting needed for routine management.

**Menu functions**:

| Menu item | Function |
|-----------|----------|
| Browse symbols | List all registered symbols (table: symbol/type/sources) |
| Query OHLCV | Query last N rows for a symbol |
| Ingest new data | Interactive data ingestion (symbol/source/date range) |
| Data statistics | Data overview statistics |
| List data sources | List available data sources |
| View proxy config | View proxy configuration |

**Design**:
- Based on `rich` library (optional: `pip install rich`), provides colored tables and panels
- Falls back to plain-text menu when `rich` is not installed
- Connects to Storage Server via HTTP, shares the same backend as CLI `stockstat ingest/query`

```mermaid
graph LR
    TUI["stockstat tui<br/>--host 192.168.1.100"] -->|"HTTP REST"| SRV["Storage Server<br/>:8000"]
    TUI -->|"rich table rendering"| USER["Terminal"]
```

### 12.2 Web Admin Interface

The Storage Server has a built-in web admin interface. Access via browser at `http://storage-server:8000/admin/`.

**Management scope**:

| Function | Endpoint | Description |
|----------|----------|-------------|
| **Overview dashboard** | `/admin/` | Symbol count, row count, per-source distribution, health status |
| **Symbol browse** | `/admin/api/symbols` | List all symbols + row count + date range |
| **Data delete** | `DELETE /admin/api/symbols/{symbol}` | Delete all data for a symbol |
| **Data ingest** | `POST /admin/api/ingest` | Trigger ingestion from the web UI |
| **Config view** | `/admin/api/config` | View DB URL / proxy / cache config (password masked) |
| **Health monitor** | `/admin/api/health` | DB connection / cache status / proxy status |
| **Data stats** | `/admin/api/stats` | Total symbols / total rows / per-source distribution |
| **Source list** | `/admin/api/sources` | Available data sources |

**Design points**:
- Management logic runs in-process on the backend (directly accesses Storage/Cache), no HTTP forwarding
- Web frontend is pure static HTML+JS (no Node build chain), served by FastAPI
- Database URL passwords are automatically masked

```mermaid
graph TB
    subgraph "User Browser"
        WEB["Web UI<br/>http://host:8000/admin/"]
    end

    subgraph "Storage Server Process"
        API["FastAPI REST<br/>(data query/ingest)"]
        ADMIN["Admin Route Plugin<br/>/admin/api/*"]
        STATIC["Static HTML+JS<br/>/admin/"]
        DB["Storage/Cache"]
    end

    WEB -->|"HTTP"| STATIC
    WEB -->|"fetch API"| ADMIN
    ADMIN -->|"in-process call"| DB
    API -->|"in-process call"| DB
```

**Why an API plugin, not a Client**: Management operations (config viewing / cache status / data deletion) must execute within the Storage Server process. A Client cannot access process-level state over the network. Admin routes call `settings` / `ohlcv_repo` / `cache` directly, with zero network overhead.

---

## 13. Test System

| Test file | Coverage | Count |
|-----------|----------|-------|
| `test_v2_core.py` | Core layer (contracts/plugin/config/events/storage/cache/codec/errors/logging) | 49 |
| `test_v2_domain.py` | Domain layer (models/sources/indicators/backtest/scheduler) | 27 |
| `test_v2_viz.py` | Visualization layer (Spec/ChartProfile/renderers/themes) | 23 |
| `test_v2_api.py` | Interface layer (DSL reflection/V2Client offline/CLI) | 17 |
| `test_frontend.py` | v1.7 indicators / DSL / viz protocol / serialization | 31 |
| `test_nonlinear.py` | 8 nonlinear functions + 3 PlotSpec factories | 37 |
| `test_backtest_*.py` (16 files) | Full backtest suite | 261 |
| `test_backend.py` | Backend API / adapters / storage / cache / proxy | 15 |
| `test_integration.py` | Classic stats + PAXG weekend correlation (real data) | 17 |
| `test_matplotlib_charts.py` | matplotlib chart generation | 12 |
| **Total** | | **489** |

---

## 14. Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend framework | FastAPI | Native async, OpenAPI docs, high performance |
| ORM | SQLAlchemy 2.0 | Multi-backend switching, declarative models |
| Default database | SQLite | Zero external dependency, auto-reads on restart |
| Production database | TimescaleDB (PostgreSQL 16) | Docker deployment, time-series optimization |
| Cache | InMemoryCache (default) / Redis (optional) | Zero-dependency default; Redis attachable |
| Compute core | pandas + numpy | De-facto standard |
| Statistics extension | scipy | Spectral entropy, hypothesis testing (core dep) |
| DSL parser | lark | EBNF-friendly (optional extra) |
| Data transfer | JSON / CSV / Arrow / Parquet | v2.0 Codec protocol unified |
| Visualization | matplotlib (optional extra) | Protocol-based adapter, lazy import |
| Deployment | Docker Compose | One-command backend stack deployment |

---

## 15. Deployment

### 14.1 Local Development (default SQLite, zero external deps)

```bash
# 1. Install backend
cd backend && pip install -e .

# 2. (Optional) Enable proxy
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. Start API service
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
# Or using v2.0 CLI:
stockstat serve --host 0.0.0.0 --port 8000

# 4. Install frontend library (another terminal)
cd frontend && pip install -e .

# 5. (Optional) Install extras
pip install -e "frontend/[matplotlib]"       # Visualization
pip install -e "frontend/[dsl]"              # DSL parser
pip install -e "frontend/[signal_processing]" # PyWavelets
```

### 14.2 Network Remote Deployment (storage service on a separate machine)

The backend can be deployed independently on any networked machine; other machines access via HTTP:

```bash
# === On the storage server (e.g. 192.168.1.100) ===
cd backend && pip install -e .

# Specify database storage location (optional; default is stockstat.db in CWD)
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"
#   SQLite absolute path: sqlite:/// + /abs/path = 4 slashes
#   PostgreSQL:           postgresql://user:pwd@host:5432/dbname

# Restarts automatically read previously downloaded data
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
```

```python
# === On user machines ===
from stockstat import StockStatClient
client = StockStatClient(host="192.168.1.100", port=8000)

# Manage data via API
client.ingest("BTC/USDT", source="binance", start="2024-01-01")  # Download
data = client.ohlcv("BTC/USDT")                                   # Query
symbols = client.symbols()                                        # List downloaded symbols
```

```bash
# Or via CLI
stockstat ingest BTC/USDT --source binance --start 2024-01-01
stockstat query BTC/USDT --limit 5
```

**Data persistence guarantee**:
- SQLite mode: data written to `stockstat.db` file; file persists across service restarts; `Base.metadata.create_all()` auto-connects to the existing database
- Docker mode: data written to `db_data` volume; survives container deletion
- In-process cache (TTL=300s) clears on restart but only affects performance, not data

### 14.3 Docker Production Deployment (TimescaleDB + Redis)

```yaml
# docker-compose.yml core structure
services:
  db:
    image: timescale/timescaledb:latest-pg16
    volumes: [db_data:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U stockstat"] }
  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://stockstat:${DB_PASSWORD}@db:5432/stockstat
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
  scheduler:
    build: ./backend
    command: python -c "import time; print('Scheduler stub'); time.sleep(3600)"
volumes:
  db_data:
  redis_data:
```

> **Note**: The `api` service code currently uses `InMemoryCache`; even with `REDIS_URL` configured, Redis is not auto-wired (requires extending `storage/cache.py`). The `scheduler` is a placeholder process.

### 14.4 Offline Mode (no backend needed)

v2.0's `V2Client` supports offline mode, using local Storage directly:

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())
# ohlcv / compute / run_dsl / backtest / plot all run locally
```

---

## 16. Project Structure

```
StockStatistic/
├── backend/                              # Storage backend service (independently deployable)
│   ├── stockstat_backend/
│   │   ├── app.py                        # FastAPI application entry
│   │   ├── config.py                     # Settings + ProxyConfig
│   │   ├── api/routes.py                 # REST routes
│   │   ├── adapters/                     # Data source adapters
│   │   ├── models/ohlcv.py               # ORM
│   │   ├── storage/                      # database / repository / cache
│   │   ├── normalizer/                   # Data normalization
│   │   └── scheduler/                    # Scheduler (v1.7 stub)
│   ├── tests/
│   └── pyproject.toml
│
├── frontend/                             # Computation frontend library
│   ├── stockstat/
│   │   ├── __init__.py                   # Public API: StockStatClient
│   │   ├── client.py                     # v1.7 compatibility layer facade
│   │   ├── config.py                     # Config dataclass
│   │   ├── compute/                      # ComputeEngine
│   │   ├── indicators/                   # Indicator implementations
│   │   ├── backtest/                     # Backtest engine (27 files)
│   │   ├── plot/                         # Visualization (PlotSpec + matplotlib)
│   │   ├── dsl/                          # DSL parser
│   │   ├── data_access/                  # DataClient
│   │   ├── export/                       # Serialization
│   │   │
│   │   ├── _core/                        # Layer 0: Universal Core (v2.0)
│   │   │   ├── contracts/                #   6 Protocols
│   │   │   ├── plugin/                   #   PluginRegistry
│   │   │   ├── config/                   #   Layered config
│   │   │   ├── events/                   #   EventBus + EventReplay
│   │   │   ├── storage/                  #   Memory + SQL storage
│   │   │   ├── cache/                    #   Null + Memory + Redis
│   │   │   ├── codec/                    #   JSON + CSV + Arrow + Parquet
│   │   │   ├── logging.py                #   Structured logging
│   │   │   ├── errors.py                 #   Error classification
│   │   │   └── _compat.py                #   v1.7 SQLAlchemy bridge
│   │   │
│   │   ├── _domain/                      # Layer 1: Financial Domain (v2.0)
│   │   │   ├── models/                   #   OHLCV / Symbol / Quote / Trade
│   │   │   ├── sources/                  #   Data source plugins
│   │   │   ├── indicators/               #   IndicatorPlugin protocol
│   │   │   ├── backtest/                 #   Backtest component plugins
│   │   │   └── scheduler/                #   Scheduler
│   │   │
│   │   ├── _viz/                         # Layer 2: Visualization (v2.0)
│   │   │   ├── specs/                    #   Unified PlotSpec + ChartProfile
│   │   │   ├── renderers/                #   Renderer plugins
│   │   │   └── themes/                   #   Theme system
│   │   │
│   │   ├── _api/                         # Layer 3: Interface (v2.0)
│   │   │   ├── dsl/                      #   DSL auto-reflection engine
│   │   │   └── client/                   #   V2Client (online + offline)
│   │   │
│   │   └── app/                          # Layer 4: Application (v2.0)
│   │       └── cli.py                    #   CLI entry point
│   │
│   ├── tests/                            # 489 tests
│   │   ├── test_v2_core.py               #   49 core layer tests
│   │   ├── test_v2_domain.py             #   27 domain layer tests
│   │   ├── test_v2_viz.py                #   23 visualization tests
│   │   ├── test_v2_api.py                #   17 interface layer tests
│   │   ├── test_frontend.py              #   31 v1.7 frontend tests
│   │   ├── test_nonlinear.py             #   37 nonlinear tests
│   │   ├── test_backtest_*.py            #   261 backtest tests
│   │   ├── test_integration.py           #   17 integration tests
│   │   └── test_matplotlib_charts.py     #   12 chart tests
│   └── pyproject.toml
│
├── docker-compose.yml
├── docs/
│   ├── USAGE.md / USAGE_CN.md
│   ├── backtest/                         # Backtest phase docs
│   └── images/                           # Chart output
├── reports/                              # Test reports + v2.0 implementation reports
├── working/                              # PAXG research working directory
├── DESIGN.md / DESIGN_CN.md
├── README.md / README_CN.md
└── LICENSE                               # GPLv3
```

---

## 17. Development Roadmap

| Phase | Content | Status |
|-------|---------|--------|
| **P0** | Storage backend MVP (SQLAlchemy + yfinance/ccxt/synthetic + REST API) | ✅ |
| **P1** | Computation frontend MVP (StockStatClient + 5 core indicators) | ✅ |
| **P2** | DSL parser (lark + 15 built-in functions) | ✅ |
| **P3** | Full indicator library (trend/oscillator/volatility/statistics) | ✅ |
| **P4** | Visualization layer (PlotSpec + PlotRenderer + matplotlib) | ✅ |
| **NL** | Signal processing & nonlinear dynamics (8 functions + 3 PlotSpec factories) | ✅ |
| **BT-0~14** | Backtest subsystem (interface→MVP→portfolio→multi-tf→cost→metrics→optimizer→intrabar) | ✅ |
| **BT-V0~V3** | Backtest visualization (9 charts + dashboard) | ✅ |
| **v2.0 Phase 1** | Universal core layer `_core` (contracts/plugin/config/events/storage/cache/codec) | ✅ |
| **v2.0 Phase 2** | Financial domain layer `_domain` (models/sources/indicators/backtest/scheduler) | ✅ |
| **v2.0 Phase 3** | Visualization layer `_viz` (unified Spec + ChartProfile + renderers + themes) | ✅ |
| **v2.0 Phase 4** | Interface layer `_api` (DSL auto-reflection + V2Client offline + CLI) | ✅ |
| **Future** | Event-driven backtest rewrite / real-time data streaming / Plotly renderer / entry_points discovery | ⏳ |

---

## Appendix A: Data Source Compatibility Matrix

| Data source | Asset type | Network | Status | History depth | Notes |
|-------------|------------|---------|--------|---------------|-------|
| yfinance direct | US stocks/ETF/index | Yes | ✅ | 10+ years | Route default |
| ccxt - Binance | Crypto | Yes | ✅ | Full history | `source=binance` |
| ccxt - Coinbase | Crypto | Yes | ✅ | Full history | `source=coinbase` |
| SyntheticAdapter | Mixed | No | ✅ | On-demand | Fixed seed |
| Alpha Vantage | Global stocks | Yes | ❌ Planned | — | — |
| Tushare | A-shares | Yes | ❌ Planned | — | — |

## Appendix B: OHLCV Data Volume Estimation

| Scope | Timeframe | Rows (1 year) | Storage estimate |
|-------|-----------|---------------|------------------|
| 1 symbol | daily | ~250 | ~2 KB |
| 1 symbol | 1-minute | ~525,000 | ~15 MB |
| Binance USDT pairs (1,479) | daily | ~370,000 | ~3 MB |
| Binance USDT pairs (1,479) | 1-minute | ~776M | ~22 GB |

> SQLite is suitable for small single-machine workloads; for GB-scale, switch to TimescaleDB + Hypertable compression (reduces to 10%~20%).

## Appendix C: v1.7 vs v2.0 Item-by-Item Comparison

| Dimension | v1.7 | v2.0 |
|-----------|------|------|
| **Layering** | 2 layers (backend / frontend) | 5 layers (core / domain / viz / api / app) |
| **Plugin mechanism** | Adapter if-elif / indicator dict / renderer if-elif | Unified PluginRegistry + entry_points |
| **Storage** | Direct SQLAlchemy ORM | StorageBackend Protocol (Memory/SQL/Timescale/Parquet) |
| **Cache** | InMemoryCache only | CacheBackend Protocol (Null/Memory/Redis) |
| **Serialization** | JSON/CSV scattered in 3 places | Codec protocol unified (+Arrow/Parquet) |
| **DSL functions** | Manually maintained `_BUILTIN_FUNCS` 15 | Auto-reflected from PluginRegistry |
| **Spec system** | PlotSpec + BacktestChartSpec dual-track | Unified PlotSpec + ChartProfile |
| **Config** | Env vars scattered across 3 dataclasses | Layered merge (defaults→file→env→kwargs) |
| **CLI** | None | serve/ingest/query/plugins/indicators |
| **Offline mode** | Must connect to HTTP | V2Client local Storage |
| **New indicator effort** | 3 changes | 1 change (register to registry) |
| **Backward compatibility** | — | v1.7 public API zero modification |

## Appendix D: Backtest Phase Documentation Index

| Phase | Doc | Test |
|-------|-----|------|
| BT-0~7 | [docs/backtest/BT0_CN.md](docs/backtest/BT0_CN.md) ~ [BT7_CN.md](docs/backtest/BT7_CN.md) | test_backtest_iface ~ strategies |
| BT-8~10 | [docs/backtest/BT8_CN.md](docs/backtest/BT8_CN.md) ~ [BT10_CN.md](docs/backtest/BT10_CN.md) | test_backtest_p0/p1/p2 |
| BT-11~14 | [docs/backtest/BT11_BT14_CN.md](docs/backtest/BT11_BT14_CN.md) | test_backtest_intrabar |
| BT-V0~V3 | [docs/backtest/BTV0_CN.md](docs/backtest/BTV0_CN.md) ~ [BTV3_CN.md](docs/backtest/BTV3_CN.md) | test_backtest_viz_* |
| BT-V Online | [docs/backtest/BT_VIZ_ONLINE_REPORT_CN.md](docs/backtest/BT_VIZ_ONLINE_REPORT_CN.md) | test_backtest_viz_online |

---

*v2.0 design document; the code implementation is authoritative.*
