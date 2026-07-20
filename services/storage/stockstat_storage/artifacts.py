from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from stockstat_contracts import ArtifactRef, new_id
from stockstat_contracts.time import utc_now

from .repository import StorageRepository


class BlobStore(Protocol):
    def put(self, digest: str, source: Path) -> None: ...
    def open(self, digest: str) -> BinaryIO: ...
    def exists(self, digest: str) -> bool: ...
    def delete(self, digest: str) -> None: ...
    def iter_digests(self): ...


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str) -> Path:
        return self.blobs / digest[:2] / digest[2:4] / digest

    def put(self, digest: str, source: Path) -> None:
        destination = self.path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def open(self, digest: str):
        return self.path(digest).open("rb")

    def exists(self, digest: str) -> bool:
        return self.path(digest).is_file()

    def delete(self, digest: str) -> None:
        self.path(digest).unlink(missing_ok=True)

    def iter_digests(self):
        for path in self.blobs.rglob("*"):
            if path.is_file() and len(path.name) == 64 and "." not in path.name:
                yield path.name


class S3BlobStore:
    def __init__(
        self,
        bucket: str,
        prefix: str = "stockstat-v31",
        client=None,
        server_side_encryption: str | None = "AES256",
        multipart_threshold: int = 64 * 1024**2,
    ):
        if client is None:
            import boto3

            client = boto3.client("s3")
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.server_side_encryption = server_side_encryption
        from boto3.s3.transfer import TransferConfig

        self.transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold,
            multipart_chunksize=16 * 1024**2,
        )

    def key(self, digest: str) -> str:
        return f"{self.prefix}/sha256/{digest}"

    def put(self, digest: str, source: Path) -> None:
        extra = (
            {"ServerSideEncryption": self.server_side_encryption}
            if self.server_side_encryption
            else None
        )
        self.client.upload_file(
            str(source),
            self.bucket,
            self.key(digest),
            ExtraArgs=extra or {},
            Config=self.transfer_config,
        )

    def open(self, digest: str):
        return self.client.get_object(Bucket=self.bucket, Key=self.key(digest))["Body"]

    def exists(self, digest: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self.key(digest))
            return True
        except Exception:
            return False

    def delete(self, digest: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.key(digest))

    def iter_digests(self):
        prefix = f"{self.prefix}/sha256/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", ()):
                yield item["Key"].removeprefix(prefix)

    def presign(self, digest: str, method="get", expires_seconds=300):
        operation = "get_object" if method == "get" else "put_object"
        return self.client.generate_presigned_url(
            operation,
            Params={"Bucket": self.bucket, "Key": self.key(digest)},
            ExpiresIn=max(1, min(int(expires_seconds), 3600)),
        )


class ArtifactService:
    def __init__(
        self, repository: StorageRepository, blob_store: BlobStore, upload_root: str | Path
    ):
        self.repository = repository
        self.blob_store = blob_store
        self.upload_root = Path(upload_root)
        self.upload_root.mkdir(parents=True, exist_ok=True)

    def commit_file(
        self,
        path: str | Path,
        *,
        kind: str,
        media_type: str,
        codec: str,
        schema_ref: str,
        expected_sha256: str | None = None,
        metadata: dict | None = None,
    ) -> ArtifactRef:
        source = Path(path)
        digest = _sha256(source)
        if expected_sha256 and digest != expected_sha256.removeprefix("sha256:"):
            raise ValueError("artifact digest mismatch")
        existed = self.blob_store.exists(digest)
        self.blob_store.put(digest, source)
        reference = ArtifactRef(
            artifact_id=new_id(),
            kind=kind,
            media_type=media_type,
            codec=codec,
            size_bytes=source.stat().st_size,
            sha256=digest,
            schema_ref=schema_ref,
            locator=f"artifact://sha256/{digest}",
            created_at=utc_now(),
        )
        try:
            self.repository.save_artifact(reference, metadata or {})
        except Exception:
            if not existed:
                self.blob_store.delete(digest)
            raise
        return reference

    def read(self, reference: ArtifactRef) -> bytes:
        with self.blob_store.open(reference.sha256) as stream:
            data = stream.read()
        if (
            len(data) != reference.size_bytes
            or hashlib.sha256(data).hexdigest() != reference.sha256
        ):
            raise ValueError("artifact integrity check failed")
        return data

    def copy_to(self, reference: ArtifactRef, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.blob_store.open(reference.sha256) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)
        if _sha256(destination) != reference.sha256:
            destination.unlink(missing_ok=True)
            raise ValueError("artifact integrity check failed")

    def iter_bytes(self, reference: ArtifactRef, chunk_size=1024 * 1024):
        digest = hashlib.sha256()
        size = 0
        with self.blob_store.open(reference.sha256) as stream:
            while chunk := stream.read(chunk_size):
                size += len(chunk)
                digest.update(chunk)
                yield chunk
        if size != reference.size_bytes or digest.hexdigest() != reference.sha256:
            raise ValueError("artifact integrity check failed")

    def presign(self, reference: ArtifactRef, method="get", expires_seconds=300):
        if not hasattr(self.blob_store, "presign"):
            raise NotImplementedError("presigned URLs require the S3 blob store")
        return self.blob_store.presign(reference.sha256, method, expires_seconds)

    def reconcile_orphans(self, delete=False):
        referenced = self.repository.artifact_digests()
        orphaned = sorted(set(self.blob_store.iter_digests()) - referenced)
        if delete:
            for digest in orphaned:
                self.blob_store.delete(digest)
        return orphaned


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
