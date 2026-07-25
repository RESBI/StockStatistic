"""stockstat-dispatcher CLI。"""
from __future__ import annotations

import click


@click.group()
def cli():
    """StockStat Dispatcher CLI."""


@cli.command("serve")
@click.option("--storage-url", default=None)
@click.option("--listen", default="0.0.0.0:9000")
@click.option("--queue-backend", default="memory")
@click.option("--redis-url", default=None)
@click.option("--alias", default="dispatch-primary")
def serve(storage_url, listen, queue_backend, redis_url, alias):
    """启动独立 Dispatcher 服务。"""
    import uvicorn
    from .app import DispatcherApp
    app = DispatcherApp.create(
        storage_url=storage_url,
        queue_backend=queue_backend,
        redis_url=redis_url,
        listen=listen,
        alias=alias,
    )
    host, _, port = listen.partition(":")
    click.echo(f"Starting StockStat Dispatcher on {listen}")
    uvicorn.run(app, host=host or "0.0.0.0", port=int(port) if port else 9000)


@cli.command("cluster")
@click.option("--dispatcher-url", default="http://localhost:9000")
def cluster_info(dispatcher_url):
    """查看集群拓扑。"""
    import httpx
    import json
    resp = httpx.get(f"{dispatcher_url}/dispatch/cluster")
    click.echo(json.dumps(resp.json(), indent=2, default=str))


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
