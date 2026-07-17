"""CLI entry point — ``stockstat`` command.

Usage:
    stockstat serve [--host 0.0.0.0] [--port 8000]
    stockstat ingest SYMBOL [--source S] [--start DATE] [--end DATE] [--tf 1d]
    stockstat query SYMBOL [--start DATE] [--tf 1d] [--limit N]
    stockstat plugins [--namespace NS]
    stockstat indicators [--category CAT]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stockstat",
        description="StockStat — programmable financial statistics platform",
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest data for a symbol")
    p_ingest.add_argument("symbol")
    p_ingest.add_argument("--source", default=None)
    p_ingest.add_argument("--start", default=None)
    p_ingest.add_argument("--end", default=None)
    p_ingest.add_argument("--tf", default="1d", help="Timeframe")

    # query
    p_query = sub.add_parser("query", help="Query OHLCV data")
    p_query.add_argument("symbol")
    p_query.add_argument("--source", default=None)
    p_query.add_argument("--start", default=None)
    p_query.add_argument("--end", default=None)
    p_query.add_argument("--tf", default="1d")
    p_query.add_argument("--limit", type=int, default=None)
    p_query.add_argument("--format", default="table", choices=["table", "json", "csv"])

    # plugins
    p_plugins = sub.add_parser("plugins", help="List registered plugins")
    p_plugins.add_argument("--namespace", default=None)

    # indicators
    p_ind = sub.add_parser("indicators", help="List registered indicators")
    p_ind.add_argument("--category", default=None)

    args = parser.parse_args(argv)

    if args.command == "serve":
        return _cmd_serve(args)
    elif args.command == "ingest":
        return _cmd_ingest(args)
    elif args.command == "query":
        return _cmd_query(args)
    elif args.command == "plugins":
        return _cmd_plugins(args)
    elif args.command == "indicators":
        return _cmd_indicators(args)
    else:
        parser.print_help()
        return 0


def _cmd_serve(args) -> int:
    import uvicorn
    print(f"Starting StockStat API on {args.host}:{args.port}...")
    uvicorn.run(
        "stockstat_backend.app:app",
        host=args.host, port=args.port, reload=False,
    )
    return 0


def _cmd_ingest(args) -> int:
    from stockstat import StockStatClient
    client = StockStatClient()
    result = client.ingest(
        symbol=args.symbol, source=args.source,
        start=args.start, end=args.end, timeframe=args.tf,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_query(args) -> int:
    from stockstat import StockStatClient
    client = StockStatClient()
    df = client.ohlcv(
        symbol=args.symbol, source=args.source,
        start=args.start, end=args.end, timeframe=args.tf,
        limit=args.limit,
    )
    if df.empty:
        print(f"No data for '{args.symbol}'. Try 'stockstat ingest {args.symbol}' first.")
        return 1

    if args.format == "json":
        print(df.reset_index().to_json(orient="records", date_format="iso"))
    elif args.format == "csv":
        print(df.to_csv())
    else:
        print(df.to_string())
    return 0


def _cmd_plugins(args) -> int:
    from stockstat._core.plugin import PluginRegistry
    from stockstat._domain.sources import register_default_sources
    from stockstat._domain.indicators import register_default_indicators
    from stockstat._domain.backtest import register_default_backtest_components
    from stockstat._viz.renderers import register_default_renderers

    reg = PluginRegistry()
    register_default_sources(reg)
    register_default_indicators(reg)
    register_default_backtest_components(reg)
    register_default_renderers(reg)

    items = reg.list(args.namespace)
    if not items:
        print("No plugins registered.")
        return 0

    print(f"{'Namespace':<20} {'Name':<25} {'Category'}")
    print("-" * 70)
    for item in items:
        plugin = item["plugin"]
        cat = getattr(plugin, "category", getattr(plugin, "component_type", ""))
        print(f"{item['namespace']:<20} {item['name']:<25} {cat}")
    print(f"\nTotal: {len(items)} plugin(s)")
    return 0


def _cmd_indicators(args) -> int:
    from stockstat._core.plugin import PluginRegistry
    from stockstat._domain.indicators import register_default_indicators, list_indicators

    reg = PluginRegistry()
    register_default_indicators(reg)

    inds = list_indicators(reg, category=args.category)
    if not inds:
        print("No indicators found.")
        return 0

    print(f"{'Name':<25} {'Category':<15} {'Description'}")
    print("-" * 70)
    for ind in inds:
        print(f"{ind['name']:<25} {ind['category']:<15} {ind['description'][:40]}")
    print(f"\nTotal: {len(inds)} indicator(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
