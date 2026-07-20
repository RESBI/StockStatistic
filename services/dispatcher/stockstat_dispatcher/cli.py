from __future__ import annotations

import argparse
import os

import uvicorn
from stockstat_contracts import parse_token_rules

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockstat-dispatcher")
    parser.add_argument("--database-url", default="sqlite:///stockstat-v31-tasks.db")
    parser.add_argument("--storage-url", default="http://127.0.0.1:8101")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument(
        "--api-token",
        action="append",
        default=[],
        help="TOKEN=jobs,cluster; repeat for additional tokens",
    )
    parser.add_argument("--internal-token", default=os.getenv("STOCKSTAT_INTERNAL_TOKEN"))
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            args.database_url,
            args.storage_url,
            token_scopes=parse_token_rules(args.api_token),
            internal_token=args.internal_token,
        ),
        host=args.host,
        port=args.port,
        access_log=False,
    )
