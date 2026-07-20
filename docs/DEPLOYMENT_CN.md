# V3.1 部署

## Profile

- Embedded：`StockStat.local()`，SQLite + LocalFS。
- 网络开发：三个 CLI 服务，SQLite + LocalFS。
- 生产：PostgreSQL、S3/MinIO、2 个以上 Dispatcher、隔离 Worker 和外部负载均衡。

复制 `.env.v31.example` 为 `.env` 并替换全部 secret：

```bash
docker compose up --build --scale dispatcher=2 --scale worker=2
```

镜像使用 UID 10001、只读根文件系统、Worker cap drop 和 tmpfs scratch。生产环境还应配置 seccomp/AppArmor 与 Worker 默认拒绝出网；只有 ingestion capability 可以注入数据源凭据。

Client 与 Worker 凭据必须分离。Client scope 为 `jobs`、`cluster`、`data`、`artifacts`；Worker 使用独立 internal token。系统只持久化 token 的 SHA-256 派生 principal ID。

PostgreSQL 的 Storage/Dispatcher 使用独立 schema、有界连接池和 statement timeout。S3 上传使用 multipart 与服务端加密，presigned URL 最长一小时。

健康端点：`/health/live`、`/health/ready`、`/metrics`。Worker 升级前通过 `/v31/cluster/workers/{worker_id}/drain` 排空。
