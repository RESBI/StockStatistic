"""stockstat CLI — 用户命令行入口。"""
from __future__ import annotations

import json
import sys

import click


@click.group()
def cli():
    """StockStat V3.1 CLI."""


@cli.group()
def data():
    """数据管理。"""


@data.command("fetch")
@click.argument("symbol")
@click.option("--timeframe", default="1d")
@click.option("--start")
@click.option("--end")
@click.option("--source")
@click.option("--storage-url", default=None)
@click.option("--limit", default=20, type=int)
def data_fetch(symbol, timeframe, start, end, source, storage_url, limit):
    """查询 OHLCV 数据。"""
    from ..client import StockStatClient
    client = StockStatClient(storage_url=storage_url) if storage_url else StockStatClient()
    try:
        df = client.ohlcv(symbol, timeframe, start, end, source)
        click.echo(df.head(limit).to_string())
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@data.command("list")
@click.option("--storage-url", default=None)
def data_list(storage_url):
    """列出所有标的。"""
    from ..client import StockStatClient
    client = StockStatClient(storage_url=storage_url) if storage_url else StockStatClient()
    for sym in client.list_symbols():
        click.echo(sym)


@data.command("ingest")
@click.option("--symbol", required=True)
@click.option("--timeframe", default="1d")
@click.option("--source", default="synthetic")
@click.option("--storage-url", default=None)
def data_ingest(symbol, timeframe, source, storage_url):
    """从数据源采集数据。"""
    from ..client import StockStatClient
    from stockstat_backend import get_adapter
    client = StockStatClient(storage_url=storage_url) if storage_url else StockStatClient()
    adapter_cls = get_adapter(source)
    adapter = adapter_cls()
    df = adapter.fetch_ohlcv(symbol, timeframe)
    rows = client.ingest(symbol, timeframe, df)
    click.echo(f"Ingested {rows} rows for {symbol} {timeframe}")


@cli.group()
def compute():
    """计算任务。"""


@compute.command("indicator")
@click.option("--name", required=True, help="indicator name (ma/rsi/macd/...)")
@click.option("--symbol", required=True)
@click.option("--window", default=20, type=int)
@click.option("--timeframe", default="1d")
@click.option("--storage-url", default=None)
def compute_indicator(name, symbol, window, timeframe, storage_url):
    """计算技术指标。"""
    from ..client import StockStatClient
    client = StockStatClient(storage_url=storage_url) if storage_url else StockStatClient()
    try:
        data = client.ohlcv(symbol, timeframe)
        result = client.compute._dispatch_indicator(name, data["close"], window=window)
        click.echo(result.tail(10).to_string())
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@compute.command("list-handlers")
def compute_list_handlers():
    """列出所有可用的 task_type handler。"""
    from stockstat_compute.handlers import list_task_types
    for tt in list_task_types():
        click.echo(tt)


@cli.group()
def task():
    """任务管理。"""


@task.command("status")
@click.argument("task_id")
def task_status(task_id):
    """查询任务状态。"""
    from ..client import StockStatClient
    client = StockStatClient()
    try:
        info = client.compute_backend.get(task_id)
        click.echo(f"Task {task_id}: {info.state.value} ({info.progress*100:.1f}%)")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group()
def cluster():
    """集群命令。"""


@cluster.command("info")
def cluster_info():
    """查看集群拓扑。"""
    from ..client import StockStatClient
    client = StockStatClient()
    info = client.cluster_info()
    click.echo(json.dumps(info, indent=2, default=str))


@cli.command("config")
def config_show():
    """显示当前配置。"""
    from stockstat_foundation import Config
    c = Config.from_env()
    click.echo(json.dumps(c.to_dict(), indent=2, default=str))


@cli.command("version")
def version():
    """显示版本。"""
    from .. import __version__
    click.echo(f"StockStat {__version__}")


@cli.command("serve")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
@click.option("--database-url", default=None)
@click.option("--admin/--no-admin", default=None)
def serve(host, port, database_url, admin):
    """启动 Storage 服务（便捷入口）。"""
    from stockstat_foundation import Config
    overrides = {}
    if database_url:
        overrides["database_url"] = database_url
    if admin is not None:
        overrides["admin_enabled"] = admin
    config = Config.from_env().copy(**overrides)
    try:
        import uvicorn
        from stockstat_backend import StorageApp
        app = StorageApp.create(config)
        click.echo(f"Starting StockStat Storage on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        click.echo("Storage server requires: pip install stockstat[server]", err=True)


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
