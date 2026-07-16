# StockStat — 可编程金融标的统计计算平台 设计报告

> **版本**: v1.5  
> **日期**: 2026-07-16  
> **状态**: 设计阶段（新增回测引擎增强子系统 BT-8~BT-10）

---

## 目录

1. [项目概述](#1-项目概述)
2. [总体架构](#2-总体架构)
3. [存储后端设计](#3-存储后端设计)
4. [计算前端设计](#4-计算前端设计)
5. [脚本语言设计](#5-脚本语言设计)
6. [API 规范](#6-api-规范)
7. [测试用例](#7-测试用例)
8. [技术栈选型](#8-技术栈选型)
9. [部署方案](#9-部署方案)
10. [项目结构](#10-项目结构)
11. [开发路线图](#11-开发路线图)
12. [回测子系统设计](#12-回测子系统设计)
13. [回测可视化子系统设计](#13-回测可视化子系统设计)
14. [回测引擎增强与可插拔执行模型](#15-回测引擎增强与可插拔执行模型)
- [附录 A: 数据源兼容性矩阵](#附录-a-数据源兼容性矩阵)
- [附录 B: OHLCV 数据量估算](#附录-b-ohlcv-数据量估算)
- [附录 C: 回测阶段实现文档索引](#附录-c-回测阶段实现文档索引)

---

## 1. 项目概述

### 1.1 项目目标

构建一个**用户可编程**的股票/虚拟货币标的统计量计算平台，核心能力包括：

- **统一数据接入**：兼容多数据源（股票交易所、加密货币交易所、第三方API），对上层提供统一接口
- **可编程计算**：用户可通过 Python 库 或自定义 DSL 编写统计计算逻辑
- **前后端分离**：存储后端作为独立可部署服务，计算前端以库形式接入，可配置连接
- **可扩展**：数据源适配器、指标算法均为插件化设计

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **数据与计算分离** | 存储后端只负责数据采集、存储、查询；计算逻辑全部在前端库完成 |
| **统一抽象** | 不同数据源的数据经标准化层后，对外暴露一致的 OHLCV 模型 |
| **可编程优先** | 不内置固定策略，提供丰富的原语让用户自由组合 |
| **渐进式复杂度** | 简单查询用 DSL 一行搞定，复杂分析用 Python 库全功能实现 |
| **可复现** | 每次计算可记录数据快照版本与参数，保证结果可复现 |

### 1.3 核心功能清单

```
□ 多数据源接入（yfinance / Alpha Vantage / Tushare / ccxt / 自定义）
□ OHLCV 标准化存储（TimescaleDB）
□ 统一 REST API 查询
□ Python 计算库（pandas/numpy 集成）
□ 表达式 DSL（SQL-like 统计查询语言）
□ 内置技术指标库（MA / EMA / RSI / MACD / ATR / Beta / Sharpe …）
□ 自定义指标注册机制
□ 计算结果导出（JSON / CSV / DataFrame）
□ 可选可视化层（协议化设计，matplotlib 作为可选 extras，核心零依赖）
□ 数据缓存与增量更新
```

---

## 2. 总体架构

### 2.1 架构总览

```mermaid
graph TB
    subgraph "数据源 Data Sources"
        DS1[yfinance<br/>美股/ETF]
        DS2[Alpha Vantage<br/>全球股票]
        DS3[Tushare<br/>A股]
        DS4[ccxt<br/>100+ 加密货币交易所]
        DS5[自定义适配器]
    end

    subgraph "存储后端 Storage Backend（独立部署服务）"
        direction TB
        DA[数据源适配器层<br/>Data Source Adapters]
        NL[数据标准化层<br/>Normalization Layer]
        SE[存储引擎<br/>TimescaleDB]
        API[统一 API 层<br/>FastAPI REST]
        SCHED[调度器<br/>定时采集/增量更新]
        CACHE[缓存层<br/>Redis]

        DA --> NL --> SE
        SCHED --> DA
        SE <--> CACHE
        API --> SE
        API <--> CACHE
    end

    subgraph "计算前端 Computation Frontend（Python 库）"
        direction TB
        CONN[连接管理器<br/>Connection Manager]
        DAL[数据访问层<br/>Data Access Layer]
        CE[计算引擎<br/>Compute Engine]
        DSL[DSL 解析器<br/>DSL Parser]
        IL[指标库<br/>Indicator Library]
        EXP[结果导出<br/>Export]

        CONN --> DAL
        DSL --> CE
        DAL --> CE
        IL --> CE
        CE --> EXP
    end

    subgraph "用户层"
        U1[Python 脚本]
        U2[DSL 脚本]
        U3[Jupyter Notebook]
    end

    DS1 & DS2 & DS3 & DS4 & DS5 --> DA
    API -.->|"HTTP/REST"| DAL
    U1 & U2 & U3 --> CE
```

### 2.2 组件职责划分

```mermaid
graph LR
    subgraph Storage["存储后端（服务进程）"]
        S1[数据采集]
        S2[数据标准化]
        S3[持久化存储]
        S4[查询服务]
        S1 --> S2 --> S3 --> S4
    end

    subgraph Compute["计算前端（Python 库 / 进程内）"]
        C1[数据拉取]
        C2[计算执行]
        C3[结果输出]
        C1 --> C2 --> C3
    end

    S4 -.->|"REST API<br/>JSON/Arrow"| C1
```

### 2.3 数据流

```mermaid
sequenceDiagram
    participant User as 用户脚本
    participant FE as 计算前端
    participant BE as 存储后端
    participant Src as 数据源

    Note over BE,Src: 阶段1: 数据采集（异步/定时）
    BE->>Src: fetch_ohlcv(symbol, range)
    Src-->>BE: 原始数据
    BE->>BE: 标准化 → 存储

    Note over User,FE: 阶段2: 计算请求
    User->>FE: run(script / python code)
    FE->>BE: GET /api/v1/ohlcv?symbol=...&...
    BE-->>FE: 标准化OHLCV数据
    FE->>FE: 执行计算逻辑
    FE-->>User: 结果（DataFrame/JSON）
```

---

## 3. 存储后端设计

### 3.1 数据源适配器层

数据源适配器采用**插件化**设计，每个适配器实现统一接口，支持热注册。

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

**适配器注册机制**：

```python
# 存储后端配置示例 (config.yaml)
data_sources:
  - name: yfinance
    type: stock
    enabled: true
    
  - name: binance
    type: crypto
    adapter: ccxt
    config:
      exchange: binance
      rate_limit: 10  # 请求/秒
    
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
      market: A股
```

### 3.1.1 代理支持

存储后端支持为所有数据源适配器配置 HTTP/SOCKS5 代理，**默认关闭**。开启后，所有对外的数据采集请求（yfinance、ccxt 等）均经由代理转发。

| 设计约束 | 说明 |
|----------|------|
| **默认关闭** | `STOCKSTAT_PROXY_ENABLED` 未设置或为 false 时，所有适配器直连 |
| **双协议支持** | 支持 `http` 和 `socks5` 两种代理类型 |
| **默认地址** | HTTP 默认 `http://127.0.0.1:8889`；SOCKS5 默认 `socks5://127.0.0.1:1089` |
| **统一注入** | 代理配置在适配器实例化时注入，对上层透明 |

```mermaid
graph LR
    subgraph "代理配置 ProxyConfig"
        PC["ProxyConfig<br/>enabled / url / proxy_type"]
    end
    
    subgraph "适配器注入"
        YD["YahooDirectAdapter<br/>requests.Session.proxies"]
        CC["CcxtAdapter<br/>exchange.proxies"]
        SY["SyntheticAdapter<br/>无需代理"]
    end
    
    PC --> YD
    PC --> CC
    PC -.->|"enabled=false<br/>proxies=None"| YD
    PC -.->|"enabled=false<br/>proxies=None"| CC
```

**环境变量配置**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | 是否启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | 代理类型：`http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | （按类型自动填充） | 代理地址，未设置时使用默认值 |

```bash
# 启用 HTTP 代理（默认地址）
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
# STOCKSTAT_PROXY_URL 默认为 http://127.0.0.1:8889

# 启用 SOCKS5 代理（默认地址）
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=socks5
# STOCKSTAT_PROXY_URL 默认为 socks5://127.0.0.1:1089

# 自定义代理地址
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://192.168.1.100:8080
```

**REST API 查询代理状态**：

```
GET /api/v1/proxy
→ {"enabled": true, "url": "http://127.0.0.1:8889", "proxy_type": "http"}

GET /api/v1/health
→ {"status": "ok", "proxy": {"enabled": true, "url": "http://127.0.0.1:8889", "proxy_type": "http"}}
```

### 3.2 数据标准化层

不同数据源的原始数据格式各异，标准化层负责将其统一为内部规范格式。

```mermaid
graph LR
    subgraph "原始数据（异构）"
        R1["yfinance<br/>Datetime/Open/High/Low/Close/Adj Close/Volume"]
        R2["ccxt<br/>timestamp(ms)/open/high/low/close/vol"]
        R3["tushare<br/>trade_date/open/high/low/close/vol/amount"]
    end

    subgraph "标准化层"
        SM["符号映射<br/>Symbol Mapper"]
        TF["时间框架对齐<br/>Timeframe Aligner"]
        TZ["时区统一<br/>UTC标准化"]
        FV["字段校验<br/>Field Validator"]
    end

    subgraph "标准化输出"
        STD["统一OHLCV<br/>symbol / ts(UTC) / open / high / low / close / volume / source"]
    end

    R1 & R2 & R3 --> SM --> TF --> TZ --> FV --> STD
```

**统一数据模型**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | `VARCHAR` | 统一符号标识，如 `BTC/USDT`, `AAPL`, `600000.SH` |
| `ts` | `TIMESTAMPTZ` | UTC 时间戳 |
| `open` | `NUMERIC` | 开盘价 |
| `high` | `NUMERIC` | 最高价 |
| `low` | `NUMERIC` | 最低价 |
| `close` | `NUMERIC` | 收盘价 |
| `volume` | `NUMERIC` | 成交量 |
| `source` | `VARCHAR` | 数据来源标识 |
| `timeframe` | `VARCHAR` | 时间周期 `1m/5m/15m/1h/4h/1d/1w` |

**符号映射表**：

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
        timestamp ts PK "时间戳"
        numeric open
        numeric high
        numeric low
        numeric close
        numeric volume
        string source
        string timeframe
    }
```

### 3.3 存储引擎

选用 **TimescaleDB**（PostgreSQL 时序扩展），理由：

- 原生 SQL，生态成熟
- Hypertable 自动按时间分区，查询高效
- 支持连续聚合（Continuous Aggregates），可预计算常用时间框架
- 与 Python 生态（pandas/SQLAlchemy）无缝对接

```mermaid
graph TB
    subgraph "TimescaleDB 存储结构"
        direction TB
        HT["hypertable: ohlcv<br/>按 timeframe 分区"]
        
        subgraph "连续聚合 Continuous Aggregates"
            CA1[agg_1h - 1小时聚合]
            CA2[agg_1d - 1日聚合]
            CA3[agg_1w - 1周聚合]
        end
        
        HT --> CA1
        CA1 --> CA2
        CA2 --> CA3
    end
    
    subgraph "元数据表"
        MT1[symbol_registry - 符号注册表]
        MT2[data_source - 数据源配置]
        MT3[ingest_log - 采集日志]
        MT4[data_version - 数据版本快照]
    end
    
    HT -.-> MT3
```

**Hypertable 创建 DDL**：

```sql
-- 创建 hypertable
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

-- 索引
CREATE INDEX idx_ohlcv_symbol_ts ON ohlcv (symbol, ts DESC);
CREATE INDEX idx_ohlcv_timeframe ON ohlcv (timeframe);

-- 连续聚合：1日级别
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

### 3.4 调度器

```mermaid
graph TB
    subgraph "调度器 Scheduler"
        CRON[定时任务引擎]
        
        subgraph "采集任务"
            T1[全量历史回填<br/>首次接入]
            T2[增量更新<br/>每日/每小时]
            T3[实时拉取<br/>WebSocket推送]
        end
        
        subgraph "维护任务"
            M1[连续聚合刷新]
            M2[数据完整性校验]
            M3[旧数据归档]
        end
    end
    
    CRON --> T1 & T2 & T3 & M1 & M2 & M3
```

### 3.5 缓存策略

```mermaid
graph LR
    REQ[查询请求] --> CHK{Redis缓存命中?}
    CHK -->|是| RET1[返回缓存]
    CHK -->|否| DB[查询TimescaleDB]
    DB --> SET[写入Redis<br/>TTL=300s]
    SET --> RET2[返回结果]
```

---

## 4. 计算前端设计

### 4.1 客户端架构

```mermaid
graph TB
    subgraph "StockStat Compute Library"
        direction TB
        
        subgraph "接入层"
            CM[ConnectionManager<br/>配置与连接管理]
            CFG[Config<br/>host/port/api_key/timeout]
        end
        
        subgraph "数据访问层"
            DC[DataClient<br/>OHLCV查询]
            MC[MetaClient<br/>符号/元数据查询]
            AR[ArrowCodec<br/>高效序列化]
        end
        
        subgraph "计算引擎"
            EN[ComputeEngine<br/>核心执行器]
            CTX[ComputeContext<br/>计算上下文]
            REG[IndicatorRegistry<br/>指标注册表]
        end
        
        subgraph "DSL 层"
            PARSER[Parser<br/>语法解析]
            AST[AST Builder<br/>抽象语法树]
            EVAL[Evaluator<br/>求值器]
        end
        
        subgraph "内置指标库"
            I1[趋势类: MA/EMA/MACD]
            I2[震荡类: RSI/KDJ]
            I3[波动类: ATR/Bollinger]
            I4[统计类: Corr/Beta/Sharpe]
            I5[自定义: 用户注册]
        end
        
        subgraph "输出层"
            DF[DataFrame输出]
            JSON[JSON输出]
            CSV[CSV输出]
        end
        
        subgraph "可视化层（可选 · 协议化）"
            PS[PlotSpec<br/>后端无关的绘图规格]
            PR[PlotRenderer 协议<br/>Null/Matplotlib/Plotly]
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

### 4.2 连接管理

```python
from stockstat import StockStatClient

# 方式1: 配置文件
client = StockStatClient.from_config("stockstat.yaml")

# 方式2: 直接配置
client = StockStatClient(
    host="localhost",
    port=8000,
    api_key="optional-key",
    timeout=30,
    cache_enabled=True
)

# 方式3: 环境变量
client = StockStatClient.from_env()
```

### 4.3 数据访问层

```python
# 获取OHLCV数据，返回 pandas DataFrame
data = client.ohlcv(
    symbol="PAXG/USDT",
    source="binance",
    start="2022-01-01",
    end="2024-12-31",
    timeframe="1d"
)
# DataFrame 列: open, high, low, close, volume (DatetimeIndex)

# 批量获取
data = client.ohlcv_batch(
    symbols=["BTC/USDT", "ETH/USDT", "PAXG/USDT"],
    start="2024-01-01",
    timeframe="1d"
)

# 获取可用符号列表
symbols = client.symbols(asset_type="crypto", source="binance")
```

### 4.4 计算引擎与指标注册

```python
from stockstat import indicator, ComputeContext

# 使用内置指标
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
beta = client.compute.beta(asset="AAPL", benchmark="^GSPC", window=60)

# 注册自定义指标
@indicator(name="weekend_gain_loss_corr", category="custom")
def weekend_monday_gain_loss(data: pd.DataFrame) -> dict:
    """
    计算 PAXG 周末涨跌幅与周一最大涨幅和最大跌幅的独立相关性。
    同时记录两者，避免选择偏差。
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

# 执行自定义指标
result = client.compute.call("weekend_gain_loss_corr", data=data)
```

### 4.5 可视化与 matplotlib 适配设计

#### 4.5.1 设计目标

可视化层遵循**核心零硬依赖**原则：核心计算库不依赖 matplotlib 或任何绘图库；当用户安装了 matplotlib 后，可自动启用增强绘图能力。

| 设计约束 | 说明 |
|----------|------|
| **零硬依赖** | `import stockstat` 不触发任何绘图库导入；`pyproject.toml` 的核心依赖不含 matplotlib |
| **协议抽象** | 定义 `PlotRenderer` 协议，多后端可插拔（matplotlib / plotly / 无渲染器） |
| **数据与渲染分离** | 计算引擎产出后端无关的 `PlotSpec`（绘图规格），由渲染器解释为具体图形 |
| **延迟导入** | matplotlib 仅在用户首次调用渲染时才被 `import`，缺失时优雅降级 |
| **可选 extras** | 通过 `pip install stockstat[matplotlib]` 拉取绘图依赖 |

#### 4.5.2 类设计

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

#### 4.5.3 模块组织与延迟导入

```
stockstat/
└── plot/
    ├── __init__.py          # 对外暴露 PlotSpec / plot() / get_renderer()
    ├── base.py              # PlotRenderer 协议 + NullRenderer 默认实现
    └── matplotlib_backend.py # matplotlib 适配（模块内延迟 import matplotlib）
```

`matplotlib_backend.py` 内部采用延迟导入，确保核心库导入链不被污染：

```python
# stockstat/plot/matplotlib_backend.py
from .base import PlotRenderer, PlotSpec

class MatplotlibRenderer(PlotRenderer):
    def __init__(self):
        self._plt = None   # 延迟到首次 render 时才导入

    def available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
            return True
        except ImportError:
            return False

    def render(self, spec: PlotSpec):
        import matplotlib.pyplot as plt   # 仅在此处导入
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

#### 4.5.4 自动检测与优雅降级

`RendererFactory.detect()` 按优先级探测已安装的后端；若全部缺失，返回 `NullRenderer`，调用时仅发出告警而非抛异常。

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
    return NullRenderer()   # 安全兜底，零依赖可用
```

#### 4.5.5 使用方式

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)
data = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")

# 方式A: 协议化绘图（推荐，后端无关）
spec = client.plot.spec(
    title="BTC/USDT 2024",
    series=[
        {"name": "close", "data": data.close, "kind": "line"},
        {"name": "ma20",  "data": data.close.rolling(20).mean(), "kind": "line"},
    ],
)
renderer = client.plot.get_renderer()     # 自动检测，缺失则 NullRenderer
renderer.render(spec)
renderer.savefig("btc.png")               # matplotlib 存在时生效

# 方式B: 直接把计算结果交给 matplotlib（用户自管依赖）
import matplotlib.pyplot as plt           # 用户自行导入
plt.plot(data.index, data.close)
plt.title("BTC/USDT")
plt.show()

# 方式C: 取回后端无关数据，自行选择任意绘图库
payload = spec.to_dict()                  # 纯 dict / JSON 可序列化
```

#### 4.5.6 依赖声明

`pyproject.toml` 采用可选 extras，核心安装不引入 matplotlib：

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

## 5. 脚本语言设计

提供**双模式**可编程接口：Python 库（全功能）+ DSL（轻量声明式）。

### 5.1 模式对比

```mermaid
graph TB
    subgraph "Python 库模式（全功能）"
        direction TB
        P1["✅ 完整 pandas/numpy 生态"]
        P2["✅ 任意复杂逻辑"]
        P3["✅ 可调试/可断点"]
        P4["⚠️ 需要 Python 环境"]
        P5["⚠️ 安全性需用户自负"]
    end
    
    subgraph "DSL 模式（轻量声明式）"
        direction TB
        D1["✅ 一行完成常见统计"]
        D2["✅ 沙箱安全执行"]
        D3["✅ 可序列化/可存储/可复现"]
        D4["✅ 非 Python 用户友好"]
        D5["⚠️ 表达能力有限"]
    end
```

### 5.2 Python 库模式

完整的 Python API，适合复杂分析场景：

```python
from stockstat import StockStatClient
import pandas as pd

client = StockStatClient(host="localhost", port=8000)

# 获取数据
paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")

# 自由计算
df = paxg.copy()
df['ret'] = df['close'].pct_change()
df['vol_20'] = df['ret'].rolling(20).std()
df['ma50'] = df['close'].rolling(50).mean()

# 任意 pandas 操作
result = df[df['vol_20'] > df['vol_20'].quantile(0.9)]
```

### 5.3 DSL 模式

设计为 **SQL-like 声明式统计查询语言**，语法贴近分析师直觉。

#### 5.3.1 语法设计

```mermaid
graph LR
    subgraph "DSL 执行流水线"
        SRC["源代码<br/>DSL Script"] --> LEX[词法分析<br/>Lexer]
        LEX --> PAR[语法分析<br/>Parser]
        PAR --> AST2["抽象语法树<br/>AST"]
        AST2 --> SEM[语义检查<br/>Semantic Check]
        SEM --> OPT[优化<br/>Optimizer]
        OPT --> EXE[求值执行<br/>Evaluator]
        EXE --> RES["结果<br/>DataFrame/JSON"]
    end
```

#### 5.3.2 语法规范

```
# DSL 语法 BNF 概要

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

#### 5.3.3 DSL 示例

```sql
-- 示例1: 计算20日均线与收盘价
SELECT 
    close,
    ma(close, 20) AS ma20,
    ema(close, 12) AS ema12
FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")

-- 示例2: 计算 RSI 超买超卖信号
SELECT 
    close,
    rsi(close, 14) AS rsi,
    CASE WHEN rsi(close, 14) > 70 THEN 'overbought'
         WHEN rsi(close, 14) < 30 THEN 'oversold'
         ELSE 'neutral' END AS signal
FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")

-- 示例3: PAXG 周末涨跌与周一高低差相关性
SELECT 
    corr(
        returns(close, filter=weekend_filter),
        spread(high, low, filter=weekday_filter(0))
    ) AS weekend_monday_corr
FROM ohlcv("PAXG/USDT", "1d", "2022-01-01", "2024-12-31")

-- 示例4: 多标的 Beta 计算
SELECT 
    beta(close, benchmark="^GSPC", window=60) AS beta_60d
FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
```

#### 5.3.4 DSL 内置函数清单

| 类别 | 函数 | 说明 |
|------|------|------|
| **趋势** | `ma(x, n)` | 简单移动平均 |
| | `ema(x, n)` | 指数移动平均 |
| | `macd(x, fast, slow, signal)` | MACD |
| **震荡** | `rsi(x, n)` | 相对强弱指数 |
| | `kdj(high, low, close, n)` | KDJ 指标 |
| **波动** | `std(x, n)` | 滚动标准差 |
| | `atr(high, low, close, n)` | 平均真实波幅 |
| | `bollinger(x, n, k)` | 布林带 |
| **统计** | `corr(x, y)` | 相关系数 |
| | `beta(x, benchmark)` | Beta 系数 |
| | `sharpe(returns, rf)` | 夏普比率 |
| | `max_drawdown(cumret)` | 最大回撤 |
| **变换** | `returns(x)` | 收益率序列 |
| | `log_returns(x)` | 对数收益率 |
| | `rolling(x, n, func)` | 滚动窗口 |
| | `shift(x, n)` | 位移 |
| | `rank(x)` | 排名 |
| **过滤** | `weekend_filter` | 周末过滤 |
| | `weekday_filter(n)` | 指定星期过滤 |
| | `spread(high, low)` | 高低差价 |

---

## 6. API 规范

### 6.1 REST API 总览

```mermaid
graph LR
    subgraph "REST API 端点"
        E1["GET /api/v1/health<br/>健康检查"]
        E2["GET /api/v1/symbols<br/>符号列表"]
        E3["GET /api/v1/symbols/:sym<br/>符号详情"]
        E4["GET /api/v1/ohlcv<br/>OHLCV查询"]
        E5["POST /api/v1/ingest<br/>手动触发采集"]
        E6["GET /api/v1/sources<br/>数据源列表"]
        E7["GET /api/v1/metadata<br/>元数据"]
    end
```

### 6.2 核心 API 定义

#### GET /api/v1/ohlcv

获取 OHLCV 数据，支持多种返回格式。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 统一符号，如 `PAXG/USDT` |
| `source` | string | 否 | 指定数据源 |
| `start` | string (ISO date) | 否 | 开始时间 |
| `end` | string (ISO date) | 否 | 结束时间 |
| `timeframe` | string | 否 | 时间周期，默认 `1d` |
| `limit` | int | 否 | 返回条数上限 |
| `format` | string | 否 | `json` / `arrow` / `csv`，默认 `json` |

**响应示例** (JSON)：

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

**Apache Arrow 格式**（高效传输）：

```
GET /api/v1/ohlcv?symbol=PAXG/USDT&format=arrow
Accept: application/vnd.apache.arrow.file

→ 返回 Arrow IPC 格式二进制流，前端可直接零拷贝转 DataFrame
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

### 6.3 错误处理

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

| HTTP Code | Error Code | 说明 |
|-----------|-----------|------|
| 400 | `INVALID_PARAMS` | 参数校验失败 |
| 404 | `SYMBOL_NOT_FOUND` | 符号不存在 |
| 404 | `DATA_NOT_FOUND` | 无数据 |
| 429 | `RATE_LIMITED` | 限流 |
| 500 | `INTERNAL_ERROR` | 服务内部错误 |

---

## 7. 测试用例

### 7.1 经典股票统计测试用例

```mermaid
mindmap
  root((测试用例))
    趋势分析
      MA金叉死叉
      EMA多空排列
      MACD背离检测
    震荡指标
      RSI超买超卖
      KDJ金叉信号
    波动率
      历史波动率计算
      ATR止损位
      布林带突破
    风险统计
      Beta系数
      最大回撤
      VaR在险价值
      Sharpe比率
    相关性
      跨资产相关性
      PAXG周末效应
    策略回测
      均线交叉策略
      动量策略
```

#### 用例 1: 移动平均线金叉/死叉

```python
"""测试 MA 金叉死叉信号的正确性"""
client = StockStatClient(host="localhost", port=8000)
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")

ma_short = data.close.rolling(5).mean()
ma_long = data.close.rolling(20).mean()

# 金叉：短均线上穿长均线
golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
# 死叉：短均线下穿长均线
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

assert golden_cross.sum() >= 0  # 至少不报错
assert death_cross.sum() >= 0
# 验证：金叉后短期收益率均值应为正
```

#### 用例 2: RSI 超买超卖检测

```python
"""RSI 值域 [0, 100]，>70 超买，<30 超卖"""
data = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
rsi = client.compute.rsi(data.close, window=14)

assert rsi.between(0, 100).all()
assert rsi.isna().sum() == 14  # 前14个为NaN
# 验证已知大涨日 RSI 应较高
```

#### 用例 3: Beta 系数计算

```python
"""Beta = Cov(Ri, Rm) / Var(Rm)"""
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")

beta = client.compute.beta(
    asset=stock.close.pct_change(),
    benchmark=market.close.pct_change(),
    window=60
)

# AAPL 的 Beta 通常在 1.0~1.3 之间
assert 0.5 < beta.dropna().mean() < 2.0
```

#### 用例 4: 最大回撤

```python
"""最大回撤 = max(1 - P_t / max(P_0..P_t))"""
data = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
cumret = data.close / data.close.iloc[0]
running_max = cumret.cummax()
drawdown = (cumret - running_max) / running_max
max_dd = drawdown.min()

assert max_dd <= 0  # 回撤应为负数
assert max_dd >= -1  # 回撤不超过-100%
```

#### 用例 5: 夏普比率

```python
"""Sharpe = (E[R] - Rf) / std(R) * sqrt(252)"""
data = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
returns = data.close.pct_change().dropna()

sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
# 高波动资产的 Sharpe 通常在 -1 ~ 3 之间
assert -5 < sharpe < 10
```

#### 用例 6: 布林带突破

```python
"""布林带 = MA ± k * std"""
data = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2)

# 上轨应始终 >= 中轨 >= 下轨
assert (upper >= mid).all()
assert (mid >= lower).all()
# 突破上轨的频率应较低（<10%）
breakout = (data.close > upper).sum() / len(data)
assert breakout < 0.15
```

#### 用例 7: 跨资产相关性

```python
"""BTC 与 ETH 应高度正相关"""
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")

corr = btc.close.pct_change().corr(eth.close.pct_change())
assert corr > 0.7  # BTC/ETH 日收益率相关性通常 > 0.7
```

### 7.2 PAXG 周末涨跌与周一独立涨跌幅相关性

> **自定义测试用例**：统计 PAXG（PAX Gold，黄金锚定代币）周末涨跌幅与周一最大涨幅 `(最高-开盘)/开盘` 和最大跌幅 `(最低-开盘)/开盘` 之间的独立相关性。同时记录两者，避免按信号方向选择极值导致的选择偏差。

#### 7.2.1 分析逻辑

```mermaid
graph LR
    subgraph "周末涨跌幅 X"
        F["周五收盘价 C_Fri"]
        S["周日收盘价 C_Sun"]
        X["X = (C_Sun - C_Fri) / C_Fri"]
    end
    
    subgraph "周一最大涨幅 Y1"
        MO["周一开盘价 O_Mon"]
        MH["周一最高价 H_Mon"]
        Y1["Y1 = (H_Mon - O_Mon) / O_Mon"]
    end

    subgraph "周一最大跌幅 Y2"
        MO2["周一开盘价 O_Mon"]
        ML["周一最低价 L_Mon"]
        Y2["Y2 = (L_Mon - O_Mon) / O_Mon"]
    end
    
    X --> CORR1["r(X, Y1)"]
    Y1 --> CORR1
    X --> CORR2["r(X, Y2)"]
    Y2 --> CORR2
```

**假设**：PAXG 锚定黄金，周末传统黄金市场休市，PAXG 周末价格若发生偏离，可能适度预测周一日内极值。通过独立记录涨幅和跌幅，避免按信号方向选择极值导致的选择偏差。

#### 7.2.2 Python 实现

```python
"""
PAXG 周末涨跌与周一独立涨跌幅相关性测试。
同时记录 (最高-开盘)/开盘 和 (最低-开盘)/开盘。
"""
import pandas as pd
from scipy import stats
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# ── 1. 获取 PAXG 日线数据 ──
paxg = client.ohlcv(
    symbol="PAXG/USDT", source="binance",
    start="2022-01-01", end="2024-12-31", timeframe="1d"
)

# ── 2. 标注星期几 ──
df = paxg.copy()
df['weekday'] = df.index.weekday

# ── 3. 提取周五收盘、周日收盘、周一 OHLC ──
fridays = df[df['weekday'] == 4][['close']].rename(columns={'close': 'fri_close'})
sundays = df[df['weekday'] == 6][['close']].rename(columns={'close': 'sun_close'})
mondays = df[df['weekday'] == 0][['open', 'high', 'low', 'close']].copy()

# ── 4. 构建周末-周一配对 ──
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

# ── 5. 计算独立相关性 ──
r_gain = result_df['weekend_return'].corr(result_df['max_gain'])
r_loss = result_df['weekend_return'].corr(result_df['max_loss'])
p_gain = stats.pearsonr(result_df['weekend_return'], result_df['max_gain'])[1]
p_loss = stats.pearsonr(result_df['weekend_return'], result_df['max_loss'])[1]

# ── 6. 分组对比 ──
up = result_df[result_df['weekend_return'] > 0]
dn = result_df[result_df['weekend_return'] < 0]

print(f"样本数:    {len(result_df)} (up={len(up)}, dn={len(dn)})")
print(f"r(涨幅):   {r_gain:.4f}  p={p_gain:.4f}")
print(f"r(跌幅):   {r_loss:.4f}  p={p_loss:.4f}")
print(f"信号>0: 涨幅={up['max_gain'].mean()*100:.4f}%, 跌幅={up['max_loss'].mean()*100:.4f}%")
print(f"信号<0: 涨幅={dn['max_gain'].mean()*100:.4f}%, 跌幅={dn['max_loss'].mean()*100:.4f}%")
```

#### 7.2.3 预期输出

```
样本数:    156 (up=76, dn=65)
r(涨幅):   0.2303  p=0.0038
r(跌幅):   -0.2004  p=0.0121
信号>0: 涨幅=0.7099%, 跌幅=-0.9070%
信号<0: 涨幅=0.5940%, 跌幅=-0.7435%
```

#### 7.2.4 测试断言

```python
def test_paxg_weekend_gain_loss(client):
    """PAXG 周末涨跌与周一独立涨跌幅测试"""
    result = compute_paxg_gain_loss(client)
    
    assert result['n_samples'] > 50, "样本数不足"
    assert -1 <= result['r_gain'] <= 1, "r(涨幅)越界"
    assert -1 <= result['r_loss'] <= 1, "r(跌幅)越界"
    
    # PAXG 波动应较小（黄金锚定）
    assert abs(result['up_gain_mean']) < 0.05
    assert abs(result['dn_loss_mean']) < 0.05
```

---

## 8. 技术栈选型

```mermaid
graph TB
    subgraph "存储后端"
        BE_LANG["Python 3.11+"]
        BE_FW["FastAPI + Uvicorn"]
        BE_DB["TimescaleDB (PostgreSQL 16)"]
        BE_CACHE["Redis"]
        BE_SCHED["APScheduler"]
        BE_DS["yfinance / ccxt / tushare / alpha_vantage"]
    end
    
    subgraph "计算前端"
        FE_LANG["Python 3.10+"]
        FE_CORE["pandas + numpy"]
        FE_STAT["scipy + statsmodels"]
        FE_PLOT["plot 协议层<br/>matplotlib 为可选 extras"]
        FE_HTTP["httpx (async client)"]
        FE_ARROW["pyarrow"]
    end
    
    subgraph "DSL"
        DSL_PARSER["lark (解析器)"]
        DSL_AST["自定义 AST"]
    end
    
    subgraph "基础设施"
        INFRA_DOCKER["Docker / Docker Compose"]
        INFRA_CI["GitHub Actions"]
        INFRA_TEST["pytest"]
    end
```

| 层 | 技术 | 选型理由 |
|----|------|----------|
| 后端框架 | FastAPI | 原生 async，自动生成 OpenAPI 文档，高性能 |
| 时序数据库 | TimescaleDB | PostgreSQL 兼容，Hypertable 高效时序查询，连续聚合 |
| 缓存 | Redis | 高速缓存查询结果，减轻 DB 压力 |
| 计算核心 | pandas + numpy | 事实标准，生态最全 |
| 统计扩展 | scipy + statsmodels | 假设检验、回归分析 |
| DSL 解析 | lark | Python 生态最成熟的解析器，EBNF 友好 |
| 数据传输 | Apache Arrow | 零拷贝列式传输，pandas 无缝对接 |
| 可视化 | matplotlib（可选 extras） | 协议化适配，延迟导入，核心零依赖，缺失时优雅降级 |
| 部署 | Docker Compose | 一键部署后端服务栈 |

---

## 9. 部署方案

### 9.1 存储后端独立部署

```mermaid
graph TB
    subgraph "Docker Compose 部署"
        direction TB
        
        subgraph "stockstat-storage 网络"
            API_C["stockstat-api<br/>FastAPI :8000"]
            DB_C["stockstat-db<br/>TimescaleDB :5432"]
            REDIS_C["stockstat-redis<br/>Redis :6379"]
            SCHED_C["stockstat-scheduler<br/>采集调度器"]
        end
        
        subgraph "数据卷"
            V1["db_data<br/>数据库持久化"]
            V2["redis_data<br/>缓存持久化"]
            V3["config<br/>配置文件"]
        end
        
        API_C --> DB_C
        API_C --> REDIS_C
        SCHED_C --> DB_C
        DB_C --> V1
        REDIS_C --> V2
    end
    
    USER["计算前端<br/>(用户机器)"] -.->|"http://host:8000"| API_C
```

**docker-compose.yml 核心结构**：

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

### 9.2 计算前端安装

```bash
# 安装计算前端库
pip install stockstat

# 配置连接
export STOCKSTAT_HOST=localhost
export STOCKSTAT_PORT=8000

# 如需通过代理访问真实数据源（在后端机器上配置）
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

```python
# 或在代码中配置
from stockstat import StockStatClient
client = StockStatClient(host="your-server.com", port=8000)
```

---

## 10. 项目结构

```
StockStatistic/
├── backend/                         # 存储后端服务
│   ├── stockstat_backend/
│   │   ├── __init__.py
│   │   ├── app.py                   # FastAPI 应用入口
│   │   ├── config.py                # 配置管理
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes_ohlcv.py      # OHLCV 查询路由
│   │   │   ├── routes_symbols.py    # 符号管理路由
│   │   │   └── routes_health.py     # 健康检查路由
│   │   ├── adapters/                # 数据源适配器
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # 适配器基类
│   │   │   ├── yfinance.py
│   │   │   ├── ccxt_adapter.py
│   │   │   ├── alphavantage.py
│   │   │   └── tushare.py
│   │   ├── models/                  # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv.py
│   │   │   └── symbol.py
│   │   ├── storage/                 # 存储层
│   │   │   ├── __init__.py
│   │   │   ├── database.py          # DB 连接
│   │   │   ├── repository.py        # 数据仓库
│   │   │   └── cache.py             # Redis 缓存
│   │   ├── normalizer/              # 数据标准化
│   │   │   ├── __init__.py
│   │   │   ├── symbol_mapper.py
│   │   │   └── timeframe.py
│   │   └── scheduler/               # 调度器
│   │       ├── __init__.py
│   │       └── ingest.py
│   ├── alembic/                     # 数据库迁移
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/                        # 计算前端库
│   ├── stockstat/
│   │   ├── __init__.py
│   │   ├── client.py                # StockStatClient 主入口
│   │   ├── config.py                # 连接配置
│   │   ├── connection.py            # 连接管理器
│   │   ├── data_access/             # 数据访问层
│   │   │   ├── __init__.py
│   │   │   ├── ohlcv.py
│   │   │   └── metadata.py
│   │   ├── compute/                 # 计算引擎
│   │   │   ├── __init__.py
│   │   │   ├── engine.py            # 核心引擎
│   │   │   ├── context.py           # 计算上下文
│   │   │   └── registry.py          # 指标注册表
│   │   ├── backtest/                # 回测子系统（v1.3 新增）
│   │   │   ├── __init__.py          # 对外导出 BacktestEngine/Strategy/...
│   │   │   ├── engine.py            # 主循环 + 事件分发
│   │   │   ├── context.py           # BacktestContext（策略可见世界）
│   │   │   ├── data_feed.py         # DataFeed + Universe 多标的多 tf 对齐
│   │   │   ├── strategy.py          # Strategy 基类 + @strategy 装饰器
│   │   │   ├── orders.py            # Order/Fill/OrderType 数据类
│   │   │   ├── broker.py            # SimulatedBroker 撮合引擎
│   │   │   ├── portfolio.py         # Portfolio/Position 账户与持仓
│   │   │   ├── cost_model.py        # 手续费/滑点模型
│   │   │   ├── fill_model.py        # 成交价决定模型
│   │   │   ├── sizing.py            # 仓位规模算法
│   │   │   ├── metrics.py           # 绩效聚合（复用 indicators.statistics）
│   │   │   ├── result.py            # BacktestResult + 报告
│   │   │   ├── benchmark.py         # 买入持有等基准
│   │   │   ├── optimizer.py         # 参数网格/optuna（可选 extras）
│   │   │   ├── walkforward.py       # 走样分析（可选）
│   │   │   ├── montecarlo.py        # 蒙特卡洛扰动（可选）
│   │   │   ├── plot_adapter.py      # equity/trades → PlotSpec（向后兼容）
│   │   │   ├── chart_spec.py        # BacktestChartSpec 专用规格（v1.4）
│   │   │   ├── chart_registry.py    # 回测图表类型注册表（v1.4）
│   │   │   ├── chart_factory.py     # detect + get_chart_renderer（v1.4）
│   │   │   ├── null_charts.py       # NullBacktestRenderer 零依赖兜底（v1.4）
│   │   │   └── matplotlib_charts.py # MatplotlibBacktestRenderer 延迟导入（v1.4）
│   │   ├── indicators/              # 内置指标库
│   │   │   ├── __init__.py
│   │   │   ├── trend.py             # MA/EMA/MACD
│   │   │   ├── oscillator.py        # RSI/KDJ
│   │   │   ├── volatility.py        # ATR/Bollinger
│   │   │   ├── statistics.py        # Corr/Beta/Sharpe
│   │   │   └── custom.py            # 自定义指标基类
│   │   ├── dsl/                     # DSL 解析器
│   │   │   ├── __init__.py
│   │   │   ├── grammar.lark         # 语法文件
│   │   │   ├── parser.py            # 解析器
│   │   │   ├── ast_nodes.py         # AST 节点
│   │   │   └── evaluator.py         # 求值器
│   │   ├── plot/                     # 可视化层（可选 · 协议化）
│   │   │   ├── __init__.py          # PlotSpec / get_renderer()
│   │   │   ├── base.py              # PlotRenderer 协议 + NullRenderer
│   │   │   └── matplotlib_backend.py # matplotlib 适配（延迟导入）
│   │   └── export/                  # 结果导出
│   │       ├── __init__.py
│   │       └── serializers.py
│   ├── tests/
│   │   ├── test_indicators.py
│   │   ├── test_dsl.py
│   │   ├── test_paxg_weekend.py     # PAXG 周末相关性测试
│   │   ├── test_classic_stats.py    # 经典统计测试
│   │   ├── test_backtest_iface.py   # 回测接口骨架测试 (BT-0)
│   │   ├── test_backtest_mvp.py     # 回测 MVP 测试 (BT-1)
│   │   ├── test_backtest_portfolio.py # 多标的/做空测试 (BT-2)
│   │   ├── test_backtest_multitf.py # 多 timeframe 测试 (BT-3)
│   │   ├── test_backtest_cost.py    # 成本模型测试 (BT-4)
│   │   ├── test_backtest_metrics.py # 绩效统计测试 (BT-5)
│   │   ├── test_backtest_optimize.py # 优化器测试 (BT-6)
│   │   ├── test_backtest_strategies.py # 12 个策略全套测试 (BT-7)
│   │   ├── test_backtest_viz_iface.py    # 回测可视化接口测试 (BT-V0)
│   │   ├── test_backtest_viz_mpl.py      # 回测可视化 matplotlib 测试 (BT-V1)
│   │   ├── test_backtest_viz_advanced.py # 回测可视化高级图表测试 (BT-V2)
│   │   ├── test_backtest_viz_dashboard.py # 回测可视化仪表盘测试 (BT-V3)
│   │   └── test_backtest_viz_online.py   # 回测可视化在线真实数据测试 (BT-V Online)
│   └── pyproject.toml
│
├── docker-compose.yml               # 后端部署编排
├── docs/
│   └── DESIGN.md                    # 本设计报告
└── README.md
```

---

## 11. 开发路线图

```mermaid
gantt
    title StockStat 开发路线图
    dateFormat  YYYY-MM-DD
    axisFormat  %m月

    section 存储后端
    项目初始化与DB设计          :a1, 2026-07-01, 14d
    数据源适配器(yfinance/ccxt)  :a2, after a1, 21d
    数据标准化层               :a3, after a2, 14d
    REST API 开发              :a4, after a3, 14d
    调度器与缓存               :a5, after a4, 14d

    section 计算前端
    客户端框架与连接管理        :b1, after a4, 10d
    数据访问层                 :b2, after b1, 10d
    内置指标库                 :b3, after b2, 21d
    DSL 解析器                 :b4, after b3, 21d
    可视化协议与mpl适配         :b5, after b3, 10d

    section 回测子系统
    BT0 接口与数据结构冻结      :bt0, after b5, 3d
    BT1 单标的单tf MVP          :bt1, after bt0, 5d
    BT2 多标的组合与做空        :bt2, after bt1, 5d
    BT3 多timeframe对齐        :bt3, after bt2, 4d
    BT4 成本与成交模型          :bt4, after bt3, 4d
    BT5 绩效统计与可视化        :bt5, after bt4, 5d
    BT6 参数优化与走样          :bt6, after bt5, 6d
    BT7 DSL集成与全套策略       :bt7, after bt6, 4d

    section 回测可视化
    BTV0 接口冻结与Null兜底     :btv0, after bt7, 2d
    BTV1 matplotlib基础渲染     :btv1, after btv0, 3d
    BTV2 高级图表(热力/分布)    :btv2, after btv1, 3d
    BTV3 组合仪表盘与标注       :btv3, after btv2, 3d

    section 测试与部署
    测试用例编写               :c1, after b3, 14d
    PAXG周末相关性测试          :c2, after b3, 7d
    Docker部署与文档            :c3, after c1, 10d
```

### 开发阶段

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P0** | 存储后端 MVP | DB + yfinance/ccxt 适配器 + 基础 API |
| **P1** | 计算前端 MVP | Client + 数据访问 + 5个核心指标 |
| **P2** | DSL 解析器 | 语法文件 + 求值器 + 10个内置函数 |
| **P3** | 完整指标库 | 趋势/震荡/波动/统计 全套指标 |
| **P4** | 可视化层 | PlotSpec + PlotRenderer 协议 + matplotlib 适配（可选 extras） |
| **P5** | 测试与部署 | 全部测试用例 + Docker + 文档 |
| **BT-0** | 回测接口冻结 | 核心 dataclass + 抽象基类签名 + 接口骨架测试 |
| **BT-1** | 单标的 MVP | DataFeed/Portfolio/Broker/Context/Engine/Result + 双均线策略 |
| **BT-2** | 多标的组合 | Universe + 做空 + 限价/止损单 + 仓位算法 + 配对交易 |
| **BT-3** | 多 timeframe | {sym:{tf:df}} 对齐 + 未来函数审计 + 多 tf 共振策略 |
| **BT-4** | 成本模型 | 手续费/滑点/印花税/资金费率 + 涨跌停 + 部分成交 |
| **BT-5** | 绩效与报告 | Sharpe/Sortino/Calmar + 回撤 + 交易明细 + PlotSpec 可视化 |
| **BT-6** | 优化与走样 | 网格搜索 + optuna + Walk-forward + 蒙特卡洛（可选 extras） |
| **BT-7** | DSL 集成 | Signal.from_dsl + 12 策略全套测试 + 文档 |
| **BT-V0** | 可视化接口冻结 | BacktestChartSpec + Renderer 协议 + Null 兜底 |
| **BT-V1** | matplotlib 基础渲染 | line/fill/scatter/多子图 + equity/drawdown/trades 三图 |
| **BT-V2** | 高级图表 | histogram/heatmap/bar + 收益分布/月度热力/参数热力 |
| **BT-V3** | 组合仪表盘 | dashboard 多子图 + 交易标注 + 批量 savefig |

---

## 12. 回测子系统设计

> **新增于 v1.3**。回测子系统是计算前端的可选增强模块，位于 `frontend/stockstat/backtest/`，纯前端实现，不修改存储后端。

### 12.1 设计目标与原则

| 目标 | 说明 |
|------|------|
| **可配置** | 自定义策略函数、多标的交易组、多时间尺度 K 线、复用计算库指标 |
| **可编程优先** | 不内置固定策略，提供 Strategy 基类 + `@strategy` 函数装饰器两种粒度 |
| **数据与计算分离** | 回测纯前端运行，数据经 `DataClient` 拉取后注入 `DataFeed` |
| **零硬依赖** | 核心仅依赖 pandas/numpy；optuna 等走 `[optimize]` extras |
| **未来函数防护** | 策略 `on_bar(t)` 只能访问 `≤ t` 数据；订单默认在 `t+1` open 成交 |
| **可复现** | seed + 数据快照版本号记录于 `BacktestResult` |

### 12.2 顶层架构

```mermaid
graph TB
    subgraph "用户策略代码 Strategy"
        US["on_bar(ctx):<br/>ctx.compute.rsi(...)<br/>ctx.broker.buy(...)"]
    end

    subgraph "回测核心"
        CTX["BacktestContext<br/>get(sym,tf,lookback) 切片<br/>compute: ComputeEngine 代理<br/>portfolio 只读视图"]
        BRK["Broker<br/>submit/cancel<br/>撮合 → Fill"]
        DF["DataFeed + Universe<br/>多标的多 tf 对齐<br/>时间游标 + 防未来函数"]
        PF["Portfolio<br/>cash / positions<br/>update_fill / mark_to_market"]
        ENG["BacktestEngine<br/>事件循环 + 钩子 + 结果收集"]
        RES["BacktestResult<br/>trades / positions / equity<br/>metrics / plot / to_dict"]
    end

    US -->|读| CTX
    US -->|写订单| BRK
    CTX -->|提供对齐 bar| US
    BRK -->|推送成交| PF
    DF --> CTX
    PF --> CTX
    ENG --> CTX
    ENG --> BRK
    ENG --> DF
    ENG --> RES
```

### 12.3 模块划分

```
frontend/stockstat/backtest/
├── __init__.py              # 对外导出
├── engine.py                # BacktestEngine：主循环、事件分发
├── context.py               # BacktestContext：策略可见的世界
├── data_feed.py             # DataFeed + Universe
├── strategy.py              # Strategy 基类、@strategy 装饰器
├── orders.py                # Order/Fill 数据类
├── broker.py                # SimulatedBroker
├── portfolio.py             # Portfolio/Position
├── cost_model.py            # CostModel 抽象 + 多实现
├── fill_model.py            # FillModel：成交价决定
├── sizing.py                # 仓位规模算法
├── metrics.py               # 绩效聚合
├── result.py                # BacktestResult + 报告
├── benchmark.py             # 基准对比
├── optimizer.py             # 参数优化（可选 extras）
├── walkforward.py           # 走样分析（可选）
├── montecarlo.py            # 蒙特卡洛（可选）
└── plot_adapter.py          # equity/trades → PlotSpec
```

### 12.4 核心接口签名

```python
# strategy.py
class Strategy:
    """策略基类。子类重写钩子。"""
    def on_start(self, ctx: BacktestContext) -> None: ...
    def on_bar(self, ctx: BacktestContext) -> None: ...        # 主入口
    def on_bar_close(self, ctx: BacktestContext) -> None: ...
    def on_fill(self, fill: Fill, ctx: BacktestContext) -> None: ...

def strategy(fn=None, *, name: str | None = None):
    """函数式策略装饰器：def on_bar(ctx) 简化写法。"""

# context.py
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
    @property
    def history(self) -> ContextHistory: ...

# orders.py
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

# engine.py
class BacktestEngine:
    def __init__(self, *,
                 data: dict[str, dict[str, pd.DataFrame]],  # {symbol: {tf: df}}
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

### 12.5 多 timeframe 对齐与未来函数防护

以**最低粒度 timeframe** 为驱动游标 `t`，更高 tf 的 bar 通过 `asof/ffill` 对齐到 `t`：

```python
# DataFeed 内部
master_index = union_of_all timestamps at finest tf
aligned[sym][tf] = df[sym][tf].reindex(master_index, method="ffill")

# Context.get(symbol, tf, lookback) 返回 ≤ t 切片（闭区间）
df = aligned[sym][tf].loc[:t]
return df.iloc[-lookback:] if lookback else df
```

- **未来函数防护**：策略 `on_bar(t)` 只能拿到 `≤ t` 数据；订单默认 `t+1` open 成交（`NextOpenFill`）
- **lookahead_audit**：可选运行时检测，访问 `> t` 数据抛 `LookaheadError`
- 指标计算基于 `≤ t` 切片，避免 lookahead

### 12.6 成本与成交模型

| 模型 | 实现 | 说明 |
|------|------|------|
| `PercentCost` | 默认 | 比例手续费 + 比例滑点（bps） |
| `FixedCost` | | 固定每笔费用 |
| `TieredCost` | | 阶梯费率 |
| `MinCost` | | 最小手续费兜底 |
| `StampDutyCost` | | 印花税（股票卖出方） |
| `FundingRateCost` | 可选 | 永续合约资金费率 |
| `NextOpenFill` | 默认 | 下一 bar open 成交，最强防未来函数 |
| `NextCloseFill` / `ThisCloseFill` | | 其他成交时点（告警） |
| `VWAPFill` / `WorstPriceFill` | | 模拟冲击 |

### 12.7 仓位规模算法

`fixed_size / fixed_amount / percent_equity / kelly / atr_risk_budget`，由策略调用 `ctx.broker.submit(order)` 前计算 `qty`，或通过 `sizing` 辅助函数。

### 12.8 绩效指标

复用 `indicators.statistics` 与新增 `metrics.py`：

总收益、年化收益、Sharpe、Sortino、Calmar、Omega、信息比率、最大回撤、回撤持续/恢复时间、胜率、盈亏比、Profit Factor、期望值、连胜连跌、月度/年度热力、收益分布、VaR。

### 12.9 与既有模块集成

| 集成点 | 方式 |
|-------|------|
| `ComputeEngine` | `Context.compute` 直接持有 client 的 ComputeEngine |
| 自定义指标 | `ctx.compute.register("divergence", fn)` → `ctx.compute.call(...)` |
| DSL | `Signal.from_dsl("SELECT ... WHERE rsi<30")` 信号生成（BT-7） |
| `indicators.statistics` | `metrics.py` 调用 sharpe/max_drawdown/var/returns |
| `plot` 协议 | `result.plot_equity()` 返回 PlotSpec，任意 renderer 渲染 |
| `export` | `result.to_csv()/to_json()` 复用 serializers |
| `data_access` | `DataFeed` 接受 DataFrame 或 client 懒加载 |

### 12.10 内置示例策略清单

12 个策略覆盖从简单到复杂，每个对应 `test_backtest_strategies.py` 测试用例：

| # | 策略 | 标的 | tf | 用到的指标/设计点 | 验证目标 |
|---|------|------|----|------------------|---------|
| 1 | 双均线交叉 | 单 | 单 | ma(5)×ma(20) | MVP 闭环 |
| 2 | 布林带突破 | 单 | 单 | bollinger | 限价单/止损 |
| 3 | RSI 超买超卖 | 单 | 单 | rsi | 反向开仓/止盈 |
| 4 | MACD 背离 | 单 | 单 | macd + 自定义指标 | register() |
| 5 | ATR 通道突破 | 单 | 单 | atr + Donchian | ATR 风险预算 |
| 6 | 网格交易 | 单 | 单 | 价格分档 | 多挂单/资金分桶 |
| 7 | 配对交易 | 多(2) | 单 | beta/corr + z-score | 多标的/做空对冲 |
| 8 | 风险平价 | 多(N) | 单 | beta/std | 定期再平衡 |
| 9 | 动量轮动 | 多(N) | 单 | 6月动量排名 | Top-K 调仓 |
| 10 | 多 tf 共振 | 单 | 多 | 日线 MA + 小时突破 | 多 tf 对齐 |
| 11 | PAXG 周末效应 | 单 | 单 | weekday 信号 | 事件驱动 |
| 12 | 马丁格尔 | 单 | 单 | 亏损翻倍 | 仓位限制/风险警示 |

### 12.11 依赖声明

```toml
[project.optional-dependencies]
backtest = ["stockstat"]                  # 核心回测，无额外依赖
optimize = ["optuna>=3.5"]                # BT-6 参数优化
backtest_full = ["stockstat[backtest]", "stockstat[optimize]", "stockstat[matplotlib]"]
```

---

## 13. 回测可视化子系统设计

> **新增于 v1.4**。在回测子系统（§12）之上叠加**零硬依赖**的可视化层：回测核心不依赖 matplotlib，但安装后自动激活丰富的回测专用图表。

### 13.1 背景与问题

回测子系统已通过 `backtest/plot_adapter.py` 复用通用 `PlotSpec` 协议产出 equity/drawdown/trades 三种基础图，但存在以下不足：

| 不足 | 说明 |
|------|------|
| PlotSpec 表达力有限 | 仅支持 line/bar/scatter + markers，无法表达**填充区域**（drawdown 填色）、**直方图**（收益分布）、**热力图**（月度/年度收益、参数网格）、**多子图组合**（仪表盘） |
| 通用协议被污染风险 | 若直接扩展 PlotSpec 加入回测专用字段，会破坏通用 plot 协议的简洁性 |
| matplotlib 耦合 | 当前 `MatplotlibRenderer` 只能渲染单 ax，回测需要的填充/热力/子图无法用通用 renderer 表达 |

### 13.2 设计原则

| 原则 | 说明 |
|------|------|
| **回测核心零硬依赖** | `backtest/` 包导入不触发 matplotlib；`import stockstat.backtest` 永远成功 |
| **专用 spec 层** | 新增 `BacktestChartSpec`（回测专用），与通用 `PlotSpec` 平行，互不污染 |
| **延迟激活** | matplotlib 安装后通过 `backtest.matplotlib_charts` 模块延迟导入激活 |
| **协议化** | 定义 `BacktestChartRenderer` 协议，Null/Matplotlib 多后端可插拔 |
| **渐进式** | 基础图（equity/drawdown）→ 高级图（热力/分布）→ 组合仪表盘 |

### 13.3 架构

```mermaid
graph TB
    subgraph "回测核心 backtest/（零 matplotlib 依赖）"
        RES["BacktestResult"]
        ADAPTER["plot_adapter.py<br/>基础 PlotSpec 构建器"]
        CHARTSPEC["chart_spec.py<br/>BacktestChartSpec 专用规格"]
        REG["chart_registry.py<br/>图表注册表"]
    end

    subgraph "通用 plot 协议（已有）"
        PS["PlotSpec"]
        PR["PlotRenderer<br/>Null/Matplotlib"]
    end

    subgraph "回测可视化后端（延迟导入 · 可选）"
        BCMPL["backtest/matplotlib_charts.py<br/>MatplotlibBacktestRenderer<br/>（matplotlib 安装后才激活）"]
        BCNULL["backtest/null_charts.py<br/>NullBacktestRenderer"]
        FACTORY["chart_factory.py<br/>detect + get_chart_renderer"]
    end

    RES --> ADAPTER --> PS
    RES --> CHARTSPEC
    CHARTSPEC --> REG
    REG --> FACTORY
    FACTORY --> BCMPL
    FACTORY --> BCNULL
    BCMPL -.->|延迟 import| PR
```

### 13.4 模块划分（新增于 `frontend/stockstat/backtest/`）

```
frontend/stockstat/backtest/
├── chart_spec.py            # BacktestChartSpec + 子规格数据类
├── chart_registry.py        # 图表类型注册表
├── chart_factory.py         # detect + get_chart_renderer
├── null_charts.py           # NullBacktestRenderer（零依赖兜底）
├── matplotlib_charts.py     # MatplotlibBacktestRenderer（延迟导入）
└── plot_adapter.py          # （已有）扩展：同时返回 PlotSpec 与 BacktestChartSpec
```

### 13.5 BacktestChartSpec 设计

```python
# chart_spec.py
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
    """回测专用图表规格，支持多子图、填充、热力、直方图。"""
    title: str = ""
    x_label: str = ""
    subplots: list[SubplotSpec] = field(default_factory=list)
    layout: tuple[int, int] = (1, 1)   # (rows, cols)
    figsize: tuple[float, float] = (12, 6)
    annotate_trades: bool = False
    source_result: object = None       # 反向引用 BacktestResult（用于交易标注）

    def add_subplot(self, title="", y_label="") -> SubplotSpec: ...
    def to_dict(self) -> dict: ...     # 可序列化（用于 Web 前端）

class BacktestChartRenderer(Protocol):
    def render(self, spec: BacktestChartSpec) -> Any: ...
    def savefig(self, path: str) -> None: ...
    def show(self) -> None: ...
    def available(self) -> bool: ...
```

### 13.6 图表类型清单

| 图表 | 类型 | 用途 | 阶段 |
|------|------|------|------|
| `equity_curve` | 多 line + 基准 | 资金曲线对比 | BT-V0 |
| `drawdown` | line + fill | 回撤填充区 | BT-V0 |
| `trades_overlay` | line + scatter 标注 | 交易点叠加 | BT-V0 |
| `returns_distribution` | histogram | 收益率分布 | BT-V2 |
| `monthly_heatmap` | heatmap | 月度收益热力 | BT-V2 |
| `yearly_returns` | bar | 年度收益对比 | BT-V2 |
| `parameter_heatmap` | heatmap | 网格搜索参数热力 | BT-V2 |
| `underwater_curve` | fill | 水下曲线（回撤持续） | BT-V2 |
| `dashboard` | 多子图组合 | 综合仪表盘 | BT-V3 |

### 13.7 与既有模块集成

| 集成点 | 方式 |
|-------|------|
| `BacktestResult` | 新增 `result.chart(name)` 方法返回 `BacktestChartSpec` |
| `plot_adapter.py` | 保留原 `plot_equity/plot_drawdown/plot_trades`（返回通用 PlotSpec，向后兼容） |
| `plot/base.py` | **不修改**——通用协议保持简洁 |
| `matplotlib_backend.py` | **不修改**——通用 renderer 保持单 ax 简单语义 |
| `client.backtest()` | 返回的 `BacktestResult` 自动具备 `.chart()` 与 `.render()` |

### 13.8 使用方式

```python
from stockstat.backtest import BacktestEngine, strategy, Order
from stockstat.backtest.chart_factory import get_chart_renderer

res = BacktestEngine(...).run()

# 方式 A：获取专用 spec，自行渲染
spec = res.chart("equity_curve")        # 返回 BacktestChartSpec
renderer = get_chart_renderer()         # 自动检测 matplotlib
renderer.render(spec)
renderer.savefig("equity.png")

# 方式 B：一行渲染
res.render("drawdown", path="dd.png")

# 方式 C：组合仪表盘
spec = res.chart("dashboard")           # 多子图组合
renderer.render(spec)

# 方式 D：向后兼容——通用 PlotSpec（无 matplotlib 也能用）
spec = res.plot_equity()                # 返回 PlotSpec（已有）
```

### 13.9 依赖声明

```toml
[project.optional-dependencies]
backtest = ["stockstat"]                          # 核心，无 matplotlib
backtest_viz = ["stockstat[backtest]", "matplotlib>=3.8"]   # 回测可视化
backtest_full = ["stockstat[backtest]", "stockstat[optimize]",
                 "stockstat[matplotlib]", "matplotlib>=3.8"]
```

### 13.10 实现阶段（BT-V 系列）

| 阶段 | 内容 | 测试 |
|------|------|------|
| **BT-V0** | 接口冻结：`BacktestChartSpec` + `BacktestChartRenderer` 协议 + Null 实现 + 基础 spec 构建器 | `test_backtest_viz_iface.py` |
| **BT-V1** | matplotlib backend：渲染 line/fill/scatter/多子图，equity/drawdown/trades 三图完整 | `test_backtest_viz_mpl.py` |
| **BT-V2** | 高级图表：histogram/heatmap/bar，returns_distribution/monthly_heatmap/yearly/parameter_heatmap | `test_backtest_viz_advanced.py` |
| **BT-V3** | 组合仪表盘 + 交易标注 + savefig 批量 + 优雅降级 | `test_backtest_viz_dashboard.py` |

---

## 15. 回测引擎增强与可插拔执行模型

> **新增于 v1.5（BT-8~BT-10）**，**扩展于 v1.6（BT-11~BT-14）**。本章节合并两轮增强：BT-8~10 基于 v5 研究暴露的不足，新增 intrabar 限价成交、Maker/Taker 费率、OCO 订单、批量回测等能力；BT-11~14 将"订单如何成交"抽象为可插拔 `ExecutionModel`，支持 intrabar 子 bar 执行而**不新增引擎类**。所有增强以**向后兼容、组合优先、最小侵入**为原则。

### 15.1 BT-8~10：引擎增强子系统

#### 15.1.1 设计目标

| 目标 | 说明 |
|------|------|
|------|------|
| **限价单 intrabar 成交** | 限价单应在盘中价格穿越限价水平时成交，而非仅检查开盘价 |
| **Maker/Taker 费率区分** | 加密货币交易所区分挂单/吃单费率，差异可达 5 倍 |
| **OCO 订单** | 一对限价单，任一成交则撤销另一方（双向挂单策略必需） |
| **Binance 费率模型** | 现货/合约 × BNB 抵扣四组合预设 |
| **多策略批量回测** | 一次运行多个策略并汇总对比 |
| **退出原因标记** | 交易记录区分 TP/SL/收盘/时间/打平/利润退出 |
| **子期间/状态分析** | 回测后按子期间或市场状态分组分析绩效 |
| **DCA 基准** | 定投基准对比 |
| **手续费敏感性扫描** | 扫描费率参数输出绩效曲线 |

### 15.2 文件变更清单

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `fill_model.py` | 修改 | 新增 `IntrabarLimitFill` |
| `cost_model.py` | 修改 | 新增 `MakerTakerCost`、`BinanceCost` + 4 预设 |
| `orders.py` | 修改 | `Fill`/`Order` 新增 `exit_reason` 字段 |
| `broker.py` | 修改 | 新增 `submit_oco()` + OCO 撤销传播 |
| `engine.py` | 修改 | 新增 `periods_per_year` 参数 |
| `result.py` | 修改 | 新增 `exit_reason_stats()` |
| `benchmark.py` | 修改 | 新增 `dca_equity()` |
| `intrabar.py` | **新增** | `IntrabarSimulator` |
| `batch_runner.py` | **新增** | `StrategyBatchRunner` + `BatchResults` |
| `analyzer.py` | **新增** | `BacktestAnalyzer` |
| `fee_sweep.py` | **新增** | `fee_sweep()` + `maker_taker_sweep()` |
| `__init__.py` | 修改 | 导出新组件 |

### 15.3 核心新增接口

#### 15.3.1 IntrabarLimitFill

```python
class IntrabarLimitFill(FillModel):
    """限价单在盘中价格穿越限价水平时成交。
    LIMIT buy: next_bar["low"] <= limit_price → 以 limit_price 成交
    LIMIT sell: next_bar["high"] >= limit_price → 以 limit_price 成交
    MARKET: 以 next_bar["open"] 成交（同 NextOpenFill）
    """
```

与 `NextOpenFill` 平行存在，策略显式选择。`NextOpenFill` 保留原逻辑不变。

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
    # Spot:  maker 0.1% / taker 0.1%  (BNB: -25%)
    # Futures: maker 0.02% / taker 0.05%  (BNB: -10%)

# 便捷预设
BINANCE_SPOT = BinanceCost(venue="spot", bnb_discount=False)
BINANCE_SPOT_BNB = BinanceCost(venue="spot", bnb_discount=True)
BINANCE_FUTURES = BinanceCost(venue="futures", bnb_discount=False)
BINANCE_FUTURES_BNB = BinanceCost(venue="futures", bnb_discount=True)
```

#### 15.3.3 OCO 订单

```python
class SimulatedBroker:
    def submit_oco(self, order_a: Order, order_b: Order) -> tuple[str, str]:
        """提交 OCO 对。任一成交时自动撤销另一方。"""
```

不新增 `OrderType`，在 Broker 层管理关联关系。

#### 15.3.4 IntrabarSimulator

```python
class IntrabarSimulator:
    """用更细粒度 K 线模拟限价单盘中成交时序。"""
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

### 15.4 实现阶段（BT-8~BT-10）

| 阶段 | 内容 | 测试 | 优先级 |
|------|------|------|--------|
| **BT-8** | P0 致命修复：`IntrabarLimitFill` + `MakerTakerCost` + OCO 订单 | `test_backtest_p0.py` | ★★★ |
| **BT-9** | P1 重要增强：`BinanceCost` + `IntrabarSimulator` + `StrategyBatchRunner` + `exit_reason` | `test_backtest_p1.py` | ★★☆ |
| **BT-10** | P2 分析工具：年化因子 + DCA + `BacktestAnalyzer` + `fee_sweep` | `test_backtest_p2.py` | ★☆☆ |

### 15.5 向后兼容保证

| 现有 API | 改进后 | 兼容性 |
|---------|--------|--------|
| `NextOpenFill()` | 保留原逻辑 | ✅ 完全兼容 |
| `PercentCost(commission=0.001)` | 保留 | ✅ 完全兼容 |
| `Order(symbol, side, qty)` | 新增 `exit_reason=""` 默认值 | ✅ 完全兼容 |
| `Fill(...)` | 新增 `exit_reason=""` 默认值 | ✅ 完全兼容 |
| `BacktestEngine(data, strategy)` | 新增 `periods_per_year=None` | ✅ 完全兼容 |

现有用户代码无需修改。新功能通过显式选择新类/参数启用。

### 15.6 依赖声明

```toml
[project.optional-dependencies]
backtest = ["stockstat"]                  # 核心（含 BT-8~10 增强）
optimize = ["optuna>=3.5"]                # BT-6 参数优化
backtest_full = ["stockstat[backtest]", "stockstat[optimize]", "stockstat[matplotlib]"]
```

无新增外部依赖。所有增强纯 Python + pandas/numpy 实现。

---

### 15.7 BT-11~14：可插拔执行模型

> 在 §15.1-15.6（BT-8~10）基础上，将"订单如何成交"抽象为可插拔 `ExecutionModel`，通过组合注入 `BacktestEngine`，支持 intrabar 子 bar 执行而**不新增引擎类**。设计原则：general 方案丰富库能力 + simplified 接口保持简洁 + 严格向前兼容。

#### 15.7.1 设计动机

§15.1 的 BT-8~BT-10 解决了 intrabar 限价成交、Maker/Taker 费率、批量回测等需求，但 v5 研究中仍暴露 5 项结构性差距（详见 `docs/backtest/BT11_BT14_CN.md`）：

| Gap | 描述 | 根因 |
|-----|------|------|
| Gap-1 | Intrabar 成交时间不追踪 | `FillModel` 只返回价格 |
| Gap-2 | 同一 parent bar 内入场+出场 | 事件循环 t→t+1 约束 |
| Gap-3 | 成交后条件退出扫描 | 无 intrabar 前向扫描 hook |
| Gap-4 | 双向均成交→双取消 | OCO 语义不足 |
| Gap-5 | 同 bar 内 SL 优先于 TP | broker 无优先级排序 |

V1 方案（独立 `IntrabarExecutionEngine` 类）存在 8 项兼容性盲点。V2 方案以 `ExecutionModel` 可插拔架构解决，**一个引擎类 + 两种执行模式**。

#### 15.7.2 架构

```mermaid
graph TB
    subgraph "BacktestEngine（唯一引擎类）"
        ENG["execution_model 参数<br/>默认 NextBarExecution"]
        EM["ExecutionModel ABC"]
        NB["NextBarExecution<br/>默认：t→t+1 成交"]
        IB["IntrabarExecution<br/>intrabar 子 bar 撮合"]
    end

    subgraph "IntrabarExecution 内部"
        FILL["IntrabarFillModel<br/>子 bar 序列扫描 + 时间追踪"]
        SCAN["_scan_sub_bars<br/>预扫描→OCO检测→apply→退出扫描"]
        EXIT["_scan_exits<br/>limit/stop 逐bar + market close 收盘"]
        OCO["register_oco_mutual<br/>双向均成交→双取消"]
    end

    subgraph "策略层（duck typing）"
        STR["Strategy 基类（不变）"]
        MIX["IntrabarMixin（可选）<br/>define_exits()"]
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

#### 15.7.3 核心接口

```python
# execution_model.py（新文件）

class ExecutionModel(ABC):
    """订单执行模型：决定订单如何在 bar 内成交。"""
    @abstractmethod
    def execute(self, engine, ctx, t, pending_orders) -> list[Fill]: ...
    @property
    @abstractmethod
    def is_intrabar(self) -> bool: ...

class NextBarExecution(ExecutionModel):
    """默认：t 提交 → t+1 bar 成交（现有行为）。"""
    is_intrabar = False

class IntrabarExecution(ExecutionModel):
    """intrabar：parent bar 内子 bar 序列撮合。"""
    def __init__(self, intrabar_tf, parent_tf=None, fill_model=None): ...
    def register_oco_mutual(self, order_a, order_b): ...
    is_intrabar = True
```

#### 15.7.4 文件变更清单

| 文件 | 变更 | 内容 |
|------|------|------|
| `execution_model.py` | **新增** | `ExecutionModel` ABC + `NextBarExecution` + `IntrabarExecution` |
| `fill_model.py` | 新增类 | `IntrabarFillResult` + `IntrabarFillModel`（继承 `IntrabarLimitFill`） |
| `orders.py` | 加字段 | `Order.priority: int = 99` + `Fill.sub_bar_ts` + `Fill.sub_bar_index` |
| `data_feed.py` | 加方法 | `DataFeed.intrabar_slice()` |
| `engine.py` | 加参数 | `execution_model` 参数 + intrabar 分支 + parent_tf 迭代 |
| `context.py` | 加方法 | `intrabar_submit()` + `intrabar_submit_oco_mutual()`（模式感知降级） |
| `broker.py` | 加方法 | `submit_oco_mutual()` |
| `strategy.py` | 新增类 | `IntrabarMixin`（可选 mixin，含 `define_exits` 默认实现） |

#### 15.7.5 5 项 Gap 的解决

| Gap | 解决方式 |
|-----|---------|
| Gap-1 | `Fill.sub_bar_ts` + `Fill.sub_bar_index` + `IntrabarFillModel.fill_with_timing()` |
| Gap-2 | `IntrabarExecution` 在 parent bar 内完成入场→退出全生命周期 |
| Gap-3 | duck typing 检测 `define_exits()` + `_scan_exits()` 前向扫描 |
| Gap-4 | `register_oco_mutual()` + 预扫描检测双向成交 |
| Gap-5 | `Order.priority` 字段 + 排序（SL priority=0 > TP priority=1） |

#### 15.7.6 向后兼容保证

| 现有 API | 改进后 | 兼容性 |
|---------|--------|--------|
| `BacktestEngine(data, strategy)` | 新增 `execution_model=None` | ✅ 默认 `NextBarExecution` = 现有行为 |
| `FillModel` ABC | 不修改 | ✅ `fill_with_timing` 非抽象新方法 |
| `Fill` / `Order` | 新增字段有默认值 | ✅ dataclass 末尾 |
| `Strategy` 基类 | 不修改 | ✅ duck typing 检测 `define_exits` |
| `@strategy` 函数 | 不修改 | ✅ 函数式策略完全兼容 |
| `ctx.intrabar_submit()` | 普通模式降级 | ✅ `broker.submit` + warning |

#### 15.7.7 实现阶段（BT-11~BT-14）

| 阶段 | 内容 | 测试 | 优先级 |
|------|------|------|--------|
| **BT-11** | ExecutionModel ABC + IntrabarFillModel + Fill/Order 字段 + intrabar_slice | `test_backtest_intrabar.py`（兼容性 + FillModel + DataFeed） | ★★★ |
| **BT-12** | IntrabarExecution + IntrabarMixin + OCO mutual + 引擎集成 | 同上（同 bar 出场 + define_exits + 优先级 + OCO） | ★★★ |
| **BT-13** | v5 策略迁移验证（33 策略 × 4 费率 = 132 次回测） | `run_redo.py`（PnL 误差 < 0.1%） | ★★☆ |
| **BT-14** | 分析与可视化适配 | `plots_redo.py` | ★☆☆ |

#### 15.7.8 验证结果

- 原有 314 项测试全部通过（零回归）
- 新增 23 项 intrabar 测试全部通过
- v5 的 33 策略 × 4 费率 = 132 次回测，关键策略 PnL 误差 < 0.1%
- 结论一致：全部策略均未击败买入持有 PAXG（+104.84%）

---

## 附录 A: 数据源兼容性矩阵

| 数据源 | 资产类型 | 免费额度 | 实时支持 | 历史深度 | 适配难度 |
|--------|---------|---------|---------|---------|---------|
| yfinance | 美股/ETF | 免费 | 延迟15min | 10年+ | 低 |
| Alpha Vantage | 全球股票 | 25次/天 | 延迟15min | 20年+ | 低 |
| Tushare | A股 | 积分制 | 盘后 | 10年+ | 中 |
| ccxt (Binance) | 加密货币 | 免费 | 实时 | 全历史 | 低 |
| ccxt (Coinbase) | 加密货币 | 免费 | 实时 | 全历史 | 低 |

## 附录 B: OHLCV 数据量估算

| 标的范围 | 标的数 | 日均数据量 | 年数据量 | 存储估算 |
|---------|--------|-----------|---------|---------|
| 美股 Top 500 | 500 | 500 行 | 125K 行 | ~10 MB |
| A股全市场 | 5000 | 5000 行 | 1.25M 行 | ~100 MB |
| 加密货币 Top 200 | 200 | 200 行 | 50K 行 | ~5 MB |
| 加密1分钟数据(200标的) | 200 | 288K 行 | 73M 行 | ~5 GB |

> TimescaleDB 压缩后可缩减至原始体积的 10%~20%。

## 附录 C: 回测阶段实现文档索引

回测核心（BT-0~BT-14）与回测可视化（BT-V0~BT-V3 + 在线验证）的阶段文档统一索引如下，存放于 `docs/backtest/`：

### C.1 回测核心（BT 系列）

| 阶段 | 文档 | 代码 | 测试 |
|------|------|------|------|
| BT-0 | [docs/backtest/BT0_CN.md](docs/backtest/BT0_CN.md) | `backtest/` 包骨架 + dataclass | `test_backtest_iface.py` |
| BT-1 | [docs/backtest/BT1_CN.md](docs/backtest/BT1_CN.md) | MVP 五大模块 | `test_backtest_mvp.py` |
| BT-2 | [docs/backtest/BT2_CN.md](docs/backtest/BT2_CN.md) | 多标的/做空/订单扩展 | `test_backtest_portfolio.py` |
| BT-3 | [docs/backtest/BT3_CN.md](docs/backtest/BT3_CN.md) | 多 tf 对齐/审计 | `test_backtest_multitf.py` |
| BT-4 | [docs/backtest/BT4_CN.md](docs/backtest/BT4_CN.md) | 成本/成交模型 | `test_backtest_cost.py` |
| BT-5 | [docs/backtest/BT5_CN.md](docs/backtest/BT5_CN.md) | 绩效/报告/可视化 | `test_backtest_metrics.py` |
| BT-6 | [docs/backtest/BT6_CN.md](docs/backtest/BT6_CN.md) | 优化/走样/蒙特卡洛 | `test_backtest_optimize.py` |
| BT-7 | [docs/backtest/BT7_CN.md](docs/backtest/BT7_CN.md) | DSL 集成/12 策略 | `test_backtest_strategies.py` |
| BT-8 | [docs/backtest/BT8_CN.md](docs/backtest/BT8_CN.md) | P0 致命修复：IntrabarLimitFill + MakerTakerCost + OCO | `test_backtest_p0.py` |
| BT-9 | [docs/backtest/BT9_CN.md](docs/backtest/BT9_CN.md) | P1 重要增强：IntrabarSimulator + BatchRunner + exit_reason | `test_backtest_p1.py` |
| BT-10 | [docs/backtest/BT10_CN.md](docs/backtest/BT10_CN.md) | P2 分析工具：DCA + Analyzer + fee_sweep | `test_backtest_p2.py` |
| BT-11 | [docs/backtest/BT11_BT14_CN.md](docs/backtest/BT11_BT14_CN.md) | ExecutionModel ABC + IntrabarFillModel + Fill/Order 字段扩展 | `test_backtest_intrabar.py` |
| BT-12 | 同上 | IntrabarExecution + IntrabarMixin + OCO mutual + 优先级 | `test_backtest_intrabar.py` |
| BT-13 | 同上 | v5 策略迁移（33 策略 × 4 费率 = 132 次回测验证） | `run_redo.py` |
| BT-14 | 同上 | 分析与可视化适配 | `plots_redo.py` |

### C.2 回测可视化（BT-V 系列 + 在线验证）

| 阶段 | 文档 | 代码 | 测试 |
|------|------|------|------|
| BT-V0 | [docs/backtest/BTV0_CN.md](docs/backtest/BTV0_CN.md) | `chart_spec.py` + `chart_registry.py` + `null_charts.py` + `chart_factory.py` | `test_backtest_viz_iface.py` |
| BT-V1 | [docs/backtest/BTV1_CN.md](docs/backtest/BTV1_CN.md) | `matplotlib_charts.py` 基础渲染 | `test_backtest_viz_mpl.py` |
| BT-V2 | [docs/backtest/BTV2_CN.md](docs/backtest/BTV2_CN.md) | histogram/heatmap/bar 高级图表 | `test_backtest_viz_advanced.py` |
| BT-V3 | [docs/backtest/BTV3_CN.md](docs/backtest/BTV3_CN.md) | dashboard 组合 + 交易标注 | `test_backtest_viz_dashboard.py` |
| BT-V Online | [docs/backtest/BT_VIZ_ONLINE_REPORT_CN.md](docs/backtest/BT_VIZ_ONLINE_REPORT_CN.md) | 真实数据在线验证 + 13 张图像 | `test_backtest_viz_online.py` |

---

*本设计文档将随项目迭代持续更新。*
