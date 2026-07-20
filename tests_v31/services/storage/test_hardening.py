from pathlib import Path

import pytest
from stockstat_storage.artifacts import ArtifactService, LocalBlobStore, S3BlobStore
from stockstat_storage.repository import SQLiteStorageRepository


def service(tmp_path):
    repository = SQLiteStorageRepository(tmp_path / "storage.db")
    repository.initialize()
    return ArtifactService(repository, LocalBlobStore(tmp_path / "objects"), tmp_path / "uploads")


def test_digest_mismatch_is_rejected_before_publish(tmp_path):
    artifacts = service(tmp_path)
    source = tmp_path / "input.bin"
    source.write_bytes(b"content")
    with pytest.raises(ValueError, match="digest mismatch"):
        artifacts.commit_file(
            source,
            kind="test",
            media_type="application/octet-stream",
            codec="raw",
            schema_ref="test/1",
            expected_sha256="0" * 64,
        )
    assert list(artifacts.blob_store.iter_digests()) == []


def test_integrity_failure_and_orphan_reconciliation(tmp_path):
    artifacts = service(tmp_path)
    source = tmp_path / "input.bin"
    source.write_bytes(b"content")
    reference = artifacts.commit_file(
        source,
        kind="test",
        media_type="application/octet-stream",
        codec="raw",
        schema_ref="test/1",
    )
    artifacts.blob_store.path(reference.sha256).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        artifacts.read(reference)
    orphan = "f" * 64
    orphan_source = tmp_path / "orphan.bin"
    orphan_source.write_bytes(b"orphan")
    artifacts.blob_store.put(orphan, orphan_source)
    assert artifacts.reconcile_orphans() == [orphan]
    assert artifacts.reconcile_orphans(delete=True) == [orphan]
    assert not artifacts.blob_store.exists(orphan)


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.upload = None

    def upload_file(self, source, bucket, key, ExtraArgs, Config):
        self.objects[key] = Path(source).read_bytes()
        self.upload = {"bucket": bucket, "key": key, "extra": ExtraArgs, "config": Config}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

    def get_object(self, Bucket, Key):
        from io import BytesIO

        return {"Body": BytesIO(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://s3.test/{operation}/{Params['Key']}?ttl={ExpiresIn}"

    def get_paginator(self, operation):
        client = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                return [
                    {"Contents": [{"Key": key} for key in client.objects if key.startswith(Prefix)]}
                ]

        return Paginator()


def test_s3_adapter_uses_sse_multipart_and_short_presign(tmp_path):
    fake = FakeS3()
    store = S3BlobStore("bucket", client=fake, server_side_encryption="AES256")
    source = tmp_path / "payload.bin"
    source.write_bytes(b"payload")
    digest = "a" * 64
    store.put(digest, source)
    assert fake.upload["extra"] == {"ServerSideEncryption": "AES256"}
    assert store.exists(digest)
    assert store.open(digest).read() == b"payload"
    assert "ttl=3600" in store.presign(digest, expires_seconds=10_000)
    assert list(store.iter_digests()) == [digest]
