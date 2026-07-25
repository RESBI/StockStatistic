"""stockstat-compute CLI（worker 命令在 P6 完整实现）。"""
from __future__ import annotations

import click


@click.group()
def cli():
    """StockStat Compute CLI."""


@cli.command("worker")
@click.option("--dispatcher-url", required=True)
@click.option("--concurrency", type=int, default=None)
@click.option("--alias", default=None)
@click.option("--label", multiple=True)
@click.option("--capabilities", default=None)
@click.option("--preemptable", is_flag=True)
def worker_cmd(dispatcher_url, concurrency, alias, label, capabilities, preemptable):
    """启动 Worker。"""
    labels = {}
    for l in label:
        if "=" in l:
            k, v = l.split("=", 1)
            labels[k] = v
    caps = capabilities.split(",") if capabilities else None
    from .worker import Worker
    w = Worker(
        dispatcher_url=dispatcher_url,
        concurrency=concurrency,
        alias=alias,
        labels=labels,
        capabilities=caps,
        preemptable=preemptable,
    )
    click.echo(f"Starting Worker: alias={w.alias}, concurrency={concurrency or 'auto'}")
    try:
        w.start()
    except KeyboardInterrupt:
        click.echo("Stopping...")
        w.stop()
        w.join()


@cli.command("list-handlers")
def list_handlers():
    """列出所有已注册的 task_type handler。"""
    from .handlers import list_task_types
    for tt in list_task_types():
        click.echo(tt)


@cli.command("hardware")
def hardware():
    """显示当前硬件信息。"""
    from .register import detect_hardware
    import json
    hw = detect_hardware()
    click.echo(json.dumps(hw, indent=2, default=str))


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
