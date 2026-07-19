# V3 P7 实施文档 — 多级 Dispatcher + Admin 监控面板

> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §20.7](../../DESIGN_V3_CN.md)
> **前置**：[P6_CN.md](P6_CN.md)（抢占 / 弹性）

---

## 1. 目标

实现 V3 §20.7 的多级 Dispatcher 级联与 Admin Task 监控面板：

1. 子 Dispatcher 注册 / 注销 / 列表
2. `cluster_info` 含 `sub_dispatchers` 字段（多级拓扑）
3. 任务历史记录（最近 1000 项）+ 状态/类型统计
4. Admin Plugin 新增 Task 监控页面（REST API）
5. WebSocket-style 进度推送（P7 用轮询模拟，真实 WS 在 V3.1+）
6. `parent_url` 字段标识子 Dispatcher 上行链路

---

## 2. 完成内容

### 2.1 多级 Dispatcher

`backend/stockstat_backend/dispatcher/core.py` 新增：

```python
class Dispatcher:
    def __init__(self, ..., alias="dispatch-primary", parent_url=None):
        self._alias = alias
        self._parent_url = parent_url  # 子 Dispatcher 上行
        self._sub_dispatchers: dict[str, dict] = {}  # P7: 子 Dispatcher 注册表

    def register_sub_dispatcher(self, sub_id, alias, address, parent_url=None):
        """子 Dispatcher 注册自己到父级。"""
        self._sub_dispatchers[sub_id] = {
            "id": sub_id, "alias": alias, "address": address,
            "status": "online", "registered_at": ...,
        }

    def unregister_sub_dispatcher(self, sub_id): ...
    def list_sub_dispatchers(self) -> list: ...
```

`cluster_info()` 输出新增字段：

```python
{
    "dispatcher": {
        "id": "dispatcher-01",
        "alias": "dispatch-primary",
        "address": "http://...",
        "parent_url": None,  # or "http://parent:9000" for sub-dispatcher
        ...
    },
    "workers": [...],
    "sub_dispatchers": [  # P7: NEW
        {"id": "sub-1", "alias": "child-east", "address": "http://east:9000", ...},
    ],
    "stats": {...},
}
```

**部署拓扑**：
```
                 ┌─── dispatch-primary (parent_url=None) ────┐
                 │                                            │
        ┌────────┴────────┐                          (Worker pool A)
        │                 │
   sub-dispatcher-1   sub-dispatcher-2
   (parent_url=       (parent_url=
    http://parent)     http://parent)
        │                 │
   (Worker pool B)   (Worker pool C)
```

### 2.2 任务历史记录

```python
class Dispatcher:
    def __init__(self, ...):
        self._task_history: list[dict] = []
        self._history_max = 1000  # keep last 1000

    def _record_history(self, state: _TaskState):
        """任务完成/失败时记录。"""
        self._task_history.append({
            "task_id": ..., "task_type": ..., "state": ...,
            "created_at": ..., "started_at": ..., "finished_at": ...,
            "worker_id": ..., "error": ..., "trace_id": ...,
        })
        # LRU trim
        if len(self._task_history) > self._history_max:
            self._task_history = self._task_history[-self._history_max:]

    def get_task_history(self, limit=100, state_filter=None) -> list:
        """Admin UI 用：返回最近 N 条任务记录。"""

    def get_task_stats(self) -> dict:
        """Admin UI 仪表盘：按 state / task_type 聚合统计 + 平均时长。"""
```

`on_complete` 和 `on_fail` 在状态变更后调用 `_record_history(state)`。

### 2.3 Admin Plugin Task 监控

`backend/stockstat_backend/plugins/admin/router.py` 新增 4 个端点：

| 端点 | 说明 |
|------|------|
| `GET /admin/api/dispatcher/cluster` | 完整集群拓扑（含 sub_dispatchers） |
| `GET /admin/api/dispatcher/tasks?limit=100&state=completed` | 任务历史 |
| `GET /admin/api/dispatcher/stats` | 聚合统计（by_state / by_type / avg_duration） |
| `GET /admin/api/dispatcher/autoscaler` | Autoscaler 指标 + 扩缩容建议 |

**接线**：`stockstat_backend/app.py` 在同时启用 admin + dispatcher 时调用
`set_dispatcher_ref(app.state.dispatcher)`，让 Admin 路由能访问
Dispatcher 实例。

**未启用时**：端点返回 404（"Dispatcher not enabled"）。

### 2.4 Dispatcher P7 路由

`backend/stockstat_backend/dispatcher/routes.py` 新增：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/dispatch/sub/register` | POST | 子 Dispatcher 注册 |
| `/dispatch/sub/unregister/{sub_id}` | POST | 子 Dispatcher 注销 |
| `/dispatch/sub` | GET | 列出子 Dispatcher |
| `/dispatch/tasks/history` | GET | 任务历史（limit + state 过滤） |
| `/dispatch/tasks/stats` | GET | 任务统计 |

### 2.5 进度推送（轮询模拟）

P7 不实现真实 WebSocket（涉及异步循环 + 连接管理），改用**轮询**：

- Client 轮询 `GET /dispatch/status/{id}` 获取当前状态
- Client 轮询 `GET /dispatch/tasks/history` 获取已完成的任务
- Worker 通过 `POST /dispatch/partial` 推送中间结果，Dispatcher 缓存
  在 `state.stream_partials`，Client 通过 `stream_results()` 迭代消费

**真实 WebSocket 推送**留待 V3.1+，需引入 `websockets` 或 `starlette.websockets`。

---

## 3. 测试体系

### 3.1 新增测试

**文件**：`frontend/tests/test_v3_multilevel.py` — **23 项**

| 类 | 测试数 | 覆盖 |
|----|--------|------|
| `TestSubDispatcher` | 6 | register / list / unregister / cluster_info 含 sub / parent_url / default |
| `TestTaskHistory` | 5 | empty / records completed / records failed / limit / state_filter |
| `TestTaskStats` | 2 | empty / after tasks (by_state, by_type, avg_duration) |
| `TestAdminDispatcherRoutes` | 3 | routes exist / 404 when not enabled / cluster topology |
| `TestDispatcherP7Routes` | 5 | endpoints exist / sub_register / sub_list / history / stats |
| `TestProgressPolling` | 2 | via status / via partials |

### 3.2 关键测试场景

#### 3.2.1 多级 Dispatcher 拓扑
```python
def test_cluster_info_includes_sub_dispatchers(self, dispatcher):
    dispatcher.register_sub_dispatcher(
        "sub-1", "child-east", "http://east:9000",
    )
    info = dispatcher.cluster_info()
    assert "sub_dispatchers" in info
    assert len(info["sub_dispatchers"]) == 1
    assert info["sub_dispatchers"][0]["alias"] == "child-east"

def test_cluster_info_includes_parent_url(self):
    sub = Dispatcher(alias="dispatch-child",
                      parent_url="http://parent:9000")
    info = sub.cluster_info()
    assert info["dispatcher"]["parent_url"] == "http://parent:9000"
```

#### 3.2.2 任务历史与统计
```python
def test_stats_after_tasks(self, dispatcher):
    # 完成 3 个任务：2 个 custom，1 个 indicator
    for task_type in ("custom", "custom", "indicator"):
        ...dispatcher.on_complete(...)
    stats = dispatcher.get_task_stats()
    assert stats["total_tasks"] == 3
    assert stats["by_state"]["completed"] == 3
    assert stats["by_type"]["custom"] == 2
    assert stats["by_type"]["indicator"] == 1
```

#### 3.2.3 Admin Plugin 接线
```python
def test_admin_dispatcher_routes_exist_when_enabled(self):
    os.environ["STOCKSTAT_ADMIN_ENABLED"] = "true"
    os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "true"
    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/admin/api/dispatcher/cluster" in paths
    assert "/admin/api/dispatcher/tasks" in paths
    assert "/admin/api/dispatcher/stats" in paths
```

#### 3.2.4 进度轮询
```python
def test_progress_via_partials(self, dispatcher):
    dispatcher.submit(spec)
    dispatcher.on_partial("w1", spec.task_id, {"progress": 0.25})
    dispatcher.on_partial("w1", spec.task_id, {"progress": 0.5})
    dispatcher.on_partial("w1", spec.task_id, {"progress": 0.75})
    state = dispatcher._tasks[spec.task_id]
    assert len(state.stream_partials) == 3
```

---

## 4. 兼容性

### 4.1 与 P6 兼容

- 所有 P6 方法（preempt / resume / drain / discover / autoscaler）不变
- P7 仅新增方法，不修改现有路径

### 4.2 与 v2.1 兼容

- 默认 `dispatcher_enabled=false`，Admin /dispatch/* 路由返回 404
- 启用后无破坏性变更（只新增端点）

### 4.3 与单级 Dispatcher 兼容

- 不注册任何子 Dispatcher 时，`sub_dispatchers` 为空列表
- `parent_url=None` 时表示这是顶级 Dispatcher

---

## 5. 已知限制

1. **WebSocket 未实现**：进度推送用轮询模拟。真实 WS 需引入
   `starlette.websockets`，并处理异步循环 + 连接生命周期。
2. **子 Dispatcher 不自动转发任务**：当前 `register_sub_dispatcher`
   只是拓扑记录。真实级联需子 Dispatcher 在本地队列空时调用父级
   `assign_task`，复杂度较高，留待 V3.1+。
3. **任务历史无持久化**：进程内 list，Dispatcher 重启后丢失。
   P7+ 改为 SQLite 或 Redis 持久化。
4. **Admin UI 仅 REST**：未提供 Web 前端页面。前端开发在 V3.1+
   或由用户自行实现（参考现有 `/admin` SPA）。

---

## 6. 文件清单

```
backend/stockstat_backend/
├── dispatcher/
│   ├── core.py              [+alias/parent_url/_sub_dispatchers/_task_history
│   │                          +register_sub_dispatcher/unregister/list
│   │                          +_record_history/get_task_history/get_task_stats
│   │                          +cluster_info 含 sub_dispatchers + parent_url]
│   └── routes.py            [+/dispatch/sub/* /dispatch/tasks/history /stats]
├── plugins/admin/
│   └── router.py            [+/admin/api/dispatcher/{cluster,tasks,stats,autoscaler}
│   │                          +set_dispatcher_ref()]
└── app.py                   [+set_dispatcher_ref() 接线]

frontend/tests/
└── test_v3_multilevel.py    [NEW, 420 行]   23 项
```

---

## 7. V3 完整阶段总结

P0 ~ P7 全部完成，累计：

| 阶段 | 测试数 | 累计 | 状态 |
|------|--------|------|------|
| 原有 v2.1 | 599 | 599 | ✅ |
| P0 协议骨架 | 50 | 649 | ✅ |
| P1 本地后端 | 58 | 707 | ✅ |
| P2 Dispatcher+Worker | 83 | 790 | ✅ |
| P3 HTTP 跨机 | 22 | 812 | ✅ |
| P4 共享内存+流式 | 34 | 846 | ✅ |
| P5 Redis+Msgpack | 17 (+6 skip) | 863 (+6) | ✅ |
| P6 抢占+弹性 | 36 | 899 | ✅ |
| P7 多级+监控 | 23 | 922 | ✅ |

**总计**：922 项通过 + 6 项跳过（无 Redis）

---

## 8. 下阶段规划（V3.1+）

- **WebSocket 进度推送**：替代轮询，实现真实推送
- **子 Dispatcher 任务转发**：完整级联调度
- **Admin Web UI**：基于现有 SPA 框架，新增 Task 监控页
- **Checkpoint 持久化**：Redis / SQLite，支持跨进程 resume
- **多 Dispatcher 高可用**：主备切换 + 故障转移
- **GPU 资源调度**：Worker 上报 GPU 负载，Dispatcher 按需路由

---

*P7 完成。V3 P0-P7 全部交付。下一步：总体测试 + PAXG 验证 + 部署测试 + 文档。*
