# V3.1 Operations Runbook

## Backup And Restore

1. Put client traffic into maintenance mode; allow active Jobs to finish or cancel them.
2. Run `pg_dump --format=custom` for both V3.1 schemas.
3. Enable S3 bucket versioning and record the Artifact prefix/version marker.
4. Restore into a new database and bucket prefix.
5. Start Storage and Dispatcher against the restored copy and run authenticated network smoke tests.
6. Compare Job counts, terminal state counts, Artifact metadata counts, and a sample of Artifact digests before routing traffic.

## Artifact Reconciliation

Call `POST /v31/artifacts/reconcile` with `{"delete": false}` first. Investigate unexpected orphan digests, then repeat with `{"delete": true}`. Never delete blobs before the metadata backup is verified.

## Dispatcher Incident

Dispatcher is stateless beyond PostgreSQL. Remove an unhealthy replica from the load balancer and replace it. Leases remain fenced by Attempt ID, generation, session, token hash, and expiry. SSE clients reconnect with `Last-Event-ID`.

## Worker Incident

Executor crashes return `EXECUTOR_CRASHED`; OOM returns `EXECUTOR_OOM`; disk exhaustion returns `DISK_FULL`. The Agent survives executor crashes. Expired leases retry until `max_attempts`, then fail terminally. Drain healthy Workers before upgrades.

## Database Incident

The services fail readiness while PostgreSQL is unavailable. Do not initialize a replacement empty database under the same endpoint. Restore connectivity or route to the tested restored copy.

## Capacity

Monitor queued WorkUnits, active WorkUnits, ready Workers, and oldest queue wait. Scale up when backlog persists beyond a normal task duration. Do not scale down the final Worker that provides a required capability. Dispatcher does not require Redis for correctness.

## Windows Worker

Run the Worker under a dedicated low-privilege account. Use Windows Job Objects or container memory/CPU limits, deny interactive login, isolate the scratch directory, and restrict outbound firewall rules. Rotate the internal token during a controlled restart.
