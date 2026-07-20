#!/usr/bin/env python3
"""stockstat-compute CLI — Worker process entry point.

Usage:
    stockstat-compute worker --dispatcher-url http://localhost:8000
    stockstat-compute worker --dispatcher-url http://dispatch:9000 --concurrency 8
    stockstat-compute worker --alias gpu-box-alpha --label rack=A-12
"""
from __future__ import annotations

import argparse
import sys
import signal


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="stockstat-compute",
        description="StockStat V3 Compute Worker",
    )
    sub = parser.add_subparsers(dest="command")

    # worker
    p_worker = sub.add_parser("worker", help="Start a compute Worker")
    p_worker.add_argument("--dispatcher-url", required=True,
                          help="Dispatcher URL (e.g. http://localhost:8000)")
    p_worker.add_argument("--concurrency", type=int, default=None,
                          help="Max concurrent tasks (default: CPU count)")
    p_worker.add_argument("--alias", default=None,
                          help="Human-readable worker name")
    p_worker.add_argument("--label", action="append", default=[],
                          help="Label in key=value format (repeatable)")
    p_worker.add_argument("--capability", action="append", default=None,
                          help="Task type capability (repeatable)")
    p_worker.add_argument("--preemptable", action="store_true",
                          help="Allow task preemption")
    p_worker.add_argument("--poll-interval", type=float, default=1.0,
                          help="Seconds between task polls (default: 1.0)")
    p_worker.add_argument("--heartbeat-interval", type=float, default=10.0,
                          help="Seconds between heartbeats (default: 10.0)")

    args = parser.parse_args(argv)

    if args.command == "worker":
        return _run_worker(args)
    parser.print_help()
    return 0


def _run_worker(args) -> int:
    # Ensure stockstat is importable
    try:
        import stockstat
    except ImportError:
        import os
        frontend = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
        sys.path.insert(0, os.path.abspath(frontend))
        try:
            import stockstat  # noqa: F401
        except ImportError:
            print("[ERROR] stockstat package not found. Install with: pip install -e frontend/")
            return 1

    from stockstat_compute.worker import Worker

    # Parse labels
    labels = {}
    for label_str in args.label:
        if "=" in label_str:
            k, v = label_str.split("=", 1)
            labels[k] = v

    worker = Worker(
        dispatcher_url=args.dispatcher_url,
        concurrency=args.concurrency,
        alias=args.alias,
        labels=labels,
        capabilities=args.capability,
        preemptable=args.preemptable,
        poll_interval=args.poll_interval,
        heartbeat_interval=args.heartbeat_interval,
    )

    # Handle Ctrl+C / SIGTERM
    def shutdown(signum, frame):
        print(f"\n[Worker] Received signal {signum}, draining...")
        worker.stop()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        worker.start()
        return 0
    except Exception as e:
        print(f"[Worker] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
