# V3.1 运维 Runbook

## 备份恢复

1. 进入维护窗口，等待或取消活动 Job。
2. 对两个 V3.1 schema 执行 `pg_dump --format=custom`。
3. 启用 S3 bucket versioning，并记录 Artifact prefix/version marker。
4. 恢复到新的数据库和 bucket prefix。
5. 用恢复副本启动 Storage/Dispatcher 并运行认证网络 smoke。
6. 对比 Job 数、终态数、Artifact 元数据数和抽样 digest 后再切流量。

## Artifact GC

先调用 `POST /v31/artifacts/reconcile`，请求体 `{"delete": false}`。调查未知 orphan 后才可用 `{"delete": true}`。元数据备份未验证前禁止删除 Blob。

## 故障处理

- Dispatcher 无本地状态，摘除异常副本后替换；SSE 用 `Last-Event-ID` 重连。
- Executor crash 为 `EXECUTOR_CRASHED`，OOM 为 `EXECUTOR_OOM`，磁盘满为 `DISK_FULL`；Agent 保持存活。
- Lease 超时按 `max_attempts` 重试，耗尽后终态失败。
- PostgreSQL 中断时 readiness 失败，不得在原 endpoint 下初始化空数据库。

## 扩缩容

监控 queued/active WorkUnit、ready Worker 和 oldest queue wait。持续 backlog 才扩容；不得缩掉最后一个提供必要 capability 的 Worker。Redis 不参与一致性。

Windows Worker 应运行在独立低权限账号下，并用 Job Object/容器限制 CPU 与内存、隔离 scratch、限制出站防火墙规则。
