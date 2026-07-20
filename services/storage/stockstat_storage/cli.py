from __future__ import annotations

import argparse
import os

import uvicorn
from stockstat_contracts import parse_token_rules

from .app import create_app
from .artifacts import S3BlobStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockstat-storage")
    parser.add_argument("--database-url", default="sqlite:///stockstat-v31-storage.db")
    parser.add_argument("--artifact-root", default=".stockstat-v31/artifacts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8101)
    parser.add_argument(
        "--api-token",
        action="append",
        default=[],
        help="TOKEN=data,artifacts; repeat for additional tokens",
    )
    parser.add_argument("--internal-token", default=os.getenv("STOCKSTAT_INTERNAL_TOKEN"))
    parser.add_argument("--max-upload-bytes", type=int, default=3 * 1024**3)
    parser.add_argument("--s3-bucket")
    parser.add_argument("--s3-prefix", default="stockstat-v31")
    parser.add_argument("--s3-endpoint", default=os.getenv("STOCKSTAT_S3_ENDPOINT"))
    parser.add_argument("--s3-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--s3-sse", default="AES256")
    args = parser.parse_args()
    blob_store = None
    if args.s3_bucket:
        import boto3

        client = boto3.client("s3", endpoint_url=args.s3_endpoint, region_name=args.s3_region)
        blob_store = S3BlobStore(
            args.s3_bucket,
            args.s3_prefix,
            client=client,
            server_side_encryption=args.s3_sse or None,
        )
    uvicorn.run(
        create_app(
            args.database_url,
            args.artifact_root,
            token_scopes=parse_token_rules(args.api_token),
            internal_token=args.internal_token,
            max_upload_bytes=args.max_upload_bytes,
            blob_store=blob_store,
        ),
        host=args.host,
        port=args.port,
        access_log=False,
    )
