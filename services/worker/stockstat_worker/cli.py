from __future__ import annotations

import argparse
import os
import signal
import time

from stockstat.http import HttpArtifactClient

from .agent import WorkerAgent
from .http import HttpDispatcherClient


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockstat-worker")
    parser.add_argument("--dispatcher-url", default="http://127.0.0.1:8100")
    parser.add_argument("--storage-url", default="http://127.0.0.1:8101")
    parser.add_argument("--root", default=".stockstat-v31/worker-http")
    parser.add_argument("--internal-token", default=os.getenv("STOCKSTAT_INTERNAL_TOKEN"))
    args = parser.parse_args()
    dispatcher = HttpDispatcherClient(args.dispatcher_url, token=args.internal_token)
    artifacts = HttpArtifactClient(args.storage_url, token=args.internal_token)
    agent = WorkerAgent(dispatcher, artifacts, args.root).start()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            time.sleep(0.2)
    finally:
        agent.stop()
        dispatcher.close()
        artifacts.close()
