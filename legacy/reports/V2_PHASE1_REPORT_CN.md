# v2.0 Phase 1 实现报告 — 通用核心层（Layer 0）

> **分支**: `dev/v2.0`
> **日期**: 2026-07-18
> **状态**: ✅ 已实现并通过测试

---

## 1. 实现范围

Phase 1 落地了 DESIGN_V2 中的 **Layer 0 通用核心层**（`stockstat/_core/`），包含 7 个子模块：

| 子模块 | 文件 | 功能 | 测试数 |
|--------|------|------|--------|
| `contracts/` | 6 个协议文件 | Protocol 定义：Plugin / Storage / Cache / Codec / Renderer / Event | 8 |
| `plugin/` | `__init__.py` | PluginRegistry：命名空间注册 + 发现 + 生命周期 | 8 |
| `config/` | `__init__.py` | 分层配置：默认→文件→环境→参数 + Schema + 命名空间访问 | 6 |
| `events/` | `__init__.py` | EventBus + Event + EventReplay（历史重放） | 6 |
| `storage/` | `__init__.py` | MemoryStorage + SQLStorage（包装 v1.7 SQLAlchemy） | 4 |
| `cache/` | `__init__.py` | NullCache + MemoryCache + RedisCache + 工厂 | 7 |
| `codec/` | `__init__.py` | JsonCodec + CsvCodec + ArrowCodec + ParquetCodec | 6 |
| `logging.py` | — | StructuredLogger（结构化日志 + 上下文绑定） | 1 |
| `errors.py` | — | AppError + 7 个子类（错误码 + 上下文 + 可恢复标志） | 3 |

**新增代码**：~1,200 行（含测试）
**新增文件**：15 个

---

## 2. 关键设计决策

### 2.1 Protocol 而非 ABC
所有协议使用 `typing.Protocol` + `@runtime_checkable`，无需继承，鸭子类型。任何具有正确方法的对象自动满足协议。

### 2.2 插件命名空间
```python
registry.register("indicators", "ma", MaIndicator())
registry.register("sources", "yfinance", YFinanceAdapter())
registry.get("indicators", "ma")
```
统一了 v1.7 中分散的 3 套注册机制（适配器 if-elif / 指标 dict / 渲染器 if-elif）。

### 2.3 事件驱动统一
```python
bus = EventBus()
bus.subscribe_handler("data.ohlcv", strategy.on_bar)
replay = EventReplay(bus)
replay.replay(historical_df)  # 回测 = 历史事件重放
```
为 Phase 2 的回测事件驱动重构奠定基础。

### 2.4 存储协议抽象
`SQLStorage` 通过 `_compat.py` 桥接 v1.7 SQLAlchemy ORM，保持零改动复用已有代码。`MemoryStorage` 独立实现，用于测试。

### 2.5 配置分层合并
```python
cfg = load_config(config_file="prod.toml", backend={"database_url": "..."})
# 默认 → TOML 文件 → 环境变量 → kwargs
```
v1.7 的所有环境变量（`DATABASE_URL` / `STOCKSTAT_*`）100% 兼容。

---

## 3. 测试结果

### 3.1 v2.0 核心层单元测试

```
tests/test_v2_core.py: 49 passed in 3.35s
```

覆盖：
- 协议导入与 runtime check
- 插件注册/注销/查找/重复检测/生命周期/延迟初始化
- 配置默认值/环境变量覆盖/kwargs 覆盖/命名空间访问
- 事件总线发布/订阅/父主题递送/无串扰/日志
- EventReplay 简单重放/多标的组重放
- MemoryStorage 写入/查询/upsert/delete/health
- NullCache/MemoryCache(TTL)/RedisCache 工厂
- JSON/CSV/Arrow/Parquet 编解码
- 错误分类与结构化日志

### 3.2 v1.7 全量回归

```
test_frontend.py + test_nonlinear.py + 14 个 backtest 测试文件:
329 passed, 3 warnings in 30.84s
```

**零回归**。新增 `_core/` 包完全独立于 v1.7 代码，不影响任何现有功能。

---

## 4. 与 v1.7 的兼容性

| v1.7 代码 | 影响 | 原因 |
|-----------|------|------|
| `stockstat/__init__.py` | 无 | `_core` 以下划线开头，不自动导入 |
| `stockstat/client.py` | 无 | 未引用 `_core` |
| `stockstat/compute/` | 无 | 未引用 `_core` |
| `stockstat/indicators/` | 无 | 未引用 `_core` |
| `stockstat/backtest/` | 无 | 未引用 `_core` |
| `stockstat/plot/` | 无 | 未引用 `_core` |
| `stockstat/dsl/` | 无 | 未引用 `_core` |
| `stockstat_backend/*` | 无 | 完全独立的后端包 |

`_core/` 是纯新增代码，零改动现有文件。

---

## 5. 后续阶段依赖

Phase 1 为后续阶段提供了：

| 后续阶段 | 使用的核心能力 |
|---------|---------------|
| Phase 2 领域层 | PluginRegistry（指标/数据源/成本模型插件化）、EventBus（回测事件驱动） |
| Phase 3 可视化 | Renderer 协议（渲染器注册到 registry）、Codec（Spec 序列化） |
| Phase 4 接口 | StorageBackend（离线模式）、CacheBackend（Redis 接入）、Codec（Arrow 传输） |
| Phase 5 兼容层 | Config（环境变量兼容）、_compat（SQLAlchemy 桥接） |

---

## 6. 待办（Phase 2+）

- [ ] Phase 2: 领域层迁移 — 将指标/数据源/回测组件注册到 PluginRegistry
- [ ] Phase 3: 可视化统一 — PlotSpec + ChartProfile 合并
- [ ] Phase 4: 接口层 — DSL 自动反射、REST 薄层、CLI
- [ ] Phase 5: 兼容层验证 + PAXG 研究程序兼容性测试
