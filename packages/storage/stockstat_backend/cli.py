"""stockstat-backend CLI。"""
from __future__ import annotations

import uvicorn
import click

from stockstat_foundation import Config


@click.group()
def cli():
    """StockStat Storage CLI."""


@cli.command("serve")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
@click.option("--database-url", default=None, help="Override database URL")
@click.option("--admin/--no-admin", default=None)
@click.option("--reload/--no-reload", default=False)
def serve(host, port, database_url, admin, reload):
    """启动 Storage HTTP 服务。"""
    overrides = {}
    if database_url:
        overrides["database_url"] = database_url
    if admin is not None:
        overrides["admin_enabled"] = admin
    config = Config.from_env().copy(**overrides)
    from .app import StorageApp
    app = StorageApp.create(config)
    click.echo(f"Starting StockStat Storage on {host}:{port}")
    click.echo(f"  database: {config.database_url}")
    click.echo(f"  admin: {config.admin_enabled}")
    uvicorn.run(app, host=host, port=port, reload=reload)


@cli.command("init-db")
@click.option("--database-url", default=None)
def init_db(database_url):
    """初始化数据库表。"""
    overrides = {}
    if database_url:
        overrides["database_url"] = database_url
    config = Config.from_env().copy(**overrides)
    from .storage.orm import OrmSession, create_engine_from_url
    engine = create_engine_from_url(config.database_url)
    orm = OrmSession(engine)
    orm.create_all()
    click.echo(f"Database initialized: {config.database_url}")


@cli.command("ingest")
@click.option("--symbol", required=True)
@click.option("--timeframe", default="1d")
@click.option("--source", default="synthetic")
@click.option("--start")
@click.option("--end")
@click.option("--database-url", default=None)
def ingest(symbol, timeframe, source, start, end, database_url):
    """从数据源采集数据并写入数据库。"""
    overrides = {}
    if database_url:
        overrides["database_url"] = database_url
    config = Config.from_env().copy(**overrides)
    from .storage.orm import OrmSession, create_engine_from_url
    from .storage.backend import StorageBackendImpl
    from .adapters import get_adapter
    engine = create_engine_from_url(config.database_url)
    orm = OrmSession(engine)
    orm.create_all()
    backend = StorageBackendImpl(orm)
    adapter_cls = get_adapter(source)
    adapter = adapter_cls()
    df = adapter.fetch_ohlcv(symbol, timeframe, start, end)
    rows = backend.ingest_ohlcv(symbol, timeframe, df)
    click.echo(f"Ingested {rows} rows for {symbol} {timeframe} from {source}")


@cli.command("list-symbols")
@click.option("--database-url", default=None)
def list_symbols(database_url):
    """列出所有标的。"""
    overrides = {}
    if database_url:
        overrides["database_url"] = database_url
    config = Config.from_env().copy(**overrides)
    from .storage.orm import OrmSession, create_engine_from_url
    from .storage.backend import StorageBackendImpl
    engine = create_engine_from_url(config.database_url)
    orm = OrmSession(engine)
    backend = StorageBackendImpl(orm)
    for sym in backend.list_symbols():
        click.echo(sym)


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
