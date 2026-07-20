# V3.1 Deployment

## Profiles

- Embedded: `StockStat.local()` with SQLite and LocalFS.
- Network development: three service CLIs with SQLite and LocalFS.
- Production: PostgreSQL, S3/MinIO, 2+ Dispatcher replicas, 1+ isolated Workers, and an external load balancer.

## Compose

Copy `.env.v31.example` to `.env`, replace every secret, then run:

```bash
docker compose up --build --scale dispatcher=2 --scale worker=2
```

The image runs as UID 10001, uses a read-only root filesystem, drops Worker capabilities, and uses per-container tmpfs scratch. Apply an environment-specific seccomp/AppArmor profile and default-deny egress policy around Workers. Only Storage ingestion capabilities should receive data-source credentials.

## Authentication

Client and Worker credentials are separate.

- Dispatcher client scopes: `jobs`, `cluster`.
- Storage client scopes: `data`, `artifacts`.
- Internal Worker token: `/internal/v31/*` control and Artifact paths.

`--api-token TOKEN=scope1,scope2` may be repeated. Tokens are compared with constant-time functions; only a SHA-256-derived principal ID is persisted. Rotate by temporarily configuring old and new client token rules, moving clients, then removing the old token. Rotate the internal token during a Worker rolling restart.

## PostgreSQL

Storage and Dispatcher use separate schemas and bounded `psycopg_pool` pools with statement timeouts. Run schema initialization before accepting traffic. Migrations are forward-only during a release window; restore the database and route to the previous immutable image for rollback.

## S3/MinIO

Configure `--s3-bucket`, `--s3-endpoint`, `--s3-prefix`, and AWS credentials. Uploads use boto3 multipart transfer and server-side encryption. Presigned URLs are capped at one hour. Configure bucket versioning and lifecycle independently from the application.

## Readiness

- `GET /health/live`: process liveness.
- `GET /health/ready`: backing-store readiness.
- `GET /metrics`: low-cardinality Prometheus text metrics.

Workers have no public HTTP listener. Drain with `POST /v31/cluster/workers/{worker_id}/drain`, wait for active Attempts to finish, then stop the process.
