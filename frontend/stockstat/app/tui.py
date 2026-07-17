"""TUI — Terminal User Interface for StockStat storage management.

Provides an interactive terminal interface for browsing and managing
stored data on a remote or local StockStat storage server.

Usage:
    stockstat tui                          # connect to localhost:8000
    stockstat tui --host 192.168.1.100     # connect to remote server

Requires the ``rich`` library (pip install rich). If not installed,
falls back to a plain-text menu.
"""
from __future__ import annotations

import sys
from typing import Optional


def run_tui(host: str = "localhost", port: int = 8000) -> int:
    """Launch the TUI, connecting to the given storage server."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.prompt import Prompt, Confirm
        from rich.live import Live
        RICH = True
    except ImportError:
        RICH = False

    from stockstat import StockStatClient

    client = StockStatClient(host=host, port=port)

    if RICH:
        return _run_rich_tui(client, host, port)
    else:
        return _run_plain_tui(client, host, port)


# ═══════════════════════════════════════════════════════════════
# Rich-based TUI
# ═══════════════════════════════════════════════════════════════

def _run_rich_tui(client, host: str, port: int) -> int:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm

    console = Console()

    def _header():
        console.clear()
        console.print(Panel.fit(
            f"[bold cyan]StockStat Storage Manager[/]\n"
            f"Server: [yellow]{host}:{port}[/]  "
            f"Status: {_health_str(client)}",
            border_style="cyan",
        ))

    def _health_str(client):
        try:
            return "[green]ONLINE[/]" if client.health() else "[red]OFFLINE[/]"
        except Exception:
            return "[red]UNREACHABLE[/]"

    while True:
        _header()
        console.print(
            "\n[bold]Menu:[/]\n"
            "  [cyan]1[/] Browse symbols\n"
            "  [cyan]2[/] Query OHLCV data\n"
            "  [cyan]3[/] Ingest new data\n"
            "  [cyan]4[/] Data statistics\n"
            "  [cyan]5[/] List data sources\n"
            "  [cyan]6[/] View proxy config\n"
            "  [cyan]q[/] Quit\n"
        )

        choice = Prompt.ask("Choice", default="1")

        if choice == "q":
            console.print("[dim]Goodbye.[/]")
            return 0

        elif choice == "1":
            _browse_symbols(console, client)

        elif choice == "2":
            _query_ohlcv(console, client)

        elif choice == "3":
            _ingest_data(console, client)

        elif choice == "4":
            _data_stats(console, client)

        elif choice == "5":
            _list_sources(console, client)

        elif choice == "6":
            _view_proxy(console, client)


def _browse_symbols(console, client):
    from rich.table import Table
    from rich.prompt import Prompt

    try:
        symbols = client.symbols()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    if not symbols:
        console.print("[yellow]No symbols registered. Use 'Ingest new data' to add some.[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    table = Table(title="Registered Symbols", show_lines=True)
    table.add_column("Symbol", style="cyan", no_wrap=True)
    table.add_column("Type", style="green")
    table.add_column("Base", style="white")
    table.add_column("Quote", style="white")
    table.add_column("Sources", style="yellow")
    table.add_column("Description", style="dim")

    for s in symbols:
        table.add_row(
            s.get("unified_symbol", ""),
            s.get("asset_type", ""),
            s.get("base_asset", ""),
            s.get("quote_asset", "") or "",
            ", ".join(s.get("sources", [])),
            s.get("description", "") or "",
        )

    console.print(table)
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def _query_ohlcv(console, client):
    from rich.table import Table
    from rich.prompt import Prompt

    symbol = Prompt.ask("Symbol", default="BTC/USDT")
    limit = Prompt.ask("Limit (rows)", default="10")

    try:
        limit_int = int(limit) if limit else 10
    except ValueError:
        limit_int = 10

    try:
        df = client.ohlcv(symbol, limit=limit_int)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    if df.empty:
        console.print(f"[yellow]No data for '{symbol}'. Try ingesting first.[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    table = Table(title=f"OHLCV: {symbol} (last {len(df)} rows)", show_lines=False)
    table.add_column("ts", style="dim", no_wrap=True)
    for col in ["open", "high", "low", "close", "volume"]:
        table.add_column(col, style="cyan", justify="right")

    for ts, row in df.iterrows():
        table.add_row(
            str(ts),
            f"{row.get('open', 0):.2f}",
            f"{row.get('high', 0):.2f}",
            f"{row.get('low', 0):.2f}",
            f"{row.get('close', 0):.2f}",
            f"{row.get('volume', 0):.0f}",
        )

    console.print(table)
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def _ingest_data(console, client):
    from rich.prompt import Prompt

    symbol = Prompt.ask("Symbol to ingest", default="BTC/USDT")
    source = Prompt.ask("Source (blank=auto)", default="")
    start = Prompt.ask("Start date (blank=skip)", default="")
    end = Prompt.ask("End date (blank=skip)", default="")
    tf = Prompt.ask("Timeframe", default="1d")

    console.print(f"[cyan]Ingesting {symbol}...[/]")

    try:
        result = client.ingest(
            symbol=symbol,
            source=source or None,
            start=start or None,
            end=end or None,
            timeframe=tf,
        )
        console.print(f"[green]Done![/] {result}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")

    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def _data_stats(console, client):
    from rich.table import Table
    from rich.prompt import Prompt

    try:
        symbols = client.symbols()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    table = Table(title="Data Statistics", show_lines=True)
    table.add_column("Symbol", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Sources", style="yellow")
    table.add_column("Rows", justify="right", style="white")

    total_rows = 0
    for s in symbols:
        sym = s["unified_symbol"]
        try:
            df = client.ohlcv(sym, limit=1)
            # We can't get exact count via API without a count endpoint,
            # so we query all and count. For large datasets this is slow;
            # in practice the admin web UI has a proper stats endpoint.
            # For TUI, just show a sample.
            rows = "?"
        except Exception:
            rows = "?"
        table.add_row(sym, s.get("asset_type", ""),
                      ", ".join(s.get("sources", [])), rows)

    console.print(table)
    console.print("[dim]Tip: Use the web admin UI at http://host:8000/admin/ for detailed statistics.[/]")
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def _list_sources(console, client):
    from rich.table import Table
    from rich.prompt import Prompt

    try:
        result = client.sources()
        sources = result if isinstance(result, list) else result.get("sources", [])
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    table = Table(title="Data Sources", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Description", style="white")

    for s in sources:
        table.add_row(s.get("name", ""), s.get("type", ""), s.get("description", ""))

    console.print(table)
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


def _view_proxy(console, client):
    from rich.table import Table
    from rich.prompt import Prompt
    import httpx

    try:
        resp = httpx.get(f"http://{client._config.host}:{client._config.port}/api/v1/proxy",
                         timeout=10)
        proxy = resp.json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        Prompt.ask("[dim]Press Enter to continue[/]", default="")
        return

    table = Table(title="Proxy Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="yellow")

    for k, v in proxy.items():
        table.add_row(k, str(v))

    console.print(table)
    Prompt.ask("[dim]Press Enter to continue[/]", default="")


# ═══════════════════════════════════════════════════════════════
# Plain-text fallback (no rich)
# ═══════════════════════════════════════════════════════════════

def _run_plain_tui(client, host: str, port: int) -> int:
    print(f"\nStockStat Storage Manager (plain mode — install 'rich' for better UI)")
    print(f"Server: {host}:{port}\n")

    while True:
        print("Menu:")
        print("  1. Browse symbols")
        print("  2. Query OHLCV data")
        print("  3. Ingest new data")
        print("  4. List data sources")
        print("  q. Quit\n")

        choice = input("Choice: ").strip()

        if choice == "q":
            print("Goodbye.")
            return 0
        elif choice == "1":
            symbols = client.symbols()
            if not symbols:
                print("  No symbols registered.")
            for s in symbols:
                print(f"  {s['unified_symbol']:15s}  {s['asset_type']:8s}  {s.get('sources', [])}")
            input("\nPress Enter to continue...")
        elif choice == "2":
            symbol = input("Symbol: ").strip() or "BTC/USDT"
            try:
                df = client.ohlcv(symbol, limit=10)
                print(df.to_string())
            except Exception as e:
                print(f"  Error: {e}")
            input("\nPress Enter to continue...")
        elif choice == "3":
            symbol = input("Symbol: ").strip()
            source = input("Source (blank=auto): ").strip() or None
            start = input("Start date: ").strip() or None
            end = input("End date: ").strip() or None
            try:
                result = client.ingest(symbol=symbol, source=source, start=start, end=end)
                print(f"  Done: {result}")
            except Exception as e:
                print(f"  Error: {e}")
            input("\nPress Enter to continue...")
        elif choice == "4":
            try:
                result = client.sources()
                sources = result if isinstance(result, list) else result.get("sources", [])
                for s in sources:
                    print(f"  {s['name']:15s}  {s['type']:8s}  {s.get('description', '')}")
            except Exception as e:
                print(f"  Error: {e}")
            input("\nPress Enter to continue...")

    return 0
