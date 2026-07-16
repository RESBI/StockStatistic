# StockStat — Programmable Financial Instrument Statistical Computing Platform Design Report

> **Version**: v1.4  
> **Date**: 2026-07-16  
> **Status**: Design Phase (backtest visualization subsystem added)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Overall Architecture](#2-overall-architecture)
3. [Storage Backend Design](#3-storage-backend-design)
4. [Computation Frontend Design](#4-computation-frontend-design)
5. [Scripting Language Design](#5-scripting-language-design)
6. [API Specification](#6-api-specification)
7. [Test Cases](#7-test-cases)
8. [Technology Stack](#8-technology-stack)
9. [Deployment](#9-deployment)
10. [Project Structure](#10-project-structure)
11. [Development Roadmap](#11-development-roadmap)
12. [Backtest Subsystem Design](#12-backtest-subsystem-design)
13. [Backtest Visualization Subsystem Design](#13-backtest-visualization-subsystem-design)
14. [Backtest Phase Documentation Index](#14-backtest-phase-documentation-index)

---

## 1. Project Overview

### 1.1 Project Goals

Build a **user-programmable** stock/cryptocurrency instrument statistical computing platform with the following core capabilities:

- **Unified Data Access**: Compatible with multiple data sources (stock exchanges, crypto exchanges, third-party APIs), exposing a unified interface to upper layers
- **Programmable Computation**: Users can write statistical computation logic via a Python library or a custom DSL
- **Frontend-Backend Separation**: The storage backend runs as an independently deployable service; the computation frontend is a library that connects via configuration
- **Extensibility**: Data source adapters and indicator algorithms are plugin-based

### 1.2 Design Principles

| Principle | Description |
|-----------|-------------|
| **Data-Computation Separation** | The storage backend handles only data ingestion, storage, and querying; all computation logic runs in the frontend library |
| **Unified Abstraction** | Data from heterogeneous sources is normalized into a consistent OHLCV model |
| **Programmability First** | No built-in fixed strategies; rich primitives let users compose freely |
| **Progressive Complexity** | Simple queries via one-line DSL; complex analysis via full-power Python library |
| **Reproducibility** | Each computation records the data snapshot version and parameters for reproducible results |

### 1.3 Core Feature Checklist

```
[ ] Multi-source data ingestion (yfinance / Alpha Vantage / Tushare / ccxt / custom)
[ ] OHLCV normalized storage (TimescaleDB)
[ ] Unified REST API query
[ ] Python computation library (pandas/numpy integration)
[ ] Expression DSL (SQL-like statistical query language)
[ ] Built-in technical indicator library (MA / EMA / RSI / MACD / ATR / Beta / Sharpe ...)
[ ] Custom indicator registration mechanism
[ ] Computation result export (JSON / CSV / DataFrame)
[ ] Optional visualization layer (protocol-based; matplotlib as optional extras, core zero-dependency)
[ ] Data caching and incremental updates
```

---

## 2. Overall Architecture

### 2.1 Architecture Overview

```mermaid
graph TB
    subgraph "Data Sources"
        DS1["yfinance<br/>US Stocks/ETF"]
        DS2["Alpha Vantage<br/>Global Stocks"]
        DS3["Tushare<br/>A-Shares"]
        DS4["ccxt<br/>100+ Crypto Exchanges"]
        DS5["Custom Adapter"]
    end

    subgraph "Storage Backend (Independently Deployable Service)"
        direction TB
        DA["Data Source Adapters"]
        NL["Normalization Layer"]
        SE["Storage Engine<br/>TimescaleDB"]
        API["Unified API Layer<br/>FastAPI REST"]
        SCHED["Scheduler<br/>Scheduled Ingest / Incremental Update"]
        CACHE["Cache Layer<br/>Redis"]

        DA --> NL --> SE
        SCHED --> DA
        SE <--> CACHE
        API --> SE
        API <--> CACHE
    end

    subgraph "Computation Frontend (Python Library)"
        direction TB
        CONN["Connection Manager"]
        DAL["Data Access Layer"]
        CE["Compute Engine"]
        DSL["DSL Parser"]
        IL["Indicator Library"]
        EXP["Export"]

        CONN --> DAL
        DSL --> CE
        DAL --> CE
        IL --> CE
        CE --> EXP
    end

    subgraph "User Layer"
        U1["Python Script"]
        U2["DSL Script"]
        U3["Jupyter Notebook"]
    end

    DS1 & DS2 & DS3 & DS4 & DS5 --> DA
    API -.->|"HTTP/REST"| DAL
    U1 & U2 & U3 --> CE
```

### 2.2 Component Responsibilities

```mermaid
graph LR
    subgraph Storage["Storage Backend (Service Process)"]
        S1["Data Ingestion"]
        S2["Normalization"]
        S3["Persistent Storage"]
        S4["Query Service"]
        S1 --> S2 --> S3 --> S4
    end

    subgraph Compute["Computation Frontend (Python Library / In-Process)"]
        C1["Data Fetch"]
        C2["Computation Execution"]
        C3["Result Output"]
        C1 --> C2 --> C3
    end

    S4 -.->|"REST API<br/>JSON/Arrow"| C1
```

### 2.3 Data Flow

```mermaid
sequenceDiagram
    participant User as User Script
    participant FE as Computation Frontend
    participant BE as Storage Backend
    participant Src as Data Source

    Note over BE,Src: Phase 1: Data Ingestion (async/scheduled)
    BE->>Src: fetch_ohlcv(symbol, range)
    Src-->>BE: Raw data
    BE->>BE: Normalize → Store

    Note over User,FE: Phase 2: Computation Request
    User->>FE: run(script / python code)
    FE->>BE: GET /api/v1/ohlcv?symbol=...&...
    BE-->>FE: Normalized OHLCV data
    FE->>FE: Execute computation logic
    FE-->>User: Result (DataFrame/JSON)
```

---

## 3. Storage Backend Design

### 3.1 Data Source Adapter Layer

Data source adapters use a **plugin-based** design. Each adapter implements a unified interface and supports hot registration.

```mermaid
classDiagram
    class DataSourceAdapter {
        <<interface>>
        +name: str
        +source_type: str
        +fetch_ohlcv(symbol, start, end, timeframe) ~ DataFrame
        +fetch_symbols() ~ list~SymbolInfo
        +supports(symbol) ~ bool
        +health_check() ~ bool
    }

    class YFinanceAdapter {
        +name = "yfinance"
        +source_type = "stock"
        +fetch_ohlcv() 
    }

    class YahooDirectAdapter {
        +name = "yfinance"
        +source_type = "stock"
        +proxy: dict
        +fetch_ohlcv()
    }

    class CcxtAdapter {
        +name = "ccxt"
        +source_type = "crypto"
        +exchange: str
        +fetch_ohlcv()
    }

    class AlphaVantageAdapter {
        +name = "alphavantage"
        +api_key: str
        +fetch_ohlcv()
    }

    class TushareAdapter {
        +name = "tushare"
        +api_key: str
        +fetch_ohlcv()
    }

    class CustomAdapter {
        +name = "custom"
        +config: dict
        +fetch_ohlcv()
    }

    DataSourceAdapter <|.. YFinanceAdapter
    DataSourceAdapter <|.. YahooDirectAdapter
    DataSourceAdapter <|.. CcxtAdapter
    DataSourceAdapter <|.. AlphaVantageAdapter
    DataSourceAdapter <|.. TushareAdapter
    DataSourceAdapter <|.. CustomAdapter
```

**Adapter Registration Mechanism**:

```python
# Storage backend config example (config.yaml)
data_sources:
  - name: yfinance
    type: stock
    enabled: true
    
  - name: binance
    type: crypto
    adapter: ccxt
    config:
      exchange: binance
      rate_limit: 10  # requests/second
    
  - name: alphavantage
    type: stock
    enabled: true
    config:
      api_key: ${ALPHA_VANTAGE_KEY}
    
  - name: tushare
    type: stock
    enabled: true
    config:
      api_key: ${TUSHARE_TOKEN}
      market: A-Shares
```

### 3.1.1 Proxy Support

The storage backend supports configuring HTTP/SOCKS5 proxies for all data source adapters, **disabled by default**. When enabled, all outbound data fetching requests (yfinance, ccxt, etc.) are routed through the proxy.

| Design Constraint | Description |
|-------------------|-------------|
| **Disabled by default** | When `STOCKSTAT_PROXY_ENABLED` is unset or false, all adapters connect directly |
| **Dual-protocol support** | Supports both `http` and `socks5` proxy types |
| **Default addresses** | HTTP defaults to `http://127.0.0.1:8889`; SOCKS5 defaults to `socks5://127.0.0.1:1089` |
| **Unified injection** | Proxy config is injected at adapter instantiation, transparent to upper layers |

```mermaid
graph LR
    subgraph "ProxyConfig"
        PC["ProxyConfig<br/>enabled / url / proxy_type"]
    end
    
    subgraph "Adapter Injection"
        YD["YahooDirectAdapter<br/>requests.Session.proxies"]
        CC["CcxtAdapter<br/>exchange.proxies"]
        SY["SyntheticAdapter<br/>no proxy needed"]
    end
    
    PC --> YD
    PC --> CC
    PC -.->|"enabled=false<br/>proxies=None"| YD
    PC -.->|"enabled=false<br/>proxies=None"| CC
```

**Environment Variable Configuration**:

| Env Var | Default | Description |
|---------|---------|-------------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | Proxy type: `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | (auto-filled by type) | Proxy URL; uses default when unset |

```bash
# Enable HTTP proxy (default address)
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
# STOCKSTAT_PROXY_URL defaults to http://127.0.0.1:8889

# Enable SOCKS5 proxy (default address)
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=socks5
# STOCKSTAT_PROXY_URL defaults to socks5://127.0.0.1:1089

# Custom proxy address
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://192.168.1.100:8080
```

**Querying Proxy Status via REST API**:

```
GET /api/v1/proxy
→ {"enabled": true, "url": "http://127.0.0.1:8889", "proxy_type": "http"}

GET /api/v1/health
→ {"status": "ok", "proxy": {"enabled": true, "url": "http://127.0.0.1:8889", "proxy_type": "http"}}
```

### 3.2 Data Normalization Layer

Raw data formats vary across data sources. The normalization layer unifies them into the internal canonical format.

```mermaid
graph LR
    subgraph "Raw Data (Heterogeneous)"
        R1["yfinance<br/>Datetime/Open/High/Low/Close/Adj Close/Volume"]
        R2["ccxt<br/>timestamp(ms)/open/high/low/close/vol"]
        R3["tushare<br/>trade_date/open/high/low/close/vol/amount"]
    end

    subgraph "Normalization Layer"
        SM["Symbol Mapper"]
        TF["Timeframe Aligner"]
        TZ["Timezone Unifier<br/>UTC Normalization"]
        FV["Field Validator"]
    end

    subgraph "Normalized Output"
        STD["Unified OHLCV<br/>symbol / ts(UTC) / open / high / low / close / volume / source"]
    end

    R1 & R2 & R3 --> SM --> TF --> TZ --> FV --> STD
```

**Unified Data Model**:

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `VARCHAR` | Unified symbol identifier, e.g. `BTC/USDT`, `AAPL`, `600000.SH` |
| `ts` | `TIMESTAMPTZ` | UTC timestamp |
| `open` | `NUMERIC` | Open price |
| `high` | `NUMERIC` | High price |
| `low` | `NUMERIC` | Low price |
| `close` | `NUMERIC` | Close price |
| `volume` | `NUMERIC` | Trading volume |
| `source` | `VARCHAR` | Data source identifier |
| `timeframe` | `VARCHAR` | Time period `1m/5m/15m/1h/4h/1d/1w` |

**Symbol Mapping Tables**:

```mermaid
erDiagram
    SYMBOL_REGISTRY ||--o{ OHLCV : "has data"
    SYMBOL_REGISTRY ||--|| SYMBOL_ALIAS : "maps from"
    
    SYMBOL_REGISTRY {
        string unified_symbol PK "BTC/USDT"
        string asset_type "crypto"
        string base_asset "BTC"
        string quote_asset "USDT"
        string description "Bitcoin"
        json metadata "{}"
    }
    
    SYMBOL_ALIAS {
        string alias PK "BTCUSDT"
        string source PK "binance"
        string unified_symbol FK "BTC/USDT"
    }
    
    OHLCV {
        string symbol FK "BTC/USDT"
        timestamp ts PK "timestamp"
        numeric open
        numeric high
        numeric low
        numeric close
        numeric volume
        string source
        string timeframe
    }
```

### 3.3 Storage Engine

We chose **TimescaleDB** (a PostgreSQL time-series extension) for the following reasons:

- Native SQL with a mature ecosystem
- Hypertable auto-partitions by time for efficient queries
- Continuous Aggregates for precomputing common timeframes
- Seamless integration with the Python ecosystem (pandas/SQLAlchemy)

```mermaid
graph TB
    subgraph "TimescaleDB Storage Structure"
        direction TB
        HT["hypertable: ohlcv<br/>partitioned by timeframe"]
        
        subgraph "Continuous Aggregates"
            CA1["agg_1h - 1-hour aggregation"]
            CA2["agg_1d - 1-day aggregation"]
            CA3["agg_1w - 1-week aggregation"]
        end
        
        HT --> CA1
        CA1 --> CA2
        CA2 --> CA3
    end
    
    subgraph "Metadata Tables"
        MT1["symbol_registry - symbol registry"]
        MT2["data_source - data source config"]
        MT3["ingest_log - ingestion log"]
        MT4["data_version - data version snapshot"]
    end
    
    HT -.-> MT3
```

**Hypertable Creation DDL**:

```sql
-- Create hypertable
CREATE TABLE ohlcv (
    symbol      VARCHAR(50)  NOT NULL,
    ts          TIMESTAMPTZ  NOT NULL,
    open        NUMERIC(20,8),
    high        NUMERIC(20,8),
    low         NUMERIC(20,8),
    close       NUMERIC(20,8),
    volume      NUMERIC(20,8),
    source      VARCHAR(50)  NOT NULL,
    timeframe   VARCHAR(10)  NOT NULL DEFAULT '1d',
    ingested_at TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (symbol, ts, timeframe)
);

SELECT create_hypertable('ohlcv', 'ts');

-- Indexes
CREATE INDEX idx_ohlcv_symbol_ts ON ohlcv (symbol, ts DESC);
CREATE INDEX idx_ohlcv_timeframe ON ohlcv (timeframe);

-- Continuous aggregate: daily level
CREATE MATERIALIZED VIEW ohlcv_1d
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 day', ts) AS day,
    first(open, ts) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, ts) AS close,
    sum(volume) AS volume,
    source
FROM ohlcv
WHERE timeframe = '1m'
GROUP BY symbol, day, source;
```

### 3.4 Scheduler

```mermaid
graph TB
    subgraph "Scheduler"
        CRON["Cron Job Engine"]
        
        subgraph "Ingestion Tasks"
            T1["Full Historical Backfill<br/>First-time onboarding"]
            T2["Incremental Update<br/>Daily/Hourly"]
            T3["Real-time Fetch<br/>WebSocket Push"]
        end
        
        subgraph "Maintenance Tasks"
            M1["Continuous Aggregate Refresh"]
            M2["Data Integrity Check"]
            M3["Old Data Archival"]
        end
    end
    
    CRON --> T1 & T2 & T3 & M1 & M2 & M3
```

### 3.5 Cache Strategy

```mermaid
graph LR
    REQ["Query Request"] --> CHK{"Redis cache hit?"}
    CHK -->|Yes| RET1["Return cached"]
    CHK -->|No| DB["Query TimescaleDB"]
    DB --> SET["Write to Redis<br/>TTL=300s"]
    SET --> RET2["Return result"]
```

---

## 4. Computation Frontend Design

### 4.1 Client Architecture

```mermaid
graph TB
    subgraph "StockStat Compute Library"
        direction TB
        
        subgraph "Access Layer"
            CM["ConnectionManager<br/>Config & Connection Management"]
            CFG["Config<br/>host/port/api_key/timeout"]
        end
        
        subgraph "Data Access Layer"
            DC["DataClient<br/>OHLCV Query"]
            MC["MetaClient<br/>Symbol/Metadata Query"]
            AR["ArrowCodec<br/>Efficient Serialization"]
        end
        
        subgraph "Compute Engine"
            EN["ComputeEngine<br/>Core Executor"]
            CTX["ComputeContext<br/>Computation Context"]
            REG["IndicatorRegistry<br/>Indicator Registry"]
        end
        
        subgraph "DSL Layer"
            PARSER["Parser<br/>Syntax Parsing"]
            AST["AST Builder<br/>Abstract Syntax Tree"]
            EVAL["Evaluator<br/>Evaluation"]
        end
        
        subgraph "Built-in Indicator Library"
            I1["Trend: MA/EMA/MACD"]
            I2["Oscillator: RSI/KDJ"]
            I3["Volatility: ATR/Bollinger"]
            I4["Statistics: Corr/Beta/Sharpe"]
            I5["Custom: User-registered"]
        end
        
        subgraph "Output Layer"
            DF["DataFrame Output"]
            JSON["JSON Output"]
            CSV["CSV Output"]
        end
        
        subgraph "Visualization Layer (Optional · Protocol-based)"
            PS["PlotSpec<br/>Backend-agnostic Plot Spec"]
            PR["PlotRenderer Protocol<br/>Null/Matplotlib/Plotly"]
        end
        
        CM --> CFG
        CM --> DC & MC
        DC --> AR
        DC & MC --> EN
        EN <--> CTX
        REG --> EN
        PARSER --> AST --> EVAL --> EN
        I1 & I2 & I3 & I4 & I5 --> REG
        EN --> DF & JSON & CSV
        EN --> PS --> PR
    end
```

### 4.2 Connection Management

```python
from stockstat import StockStatClient

# Option 1: Config file
client = StockStatClient.from_config("stockstat.yaml")

# Option 2: Direct configuration
client = StockStatClient(
    host="localhost",
    port=8000,
    api_key="optional-key",
    timeout=30,
    cache_enabled=True
)

# Option 3: Environment variables
client = StockStatClient.from_env()
```

### 4.3 Data Access Layer

```python
# Fetch OHLCV data, returns a pandas DataFrame
data = client.ohlcv(
    symbol="PAXG/USDT",
    source="binance",
    start="2022-01-01",
    end="2024-12-31",
    timeframe="1d"
)
# DataFrame columns: open, high, low, close, volume (DatetimeIndex)

# Batch fetch
data = client.ohlcv_batch(
    symbols=["BTC/USDT", "ETH/USDT", "PAXG/USDT"],
    start="2024-01-01",
    timeframe="1d"
)

# List available symbols
symbols = client.symbols(asset_type="crypto", source="binance")
```

### 4.4 Compute Engine and Indicator Registration

```python
from stockstat import indicator, ComputeContext

# Use built-in indicators
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
beta = client.compute.beta(asset="AAPL", benchmark="^GSPC", window=60)

# Register a custom indicator
@indicator(name="weekend_gain_loss_corr", category="custom")
def weekend_monday_gain_loss(data: pd.DataFrame) -> dict:
    """
    Compute independent correlations between PAXG weekend returns
    and Monday's max gain (High-Open)/Open and max loss (Low-Open)/Open.
    Records both metrics independently to avoid selection bias.
    """
    df = data.copy()
    df['weekday'] = df.index.weekday  # 0=Mon ... 6=Sun

    fridays = df[df.weekday == 4][['close']]
    sundays = df[df.weekday == 6][['close']]
    mondays = df[df.weekday == 0][['open', 'high', 'low', 'close']]

    pairs = []
    for mon_date, mon_row in mondays.iterrows():
        prev_fri = fridays.loc[:mon_date].tail(1)
        prev_sun = sundays.loc[:mon_date].tail(1)
        if len(prev_fri) > 0 and len(prev_sun) > 0:
            fri_c = prev_fri['close'].iloc[0]
            sun_c = prev_sun['close'].iloc[0]
            weekend_ret = (sun_c - fri_c) / fri_c
            mon_open = mon_row['open']
            max_gain = (mon_row['high'] - mon_open) / mon_open
            max_loss = (mon_row['low'] - mon_open) / mon_open
            pairs.append({'weekend_return': weekend_ret,
                          'max_gain': max_gain, 'max_loss': max_loss})

    result_df = pd.DataFrame(pairs)
    r_gain = result_df['weekend_return'].corr(result_df['max_gain'])
    r_loss = result_df['weekend_return'].corr(result_df['max_loss'])

    return {"r_gain": r_gain, "r_loss": r_loss, "n_samples": len(result_df)}

# Execute the custom indicator
result = client.compute.call("weekend_gain_loss_corr", data=data)
```

### 4.5 Visualization and Matplotlib Adaptability Design

#### 4.5.1 Design Goals

The visualization layer follows the **core zero hard-dependency** principle: the core computation library does not depend on matplotlib or any plotting library; when the user has matplotlib installed, enhanced plotting is automatically enabled.

| Design Constraint | Description |
|-------------------|-------------|
| **Zero hard-dependency** | `import stockstat` triggers no plotting-library import; matplotlib is absent from core dependencies in `pyproject.toml` |
| **Protocol abstraction** | A `PlotRenderer` protocol is defined; multiple backends are pluggable (matplotlib / plotly / null renderer) |
| **Data-rendering separation** | The compute engine produces backend-agnostic `PlotSpec` (plot specifications) that renderers interpret into concrete figures |
| **Lazy import** | matplotlib is only `import`ed on the user's first render call; it degrades gracefully when missing |
| **Optional extras** | Plotting dependencies are pulled via `pip install stockstat[matplotlib]` |

#### 4.5.2 Class Design

```mermaid
classDiagram
    class PlotSpec {
        +title: str
        +x_label: str
        +y_label: str
        +series: list~SeriesSpec~
        +markers: list~MarkerSpec~
        +x_type: str
    }
    class SeriesSpec {
        +name: str
        +data: pd.Series
        +kind: str
        +color: Optional~str~
        +secondary_y: bool
    }
    class MarkerSpec {
        +ts: datetime
        +label: str
        +direction: str
    }
    class PlotRenderer {
        <<interface>>
        +render(spec: PlotSpec) Any
        +show() void
        +savefig(path: str) void
        +available() bool
    }
    class NullRenderer {
        +available() False
        +render(spec) None
        +show() warn
    }
    class MatplotlibRenderer {
        -fig
        -ax
        -ax2
        +available() bool
        +render(spec)
        +show()
        +savefig(path)
    }
    class PlotlyRenderer {
        +available() bool
        +render(spec)
    }
    class RendererFactory {
        +get_renderer(name?) PlotRenderer
        +detect() str
    }

    PlotRenderer <|.. NullRenderer
    PlotRenderer <|.. MatplotlibRenderer
    PlotRenderer <|.. PlotlyRenderer
    RendererFactory --> PlotRenderer : "produces"
    PlotSpec --> SeriesSpec
    PlotSpec --> MarkerSpec
```

#### 4.5.3 Module Layout and Lazy Import

```
stockstat/
└── plot/
    ├── __init__.py          # Exposes PlotSpec / plot() / get_renderer()
    ├── base.py              # PlotRenderer protocol + NullRenderer default
    └── matplotlib_backend.py # matplotlib adapter (lazy import inside module)
```

`matplotlib_backend.py` uses a lazy import internally, ensuring the core import chain is never polluted:

```python
# stockstat/plot/matplotlib_backend.py
from .base import PlotRenderer, PlotSpec

class MatplotlibRenderer(PlotRenderer):
    def __init__(self):
        self._plt = None   # deferred until first render

    def available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
            return True
        except ImportError:
            return False

    def render(self, spec: PlotSpec):
        import matplotlib.pyplot as plt   # imported only here
        self._plt = plt
        fig, ax = plt.subplots()
        for s in spec.series:
            if s.kind == "line":
                ax.plot(s.data.index, s.data.values, label=s.name, color=s.color)
            elif s.kind == "bar":
                ax.bar(s.data.index, s.data.values, label=s.name, color=s.color)
        ax.set_title(spec.title)
        ax.legend()
        self.fig, self.ax = fig, ax
        return fig
```

#### 4.5.4 Auto-detection and Graceful Degradation

`RendererFactory.detect()` probes installed backends by priority; if none are present, it returns a `NullRenderer` that only emits a warning on call rather than raising an exception.

```python
# stockstat/plot/__init__.py
from .base import NullRenderer, PlotSpec

def get_renderer(name: str | None = None) -> "PlotRenderer":
    if name is None:
        name = RendererFactory.detect()
    if name == "matplotlib":
        from .matplotlib_backend import MatplotlibRenderer
        return MatplotlibRenderer()
    if name == "plotly":
        from .plotly_backend import PlotlyRenderer
        return PlotlyRenderer()
    return NullRenderer()   # safe fallback, usable with zero dependencies
```

#### 4.5.5 Usage

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)
data = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")

# Option A: protocol-based plotting (recommended, backend-agnostic)
spec = client.plot.spec(
    title="BTC/USDT 2024",
    series=[
        {"name": "close", "data": data.close, "kind": "line"},
        {"name": "ma20",  "data": data.close.rolling(20).mean(), "kind": "line"},
    ],
)
renderer = client.plot.get_renderer()     # auto-detected; NullRenderer if missing
renderer.render(spec)
renderer.savefig("btc.png")               # takes effect only when matplotlib is present

# Option B: hand computation results directly to matplotlib (user manages the dependency)
import matplotlib.pyplot as plt           # user imports this themselves
plt.plot(data.index, data.close)
plt.title("BTC/USDT")
plt.show()

# Option C: retrieve backend-agnostic data and choose any plotting library yourself
payload = spec.to_dict()                  # pure dict / JSON-serializable
```

#### 4.5.6 Dependency Declaration

`pyproject.toml` uses optional extras; a core install pulls no matplotlib:

```toml
[project]
name = "stockstat"
dependencies = [
    "pandas>=2.0",
    "numpy>=1.24",
    "httpx>=0.27",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
matplotlib = ["matplotlib>=3.8"]
plotly     = ["plotly>=5.20"]
plot       = ["stockstat[matplotlib]", "stockstat[plotly]"]
```

---

## 5. Scripting Language Design

A **dual-mode** programmable interface is provided: Python library (full power) + DSL (lightweight declarative).

### 5.1 Mode Comparison

```mermaid
graph TB
    subgraph "Python Library Mode (Full Power)"
        direction TB
        P1["✅ Full pandas/numpy ecosystem"]
        P2["✅ Arbitrary complex logic"]
        P3["✅ Debuggable / breakpointable"]
        P4["⚠️ Requires Python environment"]
        P5["⚠️ Security is user's responsibility"]
    end
    
    subgraph "DSL Mode (Lightweight Declarative)"
        direction TB
        D1["✅ One-liner for common statistics"]
        D2["✅ Sandboxed safe execution"]
        D3["✅ Serializable / storable / reproducible"]
        D4["✅ Friendly for non-Python users"]
        D5["⚠️ Limited expressiveness"]
    end
```

### 5.2 Python Library Mode

A full Python API for complex analysis scenarios:

```python
from stockstat import StockStatClient
import pandas as pd

client = StockStatClient(host="localhost", port=8000)

# Fetch data
paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")

# Free-form computation
df = paxg.copy()
df['ret'] = df['close'].pct_change()
df['vol_20'] = df['ret'].rolling(20).std()
df['ma50'] = df['close'].rolling(50).mean()

# Arbitrary pandas operations
result = df[df['vol_20'] > df['vol_20'].quantile(0.9)]
```

### 5.3 DSL Mode

Designed as a **SQL-like declarative statistical query language**, with syntax close to analyst intuition.

#### 5.3.1 Syntax Design

```mermaid
graph LR
    subgraph "DSL Execution Pipeline"
        SRC["Source Code<br/>DSL Script"] --> LEX["Lexer"]
        LEX --> PAR["Parser"]
        PAR --> AST2["Abstract Syntax Tree<br/>AST"]
        AST2 --> SEM["Semantic Check"]
        SEM --> OPT["Optimizer"]
        OPT --> EXE["Evaluator"]
        EXE --> RES["Result<br/>DataFrame/JSON"]
    end
```

#### 5.3.2 Grammar Specification

```
# DSL grammar BNF overview

query       ::= SELECT select_expr (',' select_expr)*
                FROM source
                [WHERE condition]
                [GROUP BY group_expr]
                [ORDER BY order_expr]
                [LIMIT n]

source      ::= ohlcv '(' symbol ',' timeframe ')'
              | ohlcv '(' symbol ',' timeframe ',' start ',' end ')'

select_expr ::= expr [AS alias]

expr        ::= function '(' expr (',' expr)* ')'
              | field
              | literal
              | expr operator expr

field       ::= 'open' | 'high' | 'low' | 'close' | 'volume'
              | 'returns' | 'log_returns'

function    ::= 'ma' | 'ema' | 'rsi' | 'macd' | 'std' | 'corr'
              | 'max' | 'min' | 'mean' | 'sum' | 'count'
              | 'rolling' | 'shift' | 'rank' | 'beta'
              | 'weekend_filter' | 'weekday_filter'
```

#### 5.3.3 DSL Examples

```sql
-- Example 1: Compute 20-day moving average and close price
SELECT 
    close,
    ma(close, 20) AS ma20,
    ema(close, 12) AS ema12
FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")

-- Example 2: Compute RSI overbought/oversold signals
SELECT 
    close,
    rsi(close, 14) AS rsi,
    CASE WHEN rsi(close, 14) > 70 THEN 'overbought'
         WHEN rsi(close, 14) < 30 THEN 'oversold'
         ELSE 'neutral' END AS signal
FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")

-- Example 3: PAXG weekend return vs Monday high-low spread correlation
SELECT 
    corr(
        returns(close, filter=weekend_filter),
        spread(high, low, filter=weekday_filter(0))
    ) AS weekend_monday_corr
FROM ohlcv("PAXG/USDT", "1d", "2022-01-01", "2024-12-31")

-- Example 4: Multi-asset Beta computation
SELECT 
    beta(close, benchmark="^GSPC", window=60) AS beta_60d
FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
```

#### 5.3.4 DSL Built-in Function Catalog

| Category | Function | Description |
|----------|----------|-------------|
| **Trend** | `ma(x, n)` | Simple moving average |
| | `ema(x, n)` | Exponential moving average |
| | `macd(x, fast, slow, signal)` | MACD |
| **Oscillator** | `rsi(x, n)` | Relative Strength Index |
| | `kdj(high, low, close, n)` | KDJ indicator |
| **Volatility** | `std(x, n)` | Rolling standard deviation |
| | `atr(high, low, close, n)` | Average True Range |
| | `bollinger(x, n, k)` | Bollinger Bands |
| **Statistics** | `corr(x, y)` | Correlation coefficient |
| | `beta(x, benchmark)` | Beta coefficient |
| | `sharpe(returns, rf)` | Sharpe ratio |
| | `max_drawdown(cumret)` | Maximum drawdown |
| **Transform** | `returns(x)` | Return series |
| | `log_returns(x)` | Log returns |
| | `rolling(x, n, func)` | Rolling window |
| | `shift(x, n)` | Shift |
| | `rank(x)` | Ranking |
| **Filter** | `weekend_filter` | Weekend filter |
| | `weekday_filter(n)` | Specific weekday filter |
| | `spread(high, low)` | High-low spread |

---

## 6. API Specification

### 6.1 REST API Overview

```mermaid
graph LR
    subgraph "REST API Endpoints"
        E1["GET /api/v1/health<br/>Health check"]
        E2["GET /api/v1/symbols<br/>Symbol list"]
        E3["GET /api/v1/symbols/:sym<br/>Symbol detail"]
        E4["GET /api/v1/ohlcv<br/>OHLCV query"]
        E5["POST /api/v1/ingest<br/>Manual ingest trigger"]
        E6["GET /api/v1/sources<br/>Data source list"]
        E7["GET /api/v1/metadata<br/>Metadata"]
    end
```

### 6.2 Core API Definitions

#### GET /api/v1/ohlcv

Fetch OHLCV data with support for multiple response formats.

**Request Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Unified symbol, e.g. `PAXG/USDT` |
| `source` | string | No | Specify data source |
| `start` | string (ISO date) | No | Start time |
| `end` | string (ISO date) | No | End time |
| `timeframe` | string | No | Time period, default `1d` |
| `limit` | int | No | Max number of rows returned |
| `format` | string | No | `json` / `arrow` / `csv`, default `json` |

**Response Example** (JSON):

```json
{
  "symbol": "PAXG/USDT",
  "source": "binance",
  "timeframe": "1d",
  "count": 731,
  "data": [
    {
      "ts": "2022-01-01T00:00:00Z",
      "open": 1812.50,
      "high": 1820.00,
      "low": 1805.00,
      "close": 1818.00,
      "volume": 15234.5
    }
  ]
}
```

**Apache Arrow Format** (efficient transfer):

```
GET /api/v1/ohlcv?symbol=PAXG/USDT&format=arrow
Accept: application/vnd.apache.arrow.file

→ Returns an Arrow IPC binary stream; the frontend can zero-copy convert to DataFrame
```

#### GET /api/v1/symbols

```json
{
  "count": 2,
  "symbols": [
    {
      "unified_symbol": "PAXG/USDT",
      "asset_type": "crypto",
      "base_asset": "PAXG",
      "quote_asset": "USDT",
      "sources": ["binance", "coinbase"],
      "description": "PAX Gold"
    },
    {
      "unified_symbol": "AAPL",
      "asset_type": "stock",
      "base_asset": "AAPL",
      "sources": ["yfinance", "alphavantage"],
      "description": "Apple Inc."
    }
  ]
}
```

### 6.3 Error Handling

```json
{
  "error": {
    "code": "SYMBOL_NOT_FOUND",
    "message": "Symbol 'XXX/USDT' not found in registry",
    "details": {
      "symbol": "XXX/USDT"
    }
  }
}
```

| HTTP Code | Error Code | Description |
|-----------|-----------|-------------|
| 400 | `INVALID_PARAMS` | Parameter validation failed |
| 404 | `SYMBOL_NOT_FOUND` | Symbol does not exist |
| 404 | `DATA_NOT_FOUND` | No data available |
| 429 | `RATE_LIMITED` | Rate limited |
| 500 | `INTERNAL_ERROR` | Internal server error |

---

## 7. Test Cases

### 7.1 Classic Stock Statistics Test Cases

```mermaid
mindmap
  root((Test Cases))
    Trend Analysis
      MA Golden/Death Cross
      EMA Bull/Bear Alignment
      MACD Divergence Detection
    Oscillators
      RSI Overbought/Oversold
      KDJ Golden Cross Signal
    Volatility
      Historical Volatility
      ATR Stop-Loss Level
      Bollinger Band Breakout
    Risk Statistics
      Beta Coefficient
      Maximum Drawdown
      Value at Risk (VaR)
      Sharpe Ratio
    Correlation
      Cross-Asset Correlation
      PAXG Weekend Effect
    Strategy Backtest
      Moving Average Crossover
      Momentum Strategy
```

#### Case 1: Moving Average Golden/Death Cross

```python
"""Test the correctness of MA golden/death cross signals"""
client = StockStatClient(host="localhost", port=8000)
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")

ma_short = data.close.rolling(5).mean()
ma_long = data.close.rolling(20).mean()

# Golden cross: short MA crosses above long MA
golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
# Death cross: short MA crosses below long MA
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

assert golden_cross.sum() >= 0  # At least no error
assert death_cross.sum() >= 0
# Verify: average short-term return after golden cross should be positive
```

#### Case 2: RSI Overbought/Oversold Detection

```python
"""RSI range [0, 100], >70 overbought, <30 oversold"""
data = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
rsi = client.compute.rsi(data.close, window=14)

assert rsi.between(0, 100).all()
assert rsi.isna().sum() == 14  # First 14 values are NaN
# Verify: RSI should be high on known large up-days
```

#### Case 3: Beta Coefficient Computation

```python
"""Beta = Cov(Ri, Rm) / Var(Rm)"""
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")

beta = client.compute.beta(
    asset=stock.close.pct_change(),
    benchmark=market.close.pct_change(),
    window=60
)

# AAPL's Beta typically ranges 1.0~1.3
assert 0.5 < beta.dropna().mean() < 2.0
```

#### Case 4: Maximum Drawdown

```python
"""Max drawdown = max(1 - P_t / max(P_0..P_t))"""
data = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
cumret = data.close / data.close.iloc[0]
running_max = cumret.cummax()
drawdown = (cumret - running_max) / running_max
max_dd = drawdown.min()

assert max_dd <= 0  # Drawdown should be non-positive
assert max_dd >= -1  # Drawdown cannot exceed -100%
```

#### Case 5: Sharpe Ratio

```python
"""Sharpe = (E[R] - Rf) / std(R) * sqrt(252)"""
data = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
returns = data.close.pct_change().dropna()

sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
# Sharpe for high-volatility assets typically ranges -1 ~ 3
assert -5 < sharpe < 10
```

#### Case 6: Bollinger Band Breakout

```python
"""Bollinger Bands = MA ± k * std"""
data = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2)

# Upper band should always be >= mid >= lower
assert (upper >= mid).all()
assert (mid >= lower).all()
# Breakout frequency above upper band should be low (<10%)
breakout = (data.close > upper).sum() / len(data)
assert breakout < 0.15
```

#### Case 7: Cross-Asset Correlation

```python
"""BTC and ETH should be highly positively correlated"""
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")

corr = btc.close.pct_change().corr(eth.close.pct_change())
assert corr > 0.7  # BTC/ETH daily return correlation typically > 0.7
```

### 7.2 PAXG Weekend Return vs Monday Independent Gain/Loss

> **Custom test case**: Compute the independent correlations between PAXG (PAX Gold, a gold-pegged token) weekend returns and Monday's max gain `(High-Open)/Open` and max loss `(Low-Open)/Open`. Both metrics are recorded independently to avoid the selection bias of picking one extreme by signal direction.

#### 7.2.1 Analysis Logic

```mermaid
graph LR
    subgraph "Weekend Return X"
        F["Friday close C_Fri"]
        S["Sunday close C_Sun"]
        X["X = (C_Sun - C_Fri) / C_Fri"]
    end
    
    subgraph "Monday Max Gain Y1"
        MO["Monday open O_Mon"]
        MH["Monday high H_Mon"]
        Y1["Y1 = (H_Mon - O_Mon) / O_Mon"]
    end

    subgraph "Monday Max Loss Y2"
        MO2["Monday open O_Mon"]
        ML["Monday low L_Mon"]
        Y2["Y2 = (L_Mon - O_Mon) / O_Mon"]
    end
    
    X --> CORR1["r(X, Y1)"]
    Y1 --> CORR1
    X --> CORR2["r(X, Y2)"]
    Y2 --> CORR2
```

**Hypothesis**: PAXG is pegged to gold. Traditional gold markets are closed on weekends. If PAXG's weekend price deviates (up or down), it may modestly predict Monday's intraday extremes. By recording both gain and loss independently, we avoid the selection bias that inflates correlation when picking one extreme by signal direction.

#### 7.2.2 Python Implementation

```python
"""
PAXG weekend return vs Monday independent gain/loss correlation test.
Records both (High-Open)/Open and (Low-Open)/Open independently.
"""
import pandas as pd
from scipy import stats
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# ── 1. Fetch PAXG daily data ──
paxg = client.ohlcv(
    symbol="PAXG/USDT", source="binance",
    start="2022-01-01", end="2024-12-31", timeframe="1d"
)

# ── 2. Label weekday ──
df = paxg.copy()
df['weekday'] = df.index.weekday

# ── 3. Extract Friday close, Sunday close, Monday OHLC ──
fridays = df[df['weekday'] == 4][['close']].rename(columns={'close': 'fri_close'})
sundays = df[df['weekday'] == 6][['close']].rename(columns={'close': 'sun_close'})
mondays = df[df['weekday'] == 0][['open', 'high', 'low', 'close']].copy()

# ── 4. Build weekend-Monday pairs ──
pairs = []
for mon_date, mon_row in mondays.iterrows():
    prev_fri = fridays.loc[:mon_date].tail(1)
    prev_sun = sundays.loc[:mon_date].tail(1)
    if len(prev_fri) > 0 and len(prev_sun) > 0:
        fri_close = prev_fri['fri_close'].iloc[0]
        sun_close = prev_sun['sun_close'].iloc[0]
        weekend_return = (sun_close - fri_close) / fri_close
        mon_open = mon_row['open']
        max_gain = (mon_row['high'] - mon_open) / mon_open
        max_loss = (mon_row['low'] - mon_open) / mon_open
        pairs.append({'weekend_return': weekend_return,
                      'max_gain': max_gain, 'max_loss': max_loss})

result_df = pd.DataFrame(pairs)

# ── 5. Compute independent correlations ──
r_gain = result_df['weekend_return'].corr(result_df['max_gain'])
r_loss = result_df['weekend_return'].corr(result_df['max_loss'])
p_gain = stats.pearsonr(result_df['weekend_return'], result_df['max_gain'])[1]
p_loss = stats.pearsonr(result_df['weekend_return'], result_df['max_loss'])[1]

# ── 6. Group comparison ──
up = result_df[result_df['weekend_return'] > 0]
dn = result_df[result_df['weekend_return'] < 0]

print(f"Samples:    {len(result_df)} (up={len(up)}, dn={len(dn)})")
print(f"r(gain):    {r_gain:.4f}  p={p_gain:.4f}")
print(f"r(loss):    {r_loss:.4f}  p={p_loss:.4f}")
print(f"Sig>0: gain={up['max_gain'].mean()*100:.4f}%, loss={up['max_loss'].mean()*100:.4f}%")
print(f"Sig<0: gain={dn['max_gain'].mean()*100:.4f}%, loss={dn['max_loss'].mean()*100:.4f}%")
```

#### 7.2.3 Expected Output

```
Samples:    156 (up=76, dn=65)
r(gain):    0.2303  p=0.0038
r(loss):    -0.2004  p=0.0121
Sig>0: gain=0.7099%, loss=-0.9070%
Sig<0: gain=0.5940%, loss=-0.7435%
```

#### 7.2.4 Test Assertions

```python
def test_paxg_weekend_gain_loss(client):
    """PAXG weekend return vs Monday independent gain/loss test"""
    result = compute_paxg_gain_loss(client)
    
    assert result['n_samples'] > 50, "Insufficient samples"
    assert -1 <= result['r_gain'] <= 1, "r(gain) out of bounds"
    assert -1 <= result['r_loss'] <= 1, "r(loss) out of bounds"
    
    # PAXG moves should be small (gold-pegged)
    assert abs(result['up_gain_mean']) < 0.05
    assert abs(result['dn_loss_mean']) < 0.05
```

---

## 8. Technology Stack

```mermaid
graph TB
    subgraph "Storage Backend"
        BE_LANG["Python 3.11+"]
        BE_FW["FastAPI + Uvicorn"]
        BE_DB["TimescaleDB (PostgreSQL 16)"]
        BE_CACHE["Redis"]
        BE_SCHED["APScheduler"]
        BE_DS["yfinance / ccxt / tushare / alpha_vantage"]
    end
    
    subgraph "Computation Frontend"
        FE_LANG["Python 3.10+"]
        FE_CORE["pandas + numpy"]
        FE_STAT["scipy + statsmodels"]
        FE_PLOT["plot protocol layer<br/>matplotlib as optional extras"]
        FE_HTTP["httpx (async client)"]
        FE_ARROW["pyarrow"]
    end
    
    subgraph "DSL"
        DSL_PARSER["lark (parser)"]
        DSL_AST["Custom AST"]
    end
    
    subgraph "Infrastructure"
        INFRA_DOCKER["Docker / Docker Compose"]
        INFRA_CI["GitHub Actions"]
        INFRA_TEST["pytest"]
    end
```

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend framework | FastAPI | Native async, auto-generated OpenAPI docs, high performance |
| Time-series database | TimescaleDB | PostgreSQL-compatible, efficient hypertable queries, continuous aggregates |
| Cache | Redis | High-speed query result caching, reduces DB load |
| Compute core | pandas + numpy | De facto standard, richest ecosystem |
| Statistical extensions | scipy + statsmodels | Hypothesis testing, regression analysis |
| DSL parsing | lark | Most mature parser in Python ecosystem, EBNF-friendly |
| Data transfer | Apache Arrow | Zero-copy columnar transfer, seamless pandas integration |
| Visualization | matplotlib (optional extras) | Protocol-based adapter, lazy import, core zero-dependency, graceful degradation when missing |
| Deployment | Docker Compose | One-command backend stack deployment |

---

## 9. Deployment

### 9.1 Storage Backend Independent Deployment

```mermaid
graph TB
    subgraph "Docker Compose Deployment"
        direction TB
        
        subgraph "stockstat-storage Network"
            API_C["stockstat-api<br/>FastAPI :8000"]
            DB_C["stockstat-db<br/>TimescaleDB :5432"]
            REDIS_C["stockstat-redis<br/>Redis :6379"]
            SCHED_C["stockstat-scheduler<br/>Ingestion Scheduler"]
        end
        
        subgraph "Data Volumes"
            V1["db_data<br/>Database persistence"]
            V2["redis_data<br/>Cache persistence"]
            V3["config<br/>Config files"]
        end
        
        API_C --> DB_C
        API_C --> REDIS_C
        SCHED_C --> DB_C
        DB_C --> V1
        REDIS_C --> V2
    end
    
    USER["Computation Frontend<br/>(User Machine)"] -.->|"http://host:8000"| API_C
```

**docker-compose.yml Core Structure**:

```yaml
version: "3.9"
services:
  db:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: stockstat
      POSTGRES_USER: stockstat
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - db_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://stockstat:${DB_PASSWORD}@db:5432/stockstat
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - db
      - redis

  scheduler:
    build: ./backend
    command: python -m stockstat.scheduler
    environment:
      DATABASE_URL: postgresql://stockstat:${DB_PASSWORD}@db:5432/stockstat
    depends_on:
      - db

volumes:
  db_data:
  redis_data:
```

### 9.2 Computation Frontend Installation

```bash
# Install the computation frontend library (core, no plotting deps)
pip install stockstat

# Optionally enable matplotlib visualization
pip install stockstat[matplotlib]

# Configure connection
export STOCKSTAT_HOST=localhost
export STOCKSTAT_PORT=8000

# To access real data sources via proxy (configure on backend machine)
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

```python
# Or configure in code
from stockstat import StockStatClient
client = StockStatClient(host="your-server.com", port=8000)
```

---

## 10. Project Structure

```
StockStatistic/
├── backend/                         # Storage backend service
│   ├── stockstat_backend/
│   │   ├── __init__.py
│   │   ├── app.py                   # FastAPI application entry
│   │   ├── config.py                # Configuration management
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes_ohlcv.py      # OHLCV query routes
│   │   │   ├── routes_symbols.py    # Symbol management routes
│   │   │   └── routes_health.py     # Health check routes
│   │   ├── adapters/                # Data source adapters
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Adapter base class
│   │   │   ├── yfinance.py
│   │   │   ├── ccxt_adapter.py
│   │   │   ├── alphavantage.py
│   │   │   └── tushare.py
│   │   ├── models/                  # Data models
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv.py
│   │   │   └── symbol.py
│   │   ├── storage/                 # Storage layer
│   │   │   ├── __init__.py
│   │   │   ├── database.py          # DB connection
│   │   │   ├── repository.py        # Data repository
│   │   │   └── cache.py             # Redis cache
│   │   ├── normalizer/              # Data normalization
│   │   │   ├── __init__.py
│   │   │   ├── symbol_mapper.py
│   │   │   └── timeframe.py
│   │   └── scheduler/               # Scheduler
│   │       ├── __init__.py
│   │       └── ingest.py
│   ├── alembic/                     # Database migrations
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/                        # Computation frontend library
│   ├── stockstat/
│   │   ├── __init__.py
│   │   ├── client.py                # StockStatClient main entry
│   │   ├── config.py                # Connection config
│   │   ├── connection.py            # Connection manager
│   │   ├── data_access/             # Data access layer
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv.py
│   │   │   └── metadata.py
│   │   ├── compute/                 # Compute engine
│   │   │   ├── __init__.py
│   │   │   ├── engine.py            # Core engine
│   │   │   ├── context.py           # Computation context
│   │   │   └── registry.py          # Indicator registry
│   │   ├── backtest/                # Backtest subsystem (v1.3)
│   │   │   ├── __init__.py          # Public exports
│   │   │   ├── engine.py            # Main loop + event dispatch
│   │   │   ├── context.py           # BacktestContext
│   │   │   ├── data_feed.py         # DataFeed + Universe multi-tf alignment
│   │   │   ├── strategy.py          # Strategy base + @strategy decorator
│   │   │   ├── orders.py            # Order/Fill dataclasses
│   │   │   ├── broker.py            # SimulatedBroker
│   │   │   ├── portfolio.py         # Portfolio/Position
│   │   │   ├── cost_model.py        # Fee/slippage models
│   │   │   ├── fill_model.py        # Fill price model
│   │   │   ├── sizing.py            # Position sizing algorithms
│   │   │   ├── metrics.py           # Performance aggregation
│   │   │   ├── result.py            # BacktestResult + report
│   │   │   ├── benchmark.py         # Buy-and-hold benchmarks
│   │   │   ├── optimizer.py         # Grid/optuna (optional extras)
│   │   │   ├── walkforward.py       # Walk-forward (optional)
│   │   │   ├── montecarlo.py            # Monte Carlo (optional)
│   │   │   ├── plot_adapter.py          # equity/trades → PlotSpec (back-compat)
│   │   │   ├── chart_spec.py            # BacktestChartSpec (v1.4)
│   │   │   ├── chart_registry.py        # chart type registry (v1.4)
│   │   │   ├── chart_factory.py         # detect + get_chart_renderer (v1.4)
│   │   │   ├── null_charts.py           # NullBacktestRenderer (v1.4)
│   │   │   └── matplotlib_charts.py     # MatplotlibBacktestRenderer lazy (v1.4)
│   │   ├── indicators/              # Built-in indicator library
│   │   │   ├── __init__.py
│   │   │   ├── trend.py             # MA/EMA/MACD
│   │   │   ├── oscillator.py        # RSI/KDJ
│   │   │   ├── volatility.py        # ATR/Bollinger
│   │   │   ├── statistics.py        # Corr/Beta/Sharpe
│   │   │   └── custom.py            # Custom indicator base class
│   │   ├── plot/                    # Visualization layer (optional · protocol-based)
│   │   │   ├── __init__.py          # PlotSpec / get_renderer()
│   │   │   ├── base.py              # PlotRenderer protocol + NullRenderer
│   │   │   └── matplotlib_backend.py # matplotlib adapter (lazy import)
│   │   └── export/                  # Result export
│   │       ├── __init__.py
│   │       └── serializers.py
│   ├── tests/
│   │   ├── test_indicators.py
│   │   ├── test_dsl.py
│   │   ├── test_paxg_weekend.py     # PAXG weekend correlation test
│   │   ├── test_classic_stats.py    # Classic statistics tests
│   │   ├── test_backtest_iface.py   # Backtest interface skeleton (BT-0)
│   │   ├── test_backtest_mvp.py     # Backtest MVP (BT-1)
│   │   ├── test_backtest_portfolio.py # Multi-asset/short (BT-2)
│   │   ├── test_backtest_multitf.py # Multi-timeframe (BT-3)
│   │   ├── test_backtest_cost.py    # Cost models (BT-4)
│   │   ├── test_backtest_metrics.py # Performance metrics (BT-5)
│   │   ├── test_backtest_optimize.py # Optimizer (BT-6)
│   │   ├── test_backtest_strategies.py # 12 strategies (BT-7)
│   │   ├── test_backtest_viz_iface.py    # Backtest viz interface (BT-V0)
│   │   ├── test_backtest_viz_mpl.py      # Backtest viz matplotlib (BT-V1)
│   │   ├── test_backtest_viz_advanced.py # Backtest viz advanced (BT-V2)
│   │   ├── test_backtest_viz_dashboard.py # Backtest viz dashboard (BT-V3)
│   │   └── test_backtest_viz_online.py   # Backtest viz online real-data (BT-V Online)
│   └── pyproject.toml
│
├── docker-compose.yml               # Backend deployment orchestration
├── docs/
│   ├── DESIGN.md                    # This design report (English)
│   └── DESIGN_CN.md                 # This design report (Chinese)
└── README.md
```

---

## 11. Development Roadmap

```mermaid
gantt
    title StockStat Development Roadmap
    dateFormat  YYYY-MM-DD
    axisFormat  %b

    section Storage Backend
    Project init & DB design           :a1, 2026-07-01, 14d
    Data source adapters (yfinance/ccxt) :a2, after a1, 21d
    Normalization layer                :a3, after a2, 14d
    REST API development               :a4, after a3, 14d
    Scheduler & cache                  :a5, after a4, 14d

    section Computation Frontend
    Client framework & connection mgmt :b1, after a4, 10d
    Data access layer                  :b2, after b1, 10d
    Built-in indicator library         :b3, after b2, 21d
    DSL parser                         :b4, after b3, 21d
    Visualization protocol & mpl adapter :b5, after b3, 10d

    section Backtest Subsystem
    BT0 Interface freeze               :bt0, after b5, 3d
    BT1 Single-asset MVP               :bt1, after bt0, 5d
    BT2 Multi-asset & short            :bt2, after bt1, 5d
    BT3 Multi-timeframe alignment      :bt3, after bt2, 4d
    BT4 Cost & fill models             :bt4, after bt3, 4d
    BT5 Metrics & reporting            :bt5, after bt4, 5d
    BT6 Optimization & walk-forward    :bt6, after bt5, 6d
    BT7 DSL integration & strategies   :bt7, after bt6, 4d

    section Backtest Visualization
    BTV0 Interface freeze & null       :btv0, after bt7, 2d
    BTV1 matplotlib basic rendering    :btv1, after btv0, 3d
    BTV2 Advanced charts (heatmap/dist) :btv2, after btv1, 3d
    BTV3 Dashboard & annotations       :btv3, after btv2, 3d

    section Testing & Deployment
    Test case writing                  :c1, after b3, 14d
    PAXG weekend correlation test      :c2, after b3, 7d
    Docker deployment & docs           :c3, after c1, 10d
```

### Development Phases

| Phase | Scope | Deliverables |
|-------|-------|--------------|
| **P0** | Storage backend MVP | DB + yfinance/ccxt adapters + basic API |
| **P1** | Computation frontend MVP | Client + data access + 5 core indicators |
| **P2** | DSL parser | Grammar file + evaluator + 10 built-in functions |
| **P3** | Full indicator library | Trend/oscillator/volatility/statistics full suite |
| **P4** | Visualization layer | PlotSpec + PlotRenderer protocol + matplotlib adapter (optional extras) |
| **P5** | Testing & deployment | All test cases + Docker + documentation |
| **BT-0** | Backtest interface freeze | Core dataclasses + abstract base signatures + interface skeleton tests |
| **BT-1** | Single-asset MVP | DataFeed/Portfolio/Broker/Context/Engine/Result + MA crossover strategy |
| **BT-2** | Multi-asset portfolio | Universe + short selling + limit/stop orders + sizing + pair trading |
| **BT-3** | Multi-timeframe | {sym:{tf:df}} alignment + lookahead audit + multi-tf resonance strategy |
| **BT-4** | Cost models | Commission/slippage/stamp duty/funding rate + limit-up/down + partial fills |
| **BT-5** | Performance & reporting | Sharpe/Sortino/Calmar + drawdown + trade ledger + PlotSpec visualization |
| **BT-6** | Optimization & walk-forward | Grid search + optuna + walk-forward + Monte Carlo (optional extras) |
| **BT-7** | DSL integration | Signal.from_dsl + 12-strategy full test suite + documentation |
| **BT-V0** | Visualization interface freeze | BacktestChartSpec + Renderer protocol + Null fallback |
| **BT-V1** | matplotlib basic rendering | line/fill/scatter/subplots + equity/drawdown/trades |
| **BT-V2** | Advanced charts | histogram/heatmap/bar + returns dist/monthly heatmap/param heatmap |
| **BT-V3** | Dashboard | multi-subplot dashboard + trade annotations + batch savefig |

---

## 12. Backtest Subsystem Design

> **Added in v1.3.** The backtest subsystem is an optional enhancement of the computation frontend, located at `frontend/stockstat/backtest/`. It is purely frontend and does not modify the storage backend.

### 12.1 Goals & Principles

| Goal | Description |
|------|-------------|
| **Configurable** | Custom strategy functions, multi-instrument trading groups, multi-timeframe bars, reuse compute-library indicators |
| **Programmable-first** | No built-in fixed strategies; provides `Strategy` base class + `@strategy` function decorator |
| **Data/compute separation** | Pure frontend; data fetched via `DataClient` then injected into `DataFeed` |
| **Zero hard dependency** | Core depends only on pandas/numpy; optuna etc. via `[optimize]` extras |
| **Lookahead protection** | `on_bar(t)` may only access data `≤ t`; orders default to fill at `t+1` open |
| **Reproducible** | seed + data snapshot version recorded in `BacktestResult` |

### 12.2 Top-level Architecture

```mermaid
graph TB
    subgraph "User Strategy"
        US["on_bar(ctx):<br/>ctx.compute.rsi(...)<br/>ctx.broker.buy(...)"]
    end
    subgraph "Backtest Core"
        CTX["BacktestContext<br/>get(sym,tf,lookback) slice<br/>compute: ComputeEngine proxy<br/>portfolio read-only"]
        BRK["Broker<br/>submit/cancel<br/>match → Fill"]
        DF["DataFeed + Universe<br/>multi-tf alignment<br/>cursor + lookahead guard"]
        PF["Portfolio<br/>cash / positions<br/>update_fill / mark_to_market"]
        ENG["BacktestEngine<br/>event loop + hooks + result"]
        RES["BacktestResult<br/>trades / positions / equity<br/>metrics / plot / to_dict"]
    end
    US -->|read| CTX
    US -->|orders| BRK
    CTX -->|aligned bars| US
    BRK -->|fills| PF
    DF --> CTX
    PF --> CTX
    ENG --> CTX
    ENG --> BRK
    ENG --> DF
    ENG --> RES
```

### 12.3 Module Layout

```
frontend/stockstat/backtest/
├── __init__.py              # public exports
├── engine.py                # main loop + event dispatch
├── context.py               # BacktestContext
├── data_feed.py             # DataFeed + Universe
├── strategy.py              # Strategy base + @strategy decorator
├── orders.py                # Order/Fill dataclasses
├── broker.py                # SimulatedBroker
├── portfolio.py             # Portfolio/Position
├── cost_model.py            # CostModel abstract + implementations
├── fill_model.py            # FillModel
├── sizing.py                # position sizing
├── metrics.py               # performance aggregation
├── result.py                # BacktestResult + report
├── benchmark.py             # benchmark comparison
├── optimizer.py             # parameter optimization (optional)
├── walkforward.py           # walk-forward (optional)
├── montecarlo.py            # Monte Carlo (optional)
└── plot_adapter.py          # equity/trades → PlotSpec
```

### 12.4 Core Interface Signatures

```python
class Strategy:
    def on_start(self, ctx: BacktestContext) -> None: ...
    def on_bar(self, ctx: BacktestContext) -> None: ...
    def on_bar_close(self, ctx: BacktestContext) -> None: ...
    def on_fill(self, fill: Fill, ctx: BacktestContext) -> None: ...

def strategy(fn=None, *, name: str | None = None): ...

class BacktestContext:
    now: pd.Timestamp
    current_bar: dict[str, pd.Series]
    def get(self, symbol: str, timeframe: str = "1d",
            lookback: int | None = None) -> pd.DataFrame: ...
    @property
    def compute(self) -> ComputeEngine: ...
    @property
    def broker(self) -> Broker: ...
    @property
    def portfolio(self) -> Portfolio: ...

@dataclass
class Order:
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    order_type: Literal["market","limit","stop","stop_limit","trailing_stop"] = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: Literal["day","gtc","ioc"] = "gtc"
    tag: str = ""

class BacktestEngine:
    def __init__(self, *,
                 data: dict[str, dict[str, pd.DataFrame]],
                 strategy: Strategy,
                 initial_cash: float = 1_000_000.0,
                 cost_model: CostModel = PercentCost(commission=0.0003, slippage=0.0002),
                 fill_model: FillModel = NextOpenFill(),
                 benchmark: str | None = None,
                 trade_on: Literal["open","close"] = "open",
                 allow_short: bool = False,
                 seed: int = 0): ...
    def run(self) -> BacktestResult: ...
```

### 12.5 Multi-timeframe Alignment & Lookahead Protection

The **finest timeframe** drives the cursor `t`; higher-timeframe bars align via `asof/ffill`:

```python
master_index = union of all timestamps at finest tf
aligned[sym][tf] = df[sym][tf].reindex(master_index, method="ffill")

# Context.get(symbol, tf, lookback) returns ≤ t slice (closed)
df = aligned[sym][tf].loc[:t]
return df.iloc[-lookback:] if lookback else df
```

- Orders default to `NextOpenFill` (fill at `t+1` open)
- Optional `lookahead_audit` raises `LookaheadError` on access to `> t`
- Indicator computation also based on `≤ t` slice

### 12.6 Cost & Fill Models

| Model | Description |
|-------|-------------|
| `PercentCost` (default) | Percentage commission + percentage slippage (bps) |
| `FixedCost` / `TieredCost` / `MinCost` | Fixed / tiered / minimum fee |
| `StampDutyCost` | Stamp duty (equity sell-side) |
| `FundingRateCost` (optional) | Perpetual funding rate |
| `NextOpenFill` (default) | Fill at next bar open — strongest lookahead protection |
| `NextCloseFill` / `ThisCloseFill` | Alternative fill timing (warned) |
| `VWAPFill` / `WorstPriceFill` | Impact simulation |

### 12.7 Performance Metrics

Reuses `indicators.statistics` plus new `metrics.py`: total/annualized return, Sharpe, Sortino, Calmar, Omega, information ratio, max drawdown, drawdown duration/recovery, win rate, profit factor, expectancy, streaks, monthly/yearly heatmap, return distribution, VaR.

### 12.8 Integration with Existing Modules

| Integration point | Mechanism |
|-------------------|-----------|
| `ComputeEngine` | `Context.compute` holds the client's ComputeEngine |
| Custom indicators | `ctx.compute.register("divergence", fn)` → `ctx.compute.call(...)` |
| DSL | `Signal.from_dsl("SELECT ... WHERE rsi<30")` (BT-7) |
| `indicators.statistics` | `metrics.py` calls sharpe/max_drawdown/var/returns |
| `plot` protocol | `result.plot_equity()` returns PlotSpec |
| `export` | `result.to_csv()/to_json()` reuses serializers |
| `data_access` | `DataFeed` accepts DataFrames or lazy client |

### 12.9 Built-in Example Strategies

| # | Strategy | Universe | tf | Indicators/Design | Validates |
|---|----------|----------|----|-------------------|-----------|
| 1 | MA crossover | single | single | ma(5)×ma(20) | MVP loop |
| 2 | Bollinger breakout | single | single | bollinger | limit/stop |
| 3 | RSI reversal | single | single | rsi | reverse/TP |
| 4 | MACD divergence | single | single | macd + custom | register() |
| 5 | ATR channel (turtle) | single | single | atr + Donchian | ATR sizing |
| 6 | Grid trading | single | single | price ladder | multi-orders |
| 7 | Pair trading | multi(2) | single | beta/corr + z-score | short/hedge |
| 8 | Risk parity | multi(N) | single | beta/std | rebalance |
| 9 | Momentum rotation | multi(N) | single | 6M rank | Top-K |
| 10 | Multi-tf resonance | single | multi | daily MA + hourly | multi-tf |
| 11 | PAXG weekend effect | single | single | weekday signal | event-driven |
| 12 | Martingale | single | single | doubling down | risk limits |

### 12.10 Dependency Declaration

```toml
[project.optional-dependencies]
backtest = ["stockstat"]
optimize = ["optuna>=3.5"]
backtest_full = ["stockstat[backtest]", "stockstat[optimize]", "stockstat[matplotlib]"]
```

---

## 13. Backtest Visualization Subsystem Design

> **Added in v1.4.** A **zero-hard-dependency** visualization layer on top of the backtest subsystem (§12): the backtest core never depends on matplotlib, but rich backtest-specific charts auto-activate when matplotlib is installed.

### 13.1 Background & Problem

The backtest subsystem already produces equity/drawdown/trades charts via `backtest/plot_adapter.py` reusing the generic `PlotSpec` protocol, but has these gaps:

| Gap | Description |
|-----|-------------|
| PlotSpec expressiveness | Only line/bar/scatter + markers; cannot express **fill areas** (drawdown shading), **histograms** (return distribution), **heatmaps** (monthly/yearly returns, parameter grids), **multi-subplot layouts** (dashboards) |
| Protocol pollution risk | Extending PlotSpec with backtest-specific fields would break the generic protocol's simplicity |
| matplotlib coupling | The generic `MatplotlibRenderer` only handles a single ax; backtest needs fill/heatmap/subplot semantics the generic renderer cannot express |

### 13.2 Design Principles

| Principle | Description |
|-----------|-------------|
| **Backtest core zero-dep** | `backtest/` package import never triggers matplotlib; `import stockstat.backtest` always succeeds |
| **Dedicated spec layer** | New `BacktestChartSpec` (backtest-specific) parallel to generic `PlotSpec`, no mutual pollution |
| **Lazy activation** | matplotlib activates via `backtest.matplotlib_charts` lazy import only when installed |
| **Protocol-based** | `BacktestChartRenderer` protocol; Null/Matplotlib pluggable backends |
| **Progressive** | basic (equity/drawdown) → advanced (heatmap/dist) → dashboard |

### 13.3 Architecture

```mermaid
graph TB
    subgraph "Backtest Core backtest/ (zero matplotlib dep)"
        RES["BacktestResult"]
        ADAPTER["plot_adapter.py<br/>basic PlotSpec builders"]
        CHARTSPEC["chart_spec.py<br/>BacktestChartSpec"]
        REG["chart_registry.py<br/>chart type registry"]
    end
    subgraph "Generic plot protocol (existing)"
        PS["PlotSpec"]
        PR["PlotRenderer<br/>Null/Matplotlib"]
    end
    subgraph "Backtest viz backends (lazy · optional)"
        BCMPL["matplotlib_charts.py<br/>MatplotlibBacktestRenderer"]
        BCNULL["null_charts.py<br/>NullBacktestRenderer"]
        FACTORY["chart_factory.py<br/>detect + get_chart_renderer"]
    end
    RES --> ADAPTER --> PS
    RES --> CHARTSPEC
    CHARTSPEC --> REG
    REG --> FACTORY
    FACTORY --> BCMPL
    FACTORY --> BCNULL
    BCMPL -.->|lazy import| PR
```

### 13.4 Module Layout (new under `frontend/stockstat/backtest/`)

```
frontend/stockstat/backtest/
├── chart_spec.py            # BacktestChartSpec + sub-specs
├── chart_registry.py        # chart type registry
├── chart_factory.py         # detect + get_chart_renderer
├── null_charts.py           # NullBacktestRenderer (zero-dep fallback)
├── matplotlib_charts.py     # MatplotlibBacktestRenderer (lazy import)
└── plot_adapter.py          # (existing) extended: returns both PlotSpec & BacktestChartSpec
```

### 13.5 BacktestChartSpec Design

```python
@dataclass
class ChartSeries:
    name: str
    data: pd.Series | pd.DataFrame
    kind: str = "line"          # line/bar/scatter/fill/histogram/heatmap
    color: str | None = None
    secondary_y: bool = False
    alpha: float = 1.0

@dataclass
class SubplotSpec:
    title: str = ""
    y_label: str = ""
    series: list[ChartSeries] = field(default_factory=list)
    share_x: bool = True

@dataclass
class BacktestChartSpec:
    title: str = ""
    x_label: str = ""
    subplots: list[SubplotSpec] = field(default_factory=list)
    layout: tuple[int, int] = (1, 1)
    figsize: tuple[float, float] = (12, 6)
    annotate_trades: bool = False
    source_result: object = None

    def add_subplot(self, title="", y_label="") -> SubplotSpec: ...
    def to_dict(self) -> dict: ...

class BacktestChartRenderer(Protocol):
    def render(self, spec: BacktestChartSpec) -> Any: ...
    def savefig(self, path: str) -> None: ...
    def show(self) -> None: ...
    def available(self) -> bool: ...
```

### 13.6 Chart Type Catalog

| Chart | Type | Use | Phase |
|-------|------|-----|-------|
| `equity_curve` | multi-line + benchmark | equity vs benchmark | BT-V0 |
| `drawdown` | line + fill | drawdown shaded area | BT-V0 |
| `trades_overlay` | line + scatter | trade markers on equity | BT-V0 |
| `returns_distribution` | histogram | return distribution | BT-V2 |
| `monthly_heatmap` | heatmap | monthly returns | BT-V2 |
| `yearly_returns` | bar | yearly comparison | BT-V2 |
| `parameter_heatmap` | heatmap | grid search heatmap | BT-V2 |
| `underwater_curve` | fill | underwater (drawdown duration) | BT-V2 |
| `dashboard` | multi-subplot | combined dashboard | BT-V3 |

### 13.7 Integration with Existing Modules

| Integration point | Mechanism |
|-------------------|-----------|
| `BacktestResult` | new `result.chart(name)` returns `BacktestChartSpec` |
| `plot_adapter.py` | keeps original `plot_equity/plot_drawdown/plot_trades` (generic PlotSpec, back-compat) |
| `plot/base.py` | **unchanged** — generic protocol stays simple |
| `matplotlib_backend.py` | **unchanged** — generic renderer stays single-ax |
| `client.backtest()` | returned `BacktestResult` auto-has `.chart()` and `.render()` |

### 13.8 Usage

```python
from stockstat.backtest import BacktestEngine, strategy, Order
from stockstat.backtest.chart_factory import get_chart_renderer

res = BacktestEngine(...).run()

# Option A: get dedicated spec, render yourself
spec = res.chart("equity_curve")        # BacktestChartSpec
renderer = get_chart_renderer()         # auto-detect matplotlib
renderer.render(spec)
renderer.savefig("equity.png")

# Option B: one-liner render
res.render("drawdown", path="dd.png")

# Option C: combined dashboard
spec = res.chart("dashboard")
renderer.render(spec)

# Option D: back-compat — generic PlotSpec (works without matplotlib)
spec = res.plot_equity()                # PlotSpec (existing)
```

### 13.9 Dependency Declaration

```toml
[project.optional-dependencies]
backtest = ["stockstat"]
backtest_viz = ["stockstat[backtest]", "matplotlib>=3.8"]
backtest_full = ["stockstat[backtest]", "stockstat[optimize]",
                 "stockstat[matplotlib]", "matplotlib>=3.8"]
```

### 13.10 Implementation Phases (BT-V series)

| Phase | Scope | Tests |
|-------|-------|-------|
| **BT-V0** | Interface freeze: `BacktestChartSpec` + `BacktestChartRenderer` protocol + Null impl + basic spec builders | `test_backtest_viz_iface.py` |
| **BT-V1** | matplotlib backend: render line/fill/scatter/subplots; full equity/drawdown/trades | `test_backtest_viz_mpl.py` |
| **BT-V2** | Advanced: histogram/heatmap/bar; returns_distribution/monthly_heatmap/yearly/parameter_heatmap | `test_backtest_viz_advanced.py` |
| **BT-V3** | Dashboard combo + trade annotations + batch savefig + graceful degradation | `test_backtest_viz_dashboard.py` |

---

## 14. Backtest Phase Documentation Index

The backtest core (BT-0–BT-7) and backtest visualization (BT-V0–BT-V3 + online validation) phase docs are indexed below under `docs/backtest/`:

### 14.1 Backtest Core (BT series)

| Phase | Document | Code | Tests |
|-------|----------|------|-------|
| BT-0 | [docs/backtest/BT0.md](docs/backtest/BT0.md) | `backtest/` skeleton + dataclasses | `test_backtest_iface.py` |
| BT-1 | [docs/backtest/BT1.md](docs/backtest/BT1.md) | MVP five modules | `test_backtest_mvp.py` |
| BT-2 | [docs/backtest/BT2.md](docs/backtest/BT2.md) | multi-asset/short/orders | `test_backtest_portfolio.py` |
| BT-3 | [docs/backtest/BT3.md](docs/backtest/BT3.md) | multi-tf alignment/audit | `test_backtest_multitf.py` |
| BT-4 | [docs/backtest/BT4.md](docs/backtest/BT4.md) | cost/fill models | `test_backtest_cost.py` |
| BT-5 | [docs/backtest/BT5.md](docs/backtest/BT5.md) | metrics/report/viz | `test_backtest_metrics.py` |
| BT-6 | [docs/backtest/BT6.md](docs/backtest/BT6.md) | optimization/walk-forward/MC | `test_backtest_optimize.py` |
| BT-7 | [docs/backtest/BT7.md](docs/backtest/BT7.md) | DSL integration/12 strategies | `test_backtest_strategies.py` |
| BT-8 | [docs/backtest/BT8.md](docs/backtest/BT8.md) | P0 fixes: IntrabarLimitFill + MakerTakerCost + OCO | `test_backtest_p0.py` |
| BT-9 | [docs/backtest/BT9.md](docs/backtest/BT9.md) | P1 enhancements: BinanceCost + IntrabarSimulator + BatchRunner + exit_reason | `test_backtest_p1.py` |
| BT-10 | [docs/backtest/BT10.md](docs/backtest/BT10.md) | P2 analysis: annualization + DCA + Analyzer + fee_sweep | `test_backtest_p2.py` |
| BT-11 | `working/PAXG-Weekend-Monday-Law-v5-redo/STAGE_REPORT.md` | ExecutionModel ABC + IntrabarFillModel + Fill/Order field extensions | `test_backtest_intrabar.py` |
| BT-12 | same | IntrabarExecution + IntrabarMixin + OCO mutual + priority | `test_backtest_intrabar.py` |
| BT-13 | same | v5 strategy migration (33 strategies × 4 fees = 132 runs validated) | `run_redo.py` |
| BT-14 | same | Analysis & visualization adaptation | `plots_redo.py` |

### 14.2 Backtest Visualization (BT-V series + online validation)

| Phase | Document | Code | Tests |
|-------|----------|------|-------|
| BT-V0 | [docs/backtest/BTV0.md](docs/backtest/BTV0.md) | `chart_spec.py` + `chart_registry.py` + `null_charts.py` + `chart_factory.py` | `test_backtest_viz_iface.py` |
| BT-V1 | [docs/backtest/BTV1.md](docs/backtest/BTV1.md) | `matplotlib_charts.py` basic rendering | `test_backtest_viz_mpl.py` |
| BT-V2 | [docs/backtest/BTV2.md](docs/backtest/BTV2.md) | histogram/heatmap/bar advanced charts | `test_backtest_viz_advanced.py` |
| BT-V3 | [docs/backtest/BTV3.md](docs/backtest/BTV3.md) | dashboard combo + annotations | `test_backtest_viz_dashboard.py` |
| BT-V Online | [docs/backtest/BT_VIZ_ONLINE_REPORT.md](docs/backtest/BT_VIZ_ONLINE_REPORT.md) | real-data online validation + 13 images | `test_backtest_viz_online.py` |

---

## 15. Backtest Engine Enhancement Subsystem Design

> **Added in v1.5.** Enhances the backtest subsystem (§12) based on 12 deficiencies exposed during v5 research (see `working/PAXG-Weekend-Monday-Law-v5/BACKTEST_IMPROVEMENT_REPORT.md`). Enhancements follow **backward-compatible, composition-first, minimal-invasion** principles — new classes/methods are added without breaking existing APIs.

### 15.1 Design Goals

| Goal | Description |
|------|-------------|
| **Intrabar limit fills** | Limit orders should fill when intrabar price crosses the limit level, not just at open |
| **Maker/Taker fee differentiation** | Crypto exchanges differentiate maker/taker rates up to 5× |
| **OCO orders** | A pair of limit orders where filling one cancels the other (required for dual-limit strategies) |
| **Binance fee model** | Spot/futures × BNB discount four-combination presets |
| **Multi-strategy batch backtest** | Run multiple strategies and aggregate comparison in one call |
| **Exit reason tagging** | Trades tagged as TP/SL/close/time/breakeven/profit exit |
| **Subperiod/regime analysis** | Post-backtest analysis grouped by subperiod or market regime |
| **DCA benchmark** | Dollar-cost-average benchmark for comparison |
| **Fee sensitivity sweep** | Sweep fee parameters and output performance curves |

### 15.2 File Changes

| File | Change | Content |
|------|--------|---------|
| `fill_model.py` | Modified | Added `IntrabarLimitFill` |
| `cost_model.py` | Modified | Added `MakerTakerCost`, `BinanceCost` + 4 presets |
| `orders.py` | Modified | `Fill`/`Order` gained `exit_reason` field |
| `broker.py` | Modified | Added `submit_oco()` + OCO cancel propagation |
| `engine.py` | Modified | Added `periods_per_year` parameter |
| `result.py` | Modified | Added `exit_reason_stats()` |
| `benchmark.py` | Modified | Added `dca_equity()` |
| `intrabar.py` | **New** | `IntrabarSimulator` |
| `batch_runner.py` | **New** | `StrategyBatchRunner` + `BatchResults` |
| `analyzer.py` | **New** | `BacktestAnalyzer` |
| `fee_sweep.py` | **New** | `fee_sweep()` + `maker_taker_sweep()` |
| `__init__.py` | Modified | Export new components |

### 15.3 Core New Interfaces

#### 15.3.1 IntrabarLimitFill

```python
class IntrabarLimitFill(FillModel):
    """Fills limit orders when intrabar price crosses the limit level.
    LIMIT buy:  next_bar["low"] <= limit_price → fills at limit_price
    LIMIT sell: next_bar["high"] >= limit_price → fills at limit_price
    MARKET:     fills at next_bar["open"] (same as NextOpenFill)
    """
```

Exists in parallel with `NextOpenFill`; strategies explicitly choose. `NextOpenFill` retains original logic unchanged.

#### 15.3.2 MakerTakerCost / BinanceCost

```python
@dataclass
class MakerTakerCost(CostModel):
    maker_rate: float = 0.001
    taker_rate: float = 0.001
    slippage: float = 0.0001
    # LIMIT → maker_rate, MARKET/STOP → taker_rate

@dataclass
class BinanceCost(CostModel):
    venue: str = "spot"          # "spot" | "futures"
    bnb_discount: bool = False
    slippage: float = 0.0001
    # Spot:    maker 0.1% / taker 0.1%  (BNB: -25%)
    # Futures: maker 0.02% / taker 0.05%  (BNB: -10%)

# Convenience presets
BINANCE_SPOT = BinanceCost(venue="spot", bnb_discount=False)
BINANCE_SPOT_BNB = BinanceCost(venue="spot", bnb_discount=True)
BINANCE_FUTURES = BinanceCost(venue="futures", bnb_discount=False)
BINANCE_FUTURES_BNB = BinanceCost(venue="futures", bnb_discount=True)
```

#### 15.3.3 OCO Orders

```python
class SimulatedBroker:
    def submit_oco(self, order_a: Order, order_b: Order) -> tuple[str, str]:
        """Submit an OCO pair. When either fills, the other is auto-cancelled."""
```

No new `OrderType`; the association is managed at the Broker layer.

#### 15.3.4 IntrabarSimulator

```python
class IntrabarSimulator:
    """Simulate limit order fills using finer-grained bars."""
    def __init__(self, fine_data: pd.DataFrame): ...
    def check_fill(self, price_level, side, start_ts, end_ts) -> tuple: ...
    def first_to_fill(self, levels, start_ts, end_ts) -> tuple | None: ...
```

#### 15.3.5 StrategyBatchRunner

```python
class StrategyBatchRunner:
    def run_all(self, strategies: dict) -> BatchResults: ...
    def run_all_fees(self, strategies: dict, cost_models: dict) -> BatchResults: ...

class BatchResults:
    def to_dataframe(self) -> pd.DataFrame: ...
    def equity_curves(self) -> dict: ...
    def best_by(self, metric: str) -> tuple: ...
    def rank(self, metric: str) -> pd.DataFrame: ...
```

#### 15.3.6 BacktestAnalyzer

```python
class BacktestAnalyzer:
    @staticmethod
    def subperiod_metrics(result, split_dates) -> dict: ...
    @staticmethod
    def regime_conditional_metrics(result, regime_series) -> dict: ...
    @staticmethod
    def rolling_metric(result, metric, window) -> pd.Series: ...
    @staticmethod
    def trade_analysis_by_exit(result) -> pd.DataFrame: ...
```

### 15.4 Implementation Phases (BT-8–BT-10)

| Phase | Content | Tests | Priority |
|-------|---------|-------|----------|
| **BT-8** | P0 critical fixes: `IntrabarLimitFill` + `MakerTakerCost` + OCO orders | `test_backtest_p0.py` | ★★★ |
| **BT-9** | P1 enhancements: `BinanceCost` + `IntrabarSimulator` + `StrategyBatchRunner` + `exit_reason` | `test_backtest_p1.py` | ★★☆ |
| **BT-10** | P2 analysis tools: annualization + DCA + `BacktestAnalyzer` + `fee_sweep` | `test_backtest_p2.py` | ★☆☆ |

### 15.5 Backward Compatibility Guarantee

| Existing API | After Enhancement | Compatibility |
|-------------|-------------------|---------------|
| `NextOpenFill()` | Original logic retained | ✅ Fully compatible |
| `PercentCost(commission=0.001)` | Retained | ✅ Fully compatible |
| `Order(symbol, side, qty)` | New `exit_reason=""` default | ✅ Fully compatible |
| `Fill(...)` | New `exit_reason=""` default | ✅ Fully compatible |
| `BacktestEngine(data, strategy)` | New `periods_per_year=None` | ✅ Fully compatible |

Existing user code requires no modifications. New features are enabled by explicitly selecting new classes/parameters.

### 15.6 Dependency Declaration

```toml
[project.optional-dependencies]
backtest = ["stockstat"]                  # Core (includes BT-8–10 enhancements)
optimize = ["optuna>=3.5"]                # BT-6 parameter optimization
backtest_full = ["stockstat[backtest]", "stockstat[optimize]", "stockstat[matplotlib]"]
```

No new external dependencies. All enhancements are pure Python + pandas/numpy.

---

## 16. Pluggable Execution Model Design

> **Added in v1.6 (BT-11–BT-14).** Builds on §15 enhancements by abstracting "how orders fill" into a pluggable `ExecutionModel`, injected into `BacktestEngine` via composition. Supports intrabar sub-bar execution **without adding a new engine class**. Design principle: general solution enriches library + simplified interface stays concise + strict backward compatibility.

### 16.1 Design Motivation

§15's BT-8–BT-10 addressed intrabar limit fills, Maker/Taker fees, and batch backtesting, but v5 research still exposed 5 structural gaps (see `working/PAXG-Weekend-Monday-Law-v5-redo/BACKTEST_IMPROVEMENT_REPORT_V2.md`):

| Gap | Description | Root Cause |
|-----|-------------|------------|
| Gap-1 | Intrabar fill timing not tracked | `FillModel` returns only price |
| Gap-2 | Same-bar entry + exit | Event loop t→t+1 constraint |
| Gap-3 | Post-entry conditional exit scan | No intrabar forward-scan hook |
| Gap-4 | Dual-fill → dual-cancel | OCO semantics insufficient |
| Gap-5 | SL priority over TP within same bar | Broker has no priority sorting |

The V1 approach (a separate `IntrabarExecutionEngine` class) had 8 compatibility blind spots. The V2 approach uses a pluggable `ExecutionModel` architecture: **one engine class + two execution modes**.

### 16.2 Architecture

```mermaid
graph TB
    subgraph "BacktestEngine (single engine class)"
        ENG["execution_model parameter<br/>default: NextBarExecution"]
        EM["ExecutionModel ABC"]
        NB["NextBarExecution<br/>default: t→t+1 fill"]
        IB["IntrabarExecution<br/>intrabar sub-bar matching"]
    end

    subgraph "IntrabarExecution internals"
        FILL["IntrabarFillModel<br/>sub-bar scan + timing"]
        SCAN["_scan_sub_bars<br/>pre-scan→OCO check→apply→exit scan"]
        EXIT["_scan_exits<br/>limit/stop per-bar + market close at session end"]
        OCO["register_oco_mutual<br/>both fill → both cancel"]
    end

    subgraph "Strategy layer (duck typing)"
        STR["Strategy base class (unchanged)"]
        MIX["IntrabarMixin (optional)<br/>define_exits()"]
    end

    ENG --> EM
    EM --> NB
    EM --> IB
    IB --> FILL
    IB --> SCAN
    SCAN --> EXIT
    SCAN --> OCO
    STR -.-> MIX
```

### 16.3 Core Interfaces

```python
# execution_model.py (new file)

class ExecutionModel(ABC):
    """Execution model: decides how/when pending orders fill within a bar."""
    @abstractmethod
    def execute(self, engine, ctx, t, pending_orders) -> list[Fill]: ...
    @property
    @abstractmethod
    def is_intrabar(self) -> bool: ...

class NextBarExecution(ExecutionModel):
    """Default: order submitted at t → fills at t+1 bar (existing behavior)."""
    is_intrabar = False

class IntrabarExecution(ExecutionModel):
    """Intrabar: matches orders within a parent bar's sub-bar sequence."""
    def __init__(self, intrabar_tf, parent_tf=None, fill_model=None): ...
    def register_oco_mutual(self, order_a, order_b): ...
    is_intrabar = True
```

### 16.4 File Changes

| File | Change | Content |
|------|--------|---------|
| `execution_model.py` | **New** | `ExecutionModel` ABC + `NextBarExecution` + `IntrabarExecution` |
| `fill_model.py` | New classes | `IntrabarFillResult` + `IntrabarFillModel` (inherits `IntrabarLimitFill`) |
| `orders.py` | New fields | `Order.priority: int = 99` + `Fill.sub_bar_ts` + `Fill.sub_bar_index` |
| `data_feed.py` | New method | `DataFeed.intrabar_slice()` |
| `engine.py` | New param | `execution_model` parameter + intrabar branch + parent_tf iteration |
| `context.py` | New methods | `intrabar_submit()` + `intrabar_submit_oco_mutual()` (mode-aware degradation) |
| `broker.py` | New method | `submit_oco_mutual()` |
| `strategy.py` | New class | `IntrabarMixin` (optional mixin with `define_exits` default) |

### 16.5 Gap Resolution

| Gap | Solution |
|-----|----------|
| Gap-1 | `Fill.sub_bar_ts` + `Fill.sub_bar_index` + `IntrabarFillModel.fill_with_timing()` |
| Gap-2 | `IntrabarExecution` completes entry→exit lifecycle within a parent bar |
| Gap-3 | Duck-typed `define_exits()` detection + `_scan_exits()` forward scan |
| Gap-4 | `register_oco_mutual()` + pre-scan detects dual fills |
| Gap-5 | `Order.priority` field + sort (SL priority=0 > TP priority=1) |

### 16.6 Backward Compatibility Guarantee

| Existing API | After Enhancement | Compatibility |
|-------------|-------------------|---------------|
| `BacktestEngine(data, strategy)` | New `execution_model=None` | ✅ Default `NextBarExecution` = existing behavior |
| `FillModel` ABC | Unchanged | ✅ `fill_with_timing` is a non-abstract new method |
| `Fill` / `Order` | New fields have defaults | ✅ Dataclass trailing defaults |
| `Strategy` base class | Unchanged | ✅ Duck-typed `define_exits` detection |
| `@strategy` functions | Unchanged | ✅ Function-style strategies fully compatible |
| `ctx.intrabar_submit()` | Degrades in default mode | ✅ Falls back to `broker.submit` + warning |

### 16.7 Implementation Phases (BT-11–BT-14)

| Phase | Content | Tests | Priority |
|-------|---------|-------|----------|
| **BT-11** | ExecutionModel ABC + IntrabarFillModel + Fill/Order fields + intrabar_slice | `test_backtest_intrabar.py` (compat + FillModel + DataFeed) | ★★★ |
| **BT-12** | IntrabarExecution + IntrabarMixin + OCO mutual + engine integration | same (same-bar exit + define_exits + priority + OCO) | ★★★ |
| **BT-13** | v5 strategy migration validation (33 strategies × 4 fees = 132 runs) | `run_redo.py` (PnL error < 0.1%) | ★★☆ |
| **BT-14** | Analysis & visualization adaptation | `plots_redo.py` | ★☆☆ |

### 16.8 Validation Results

- All 314 pre-existing tests pass (zero regression)
- All 23 new intrabar tests pass
- v5's 33 strategies × 4 fees = 132 runs, key strategy PnL error < 0.1%
- Conclusion unchanged: no strategy beat buy-and-hold PAXG (+104.84%)

---

## Appendix A: Data Source Compatibility Matrix

| Data Source | Asset Type | Free Quota | Real-time Support | Historical Depth | Adapter Difficulty |
|-------------|-----------|-----------|-------------------|-----------------|-------------------|
| yfinance | US Stocks/ETF | Free | 15-min delayed | 10+ years | Low |
| Alpha Vantage | Global Stocks | 25 req/day | 15-min delayed | 20+ years | Low |
| Tushare | A-Shares | Credit-based | End-of-day | 10+ years | Medium |
| ccxt (Binance) | Crypto | Free | Real-time | Full history | Low |
| ccxt (Coinbase) | Crypto | Free | Real-time | Full history | Low |

## Appendix B: OHLCV Data Volume Estimation

| Instrument Scope | # Instruments | Daily Data | Annual Data | Storage Estimate |
|-----------------|---------------|-----------|------------|-----------------|
| US Top 500 | 500 | 500 rows | 125K rows | ~10 MB |
| A-Share full market | 5000 | 5000 rows | 1.25M rows | ~100 MB |
| Crypto Top 200 | 200 | 200 rows | 50K rows | ~5 MB |
| Crypto 1-min data (200 instruments) | 200 | 288K rows | 73M rows | ~5 GB |

> TimescaleDB compression can reduce this to 10%~20% of the raw volume.

---

*This design document will be continuously updated as the project iterates.*
