from __future__ import annotations

import argparse
import json

from . import __version__
from .dsl import DSLCompiler
from .migration import report
from .strategy_package import package_module, verify_package


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockstat")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version")
    migrate = subparsers.add_parser("migrate-scan")
    migrate.add_argument("path")
    dsl = subparsers.add_parser("dsl-explain")
    dsl.add_argument("source")
    package = subparsers.add_parser("strategy-package")
    package.add_argument("module_file")
    package.add_argument("entrypoint")
    package.add_argument("output")
    verify = subparsers.add_parser("strategy-verify")
    verify.add_argument("path")
    verify.add_argument("--trusted-key", action="append", default=[])
    args = parser.parse_args()
    if args.command in {None, "version"}:
        print(f"StockStat {__version__}")
    elif args.command == "migrate-scan":
        print(json.dumps(report(args.path), indent=2))
    elif args.command == "dsl-explain":
        print(DSLCompiler().compile(args.source))
    elif args.command == "strategy-package":
        print(json.dumps(package_module(args.module_file, args.entrypoint, args.output), indent=2))
    elif args.command == "strategy-verify":
        print(json.dumps(verify_package(args.path, trusted_public_keys=args.trusted_key), indent=2))
